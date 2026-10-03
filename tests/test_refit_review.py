"""Module review tests for modules/refit.py (2026-10-03).

Every database call is stubbed. No refit spends a credit or a tonne of alloy.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.refit as refit  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


SHIP = {"id": 4, "name": "Blizzard Zero", "tier": 3, "hull": 400, "speed": 60}
MOD = {"id": 45, "name": "Void Drive", "category": "void", "cost_alloys": 100,
       "cost_credits": 200}


class _StubDB:
    def __init__(self, ship=SHIP, module=MOD, resources=None, available=None):
        self.ship = ship
        self.module = module
        self.resources = resources
        self.available = available or []
        self.reads = []
        self.writes = []

    async def fetchrow(self, sql, *args):
        self.reads.append((sql, args))
        if "FROM maya_rp.ships" in sql:
            return self.ship
        if "FROM maya_rp.modules" in sql:
            return self.module
        if "FROM maya_rp.resources" in sql:
            return self.resources
        return None

    async def fetch(self, sql, *args):
        self.reads.append((sql, args))
        if "cost_alloys" in sql:
            return self.available
        return []

    async def execute(self, sql, *args):
        self.writes.append((sql, args))
        return "OK"

    def sql_with(self, needle):
        return [sql for sql, _ in self.writes if needle in sql]


# ── A session with no resources row ─────────────────────────────────────


def test_a_refit_without_a_resources_row_is_refused_instead_of_raising(monkeypatch):
    """`res["alloys"]` raised TypeError; session 5 has no resources row."""
    stub = _StubDB(resources=None)
    monkeypatch.setattr(refit, "Database", stub)
    out = _run(refit.install_module("Blizzard", "Void Drive", 1, session_id=5))
    assert "No resources row for session 5" in out["error"], out
    assert stub.writes == []


def test_an_upgrade_without_a_resources_row_is_refused_instead_of_raising(monkeypatch):
    stub = _StubDB(resources=None)
    monkeypatch.setattr(refit, "Database", stub)
    out = _run(refit.upgrade_ship("Blizzard", session_id=5))
    assert "No resources row for session 5" in out["error"], out
    assert stub.writes == []


# ── Slots are slots ─────────────────────────────────────────────────────


def test_a_slot_below_one_is_refused(monkeypatch):
    stub = _StubDB(resources={"alloys": 10**6, "credits": 10**6})
    monkeypatch.setattr(refit, "Database", stub)
    for bad in (0, -3):
        out = _run(refit.install_module("Blizzard", "Void Drive", bad, session_id=3))
        assert "slot_index must be at least 1" in out["error"], (bad, out)
    assert stub.writes == []


def test_a_refit_pays_and_reports_the_slot(monkeypatch):
    stub = _StubDB(resources={"alloys": 10**6, "credits": 10**6})
    monkeypatch.setattr(refit, "Database", stub)

    out = _run(refit.install_module("Blizzard", "Void Drive", 2, session_id=3))

    assert out["slot"] == 2 and out["cost_credits"] == 200
    spent = [args for sql, args in stub.writes if "alloys=alloys-$1" in sql]
    assert spent == [(100, 200, 3)]
    assert stub.sql_with("INSERT INTO maya_rp.ship_modules")


# ── An unbounded module is still offered ────────────────────────────────


def test_a_module_with_no_upper_tier_is_offered(monkeypatch):
    """`tier_max >= $1` is NULL for an unlimited module, so it was hidden."""
    stub = _StubDB(resources={"alloys": 1, "credits": 1})
    monkeypatch.setattr(refit, "Database", stub)
    _run(refit.list_modules("Blizzard", session_id=3))
    offered = [sql for sql, _ in stub.reads if "cost_alloys" in sql]
    assert offered and "tier_max IS NULL OR tier_max" in offered[0], offered


def test_an_upgrade_costs_the_declared_rate_and_boosts_hull_and_speed(monkeypatch):
    stub = _StubDB(resources={"alloys": 10**6, "credits": 10**6})
    monkeypatch.setattr(refit, "Database", stub)

    out = _run(refit.upgrade_ship("Blizzard", session_id=3))

    assert (out["old_tier"], out["new_tier"]) == (3, 4)
    assert out["hull_after"] == round(400 * 1.25)
    assert out["speed_after"] == round(60 * 1.15)
    spent = [args for sql, args in stub.writes if "alloys=alloys-$1" in sql]
    assert spent == [(3 * 2000, 3 * 1000, 3)]
    ship_update = [args for sql, args in stub.writes if "UPDATE maya_rp.ships" in sql][0]
    assert ship_update == (4, 500, 500, 69, 4, 3)


def test_a_ship_at_max_tier_is_refused(monkeypatch):
    stub = _StubDB(ship={**SHIP, "tier": 4}, resources={"alloys": 10**6, "credits": 10**6})
    monkeypatch.setattr(refit, "Database", stub)
    out = _run(refit.upgrade_ship("Blizzard", session_id=3))
    assert "already at max tier" in out["error"], out
    assert stub.writes == []


def test_an_unknown_ship_is_refused_by_name(monkeypatch):
    stub = _StubDB(ship=None)
    monkeypatch.setattr(refit, "Database", stub)
    assert "not found" in _run(refit.list_modules("Nope", session_id=3))["error"]
    assert "not found" in _run(refit.install_module("Nope", "Void Drive", 1, 3))["error"]
    assert "not found" in _run(refit.upgrade_ship("Nope", session_id=3))["error"]
    assert stub.writes == []


def test_poor_funds_are_refused_before_anything_is_spent(monkeypatch):
    stub = _StubDB(resources={"alloys": 1, "credits": 1})
    monkeypatch.setattr(refit, "Database", stub)
    assert "Need" in _run(refit.install_module("Blizzard", "Void Drive", 1, 3))["error"]
    assert "Need" in _run(refit.upgrade_ship("Blizzard", session_id=3))["error"]
    assert stub.writes == []
