"""Module review tests for modules/fleet.py (2026-10-03).

Every database call is stubbed and the dice are fixed, so no battle is fought.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.fleet as fleet  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


FLEET = {"id": 7, "name": "Legion Vanguard", "formation": "spearhead"}
SHIPS = [
    {"id": 1, "name": "Maw-1", "hull_current": 400, "hull": 400, "speed": 60,
     "tier": 3, "power_rating": 120},
    {"id": 2, "name": "Maw-2", "hull_current": 300, "hull": 400, "speed": 50,
     "tier": 3, "power_rating": 90},
]


class _StubDB:
    def __init__(self, fleet_row=FLEET, ships=None, exists=False, fuel_row=None):
        self.fleet_row = fleet_row
        self.ships = SHIPS if ships is None else ships
        self.exists = exists
        self.fuel_row = fuel_row
        self.reads = []
        self.writes = []
        self.fuel_calls = []

    async def fetchval(self, sql, *args):
        self.reads.append((sql, args))
        if "EXISTS" in sql:
            return self.exists
        if "FROM maya_rp.ships" in sql:
            return 1
        if "FROM maya_rp.fleets" in sql:
            return 7
        if "SUM(s.power_rating)" in sql:
            return 210
        return 0

    async def fetchrow(self, sql, *args):
        self.reads.append((sql, args))
        if "UPDATE maya_rp.resources" in sql:
            self.fuel_calls.append(args)
            return self.fuel_row
        if "FROM maya_rp.fleets" in sql:
            return self.fleet_row
        return None

    async def fetch(self, sql, *args):
        self.reads.append((sql, args))
        if "s.power_rating, s.hull" in sql or "s.hull_current, s.hull" in sql:
            return self.ships
        if "FROM maya_rp.fleets" in sql:
            return [{**self.fleet_row, "status": "active", "flagship": None}]
        return []

    async def execute(self, sql, *args):
        self.writes.append((sql, args))
        return "OK"


# ── A formation the schema does not allow ───────────────────────────────


def test_an_unknown_formation_is_refused(monkeypatch):
    """The CLI prints the six the schema allows; FORMATION_MULT holds the six."""
    stub = _StubDB()
    monkeypatch.setattr(fleet, "Database", stub)
    out = _run(fleet.create_fleet("Review Fleet", "wedge", session_id=3))
    assert "Unknown formation" in out["error"], out
    assert "spearhead" in out["error"] and "scatter" in out["error"]
    assert stub.writes == []


def test_a_nameless_fleet_is_refused(monkeypatch):
    stub = _StubDB()
    monkeypatch.setattr(fleet, "Database", stub)
    assert "needs a name" in _run(fleet.create_fleet("   ", "wall", session_id=3))["error"]
    assert stub.writes == []


def test_a_known_formation_is_created(monkeypatch):
    stub = _StubDB()
    monkeypatch.setattr(fleet, "Database", stub)
    out = _run(fleet.create_fleet("Review Fleet", "wall", session_id=3))
    assert out == {"fleet": "Review Fleet", "formation": "wall"}
    (_, args), = stub.writes
    assert args == (3, "Review Fleet", "wall")


def test_a_duplicate_fleet_is_refused(monkeypatch):
    stub = _StubDB(exists=True)
    monkeypatch.setattr(fleet, "Database", stub)
    out = _run(fleet.create_fleet("Legion Vanguard", "wall", session_id=3))
    assert "already exists" in out["error"], out
    assert stub.writes == []


# ── The battle pays for what it reports ─────────────────────────────────


def test_a_battle_says_when_no_fuel_could_be_spent(monkeypatch):
    stub = _StubDB(fuel_row=None)
    monkeypatch.setattr(fleet, "Database", stub)
    logged = []
    monkeypatch.setattr(fleet, "info", lambda *a: logged.append(a[-1]))

    out = _run(fleet.fleet_battle("Legion Vanguard", "blitz", 100, session_id=5))

    assert out["fuel_cost"] > 0
    assert any("no resources row for session 5" in line for line in logged), logged
    assert stub.fuel_calls and stub.fuel_calls[0][1] == 5


def test_an_unknown_tactic_is_named_in_the_log(monkeypatch):
    stub = _StubDB(fuel_row={"fuel": 100})
    monkeypatch.setattr(fleet, "Database", stub)
    logged = []
    monkeypatch.setattr(fleet, "info", lambda *a: logged.append(a[-1]))

    out = _run(fleet.fleet_battle("Legion Vanguard", "ramming", 100, session_id=3))

    assert "outcome" in out, out
    assert any("'ramming' is not one of" in line for line in logged), logged


def test_a_known_tactic_is_not_flagged(monkeypatch):
    stub = _StubDB(fuel_row={"fuel": 100})
    monkeypatch.setattr(fleet, "Database", stub)
    logged = []
    monkeypatch.setattr(fleet, "info", lambda *a: logged.append(a[-1]))
    _run(fleet.fleet_battle("Legion Vanguard", "blitz", 100, session_id=3))
    assert not any("is not one of" in line for line in logged), logged


def test_the_damage_lands_inside_the_session(monkeypatch):
    stub = _StubDB(fuel_row={"fuel": 100})
    monkeypatch.setattr(fleet, "Database", stub)
    _run(fleet.fleet_battle("Legion Vanguard", "blitz", 100, session_id=3))
    hulls = [(sql, args) for sql, args in stub.writes if "UPDATE maya_rp.ships" in sql]
    assert hulls, "no ship took damage"
    for sql, args in hulls:
        assert "session_id=$4" in sql and args[-1] == 3, (sql, args)


def test_a_fleet_with_no_active_ships_cannot_fight(monkeypatch):
    stub = _StubDB(ships=[])
    monkeypatch.setattr(fleet, "Database", stub)
    out = _run(fleet.fleet_battle("Legion Vanguard", "blitz", 100, session_id=3))
    assert "No active ships" in out["error"], out
    assert stub.writes == []


def test_the_listing_scopes_members_and_power(monkeypatch):
    stub = _StubDB()
    monkeypatch.setattr(fleet, "Database", stub)
    _run(fleet.list_fleets(session_id=3))
    scoped = [sql for sql, _ in stub.reads if "fleet_members" in sql]
    assert scoped
    for sql in scoped:
        assert "s.session_id=$2" in sql, sql
