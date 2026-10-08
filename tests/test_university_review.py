"""Module review tests for modules/university.py (2026-10-03).

Every database call is stubbed. No graduation is recorded.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.university as uni  # noqa: E402

# Scratch session: sessions 3 and 5 are frozen reference data and the writers refuse them.
SID = 900 + os.getpid() % 100


def _run(coro):
    return asyncio.run(coro)


class _StubDB:
    def __init__(self, campuses=4, labs=1, game_day=2250, already=0, tech_row="default",
                 projects=10, finished=6):
        self.campuses = campuses
        self.labs = labs
        self.game_day = game_day
        self.already = already
        self.tech_row = {"tech_score": 100} if tech_row == "default" else tech_row
        self.projects = projects
        self.finished = finished
        self.reads = []
        self.writes = []

    @contextlib.asynccontextmanager
    async def transaction(self):
        """The stub is its own connection: statements inside a transaction land in the same record."""
        yield self

    async def fetchval(self, sql, *args):
        self.reads.append((sql, args))
        if "university_campuses" in sql and "SUM" not in sql:
            return self.campuses
        if "research_labs" in sql:
            return self.labs
        if "SUM(uc.research_rate)" in sql:
            return 2.5
        if "game_day" in sql:
            return self.game_day
        if "tags @>" in sql:
            return self.already
        if "research_projects" in sql:
            return self.finished if "unlocked=true" in sql else self.projects
        return 0

    async def fetchrow(self, sql, *args):
        self.reads.append((sql, args))
        if "UPDATE maya_rp.resources" in sql:
            self.writes.append((sql, args))
            return self.tech_row
        return None

    async def execute(self, sql, *args):
        self.writes.append((sql, args))
        return "OK"


# ── The graduation cycle fires once per day ─────────────────────────────


def test_the_tick_reports_the_campus_numbers(monkeypatch):
    stub = _StubDB(game_day=2250)          # 2250 % 30 == 0
    monkeypatch.setattr(uni, "Database", stub)

    out = _run(uni.run_tick(session_id=SID))

    assert out == {"total": 10, "finished": 6, "campuses": 4, "labs": 1,
                   "research_rate": 2.5, "graduated": 7}, out


def test_the_second_tick_on_the_same_day_graduates_nothing(monkeypatch):
    """A manual tick plus the orchestrator tick on day 30 graduated twice."""
    stub = _StubDB(game_day=2250, already=1)
    monkeypatch.setattr(uni, "Database", stub)
    logged = []
    monkeypatch.setattr(uni, "info", lambda *a: logged.append(a[-1]))

    out = _run(uni.run_tick(session_id=SID))

    assert out["graduated"] == 0, out
    assert any("already recorded" in line for line in logged), logged
    assert [sql for sql, _ in stub.writes if "tech_score" in sql] == []
    assert [sql for sql, _ in stub.writes if "INSERT INTO maya_rp.events" in sql] == []


def test_the_graduation_records_the_day_it_belonged_to(monkeypatch):
    stub = _StubDB(game_day=2250)
    monkeypatch.setattr(uni, "Database", stub)

    _run(uni.run_tick(session_id=SID))

    marker = [(sql, args) for sql, args in stub.reads if "tags @>" in sql]
    assert marker and json.loads(marker[0][1][1]) == ["day:2250"], marker
    event = [args for sql, args in stub.writes if "INSERT INTO maya_rp.events" in sql][0]
    assert json.loads(event[3]) == ["science", "university", "day:2250"], event
    assert event[0] == SID


def test_a_session_without_a_resources_row_is_told(monkeypatch):
    stub = _StubDB(game_day=2250, tech_row=None)
    monkeypatch.setattr(uni, "Database", stub)
    logged = []
    monkeypatch.setattr(uni, "info", lambda *a: logged.append(a[-1]))

    out = _run(uni.run_tick(session_id=SID))

    assert out["graduated"] == 7
    assert any(f"No resources row for session {SID}" in line for line in logged), logged


def test_a_day_that_is_not_a_cycle_day_graduates_nothing(monkeypatch):
    stub = _StubDB(game_day=2249)
    monkeypatch.setattr(uni, "Database", stub)

    out = _run(uni.run_tick(session_id=SID))

    assert out["graduated"] == 0
    assert stub.writes == []


def test_no_campuses_means_no_graduation(monkeypatch):
    stub = _StubDB(campuses=0, game_day=2250)
    monkeypatch.setattr(uni, "Database", stub)
    out = _run(uni.run_tick(session_id=SID))
    assert out["graduated"] == 0
    assert stub.writes == []


def test_the_tick_returns_an_error_instead_of_raising(monkeypatch):
    class _Boom(_StubDB):
        async def fetchval(self, sql, *args):
            raise RuntimeError("connection reset")
    monkeypatch.setattr(uni, "Database", _Boom())
    logged = []
    monkeypatch.setattr(uni, "error", lambda *a: logged.append(a[-1]))
    out = _run(uni.run_tick(session_id=SID))
    assert "connection reset" in out["error"]
    assert any("connection reset" in line for line in logged)
