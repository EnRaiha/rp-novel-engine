"""Module review tests for modules/manufacturing.py.

Defect covered by this pass:

1. A malformed recipe payload aborted the WHOLE tick: `json.loads` ran outside any
   per-line guard, so one unreadable `inputs`/`outputs` string stopped every
   production line in the campaign. A bad line is skipped and named now.
2. The stockpile and line writes matched on id alone; they carry the session (and
   the line writes carry the colony the line was read from).

Checked and found correct, and the docstrings record the earlier pass: `efficiency`
is read with an explicit NULL test rather than `or 1.0`, so a line set to zero
throughput consumes and produces nothing; availability is `SUM(quantity-reserved)`;
the take loop never dips into the reserved quantity; a zero-throughput line writes
no nought-quantity stockpile row; the blocked and unblocked counters are separate;
and the line selection joins `colonies` on its session.

The take is guarded and shares one transaction with the outputs. The race and the
rollback run against the database in tests/test_infra_manufacturing_fix2.py.

No database: every test drives a fake Database.
"""
from __future__ import annotations

import json

import pytest

import modules.manufacturing as mf


@pytest.fixture(autouse=True)
def _writable(monkeypatch):
    """The real frozen list must not decide these tests: they name session 3 or 5."""
    monkeypatch.setattr("core.session.is_frozen", lambda sid: False)


class FakeDB:
    def __init__(self, fetch=None, fetchrow=None, fetchval=100, rows=None):
        self.fetch_rows = fetch if fetch is not None else []
        self.row_map = rows or {}
        self.fetchrow_value = fetchrow
        self.fetchval_value = fetchval
        self.calls = []

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", " ".join(sql.split()), args))
        if isinstance(self.fetch_rows, dict):
            for marker, value in self.fetch_rows.items():
                if marker != "*" and marker in sql:
                    return value
            return self.fetch_rows.get("*", [])
        return self.fetch_rows

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", " ".join(sql.split()), args))
        for marker, value in self.row_map.items():
            if marker in sql:
                return value
        return self.fetchrow_value

    async def fetchval(self, sql, *args):
        self.calls.append(("fetchval", " ".join(sql.split()), args))
        return self.fetchval_value

    async def execute(self, sql, *args):
        self.calls.append(("execute", " ".join(sql.split()), args))
        return "UPDATE 1"

    def sql(self, kind=None):
        return [c[1] for c in self.calls if kind is None or c[0] == kind]

    def args_for(self, needle, kind=None):
        return [c[2] for c in self.calls
                if needle in c[1] and (kind is None or c[0] == kind)]


class _Tx:
    """Stands in for `Database.transaction()`: yields the fake as the connection."""

    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


def _install(monkeypatch, fake):
    for name in ("fetch", "fetchrow", "fetchval", "execute"):
        monkeypatch.setattr("modules.manufacturing.Database." + name, getattr(fake, name))
    monkeypatch.setattr("modules.manufacturing.Database.transaction", lambda: _Tx(fake))
    return fake


def _line(line_id, recipe_id=1, colony_id=3, eff=1.0, status="running"):
    return {"id": line_id, "colony_id": colony_id, "recipe_id": recipe_id,
            "efficiency": eff, "status": status}


def _recipe(inputs, outputs, name="Alloy Smelting"):
    return {"inputs": json.dumps(inputs), "outputs": json.dumps(outputs), "name": name}


# ── 1. One bad line does not stop the tick ──────────────────────────────

async def test_a_malformed_recipe_is_skipped_and_the_other_line_produces(monkeypatch):
    seen = []
    monkeypatch.setattr("modules.manufacturing.error", lambda mod, msg: seen.append(msg))
    lines = [_line(1, recipe_id=11), _line(2, recipe_id=12)]
    recipes = {11: {"inputs": "{not json", "outputs": "{}", "name": "Broken"},
               12: _recipe({"ore": 2}, {"alloy": 1})}
    fake = _install(monkeypatch, FakeDB(
        fetch={"production_lines": lines, "material_stockpiles": [{"id": 5, "avail": 100}]},
        rows={}))

    async def fetchrow(sql, *args):
        fake.calls.append(("fetchrow", " ".join(sql.split()), args))
        return recipes.get(args[0])

    monkeypatch.setattr("modules.manufacturing.Database.fetchrow", fetchrow)

    out = await mf.run_tick(5)

    assert out["lines"] == 2
    assert any("unreadable" in m and "line 1" in m for m in seen), seen
    assert fake.args_for("quantity=quantity-$1", "execute"), "the good line did not consume"
    assert fake.args_for("INSERT INTO maya_rp.material_stockpiles", "execute"), \
        "the good line stopped producing"


async def test_a_line_with_no_recipe_row_is_named(monkeypatch):
    seen = []
    monkeypatch.setattr("modules.manufacturing.error", lambda mod, msg: seen.append(msg))
    fake = _install(monkeypatch, FakeDB(
        fetch={"production_lines": [_line(4, recipe_id=99)], "material_stockpiles": []},
        fetchrow=None))

    out = await mf.run_tick(5)

    assert out["lines"] == 1
    assert any("no recipe 99" in m for m in seen), seen
    assert not fake.args_for("quantity=quantity-$1", "execute")


# ── 2. The writes are scoped ────────────────────────────────────────────

async def test_the_consumption_write_carries_the_session(monkeypatch):
    fake = _install(monkeypatch, FakeDB(
        fetch={"production_lines": [_line(1)],
               "material_stockpiles": [{"id": 5, "avail": 100}]},
        rows={"recipes WHERE id=$1": _recipe({"ore": 2}, {"alloy": 1})}))

    await mf.run_tick(5)

    taken = fake.args_for("quantity=quantity-$1", "execute")[0]
    assert taken == (2.0, 5, 5)
    assert "session_id=$3" in [s for s in fake.sql("execute") if "quantity=quantity-$1" in s][0]


async def test_the_blocked_write_carries_the_colony_and_the_session(monkeypatch):
    fake = _install(monkeypatch, FakeDB(
        fetch={"production_lines": [_line(1)], "material_stockpiles": []},
        rows={"recipes WHERE id=$1": _recipe({"ore": 10}, {"alloy": 1})}, fetchval=0))

    out = await mf.run_tick(5)

    assert out["blocked"] == 1
    blocked = fake.args_for("SET status='blocked'", "execute")[0]
    assert blocked == (1, 3, 5)
    assert "session_id=$3" in [s for s in fake.sql("execute") if "SET status='blocked'" in s][0]


async def test_the_line_query_joins_the_colony_session(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[], rows={}))

    await mf.run_tick(5)

    sql = fake.sql("fetch")[0]
    assert "pl.session_id=$1" in sql and "c.session_id=$1" in sql
    assert "pl.status IN ('running','blocked')" in sql
    assert fake.args_for("production_lines", "fetch")[0] == (5,)


# ── Contract an earlier pass already set ────────────────────────────────

async def test_a_zero_efficiency_line_consumes_and_produces_nothing(monkeypatch):
    fake = _install(monkeypatch, FakeDB(
        fetch={"production_lines": [_line(1, eff=0.0)],
               "material_stockpiles": [{"id": 5, "avail": 100}]},
        rows={"recipes WHERE id=$1": _recipe({"ore": 2}, {"alloy": 1})}))

    out = await mf.run_tick(5)

    assert out["lines"] == 1
    assert not fake.args_for("quantity=quantity-$1", "execute"), "a stopped line consumed stock"
    assert not fake.args_for("quantity=quantity+$1", "execute"), "a stopped line produced stock"
    assert not fake.args_for("INSERT INTO maya_rp.material_stockpiles", "execute")


async def test_an_unknown_efficiency_is_one_not_zero(monkeypatch):
    fake = _install(monkeypatch, FakeDB(
        fetch={"production_lines": [_line(1, eff=None)],
               "material_stockpiles": [{"id": 5, "avail": 100}]},
        rows={"recipes WHERE id=$1": _recipe({"ore": 2}, {"alloy": 1})}))

    await mf.run_tick(5)

    taken = fake.args_for("quantity=quantity-$1", "execute")[0]
    assert taken[0] == 2.0, "a NULL efficiency should read as full rate"


async def test_availability_and_take_never_dip_into_reserved_stock(monkeypatch):
    fake = _install(monkeypatch, FakeDB(
        fetch={"production_lines": [_line(1)], "material_stockpiles": [{"id": 5, "avail": 3}]},
        rows={"recipes WHERE id=$1": _recipe({"ore": 5}, {"alloy": 1})}, fetchval=3))

    out = await mf.run_tick(5)

    assert out["blocked"] == 1
    assert not fake.args_for("quantity=quantity-$1", "execute")


async def test_run_tick_reports_a_crash_as_an_error(monkeypatch):
    seen = []
    monkeypatch.setattr("modules.manufacturing.error", lambda mod, msg: seen.append(msg))

    async def boom(*_a, **_k):
        raise RuntimeError("belt jam")

    _install(monkeypatch, FakeDB())
    monkeypatch.setattr("modules.manufacturing.Database.fetch", boom)

    out = await mf.run_tick(5)

    assert "belt jam" in out["error"]
    assert any("belt jam" in m for m in seen), seen
