"""Module review tests for modules/alchemy.py.

Defects covered:

1. The recipe lookup matched a partial name with `LIKE` and no ORDER BY, so a
   partial that hit two recipes brewed whichever row PostgreSQL returned first.
   An exact name wins now, and the rest resolve in id order.
2. `qty` was never validated: a negative count returned `{"attempts": -1}`.
3. `success_rate or 1.0` read a declared 0.0 ("this recipe never works") as
   "this recipe always works".

The catalyst hole is pinned rather than patched: five of the six live recipes
declare one and `transmute` never reads, requires or consumes it. Enforcing it
is a gameplay decision, and recipe 16 literally spells its catalyst "None", so
the data has to be settled before the code can enforce anything.

No database: every test drives a fake Database; its `transaction()` yields the fake itself, so statements run
on the transaction connection land in the same recording. Every call uses a scratch session id, because the
frozen guard refuses sessions 3 and 5.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

import pytest

import modules.alchemy as alchemy

SID = 900 + os.getpid() % 100


class FakeDB:
    def __init__(self, fetchrow=None, fetch=None, fetchval=0, execute_tag="UPDATE 1"):
        self.fetchrow_value = fetchrow
        self.fetch_rows = fetch if fetch is not None else []
        self.fetchval_value = fetchval
        self.execute_tag = execute_tag
        self.calls = []

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", " ".join(sql.split()), args))
        if callable(self.fetchrow_value):
            return self.fetchrow_value(sql, args)
        return self.fetchrow_value

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", " ".join(sql.split()), args))
        if callable(self.fetch_rows):
            return self.fetch_rows(sql, args)
        return self.fetch_rows

    async def fetchval(self, sql, *args):
        self.calls.append(("fetchval", " ".join(sql.split()), args))
        return self.fetchval_value

    async def execute(self, sql, *args):
        self.calls.append(("execute", " ".join(sql.split()), args))
        return self.execute_tag

    @asynccontextmanager
    async def transaction(self):
        yield self

    def sql(self, kind=None):
        return [c[1] for c in self.calls if kind is None or c[0] == kind]

    def args_for(self, needle, kind=None):
        return [c[2] for c in self.calls
                if needle in c[1] and (kind is None or c[0] == kind)]


def _stock(quantity, **per_material):
    """A `fetch` answer: one stockpile row per material, `quantity` unless `per_material` names it."""
    def answer(sql, args):
        have = per_material.get(args[1].replace(" ", "_"), quantity)
        return [{"id": 1, "quantity": have}] if have else []
    return answer


def _install(monkeypatch, fake):
    for name in ("fetchrow", "fetch", "fetchval", "execute", "transaction"):
        monkeypatch.setattr("modules.alchemy.Database." + name, getattr(fake, name))
    return fake


RECIPE = {"id": 16, "name": "Pool Water Purification", "category": "refinement",
          "inputs": {"Catalyst": 1, "Contaminated Water": 10},
          "outputs": {"Pool Salts": 1, "Pure Water": 10},
          "catalyst": "None", "success_rate": 0.95, "tech_tier": 2, "lore_text": ""}


# ── 1. The recipe lookup is deterministic ────────────────────────────────

async def test_the_recipe_lookup_prefers_an_exact_name_and_orders_the_rest(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchrow=RECIPE, fetch=_stock(1000)))

    await alchemy.transmute("Pool Water Purification", 1, SID)

    sql = fake.sql("fetchrow")[0]
    assert "ORDER BY (LOWER(name) = LOWER($2)) DESC, id LIMIT 1" in sql, sql
    assert fake.args_for("alchemy_recipes", "fetchrow")[0] == ("%Pool Water Purification%",
                                                               "Pool Water Purification")


async def test_a_partial_name_still_resolves(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchrow=RECIPE, fetch=_stock(1000)))

    out = await alchemy.transmute("Purification", 1, SID)

    assert out["recipe"] == "Pool Water Purification"


async def test_an_unknown_recipe_is_answered_not_crashed(monkeypatch):
    _install(monkeypatch, FakeDB(fetchrow=None))

    out = await alchemy.transmute("no such recipe at all", 1, SID)

    assert "not found" in out["error"]


# ── 2. Quantity validation ───────────────────────────────────────────────

@pytest.mark.parametrize("qty", [0, -1, -25])
async def test_a_non_positive_quantity_is_refused(monkeypatch, qty):
    fake = _install(monkeypatch, FakeDB(fetchrow=RECIPE, fetch=_stock(1000)))

    with pytest.raises(ValueError, match="qty must be at least 1"):
        await alchemy.transmute("Pool Water Purification", qty, SID)

    assert not fake.sql("execute"), "a refused brew still touched the stockpile"


# ── 3. A declared zero success rate means zero ───────────────────────────

async def test_a_zero_success_rate_never_succeeds(monkeypatch):
    impossible = dict(RECIPE, success_rate=0.0)
    fake = _install(monkeypatch, FakeDB(fetchrow=impossible, fetch=_stock(1000)))
    monkeypatch.setattr(alchemy.random, "random", lambda: 0.0)   # would succeed at 1.0

    out = await alchemy.transmute("Pool Water Purification", 3, SID)

    assert out == {"recipe": "Pool Water Purification", "attempts": 3, "successes": 0}
    assert not fake.args_for("INSERT INTO maya_rp.material_stockpiles", "execute")


async def test_a_null_success_rate_defaults_to_certain(monkeypatch):
    certain = dict(RECIPE, success_rate=None)
    _install(monkeypatch, FakeDB(fetchrow=certain, fetch=_stock(1000)))
    monkeypatch.setattr(alchemy.random, "random", lambda: 0.99)

    out = await alchemy.transmute("Pool Water Purification", 2, SID)

    assert out["successes"] == 2


# ── Contract the module claims ───────────────────────────────────────────

def _stock_writes(fake):
    """Statements that touch the stockpile table; the advisory lock does not."""
    return [s for s in fake.sql("execute") if "material_stockpiles" in s]


async def test_contract_every_input_is_checked_before_anything_is_taken(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchrow=RECIPE, fetch=_stock(0)))

    out = await alchemy.transmute("Pool Water Purification", 1, SID)

    assert out["error"].startswith("Need 1 Catalyst")
    assert not _stock_writes(fake), "stock was consumed before the shortfall was found"


async def test_contract_a_shortfall_takes_the_whole_quantity_into_account(monkeypatch):
    fake = _install(monkeypatch, FakeDB(
        fetchrow=RECIPE, fetch=_stock(100, Contaminated_Water=10)))

    out = await alchemy.transmute("Pool Water Purification", 5, SID)

    # 5 × Contaminated Water needs 50; the stockpile holds 10
    assert "Contaminated Water" in out["error"], out
    assert not _stock_writes(fake)


async def test_contract_successful_brews_consume_and_grant(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchrow=RECIPE, fetch=_stock(100)))
    monkeypatch.setattr(alchemy.random, "random", lambda: 0.0)

    out = await alchemy.transmute("Pool Water Purification", 2, SID)

    assert out == {"recipe": "Pool Water Purification", "attempts": 2, "successes": 2}
    taken = fake.args_for("quantity=quantity-$1", "execute")
    assert [t[0] for t in taken] == [2, 20]          # Catalyst 1×2, Water 10×2
    granted = fake.args_for("COALESCE(quantity,0)+$1", "execute")
    # one upsert per output, scaled by the successes: Salts 1×2 and Water 10×2
    assert sorted(g[0] for g in granted) == [2, 20]
    assert fake.args_for("material_stockpiles", "fetch")[0] == (SID, "Catalyst")


async def test_the_catalyst_hole_is_pinned(monkeypatch):
    """Five of six live recipes declare a catalyst that transmute ignores.

    This test states the current contract so that wiring the catalyst later
    fails here first and forces the decision, instead of changing silently.
    """
    fake = _install(monkeypatch, FakeDB(fetchrow=RECIPE, fetch=_stock(100)))

    await alchemy.transmute("Pool Water Purification", 1, SID)

    checked = {args[1] for args in fake.args_for("material_stockpiles", "fetch")}
    assert checked == {"Catalyst", "Contaminated Water"}, checked
    assert RECIPE["catalyst"] is not None, "this recipe does declare a catalyst"
    # it is never asked for by name as a catalyst, only as the input ingredient
    assert not any("catalyst" in s.lower() and "SELECT" in s
                   for s in fake.sql("fetch") if "material_stockpiles" in s)


async def test_contract_the_recipe_book_lists_the_catalogue(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[RECIPE]))

    out = await alchemy.list_recipes()

    assert out == [RECIPE]
    assert "ORDER BY category, tech_tier" in fake.sql("fetch")[0]
