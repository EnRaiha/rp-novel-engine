"""Module review tests for modules/weapon_design.py.

Defects covered:

1. `produce_weapons` read `res["alloys"]` without checking that the session has a
   resources row, so a session with none raised
   `TypeError: 'NoneType' object is not subscriptable` instead of a message. The
   sibling paths (`design_blueprint`, `apply_upgrade`) both refuse this case.
2. The same line compared NULL columns directly, so a resources row with a NULL
   credits column raised instead of reporting. `design_blueprint` now charges with a guarded
   UPDATE, so a NULL balance matches no row and the charge reports `Need N credits`.

Checked and found correct, so the row is not silent about what it looked at:
`weapons`, `weapon_blueprints` and `weapon_upgrades` carry no `session_id`
column, measured against information_schema, so their unscoped reads and writes
are correct as they are; `produce_weapons` already reads a NULL `alloy_cost` as
zero, which is what the three live blueprints carry; `apply_upgrade` whitelists
the column it writes and refuses an unknown `effect_type` rather than charging.

`produce_weapons` and `design_blueprint` charge and write in one transaction. A refused charge
rolls the whole transaction back, so no write survives. `produce_weapons` inserts one catalogue row per
weapon name however large `qty` is, because `weapons` is global and has no quantity column.

No database: every test drives a fake connection. SID is a scratch session id, never a frozen campaign.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

import pytest

from modules import weapon_design

SID = 900 + os.getpid() % 100


class FakeDB:
    """fetchrow answers from a queue, in call order.

    `charge_tag` is the command tag the guarded charge returns. `UPDATE 0` models a balance too low
    (or NULL) for the `credits>=$1` guard. `executes` holds only what a transaction committed: an
    exception inside `transaction()` drops that transaction's statements, as a rollback does.
    """

    def __init__(self, rows=(), fetchval=None, charge_tag="UPDATE 1"):
        self.rows = list(rows)
        self.fetchval_result = fetchval
        self.charge_tag = charge_tag
        self.executes: list[tuple[str, tuple]] = []

    async def fetchrow(self, sql, *args):
        return self.rows.pop(0) if self.rows else None

    async def fetchval(self, sql, *args):
        return self.fetchval_result

    async def fetch(self, sql, *args):
        return []

    async def execute(self, sql, *args):
        self.executes.append((" ".join(sql.split()), args))
        return self.charge_tag if "UPDATE maya_rp.resources" in sql else "INSERT 0 1"

    @asynccontextmanager
    async def transaction(self):
        mark = len(self.executes)
        try:
            yield self
        except BaseException:
            del self.executes[mark:]
            raise


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(weapon_design.Database, "fetchrow", staticmethod(fake.fetchrow))
    monkeypatch.setattr(weapon_design.Database, "fetchval", staticmethod(fake.fetchval))
    monkeypatch.setattr(weapon_design.Database, "fetch", staticmethod(fake.fetch))
    monkeypatch.setattr(weapon_design.Database, "execute", staticmethod(fake.execute))
    monkeypatch.setattr(weapon_design.Database, "transaction", staticmethod(fake.transaction))
    return fake


BLUEPRINT = {"id": 1, "name": "PD-3 Beehive Blueprint", "category": "missile",
             "base_damage": 12, "base_range": 40, "slot_size": "M", "tier_required": 5,
             "alloy_cost": None, "credit_cost": 15000, "research_cost": 4000}


async def test_produce_weapons_tells_a_session_without_a_resources_row(db):
    """(1) A session with no resources row used to raise TypeError."""
    db.rows = [BLUEPRINT, None]
    out = await weapon_design.produce_weapons("PD-3 Beehive Blueprint", qty=1, session_id=SID)
    assert out == {"error": f"no resources row for session {SID}"}, out
    assert db.executes == [], "it charged a session it had no ledger for"


async def test_produce_weapons_reads_a_null_ledger_as_empty(db):
    """(2) A row with NULL credits is a treasury of zero, not an exception."""
    db.rows = [BLUEPRINT, {"alloys": None, "credits": None}]
    out = await weapon_design.produce_weapons("PD-3 Beehive Blueprint", qty=1, session_id=SID)
    assert "error" in out, out
    assert db.executes == [], "a NULL treasury paid for a weapon"


async def test_design_blueprint_reads_a_null_credits_column_as_zero(db):
    """(2) Same comparison, the other money path.

    The guarded charge `credits>=$1` matches no row when credits is NULL, so the fake returns
    `UPDATE 0` and the refusal rolls the transaction back.
    """
    db.charge_tag = "UPDATE 0"
    out = await weapon_design.design_blueprint("New Gun", "cannon", 10, 20, "L", 3, session_id=SID)
    assert out == {"error": f"Need {10 * 200 + 20 * 50 + 3 * 500} credits"}, out
    assert db.executes == [], "a NULL treasury paid for a blueprint"


async def test_produce_weapons_charges_once_and_lists_the_type_once(db):
    """The charge covers `qty`; `weapons` is global with no quantity column, so one catalogue row is inserted."""
    db.rows = [BLUEPRINT, {"alloys": 100, "credits": 40000}]
    out = await weapon_design.produce_weapons("PD-3 Beehive Blueprint", qty=2, session_id=SID)
    assert out["produced"] == 2 and out["cost_credits"] == 30000, out
    charges = [e for e in db.executes if e[0].startswith("UPDATE maya_rp.resources")]
    inserts = [e for e in db.executes if e[0].startswith("INSERT INTO maya_rp.weapons")]
    assert len(charges) == 1, charges
    assert charges[0][1] == (0, 30000, SID), charges
    assert len(inserts) == 1, f"{len(inserts)} catalogue rows for one weapon name"


async def test_design_blueprint_refuses_when_the_credits_are_short(db):
    db.charge_tag = "UPDATE 0"
    out = await weapon_design.design_blueprint("New Gun", "cannon", 10, 20, "L", 3, session_id=SID)
    assert "error" in out, out
    assert db.executes == [], "a refused charge left a write behind"


async def test_design_blueprint_charges_and_inserts_in_one_transaction(db, monkeypatch):
    """The charge and the insert commit together; the new id comes from the transaction's own fetchval."""
    async def fetchval(sql, *args):
        return None if "SELECT id FROM" in sql else 77

    monkeypatch.setattr(db, "fetchval", fetchval)
    out = await weapon_design.design_blueprint("New Gun", "cannon", 10, 20, "L", 3, session_id=SID)
    assert out["name"] == "New Gun" and out["cost_credits"] == 10 * 200 + 20 * 50 + 3 * 500, out
    assert [e[0] for e in db.executes if e[0].startswith("UPDATE maya_rp.resources")], db.executes


@pytest.mark.parametrize("damage, range_m, tier", [(0, 5, 1), (-3, 5, 1), (5, 0, 1), (5, 5, -1), (2.5, 5, 1)])
async def test_design_blueprint_refuses_a_non_positive_number(db, damage, range_m, tier):
    """A negative damage priced the blueprint below zero and the charge refunded the treasury."""
    out = await weapon_design.design_blueprint("Free Gun", "cannon", damage, range_m, "L", tier, session_id=SID)
    assert "must be a positive integer" in out.get("error", ""), out
    assert db.executes == []


@pytest.mark.parametrize("qty", [0, -2, 1.5])
async def test_produce_weapons_refuses_a_non_positive_quantity(db, qty):
    out = await weapon_design.produce_weapons("PD-3 Beehive Blueprint", qty=qty, session_id=SID)
    assert "qty must be a positive integer" in out.get("error", ""), out
    assert db.executes == []
