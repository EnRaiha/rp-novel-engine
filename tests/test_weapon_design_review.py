"""Module review tests for modules/weapon_design.py.

Defects covered:

1. `produce_weapons` read `res["alloys"]` without checking that the session has a
   resources row. Session 5 has none, so the live arc's build raised
   `TypeError: 'NoneType' object is not subscriptable` instead of a message. The
   sibling paths (`design_blueprint`, `apply_upgrade`) both refuse this case.
2. The same line compared NULL columns directly, and `design_blueprint` did too,
   so a resources row with a NULL credits column raised instead of reporting.

Checked and found correct, so the row is not silent about what it looked at:
`weapons`, `weapon_blueprints` and `weapon_upgrades` carry no `session_id`
column, measured against information_schema, so their unscoped reads and writes
are correct as they are; `produce_weapons` already reads a NULL `alloy_cost` as
zero, which is what the three live blueprints carry; `apply_upgrade` whitelists
the column it writes and refuses an unknown `effect_type` rather than charging.

Reported rather than changed: `produce_weapons` deducts the credits before it
inserts the weapons, so a failed insert leaves the charge with no record. That is
the same shape as the research/manufacturing race already on the open list.

No database: every test drives a fake connection.
"""
from __future__ import annotations

import pytest

from modules import weapon_design


class FakeDB:
    """fetchrow answers from a queue, in call order."""

    def __init__(self, rows=(), fetchval=None):
        self.rows = list(rows)
        self.fetchval_result = fetchval
        self.executes: list[tuple[str, tuple]] = []

    async def fetchrow(self, sql, *args):
        return self.rows.pop(0) if self.rows else None

    async def fetchval(self, sql, *args):
        return self.fetchval_result

    async def fetch(self, sql, *args):
        return []

    async def execute(self, sql, *args):
        self.executes.append((" ".join(sql.split()), args))
        return "UPDATE 1"


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(weapon_design.Database, "fetchrow", staticmethod(fake.fetchrow))
    monkeypatch.setattr(weapon_design.Database, "fetchval", staticmethod(fake.fetchval))
    monkeypatch.setattr(weapon_design.Database, "fetch", staticmethod(fake.fetch))
    monkeypatch.setattr(weapon_design.Database, "execute", staticmethod(fake.execute))
    return fake


BLUEPRINT = {"id": 1, "name": "PD-3 Beehive Blueprint", "category": "missile",
             "base_damage": 12, "base_range": 40, "slot_size": "M", "tier_required": 5,
             "alloy_cost": None, "credit_cost": 15000, "research_cost": 4000}


async def test_produce_weapons_tells_a_session_without_a_resources_row(db):
    """(1) The live arc has no resources row; this used to raise TypeError."""
    db.rows = [BLUEPRINT, None]
    out = await weapon_design.produce_weapons("PD-3 Beehive Blueprint", qty=1, session_id=5)
    assert out == {"error": "no resources row for session 5"}, out
    assert db.executes == [], "it charged a session it had no ledger for"


async def test_produce_weapons_reads_a_null_ledger_as_empty(db):
    """(2) A row with NULL credits is a treasury of zero, not an exception."""
    db.rows = [BLUEPRINT, {"alloys": None, "credits": None}]
    out = await weapon_design.produce_weapons("PD-3 Beehive Blueprint", qty=1, session_id=5)
    assert "error" in out, out
    assert db.executes == []


async def test_design_blueprint_reads_a_null_credits_column_as_zero(db):
    """(2) Same comparison, the other money path.

    The existence check goes through `fetchval`, so the ledger row is the only
    `fetchrow` this path makes.
    """
    db.rows = [{"credits": None}]
    out = await weapon_design.design_blueprint("New Gun", "cannon", 10, 20, "L", 3, session_id=5)
    assert out == {"error": f"Need {10 * 200 + 20 * 50 + 3 * 500} credits"}, out
    assert db.executes == []


async def test_produce_weapons_charges_once_and_produces_qty(db):
    db.rows = [BLUEPRINT, {"alloys": 100, "credits": 40000}]
    out = await weapon_design.produce_weapons("PD-3 Beehive Blueprint", qty=2, session_id=5)
    assert out["produced"] == 2 and out["cost_credits"] == 30000, out
    charges = [e for e in db.executes if e[0].startswith("UPDATE maya_rp.resources")]
    inserts = [e for e in db.executes if e[0].startswith("INSERT INTO maya_rp.weapons")]
    assert len(charges) == 1 and len(inserts) == 2


async def test_design_blueprint_refuses_when_the_credits_are_short(db):
    db.rows = [{"credits": 10}]
    out = await weapon_design.design_blueprint("New Gun", "cannon", 10, 20, "L", 3, session_id=5)
    assert "error" in out
    assert db.executes == []
