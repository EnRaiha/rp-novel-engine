"""Module review tests for modules/fleet_economy.py (2026-10-03).

Every database call is stubbed. No fleet burns a litre of fuel.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.fleet_economy as fe  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


class _StubDB:
    def __init__(self, ships=4, population=1_000_000, crew=100, resources=None,
                 updated=None):
        self.ships = ships
        self.population = population
        self.crew = crew
        self.resources = resources
        self.updated = updated
        self.reads = []
        self.writes = []

    async def fetchval(self, sql, *args):
        self.reads.append((sql, args))
        if "COUNT(*)" in sql:
            return self.ships
        if "population" in sql:
            return self.population
        if "SUM(crew_current)" in sql:
            return self.crew
        return 0

    async def fetchrow(self, sql, *args):
        self.reads.append((sql, args))
        if "UPDATE maya_rp.resources" in sql:
            self.writes.append((sql, args))
            return self.updated
        if "FROM maya_rp.resources" in sql:
            return self.resources
        return None

    async def execute(self, sql, *args):
        self.writes.append((sql, args))
        return "OK"


# ── The burn arithmetic ─────────────────────────────────────────────────


def test_the_burn_follows_its_declared_rates(monkeypatch):
    stub = _StubDB(ships=4, population=1_000_000, crew=100)
    monkeypatch.setattr(fe, "Database", stub)

    burn = _run(fe.calculate_daily_burn(3))

    assert burn["fuel"] == 4 * fe.BURN_RATES["per_active_ship"] + fe.BURN_RATES["base_consumption"]
    assert burn["food"] == max(1, round(1_000_000 * 0.001 * 24))
    assert burn["credits"] == 100 + 100 * 2
    assert burn["alloy"] == 0
    assert stub.reads and all("session_id=$1" in sql for sql, _ in stub.reads)


def test_a_fleet_with_no_crew_still_pays_the_base_cost(monkeypatch):
    stub = _StubDB(ships=0, population=0, crew=0)
    monkeypatch.setattr(fe, "Database", stub)
    burn = _run(fe.calculate_daily_burn(5))
    assert burn["credits"] == 100
    assert burn["food"] == 1


# ── The burn is applied in one statement ────────────────────────────────


def test_the_burn_is_decremented_in_the_database(monkeypatch):
    """The old read-modify-write set absolute values from a snapshot."""
    stub = _StubDB(updated={"fuel": 900, "alloys": 500, "credits": 700})
    monkeypatch.setattr(fe, "Database", stub)

    out = _run(fe.apply_burn(3))

    (sql, args), = stub.writes
    assert "fuel=GREATEST(0, fuel-$1)" in sql and "RETURNING" in sql, sql
    assert args == (90, 0, 300, 3)
    assert out["fuel_remaining"] == 900 and out["credits_remaining"] == 700


def test_a_session_with_no_resources_row_is_refused(monkeypatch):
    stub = _StubDB(updated=None)
    monkeypatch.setattr(fe, "Database", stub)

    out = _run(fe.apply_burn(5))

    assert "No resources row for session 5" in out["error"], out


def test_the_tick_reports_the_burn_and_survives_its_own_error(monkeypatch):
    stub = _StubDB(updated={"fuel": 10, "alloys": 10, "credits": 10})
    monkeypatch.setattr(fe, "Database", stub)
    out = _run(fe.run_tick(session_id=3))
    assert out["burn"]["fuel"] == 90 and out["fuel_remaining"] == 10

    class _Boom(_StubDB):
        async def fetchval(self, sql, *args):
            raise RuntimeError("connection reset")
    monkeypatch.setattr(fe, "Database", _Boom())
    logged = []
    monkeypatch.setattr(fe, "info", lambda *a: logged.append(a[-1]))
    out = _run(fe.run_tick(session_id=3))
    assert "connection reset" in out["error"]
    assert any("connection reset" in line for line in logged)


# ── The summary ─────────────────────────────────────────────────────────


def test_the_summary_counts_the_days_of_fuel_left(monkeypatch):
    stub = _StubDB(ships=4, resources={"fuel": 180, "alloys": 100, "credits": 100})
    monkeypatch.setattr(fe, "Database", stub)

    out = _run(fe.get_burn_summary(3))

    assert out["days_of_fuel"] == 2 and out["critical"] is True, out

    stub = _StubDB(ships=4, resources={"fuel": 900, "alloys": 100, "credits": 100})
    monkeypatch.setattr(fe, "Database", stub)
    out = _run(fe.get_burn_summary(3))
    assert out["days_of_fuel"] == 10 and out["critical"] is False


def test_the_caravan_rolls_inside_its_declared_ranges(monkeypatch):
    monkeypatch.setattr(fe.random, "randint", lambda a, b: a)
    out = _run(fe.generate_caravan(3))
    assert out["cargo"] in ("fuel", "alloys", "food", "credits")
    assert out["quantity"] == 100 and out["transit_days"] == 1
