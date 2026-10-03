"""Module review tests for modules/ship_building.py (2026-10-03).

Every database call is stubbed, and `generate_ship` is replaced with a fixed
hull, so no test spends a credit or a tonne of alloy.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.ship_building as sb  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


SHIP = {
    "name": "Review Runner", "class_name": "Corvette", "ship_type": "warship",
    "class_id": 1, "tier": 1, "mass": 1000, "length_m": 80, "hull": 400, "speed": 90,
    "crew": 12, "total_alloy_cost": 100, "total_credit_cost": 200,
    "armaments": [], "modules": [],
}


class _StubDB:
    def __init__(self, resources=None, stockpiles=None, crew_available=0):
        self.resources = resources
        self.stockpiles = stockpiles or {}
        self.crew_available = crew_available
        self.reads = []
        self.writes = []

    async def fetchrow(self, sql, *args):
        self.reads.append((sql, args))
        if "FROM maya_rp.resources" in sql:
            return self.resources
        if "FROM maya_rp.ships" in sql:
            if args[0] != 99:
                return None
            return {"id": args[0], "name": "Review Runner", "power_rating": 10, "hull": 400}
        return None

    async def fetchval(self, sql, *args):
        self.reads.append((sql, args))
        if "FROM maya_rp.material_stockpiles" in sql:
            return self.stockpiles.get(args[1], 0)
        if "FROM maya_rp.crew_roster" in sql:
            return self.crew_available
        if "INSERT INTO maya_rp.ships" in sql:
            self.writes.append((sql, args))
            return 4242
        return 0

    async def fetch(self, sql, *args):
        self.reads.append((sql, args))
        if "FROM maya_rp.material_stockpiles" in sql:
            name = args[1]
            have = self.stockpiles.get(name, 0)
            return [{"id": 1, "available": have}] if have else []
        return []

    async def execute(self, sql, *args):
        self.writes.append((sql, args))
        return "OK"

    def statements(self, needle):
        return [(sql, args) for sql, args in self.writes if needle in sql]


@pytest.fixture
def ship(monkeypatch):
    async def fake_generate(*args, **kwargs):
        return dict(SHIP)
    monkeypatch.setattr(sb, "generate_ship", fake_generate)
    return fake_generate


# ── The tier decides the materials, or the build is refused ─────────────


def test_an_unknown_tier_is_refused_instead_of_built_from_tier_one_materials(monkeypatch, ship):
    stub = _StubDB(resources={"alloys": 10**9, "credits": 10**9})
    monkeypatch.setattr(sb, "Database", stub)

    out = _run(sb.build_ship("Corvette", 9, "warship", "Review Runner", session_id=3))

    assert "Unknown tier 9" in out["error"], out
    assert stub.writes == [], "a refused build wrote something"


def test_a_known_tier_still_builds(monkeypatch, ship):
    stub = _StubDB(resources={"alloys": 10**9, "credits": 10**9},
                   stockpiles={"Alloy Ingot": 10**6})
    monkeypatch.setattr(sb, "Database", stub)

    out = _run(sb.build_ship("Corvette", 1, "warship", "Review Runner", session_id=3))

    assert out["ship_id"] == 4242, out
    assert out["cost_credits"] == 200


def test_a_shortfall_after_the_deduction_is_reported_not_swallowed(monkeypatch, ship):
    """The stockpile is read twice: once to check, once to take."""
    stub = _StubDB(resources={"alloys": 10**9, "credits": 10**9}, stockpiles={})
    monkeypatch.setattr(sb, "Database", stub)
    # The check says there is enough, the take loop finds nothing.
    async def fetchval(sql, *args):
        stub.reads.append((sql, args))
        if "FROM maya_rp.material_stockpiles" in sql:
            return 10**6
        return 0
    monkeypatch.setattr(stub, "fetchval", fetchval)
    logged = []
    monkeypatch.setattr(sb, "error", lambda *a: logged.append(a[-1]))

    out = _run(sb.build_ship("Corvette", 1, "warship", "Review Runner", session_id=3))

    assert "short by" in out["error"], out
    assert stub.statements("INSERT INTO maya_rp.ships") == []
    assert any("already spent" in line for line in logged)


# ── The crew that boards is the crew the ship reports ──────────────────


def test_an_undercrewed_ship_actually_takes_the_crew_it_counts(monkeypatch):
    stub = _StubDB(crew_available=3)
    monkeypatch.setattr(sb, "Database", stub)

    out = _run(sb.assign_crew_to_ship(3, 99, 10))

    assert out["warning"] is True and out["deficit"] == 7
    roster = stub.statements("UPDATE maya_rp.crew_roster")
    assert roster, "the ship reported crew it never boarded"
    assert roster[0][1][2] == 3, roster[0]
    ship_update = stub.statements("UPDATE maya_rp.ships")[0]
    assert ship_update[1][0] == 3, "crew_current disagrees with the roster"
    assert "session_id=$5" in ship_update[0].replace(" ", "")


def test_a_crewed_ship_takes_exactly_what_it_asked_for(monkeypatch):
    stub = _StubDB(crew_available=12)
    monkeypatch.setattr(sb, "Database", stub)

    out = _run(sb.assign_crew_to_ship(3, 99, 10))

    assert out == {"warning": False, "crew": 10, "status": "active"}
    assert stub.statements("UPDATE maya_rp.crew_roster")[0][1][2] == 10
    assert "ORDER BY id" in stub.statements("UPDATE maya_rp.crew_roster")[0][0]


def test_the_roster_pick_is_deterministic(monkeypatch):
    """LIMIT without ORDER BY let PostgreSQL choose which crew boarded."""
    stub = _StubDB(crew_available=5)
    monkeypatch.setattr(sb, "Database", stub)
    _run(sb.assign_crew_to_ship(3, 99, 2))
    sql = stub.statements("UPDATE maya_rp.crew_roster")[0][0]
    assert "ORDER BY id" in sql, sql


def test_an_unknown_ship_is_refused_before_any_write(monkeypatch):
    stub = _StubDB()
    monkeypatch.setattr(sb, "Database", stub)
    out = _run(sb.assign_crew_to_ship(3, 999_999_999, 4))
    assert out["error"] == "Ship not found", out
    assert stub.writes == [], "an unknown ship still wrote"


def test_the_shortage_report_counts_one_campaign(monkeypatch):
    stub = _StubDB(crew_available=2)
    monkeypatch.setattr(sb, "Database", stub)
    out = _run(sb.crew_shortage_report(3))
    assert set(out) == {"crew_total", "crew_unassigned", "ships_active", "undercrewed",
                        "shortage", "status"}
    for sql, args in stub.reads:
        if "crew_roster" in sql or "FROM maya_rp.ships" in sql:
            assert args and args[0] == 3, (sql, args)
