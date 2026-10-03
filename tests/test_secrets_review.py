"""Module review tests for modules/secrets.py (2026-10-03).

Every database call is stubbed. No secret row is planted.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.secrets as secrets  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


class _StubDB:
    def __init__(self, active=(), game_day=2253, count=0, names=None):
        self.active = list(active)
        self.game_day = game_day
        self.count = count
        self.names = names or {}
        self.reads = []
        self.writes = []

    async def fetchval(self, sql, *args):
        self.reads.append((sql, args))
        # The INSERT carries planted_game_day in its column list, so it has to be
        # matched before the game_day read.
        if "INSERT INTO maya_rp.secrets" in sql:
            self.writes.append((sql, args))
            return 42
        if "game_day" in sql:
            return self.game_day
        if "COUNT(*)" in sql:
            return self.count
        if "SELECT name FROM maya_rp.characters" in sql:
            return self.names.get(args[0])
        return None

    async def fetch(self, sql, *args):
        self.reads.append((sql, args))
        if "FROM maya_rp.secrets" in sql:
            return self.active
        if "FROM maya_rp.characters" in sql:
            return []
        return []

    async def fetchrow(self, sql, *args):
        self.reads.append((sql, args))
        return None

    async def execute(self, sql, *args):
        self.writes.append((sql, args))
        return "OK"


# ── The log call used to crash every plant ──────────────────────────────


def test_planting_a_secret_does_not_raise(monkeypatch):
    """core.log.info takes (module, msg); the third keyword raised TypeError."""
    stub = _StubDB()
    monkeypatch.setattr(secrets, "Database", stub)

    secret_id = _run(secrets.plant("guilt", 2071, "Rika ignored a warning", session_id=5))

    assert secret_id == 42
    assert stub.writes, "nothing was planted"


def test_the_plant_line_names_the_holder(monkeypatch):
    stub = _StubDB()
    monkeypatch.setattr(secrets, "Database", stub)
    logged = []
    monkeypatch.setattr(secrets, "info", lambda *a: logged.append(a))

    _run(secrets.plant("guilt", 2071, "content", session_id=5))

    assert logged == [("secrets", "Planted: guilt for holder 2071")], logged


def test_the_seed_walks_its_ten_characters(monkeypatch):
    chars = [{"id": i, "name": f"Crew {i}", "role": "crew"} for i in range(1, 11)]
    stub = _StubDB()

    async def fetch(sql, *args):
        stub.reads.append((sql, args))
        if "FROM maya_rp.characters" in sql and "status='active'" in sql:
            return chars
        return []
    monkeypatch.setattr(stub, "fetch", fetch)
    monkeypatch.setattr(secrets, "Database", stub)

    _run(secrets.seed_initial(session_id=5))

    assert stub.writes, "the seed planted nothing"


# ── Discovery ───────────────────────────────────────────────────────────


def test_a_discovered_secret_names_the_holder_inside_the_session(monkeypatch):
    stub = _StubDB(active=[{"id": 7, "secret_type": "guilt", "holder_character_id": 2071,
                            "content": "c", "discovery_trigger": "deep_bond_conversation",
                            "consequence_description": "trust", "auto_reveal_game_day": None}],
                   names={2071: "Rika Voss"})
    monkeypatch.setattr(secrets, "Database", stub)

    out = _run(secrets.check_discovery("a deep and honest conversation about the bond", 5))

    assert out and out[0]["holder"] == "Rika Voss", out
    lookups = [(sql, args) for sql, args in stub.reads if "SELECT name FROM maya_rp.characters" in sql]
    assert lookups and "session_id=$2" in lookups[0][0] and lookups[0][1][1] == 5


def test_an_auto_reveal_day_reveals_the_secret(monkeypatch):
    stub = _StubDB(active=[{"id": 7, "secret_type": "player_blind", "holder_character_id": 2071,
                            "content": "c", "discovery_trigger": "investigation",
                            "consequence_description": "d", "auto_reveal_game_day": 2250}],
                   names={2071: "Izzat"})
    monkeypatch.setattr(secrets, "Database", stub)

    out = _run(secrets.check_discovery("nothing relevant here at all", 5))

    assert out and out[0]["secret_id"] == 7, out
    revealed = [sql for sql, _ in stub.writes if "status='revealed'" in sql]
    assert revealed


def test_the_tick_reveals_only_what_is_due(monkeypatch):
    stub = _StubDB(active=[{"id": 9, "content": "x"}])
    monkeypatch.setattr(secrets, "Database", stub)

    out = _run(secrets.run_tick(session_id=5))

    assert out == {"auto_revealed": 1}
    (sql, args), = stub.writes
    assert "auto_reveal_game_day<=$2" in stub.reads[-1][0]
    assert args == (2253, 9)


def test_the_tick_reads_inside_its_session(monkeypatch):
    stub = _StubDB()
    monkeypatch.setattr(secrets, "Database", stub)
    _run(secrets.run_tick(session_id=5))
    for sql, args in stub.reads:
        if "FROM maya_rp.secrets" in sql:
            assert "session_id=$1" in sql and args[0] == 5, (sql, args)
