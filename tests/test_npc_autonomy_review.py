"""Module review tests for modules/npc_autonomy.py (2026-10-03).

Every database call is stubbed. No NPC morale is written.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.npc_autonomy as npc  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


def _row(name, archetype="stoic", morale=None, fear=None, loyalty=None):
    return {"id": abs(hash(name)) % 10_000, "name": name, "archetype": archetype,
            "personal_morale": morale, "personal_fear": fear,
            "personal_loyalty": loyalty, "current_mood": None}


class _StubDB:
    def __init__(self, npcs=(), interactions=(), names=None, game_day=2253):
        self.npcs = list(npcs)
        self.interactions = list(interactions)
        self.names = names or {}
        self.game_day = game_day
        self.reads = []
        self.writes = []

    async def fetch(self, sql, *args):
        self.reads.append((sql, args))
        if "npc_internal_state nis JOIN" in sql:
            return self.npcs
        if "LEFT JOIN maya_rp.npc_internal_state" in sql:
            return self.npcs
        if "FROM maya_rp.characters" in sql:
            return self.npcs
        return []

    async def fetchrow(self, sql, *args):
        self.reads.append((sql, args))
        if "FROM maya_rp.npc_offscreen_interactions" in sql:
            return self.interactions[0] if self.interactions else None
        return None

    async def fetchval(self, sql, *args):
        self.reads.append((sql, args))
        if "game_day" in sql:
            return self.game_day
        if "SELECT name FROM maya_rp.characters" in sql:
            return self.names.get(args[0])
        return 0

    async def execute(self, sql, *args):
        self.writes.append((sql, args))
        return "OK"


# ── A stored zero is a value ────────────────────────────────────────────


def test_a_zero_morale_and_loyalty_are_read_as_stored(monkeypatch):
    """`or 50` raised a broken NPC to 50 and a disloyal one to 50."""
    stub = _StubDB(npcs=[_row("Kael", "stoic", morale=0, fear=0, loyalty=0)])
    monkeypatch.setattr(npc, "Database", stub)

    _run(npc.react_to_event("combat_victory", session_id=5))

    upsert = [args for sql, args in stub.writes if "npc_internal_state" in sql][0]
    morale, fear, loyalty = upsert[2], upsert[3], upsert[4]
    # stoic is a slow reactor: 2 * 0.5 = 1 morale, -1 * 0.5 = 0 fear, 1 * 0.5 = 0 loyalty
    assert morale == 1, upsert
    assert loyalty == 0, upsert
    assert fear == 0, upsert


def test_a_missing_state_still_reads_the_documented_defaults(monkeypatch):
    stub = _StubDB(npcs=[_row("Mira", "stoic")])
    monkeypatch.setattr(npc, "Database", stub)

    _run(npc.react_to_event("holiday", session_id=5))

    upsert = [args for sql, args in stub.writes if "npc_internal_state" in sql][0]
    assert upsert[2] == 51      # 50 + int(3 * 0.5)
    assert upsert[4] == 50      # loyalty default, holiday shifts l by 0


# ── An archetype the table does not carry ───────────────────────────────


def test_an_unknown_archetype_is_named_once(monkeypatch):
    stub = _StubDB(npcs=[_row("Pirate One", "pirate"), _row("Leader", "leader")])
    monkeypatch.setattr(npc, "Database", stub)
    logged = []
    monkeypatch.setattr(npc, "info", lambda *a: logged.append(a[-1]))

    _run(npc.react_to_event("combat_victory", session_id=5))

    assert len([line for line in logged if "not in ARCHETYPES" in line]) == 1, logged
    assert "'leader'" in logged[0] and "'pirate'" in logged[0], logged


def test_a_known_archetype_is_not_flagged(monkeypatch):
    stub = _StubDB(npcs=[_row("Kael", "ambitious")])
    monkeypatch.setattr(npc, "Database", stub)
    logged = []
    monkeypatch.setattr(npc, "info", lambda *a: logged.append(a[-1]))
    _run(npc.react_to_event("combat_victory", session_id=5))
    assert logged == []


def test_a_fast_archetype_moves_more_than_a_slow_one(monkeypatch):
    stub = _StubDB(npcs=[_row("Fast", "rebellious", morale=50, fear=0, loyalty=50),
                         _row("Slow", "stoic", morale=50, fear=0, loyalty=50)])
    monkeypatch.setattr(npc, "Database", stub)
    _run(npc.react_to_event("combat_defeat", session_id=5))
    upserts = [args for sql, args in stub.writes if "npc_internal_state" in sql]
    fast = next(a for a in upserts if a[0] == _row("Fast")["id"])
    slow = next(a for a in upserts if a[0] == _row("Slow")["id"])
    assert fast[2] < slow[2], (fast, slow)      # combat_defeat morale is negative


def test_an_event_with_no_declared_reaction_does_nothing(monkeypatch):
    stub = _StubDB(npcs=[_row("Kael")])
    monkeypatch.setattr(npc, "Database", stub)
    assert _run(npc.react_to_event("weather", session_id=5)) == []
    assert stub.reads == [] and stub.writes == []


# ── The discovery read ──────────────────────────────────────────────────


def test_the_discovery_names_are_read_inside_the_session(monkeypatch):
    stub = _StubDB(interactions=[{"id": 3, "character_a": 11, "character_b": 12,
                                  "interaction_type": "gossip", "description": "d",
                                  "game_day": 10}],
                   names={11: "A", 12: "B"})
    monkeypatch.setattr(npc, "Database", stub)

    out = _run(npc.discover_off_screen(session_id=5))

    assert out["characters"] == ["A", "B"], out
    lookups = [(sql, args) for sql, args in stub.reads if "SELECT name FROM maya_rp.characters" in sql]
    assert lookups and all("session_id=$2" in sql and args[1] == 5 for sql, args in lookups), lookups


def test_a_discovered_interaction_is_marked_once(monkeypatch):
    stub = _StubDB(interactions=[{"id": 3, "character_a": 11, "character_b": 12,
                                  "interaction_type": "gossip", "description": "d",
                                  "game_day": 10}], names={11: "A", 12: "B"})
    monkeypatch.setattr(npc, "Database", stub)
    _run(npc.discover_off_screen(session_id=5))
    marked = [args for sql, args in stub.writes if "SET discovered=true" in sql]
    assert marked == [(3,)]


def test_nothing_undiscovered_returns_none(monkeypatch):
    stub = _StubDB()
    monkeypatch.setattr(npc, "Database", stub)
    assert _run(npc.discover_off_screen(session_id=5)) is None
    assert stub.writes == []


def test_the_tick_scopes_its_state_reads(monkeypatch):
    stub = _StubDB(npcs=[])
    monkeypatch.setattr(npc, "Database", stub)
    out = _run(npc.run_tick(session_id=5))
    assert set(out) == {"off_screen", "anxious"}
    for sql, args in stub.reads + stub.writes:
        if "npc_internal_state" in sql:
            assert 5 in args, (sql, args)
