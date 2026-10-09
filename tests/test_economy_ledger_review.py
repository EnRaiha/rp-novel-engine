"""Module review tests for modules/_economy.py — the shared ledger rule.

Defects covered:

1. `_deduct_resources` reported resources outside the whitelist under a
   `#skipped` STRING key inside a dict of resource amounts, so `charged` mixed
   numbers and a list: a caller iterating `.items()` met `("#skipped", [...])`,
   and the "charge" was a skip, which is not a refusal. A cost naming anything
   unchargeable is refused up front now, by name, before any charge, so a
   rejected cost cannot leave a half-charged treasury behind either.
2. `_check_afford` carried a second copy of the whitelist: the SELECT column
   list was typed out again beside RESOURCE_COLUMNS, so a column could exist in
   one and be missing from the other. The SELECT is built from the tuple now.
3. A resource the ledger has no column for read exactly like a treasury that is
   short ("unknown resource 'food'"), which hides whether the catalogue or the
   coffers are at fault. The reason names the missing column now.

The live consequence is pinned read-only at the end: the catalogues charge
`food`, and `maya_rp.resources` has no `food` column.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import re  # noqa: E402

from core.db import Database  # noqa: E402
from modules import infrastructure  # noqa: E402
from modules._economy import (RESOURCE_COLUMNS, InsufficientResources,  # noqa: E402
                              _check_afford, _deduct_resources, stochastic_round)


def _guard_denies(sql: str, args, row) -> bool:
    """True when a guarded charge's WHERE clause cannot match the fixed row.

    Without this the fake answers a short charge exactly like a paid one, so a test of the refusal
    passed with the guard deleted from the statement. That was measured: removing the guard failed a
    SQL-shape assertion elsewhere and left the refusal test green.
    """
    if not isinstance(row, dict) or "UPDATE maya_rp.resources" not in sql:
        return False
    for match in re.finditer(r"COALESCE\((\w+), 0\) >= \$(\d+)", sql):
        column, index = match.group(1), int(match.group(2))
        if (row.get(column) or 0) < args[index - 1]:
            return True
    return False


class FakeDB:
    def __init__(self, fetchrow=None):
        self.fetchrow_value = fetchrow
        self.calls = []

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", " ".join(sql.split()), args))
        if _guard_denies(sql, args, self.fetchrow_value):
            return None
        return self.fetchrow_value

    async def fetchval(self, sql, *args):
        # Kept stubbed even though the charge no longer calls it. Leaving a method unstubbed did not
        # merely make a test red: it let the statement through to the live pool, so the test wrote to
        # maya_rp.resources for real and the fake recorded nothing. Any new call path gets a stub here
        # before it gets a test.
        self.calls.append(("fetchval", " ".join(sql.split()), args))
        return 0.0

    async def execute(self, sql, *args):
        self.calls.append(("execute", " ".join(sql.split()), args))
        return "UPDATE 1"

    def sql(self, kind=None):
        return [c[1] for c in self.calls if kind is None or c[0] == kind]


def _install(monkeypatch, fake):
    for name in ("fetchrow", "execute", "fetchval"):
        monkeypatch.setattr("modules._economy.Database." + name, getattr(fake, name))
    return fake


# ── 1. An unchargeable cost is refused, not skipped ──────────────────────

async def test_a_cost_outside_the_whitelist_is_refused_by_name(monkeypatch):
    fake = _install(monkeypatch, FakeDB())

    with pytest.raises(ValueError, match="unicorns"):
        await _deduct_resources(3, {"credits": 0, "unicorns": 5})

    assert not fake.sql("execute"), "a refused cost still moved the treasury"


async def test_the_refusal_lists_what_can_be_charged(monkeypatch):
    _install(monkeypatch, FakeDB())

    with pytest.raises(ValueError) as err:
        await _deduct_resources(3, {"food": 100})

    message = str(err.value)
    assert "food" in message and "credits" in message and "alloys" in message, message


async def test_charged_holds_numbers_only(monkeypatch):
    # ONE guarded statement charges the whole cost now: every column is compared to its cost in the
    # WHERE clause and all of it is debited in the same UPDATE. The row is that statement's RETURNING.
    fake = _install(monkeypatch, FakeDB(fetchrow={"credits": 900, "alloys": 80}))

    charged = await _deduct_resources(5, {"credits": 100, "alloys": 20})

    assert charged == {"credits": 100, "alloys": 20}
    assert all(isinstance(v, (int, float)) for v in charged.values())
    assert all(isinstance(k, str) and not k.startswith("#") for k in charged)
    assert len(fake.sql("fetchrow")) == 1, "the cost is one statement, not one statement per resource"
    assert not fake.sql("fetchval"), "the per-resource charge path is gone"
    sql = fake.sql("fetchrow")[0]
    assert "COALESCE(credits, 0) >= $" in sql and "COALESCE(alloys, 0) >= $" in sql, \
        "every resource is guarded in the WHERE"


async def test_a_short_treasury_charges_nothing(monkeypatch):
    """The guard is in the statement. When it does not match, nothing moved and the caller is told by
    exception rather than by a clamped column: `GREATEST(0, credits - $1)` used to take a treasury to
    zero and report success."""
    # A treasury of 10 against a cost of 100. The row is a real one, so the fake has to apply the
    # statement's own guard to reject it. A bare `fetchrow=None` made this test green with the guard
    # deleted from the SQL, which is the definition of passing for the wrong reason.
    fake = _install(monkeypatch, FakeDB(fetchrow={"credits": 10}))

    with pytest.raises(InsufficientResources):
        await _deduct_resources(5, {"credits": 100})

    # Two reads: the guarded UPDATE, then `_check_afford` to say WHY it did not match, so the caller
    # is told "no resources" or the short column rather than a bare refusal.
    assert len(fake.sql("fetchrow")) == 2, "the failed charge is the UPDATE plus the reason"
    assert not fake.sql("execute"), "a refused charge still moved the treasury"


async def test_a_zero_cost_issues_no_statement(monkeypatch):
    """A cost of zero is a no-op, not an UPDATE that rewrites the row."""
    fake = _install(monkeypatch, FakeDB(fetchrow={"credits": 900}))

    assert await _deduct_resources(5, {"credits": 0}) == {"credits": 0}

    assert not fake.sql("fetchrow"), "a zero cost still ran a statement"


async def test_a_float_cost_is_refused_before_any_charge(monkeypatch):
    """asyncpg rejects a float for an INTEGER parameter, and catalogue costs come out of jsonb, where
    `50000.0` is legal. It is refused here rather than at the driver."""
    fake = _install(monkeypatch, FakeDB(fetchrow={"credits": 900}))

    with pytest.raises(ValueError, match="whole number"):
        await _deduct_resources(5, {"credits": 500.5})

    assert not fake.sql("fetchrow"), "a bad quantity still reached the database"


async def test_a_negative_cost_is_refused(monkeypatch):
    """A negative cost would credit the treasury."""
    fake = _install(monkeypatch, FakeDB(fetchrow={"credits": 900}))

    with pytest.raises(ValueError, match="whole number"):
        await _deduct_resources(5, {"credits": -50})

    assert not fake.sql("fetchrow")


def test_stochastic_round_keeps_the_long_run_rate():
    """`progress_pct`, `spread_progress` and `eradication_campaigns.progress` are INTEGER columns and
    a tick adds well under 1 (Spore Drift: 0.25). `int()` truncated every step to 0, so a site at that
    rate never moved. The expected value of the rounded result is the value itself."""
    import random

    random.seed(20261009)
    value = 0.25
    draws = 40_000
    total = sum(stochastic_round(value) for _ in range(draws))

    assert abs(total / draws - value) < 0.02, "the long-run rate drifted"
    assert stochastic_round(0.0) == 0
    assert stochastic_round(0.999) in (0, 1)
    assert stochastic_round(7.0) == 7, "a whole number is returned unchanged"


async def test_an_empty_cost_charges_nothing(monkeypatch):
    fake = _install(monkeypatch, FakeDB())

    assert await _deduct_resources(5, {}) == {}
    assert not fake.sql("execute")


# ── 2 + 3. One whitelist, and a reason that names the fault ─────────────

async def test_the_select_list_is_built_from_the_whitelist(monkeypatch):
    columns = {c: 0 for c in RESOURCE_COLUMNS}
    fake = _install(monkeypatch, FakeDB(fetchrow=columns))

    ok, reason = await _check_afford(5, {"credits": 10})

    assert ok is False and "need 10 credits" in reason
    sql = fake.sql("fetchrow")[0]
    for column in RESOURCE_COLUMNS:
        assert column in sql, column
    assert "SELECT credits, alloys, fuel" in sql


async def test_an_unchargeable_resource_is_named_in_the_reason(monkeypatch):
    _install(monkeypatch, FakeDB(fetchrow={c: 0 for c in RESOURCE_COLUMNS}))

    ok, reason = await _check_afford(5, {"food": 100})

    assert ok is False
    assert "food" in reason and "not a ledger resource column" in reason, reason
    assert reason != "no resources"


async def test_a_missing_treasury_says_so(monkeypatch):
    _install(monkeypatch, FakeDB(fetchrow=None))

    assert await _check_afford(5, {"credits": 1}) == (False, "no resources")


async def test_an_affordable_cost_passes_with_an_empty_reason(monkeypatch):
    _install(monkeypatch, FakeDB(fetchrow={c: 500 for c in RESOURCE_COLUMNS}))

    assert await _check_afford(5, {"credits": 100, "alloys": 50}) == (True, "")


async def test_a_null_column_counts_as_zero(monkeypatch):
    row = {c: None for c in RESOURCE_COLUMNS}
    _install(monkeypatch, FakeDB(fetchrow=row))

    ok, reason = await _check_afford(5, {"credits": 1})

    assert ok is False and "have 0" in reason, reason


# ── The three callers still share one function object ───────────────────

def test_all_three_modules_share_one_copy():
    from modules import megastructures_ports, space_horror

    assert infrastructure._deduct_resources is megastructures_ports._deduct_resources
    assert infrastructure._deduct_resources is space_horror._deduct_resources


# ── The live consequence, read-only ─────────────────────────────────────

class TestTheFoodGap:
    """`food` is charged by the catalogues and has no column in `maya_rp.resources`.

    This test PASSES while the gap is exactly `food`, and fails the moment the
    column appears or a catalogue stops charging it, so the note cannot rot.
    """

    async def test_the_catalogues_charge_a_resource_the_ledger_cannot(self):
        await Database.init()
        try:
            real = {
                row["column_name"]
                for row in await Database.fetch(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema='maya_rp' AND table_name='resources'")
            }
            charged_keys = set()
            for table, column in (("infrastructure_types", "build_cost_resources"),
                                  ("megastructure_types", "total_cost_resources"),
                                  ("port_types", "build_cost_resources")):
                keys = await Database.fetch(
                    f"SELECT DISTINCT jsonb_object_keys({column}::jsonb) AS k "
                    f"FROM maya_rp.{table} WHERE {column} IS NOT NULL")
                charged_keys |= {r["k"] for r in keys}
        finally:
            await Database.close()

        unchargeable = sorted(charged_keys - set(RESOURCE_COLUMNS))
        assert unchargeable == ["food"], (
            f"the catalogue/ledger gap changed: {unchargeable}. "
            f"Ledger columns: {RESOURCE_COLUMNS}. resources columns: {sorted(real)}")
        assert "food" not in real, "a food column appeared — clear the note in _economy.py"

    async def test_the_bio_dome_is_refused_even_with_a_full_treasury(self, monkeypatch):
        """The live cost is {"food": 100, "alloys": 600}: unlimited everything
        still cannot pay it, because the ledger has no food column to charge."""
        await Database.init()
        try:
            dome = await Database.fetchrow(
                "SELECT build_cost_resources FROM maya_rp.infrastructure_types "
                "WHERE build_cost_resources::text ILIKE '%food%' LIMIT 1")
        finally:
            await Database.close()

        assert dome is not None, "no catalogue row charges food any more — clear the note"
        costs = dome["build_cost_resources"]
        if isinstance(costs, str):
            import json
            costs = json.loads(costs)

        _install(monkeypatch, FakeDB(fetchrow={c: 10 ** 9 for c in RESOURCE_COLUMNS}))
        ok, reason = await _check_afford(3, costs)

        assert ok is False and "food" in reason, reason
