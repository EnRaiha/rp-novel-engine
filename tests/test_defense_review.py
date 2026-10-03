"""Module review tests for modules/defense.py (2026-10-03). Every call is stubbed."""
from __future__ import annotations

import asyncio
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.defense as defense  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


class _StubDB:
    def __init__(self, colony=None, resources=None, install=None):
        self.colony = colony
        self.resources = resources
        self.install = install
        self.reads = []
        self.writes = []

    async def fetchrow(self, sql, *args):
        self.reads.append((sql, args))
        if "FROM maya_rp.colonies" in sql:
            return self.colony
        if "FROM maya_rp.resources" in sql:
            return self.resources
        if "defense_installations" in sql:
            return self.install
        return None

    async def fetch(self, sql, *args):
        self.reads.append((sql, args))
        return []

    async def execute(self, sql, *args):
        self.writes.append((sql, args))
        return "OK"


COLONY = {"id": 9, "name": "Heaven Yard"}


def test_an_unknown_type_is_refused_by_name(monkeypatch):
    stub = _StubDB(colony=COLONY, resources={"alloys": 10**6})
    monkeypatch.setattr(defense, "Database", stub)
    out = _run(defense.build("Heaven Yard", "death_star", session_id=3))
    assert "Invalid type" in out["error"] and "orbital_platform" in out["error"], out
    assert stub.writes == []


def test_a_build_pays_and_reports(monkeypatch):
    stub = _StubDB(colony=COLONY, resources={"alloys": 10**6})
    monkeypatch.setattr(defense, "Database", stub)
    out = _run(defense.build("Heaven Yard", "shield_generator", session_id=3))
    assert out == {"type": "shield_generator", "colony": "Heaven Yard", "rating": 200, "cost": 4000}
    spent = [args for sql, args in stub.writes if "alloys=alloys-$1" in sql]
    assert spent == [(4000, 3)]


def test_a_colony_from_another_campaign_is_refused(monkeypatch):
    stub = _StubDB(colony=None, resources={"alloys": 10**6})
    monkeypatch.setattr(defense, "Database", stub)
    assert "not found" in _run(defense.build("Elsewhere", "minefield", session_id=5))["error"]
    assert stub.writes == []


def test_an_upgrade_costs_level_times_two_thousand(monkeypatch):
    stub = _StubDB(resources={"alloys": 10**6},
                   install={"id": 4, "installation_type": "minefield", "level": 2,
                            "defense_rating": 150})
    monkeypatch.setattr(defense, "Database", stub)
    out = _run(defense.upgrade(4, session_id=3))
    assert out == {"type": "minefield", "level": 3, "rating": 210, "cost": 4000}
    updated = [args for sql, args in stub.writes if "SET level=$1" in sql]
    assert updated == [(3, 210, 4, 3)], updated


def test_an_upgrade_of_another_campaigns_installation_is_refused(monkeypatch):
    stub = _StubDB(resources={"alloys": 10**6}, install=None)
    monkeypatch.setattr(defense, "Database", stub)
    assert "not found" in _run(defense.upgrade(4, session_id=5))["error"]
    assert stub.writes == []


def test_max_level_and_poor_funds_are_refused(monkeypatch):
    stub = _StubDB(resources={"alloys": 10**6},
                   install={"id": 4, "installation_type": "minefield", "level": 5,
                            "defense_rating": 900})
    monkeypatch.setattr(defense, "Database", stub)
    assert "max level" in _run(defense.upgrade(4, session_id=3))["error"]

    stub = _StubDB(resources={"alloys": 1},
                   install={"id": 4, "installation_type": "minefield", "level": 2,
                            "defense_rating": 150})
    monkeypatch.setattr(defense, "Database", stub)
    assert "Need 4000 alloys" in _run(defense.upgrade(4, session_id=3))["error"]
    assert stub.writes == []
