"""Module review tests for modules/victory.py (2026-10-03). Every call is stubbed."""
from __future__ import annotations

import asyncio
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.victory as victory  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


class _StubDB:
    def __init__(self, factions=4, territory=10, credits=50_000_000, allied=2,
                 reputation=0, projects=10, unlocked=5):
        self.factions = factions
        self.territory = territory
        self.credits = credits
        self.allied = allied
        self.reputation = reputation
        self.projects = projects
        self.unlocked = unlocked
        self.reads = []
        self.writes = []

    async def fetch(self, sql, *args):
        self.reads.append((sql, args))
        if "factions" in sql and "COUNT(*)" in sql and "standing" in sql:
            return [{"a": self.allied}]
        if "factions" in sql and "COUNT(*)" in sql:
            return [{"c": self.factions}]
        return []

    async def fetchrow(self, sql, *args):
        self.reads.append((sql, args))
        if "COUNT(*) AS t FROM territory" in sql:
            return {"t": self.territory}
        if "credits" in sql:
            return {"credits": self.credits}
        if "research_projects" in sql:
            return {"t": self.projects, "u": self.unlocked}
        if "reputation" in sql:
            return {"reputation": self.reputation}
        return None

    async def execute(self, sql, *args):
        self.writes.append((sql, args))
        return "OK"


def test_every_scoped_axis_query_names_the_session(monkeypatch):
    """territory, factions and resources carry session_id; the old queries had none."""
    import re

    stub = _StubDB()
    monkeypatch.setattr(victory, "Database", stub)
    _run(victory.run_tick(session_id=5))

    for sql, args in stub.reads + stub.writes:
        if re.search(r"\b(territory|factions|resources)\b", sql) and "research_projects" not in sql:
            assert "session_id" in sql, sql
            assert 5 in args, (sql, args)


def test_the_axes_land_in_the_return(monkeypatch):
    stub = _StubDB(factions=4, territory=10, credits=50_000_000, allied=2,
                   reputation=0, projects=10, unlocked=5)
    monkeypatch.setattr(victory, "Database", stub)
    logged = []
    monkeypatch.setattr(victory, "info", lambda *a: logged.append(a[-1]))

    out = _run(victory.run_tick(session_id=3))

    assert out["session_id"] == 3
    assert out["victory"]["military"] == 50.0     # 10 / 4 * 20
    assert out["victory"]["economic"] == 50.0     # 50M / 100M * 100
    assert out["victory"]["diplomatic"] == 50.0   # 2 / 4 * 100
    assert out["victory"]["technological"] == 50.0
    assert out["victory"]["cultural"] == 50.0
    assert out["score"] == 50.0
    assert logged and "Victory:" in logged[0]


def test_the_tracking_update_is_written_for_each_axis(monkeypatch):
    stub = _StubDB()
    monkeypatch.setattr(victory, "Database", stub)
    _run(victory.run_tick(session_id=3))
    progress = [(sql, args) for sql, args in stub.writes if "SET progress=$1" in sql]
    assert len(progress) == 6, progress
    assert all("session_id=$3" in sql for sql, _ in progress)
    assert {args[1] for _, args in progress} == {
        "military", "economic", "diplomatic", "technological", "cultural", "score"}


def test_a_completed_axis_is_marked_once(monkeypatch):
    stub = _StubDB(factions=1, territory=100, credits=100_000_000, allied=1)
    monkeypatch.setattr(victory, "Database", stub)
    _run(victory.run_tick(session_id=3))
    completed = [sql for sql, _ in stub.writes if "completed=true" in sql]
    assert completed, "an axis at 100 was never marked complete"
    assert all("completed=false" in sql for sql in completed)


def test_the_tick_resolves_its_session(monkeypatch):
    from core.config import Config

    stub = _StubDB()
    monkeypatch.setattr(victory, "Database", stub)
    out = _run(victory.run_tick())
    assert out["session_id"] == Config.SESSION_ID
