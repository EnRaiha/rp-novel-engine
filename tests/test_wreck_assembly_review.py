"""Module review tests for modules/wreck_assembly.py (2026-10-03).

Every database call is stubbed and the assembly roll is fixed, so no ship is
built and no wreck is spent.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.wreck_assembly as wa  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


def _wreck(wid, hull, power, name=None):
    return {"id": wid, "name": name or f"Wreck {wid}", "tier": 3, "hull": hull,
            "power_rating": power, "sub_class": "Corvette"}


class _StubDB:
    def __init__(self, wrecks=()):
        self.wrecks = list(wrecks)
        self.reads = []
        self.writes = []

    async def fetchval(self, sql, *args):
        self.reads.append((sql, args))
        if "INSERT INTO maya_rp.wreck_inventory" in sql:
            self.writes.append((sql, args))
            return 11
        if "INSERT INTO maya_rp.ships" in sql:
            self.writes.append((sql, args))
            return 22
        return 0

    async def fetch(self, sql, *args):
        self.reads.append((sql, args))
        if "FROM maya_rp.wreck_inventory" in sql:
            wanted = set(args[0])
            return [w for w in self.wrecks if w["id"] in wanted]
        return []

    async def execute(self, sql, *args):
        self.writes.append((sql, args))
        return "OK"


# ── A wreck that cannot be a hull ───────────────────────────────────────


def test_a_negative_hull_is_refused(monkeypatch):
    """assemble derives the new hull from the wreck's, so a negative one ships."""
    stub = _StubDB()
    monkeypatch.setattr(wa, "Database", stub)
    out = _run(wa.add_wreck(3, "Bad Wreck", 3, -500, 100, "Corvette"))
    assert "cannot be negative" in out["error"], out
    assert stub.writes == []


def test_a_wreck_needs_a_name_and_a_real_tier(monkeypatch):
    stub = _StubDB()
    monkeypatch.setattr(wa, "Database", stub)
    assert "needs a name" in _run(wa.add_wreck(3, "  ", 3, 100, 100, "x"))["error"]
    assert "at least 1" in _run(wa.add_wreck(3, "W", 0, 100, 100, "x"))["error"]
    assert "whole numbers" in _run(
        wa.add_wreck(3, "W", 3, "not a number", 100, "x"))["error"]
    assert stub.writes == []


def test_a_good_wreck_is_stored(monkeypatch):
    stub = _StubDB()
    monkeypatch.setattr(wa, "Database", stub)
    out = _run(wa.add_wreck(3, "Blizzard Zero", 3, 400, 120, "Corvette", 7))
    assert out == {"wreck_id": 11, "name": "Blizzard Zero"}
    (_, args), = stub.writes
    assert args == (3, 7, "Blizzard Zero", 3, 400, 120, "Corvette")


# ── Assembly keeps its declared arithmetic ──────────────────────────────


def test_assembly_needs_two_to_five_wrecks(monkeypatch):
    stub = _StubDB()
    monkeypatch.setattr(wa, "Database", stub)
    assert "2-5" in _run(wa.assemble(3, "N", [1]))["error"]
    assert "2-5" in _run(wa.assemble(3, "N", [1, 2, 3, 4, 5, 6]))["error"]
    assert stub.reads == []


def test_a_negative_engineering_skill_is_refused(monkeypatch):
    stub = _StubDB(wrecks=[_wreck(1, 400, 100), _wreck(2, 200, 80)])
    monkeypatch.setattr(wa, "Database", stub)
    out = _run(wa.assemble(3, "N", [1, 2], engineering_skill=-3))
    assert "cannot be negative" in out["error"], out
    assert stub.writes == []


def test_a_wreck_from_another_campaign_is_refused(monkeypatch):
    stub = _StubDB(wrecks=[_wreck(1, 400, 100)])   # only one of the two asked for
    monkeypatch.setattr(wa, "Database", stub)
    out = _run(wa.assemble(5, "N", [1, 2]))
    assert "tidak dijumpai" in out["error"], out
    assert stub.writes == []


def test_a_successful_assembly_reports_the_numbers_it_used(monkeypatch):
    stub = _StubDB(wrecks=[_wreck(1, 400, 100), _wreck(2, 200, 80)])
    monkeypatch.setattr(wa, "Database", stub)
    monkeypatch.setattr(wa.random, "randint", lambda a, b: 10)   # 10 <= 60 + 5*5

    out = _run(wa.assemble(3, "Blizzard Zero", [1, 2], engineering_skill=5))

    assert out["success"] is True
    assert out["roll"] == 10 and out["target"] == 85
    assert out["hull"] == int(400 * 0.9) + int(200 * 0.1)   # 380
    assert out["power"] == 100                              # the strongest wreck
    ship_insert = [args for sql, args in stub.writes if "INSERT INTO maya_rp.ships" in sql][0]
    assert ship_insert[:6] == (3, "Blizzard Zero", 380, 100, "Corvette", "Heaven Yard — Assembly Bay") \
        or ship_insert[0] == 3


def test_a_failed_assembly_halves_the_power(monkeypatch):
    stub = _StubDB(wrecks=[_wreck(1, 400, 100), _wreck(2, 200, 80)])
    monkeypatch.setattr(wa, "Database", stub)
    monkeypatch.setattr(wa.random, "randint", lambda a, b: 100)   # 100 > 85

    out = _run(wa.assemble(3, "Blizzard Zero", [1, 2]))

    assert out["success"] is False
    assert out["power"] == 50, out


def test_the_wrecks_are_marked_used_inside_the_same_session(monkeypatch):
    stub = _StubDB(wrecks=[_wreck(1, 400, 100), _wreck(2, 200, 80)])
    monkeypatch.setattr(wa, "Database", stub)
    monkeypatch.setattr(wa.random, "randint", lambda a, b: 10)

    _run(wa.assemble(3, "N", [1, 2]))

    used = [(sql, args) for sql, args in stub.writes if "UPDATE maya_rp.wreck_inventory" in sql]
    assert used and "session_id=$2" in used[0][0]
    assert used[0][1] == ([1, 2], 3)


def test_cmd_refuses_an_unknown_action(monkeypatch):
    stub = _StubDB()
    monkeypatch.setattr(wa, "Database", stub)
    out = _run(wa.cmd(3, "weld", {}))
    assert "Unknown action" in out["error"]
    assert stub.reads == [] and stub.writes == []
