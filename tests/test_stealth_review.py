"""Module review tests for modules/stealth.py (2026-10-03).

Every database call is stubbed and the dice are fixed, so no spy is built and no
lane gains intel.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.stealth as stealth  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


UNIT = {"id": 4, "name": "Shadow Probe", "base_cost_alloys": 5000,
        "cloak_level": 3, "max_lanes": 2}


class _StubDB:
    def __init__(self, unit=UNIT, match_count=1, kinds=(), resources=None, spy=None,
                 lane_row=None):
        self.unit = unit
        self.match_count = match_count
        self.kinds = list(kinds)
        self.resources = resources
        self.spy = spy
        self.lane_row = lane_row
        self.reads = []
        self.writes = []
        self.lane_calls = []

    async def fetchval(self, sql, *args):
        self.reads.append((sql, args))
        if "count(*) FROM maya_rp.stealth_unit_types" in sql:
            return self.match_count
        return 0

    async def fetchrow(self, sql, *args):
        self.reads.append((sql, args))
        if "UPDATE maya_rp.space_lanes" in sql:
            self.lane_calls.append(args)
            return self.lane_row
        if "FROM maya_rp.stealth_unit_types" in sql:
            return self.unit
        if "FROM maya_rp.resources" in sql:
            return self.resources
        if "FROM maya_rp.stealth_units" in sql:
            return self.spy
        return None

    async def fetch(self, sql, *args):
        self.reads.append((sql, args))
        if "SELECT name FROM maya_rp.stealth_unit_types" in sql:
            return [{"name": n} for n in self.kinds]
        return []

    async def execute(self, sql, *args):
        self.writes.append((sql, args))
        return "OK"


# ── A unit type nobody can pin down ─────────────────────────────────────


def test_an_ambiguous_unit_type_is_refused(monkeypatch):
    """'probe' matches Shadow Probe and Pool Observation Probe on live rows."""
    stub = _StubDB(match_count=2, kinds=["Shadow Probe", "Pool Observation Probe"])
    monkeypatch.setattr(stealth, "Database", stub)

    out = _run(stealth.build_spy("probe", "Review Spy", session_id=5))

    assert "matches 2 unit types" in out["error"], out
    assert "Pool Observation Probe" in out["error"]
    assert stub.writes == [], "an ambiguous type still spent alloys"


def test_a_pinned_unit_type_builds_and_reports_the_cost(monkeypatch):
    stub = _StubDB(resources={"alloys": 10**6})
    monkeypatch.setattr(stealth, "Database", stub)

    out = _run(stealth.build_spy("Shadow Probe", "Review Spy", session_id=5))

    assert out == {"name": "Review Spy", "type": "Shadow Probe", "cloak": 3, "lanes": 2}
    spent = [args for sql, args in stub.writes if "alloys=alloys-$1" in sql]
    assert spent == [(5000, 5)]
    built = [args for sql, args in stub.writes if "INSERT INTO maya_rp.stealth_units" in sql]
    assert built == [(5, 4, "Review Spy")]


def test_a_spy_nobody_can_afford_is_refused(monkeypatch):
    stub = _StubDB(resources=None)
    monkeypatch.setattr(stealth, "Database", stub)
    out = _run(stealth.build_spy("Shadow Probe", "Review Spy", session_id=5))
    assert "Need" in out["error"], out
    assert stub.writes == []


def test_an_unknown_unit_type_is_refused(monkeypatch):
    stub = _StubDB(match_count=0, unit=None)
    monkeypatch.setattr(stealth, "Database", stub)
    out = _run(stealth.build_spy("Dragon", "Review Spy", session_id=5))
    assert "Unknown unit type" in out["error"], out


# ── Intel lands on a lane or says it did not ────────────────────────────


def test_intel_that_lands_on_no_lane_is_reported(monkeypatch):
    stub = _StubDB(spy={"id": 1, "name": "Review Spy"}, lane_row=None)
    monkeypatch.setattr(stealth, "Database", stub)
    def rigged(a, b):
        return 40 if (a, b) == (20, 80) else 1 if (a, b) == (1, 100) else 0
    monkeypatch.setattr(stealth.random, "randint", rigged)
    logged = []
    monkeypatch.setattr(stealth, "info", lambda *a: logged.append(a[-1]))

    out = _run(stealth.hack("Review Spy", "siphon", "Nowhere Lane", session_id=5))

    assert out["outcome"] == "success" and out["intel_gained"] == 40, out
    assert out["lanes_touched"] == 0, out
    assert any("no lane in session 5" in line for line in logged), logged
    assert stub.lane_calls == [(40, 5, "Nowhere Lane")]


def test_intel_that_lands_reports_the_lane(monkeypatch):
    stub = _StubDB(spy={"id": 1, "name": "Review Spy"}, lane_row={"id": 9})
    monkeypatch.setattr(stealth, "Database", stub)
    def rigged(a, b):
        return 40 if (a, b) == (20, 80) else 1 if (a, b) == (1, 100) else 0
    monkeypatch.setattr(stealth.random, "randint", rigged)

    out = _run(stealth.hack("Review Spy", "siphon", "TKG Gate", session_id=5))

    assert out["lanes_touched"] == 1, out


def test_a_failed_hack_banks_nothing(monkeypatch):
    stub = _StubDB(spy={"id": 1, "name": "Review Spy"})

    def rigged(a, b):
        return 5 if (a, b) == (20, 80) else 100 if (a, b) == (1, 100) else 0
    monkeypatch.setattr(stealth, "Database", stub)
    monkeypatch.setattr(stealth.random, "randint", rigged)

    out = _run(stealth.hack("Review Spy", "siphon", "TKG Gate", session_id=5))

    assert out["outcome"] == "failure", out
    assert out["intel_gained"] == 0
    assert stub.lane_calls == [], "a failed hack still touched a lane"


def test_a_spy_from_another_campaign_is_refused(monkeypatch):
    stub = _StubDB(spy=None)
    monkeypatch.setattr(stealth, "Database", stub)
    assert "not found" in _run(stealth.hack("Review Spy", "siphon", "x", session_id=5))["error"]
    assert "not found" in _run(stealth.deploy_spy("Review Spy", "lane-1", session_id=5))["error"]
    assert stub.writes == []


def test_the_anticloak_grid_clamps_its_level_and_charges_it(monkeypatch):
    stub = _StubDB(resources={"alloys": 10**6})
    monkeypatch.setattr(stealth, "Database", stub)

    out = _run(stealth.build_anticloak("TKG", level=9, session_id=5))

    assert out["level"] == 5 and out["cost"] == 500000 and out["detection"] == 95
    spent = [args for sql, args in stub.writes if "alloys=alloys-$1" in sql]
    assert spent == [(500000, 5)]
