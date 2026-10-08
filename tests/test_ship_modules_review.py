"""Module review tests for modules/ship_modules.py (2026-10-03).

Every database call is stubbed. Nothing here fits a module on a real ship.
"""
from __future__ import annotations

import asyncio
import contextlib
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.ship_modules as sm  # noqa: E402

# Scratch session: sessions 3 and 5 are frozen reference data and install_module refuses them.
SID = 900 + os.getpid() % 100


def _run(coro):
    return asyncio.run(coro)


class _StubDB:
    def __init__(self, ship=None, module=None, match_count=1, names=(), used=0, dup=None):
        self.ship = ship
        self.module = module
        self.match_count = match_count
        self.names = list(names)
        self.used = used
        self.dup = dup
        self.reads = []
        self.writes = []

    @contextlib.asynccontextmanager
    async def transaction(self):
        """The stub is its own connection: statements inside a transaction land in the same record."""
        yield self

    async def fetchrow(self, sql, *args):
        self.reads.append((sql, args))
        if "FROM maya_rp.ships" in sql and "FOR UPDATE" in sql:
            return {"id": args[0]} if self.ship else None
        if "FROM maya_rp.ships" in sql:
            return self.ship
        if "FROM maya_rp.modules" in sql and "SELECT *" in sql:
            return self.module
        if "FROM maya_rp.ship_modules" in sql:
            return self.dup
        return None

    async def fetchval(self, sql, *args):
        self.reads.append((sql, args))
        if "count(*) FROM maya_rp.modules" in sql:
            return self.match_count
        if "INSERT INTO maya_rp.ship_modules" in sql:
            self.writes.append((sql, args))
            return 77
        if "ship_modules" in sql:
            return self.used
        return 0

    async def fetch(self, sql, *args):
        self.reads.append((sql, args))
        if "SELECT name FROM maya_rp.modules" in sql:
            return [{"name": n} for n in self.names]
        return []


SHIP = {"id": 4, "name": "Maw-1", "tier": 6, "sub_class": "Cruiser", "module_slots": 3}
DRIVE = {"id": 45, "name": "Void Drive", "category": "void", "tier_min": 4, "tier_max": 8,
         "effect_value": 1}


# ── A pattern that matches two modules must not pick one silently ───────


def test_a_module_name_that_matches_several_is_refused(monkeypatch):
    """'drive' matches Void Drive and Quiet Drive Nullifier on live rows."""
    stub = _StubDB(ship=SHIP, module=DRIVE, match_count=2,
                   names=["Quiet Drive Nullifier", "Void Drive"])
    monkeypatch.setattr(sm, "Database", stub)

    with pytest.raises(ValueError) as excinfo:
        _run(sm.install_module(4, "drive", session_id=SID))

    assert "matches 2 modules" in str(excinfo.value)
    assert "Void Drive" in str(excinfo.value) and "Quiet Drive Nullifier" in str(excinfo.value)
    assert stub.writes == [], "an ambiguous name still fitted something"


def test_one_match_installs_and_reports_the_slot(monkeypatch):
    stub = _StubDB(ship=SHIP, module=DRIVE, match_count=1, used=1)
    monkeypatch.setattr(sm, "Database", stub)

    out = _run(sm.install_module(4, "Void Drive", session_id=SID))

    assert out == {"id": 77, "ship": "Maw-1", "module": "Void Drive",
                   "category": "void", "slot": 2}
    insert = [args for sql, args in stub.writes if "INSERT INTO maya_rp.ship_modules" in sql]
    assert insert == [(4, 45, 2)]


def test_no_match_still_refuses_by_name(monkeypatch):
    stub = _StubDB(ship=SHIP, module=None, match_count=0)
    monkeypatch.setattr(sm, "Database", stub)
    with pytest.raises(ValueError, match="No module named"):
        _run(sm.install_module(4, "Unobtainium", session_id=SID))


def test_a_ship_from_another_campaign_is_refused(monkeypatch):
    stub = _StubDB(ship=None, module=DRIVE)
    monkeypatch.setattr(sm, "Database", stub)
    with pytest.raises(ValueError, match="No ship id=4"):
        _run(sm.install_module(4, "Void Drive", session_id=SID))
    assert stub.writes == []


# ── The fitted list is scoped through the ship ──────────────────────────


def test_listing_fitted_modules_names_the_session(monkeypatch):
    stub = _StubDB()
    monkeypatch.setattr(sm, "Database", stub)
    _run(sm.list_modules(4, session_id=3))
    (sql, args), = stub.reads
    assert "s.session_id=$2" in sql
    assert args == (4, 3)


def test_listing_defaults_to_the_resolved_session(monkeypatch):
    """`None` resolves through `require_session`, here from RP_SESSION."""
    monkeypatch.setenv("RP_SESSION", str(SID))
    stub = _StubDB()
    monkeypatch.setattr(sm, "Database", stub)
    _run(sm.list_modules(4))
    (_, args), = stub.reads
    assert args == (4, SID)


# ── The void crossing keeps its declared arithmetic ─────────────────────


def test_a_fleet_without_a_drive_cannot_cross(monkeypatch):
    stub = _StubDB()
    monkeypatch.setattr(sm, "Database", stub)
    with pytest.raises(ValueError, match="No Void Drive in fleet"):
        _run(sm.void_crossing_cost(1, 2, "Legion Vanguard", session_id=3))


def test_the_ward_reduces_the_risk_and_never_below_the_floor(monkeypatch):
    stub = _StubDB()
    monkeypatch.setattr(sm, "Database", stub)

    async def fetch(sql, *args):
        stub.reads.append((sql, args))
        if "has_drive" in sql:
            return [{"id": 1, "name": "Maw-1", "sub_class": "Cruiser", "tier": 6,
                     "has_drive": True}]
        return [{"effect_value": 20, "grade": 3}, {"effect_value": 20, "grade": 2}]

    monkeypatch.setattr(stub, "fetch", fetch)
    plan = _run(sm.void_crossing_cost(1, 2, "SEF-3 Silent Maw", session_id=3))
    assert plan["ward"] == 40
    assert plan["risk_pct"] == sm.VOID_BASE_RISK_PCT - 40 or plan["risk_pct"] == 5
    assert plan["hours_per_unit"] == sm.VOID_HOURS_PER_UNIT
    assert plan["drive_ships"] == ["Maw-1"]


def test_a_fleet_name_is_required(monkeypatch):
    stub = _StubDB()
    monkeypatch.setattr(sm, "Database", stub)
    assert _run(sm.fleet_void_capable(None)) == {
        "capable": False, "ships": 0, "drive_ships": 0, "drive_names": []}
    assert stub.reads == []
