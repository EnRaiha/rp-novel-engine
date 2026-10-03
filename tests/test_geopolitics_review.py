"""Module review tests for modules/geopolitics.py (2026-10-03).

Every database call is stubbed. No war, raid or event row is created.
"""
from __future__ import annotations

import asyncio
import pathlib
import re
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.geopolitics as geo  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


FACTIONS = [
    {"id": 1, "name": "Setia Empire", "standing": "hostile", "economic_strength": 1,
     "pirate_fleet_power": 0, "reputation": 0},
    {"id": 2, "name": "Iron Concord", "standing": "hostile", "economic_strength": 1,
     "pirate_fleet_power": 9000, "reputation": 0},
    {"id": 3, "name": "The Den", "standing": "hostile", "economic_strength": 1,
     "pirate_fleet_power": 0, "reputation": 0},
    {"id": 4, "name": "Golden Guild", "standing": "hostile", "economic_strength": 1,
     "pirate_fleet_power": 0, "reputation": 0},
]


class _StubDB:
    def __init__(self, relations=(), tension=(), undiscovered=True):
        self.relations = list(relations)
        self.tension = list(tension)
        self.undiscovered = undiscovered
        self.reads = []
        self.writes = []

    async def fetch(self, sql, *args):
        self.reads.append((sql, args))
        if "FROM maya_rp.factions" in sql:
            return [f for f in FACTIONS if f["name"] != "Setia Empire"]
        if "military_tension" in sql:
            return self.tension
        return []

    async def fetchrow(self, sql, *args):
        self.reads.append((sql, args))
        if "FROM maya_rp.faction_relations" in sql:
            for rel in self.relations:
                if {rel["faction_a"], rel["faction_b"]} == {args[1], args[2]}:
                    return rel
            return None
        if "FROM maya_rp.factions" in sql:
            for f in FACTIONS:
                if f["id"] == args[0]:
                    return {"name": f["name"]}
            return None
        return None

    async def fetchval(self, sql, *args):
        self.reads.append((sql, args))
        if "system_name FROM maya_rp.territory" in sql:
            return "TKG"
        if "COUNT(*)" in sql:
            return 0
        if "game_day" in sql:
            return 2253
        return 0

    async def execute(self, sql, *args):
        self.writes.append((sql, args))
        return "OK"


def test_the_tick_reads_its_own_campaign_only(monkeypatch):
    # Every roll fires, and one hot relation exists, so the escalation branch that
    # looks the two factions up by id actually runs.
    monkeypatch.setattr(geo.random, "random", lambda: 0.0)
    stub = _StubDB(tension=[{"faction_a": 2, "faction_b": 3, "military_tension": 0.9}])
    monkeypatch.setattr(geo, "Database", stub)
    _run(geo.run_tick(session_id=5))
    for sql, args in stub.reads:
        if "FROM maya_rp.factions" in sql:
            # Every faction lookup carries the session, including each of the two
            # subqueries inside the existing-war count.
            for lookup in re.findall(r"FROM maya_rp\.factions WHERE id=\$\d[^)]*", sql):
                assert "session_id" in lookup, (sql, lookup)
            assert 5 in args, (sql, args)


def test_a_hostile_pair_can_produce_a_skirmish_event(monkeypatch):
    monkeypatch.setattr(geo.random, "random", lambda: 0.0)   # every roll fires
    stub = _StubDB(relations=[{"faction_a": 2, "faction_b": 3, "standing": "hostile"}])
    monkeypatch.setattr(geo, "Database", stub)

    out = _run(geo.run_tick(session_id=5))

    assert out["events_generated"] >= 1
    events = [args for sql, args in stub.writes if "INSERT INTO maya_rp.events" in sql]
    assert events and events[0][0] == 5
    assert "skirmish" in events[0][2], events[0]


def test_a_neutral_pair_reports_a_convoy_and_an_ally_reports_maneuvers(monkeypatch):
    monkeypatch.setattr(geo.random, "random", lambda: 0.0)
    stub = _StubDB(relations=[{"faction_a": 2, "faction_b": 3, "standing": "neutral"},
                              {"faction_a": 2, "faction_b": 4, "standing": "ally"}])
    monkeypatch.setattr(geo, "Database", stub)
    _run(geo.run_tick(session_id=5))
    text = " ".join(args[2] for sql, args in stub.writes if "INSERT INTO maya_rp.events" in sql)
    assert "Trade convoy" in text and "Joint fleet maneuvers" in text, text


def test_a_powerful_hostile_schedules_a_raid(monkeypatch):
    monkeypatch.setattr(geo.random, "random", lambda: 0.0)
    stub = _StubDB()
    monkeypatch.setattr(geo, "Database", stub)

    _run(geo.run_tick(session_id=5))

    raids = [args for sql, args in stub.writes if "incoming_raids" in sql]
    assert raids, "a 9000-power hostile faction scheduled nothing"
    assert raids[0][0] == 5 and raids[0][1] == "Iron Concord"
    assert raids[0][3] >= 5400, raids[0]      # 0.6x to 1.0x of 9000


def test_hot_tension_can_start_a_border_war(monkeypatch):
    monkeypatch.setattr(geo.random, "random", lambda: 0.0)
    stub = _StubDB(tension=[{"faction_a": 2, "faction_b": 3, "military_tension": 0.9}])
    monkeypatch.setattr(geo, "Database", stub)

    _run(geo.run_tick(session_id=5))

    wars = [args for sql, args in stub.writes if "INSERT INTO maya_rp.wars" in sql]
    assert wars and wars[0][0] == 5, wars
    assert "border tension with" in wars[0][2], wars[0]
    assert wars[0][4] == 2253, wars[0]


def test_an_existing_war_stops_a_second_one(monkeypatch):
    monkeypatch.setattr(geo.random, "random", lambda: 0.0)
    stub = _StubDB(tension=[{"faction_a": 2, "faction_b": 3, "military_tension": 0.9}])

    async def fetchval(sql, *args):
        stub.reads.append((sql, args))
        if "COUNT(*)" in sql:
            return 1
        if "system_name FROM maya_rp.territory" in sql:
            return "TKG"
        return 2253
    monkeypatch.setattr(stub, "fetchval", fetchval)
    monkeypatch.setattr(geo, "Database", stub)

    _run(geo.run_tick(session_id=5))

    assert [sql for sql, _ in stub.writes if "maya_rp.wars" in sql] == []
