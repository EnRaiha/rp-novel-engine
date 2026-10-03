"""Module review tests for modules/chrono_engine.py (2026-10-03).

Every database call is stubbed. A time skip moves the treasury, the calendar and
the world, so the tests read what the module would send and never send it.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.chrono_engine as chrono  # noqa: E402
from modules.calendar_tkg import DAYS_PER_MONTH  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


class _StubDB:
    """Answers chrono_engine's statements and records every SQL string it saw."""

    def __init__(self, resources_row=None, day=2253):
        self.resources_row = resources_row
        self.day = day
        self.reads = []
        self.writes = []

    async def fetchrow(self, sql, *args):
        self.reads.append((sql, args))
        if "FROM maya_rp.resources" in sql:
            return self.resources_row
        return None

    async def fetchval(self, sql, *args):
        self.reads.append((sql, args))
        if "FROM maya_rp.sessions" in sql:
            return self.day
        if "AVG(personal_morale)" in sql:
            return 55
        return 0

    async def fetch(self, sql, *args):
        self.reads.append((sql, args))
        return []

    async def execute(self, sql, *args):
        self.writes.append((sql, args))
        return "OK"

    def wrote(self, needle):
        return [(sql, args) for sql, args in self.writes if needle in sql]


@pytest.fixture
def quiet_world(monkeypatch):
    """Geopolitics and collapse are other modules; this file tests one module."""
    import modules.collapse as collapse
    import modules.geopolitics as geopolitics

    async def no_turn(session_id):
        return {"events_generated": 0}

    async def no_collapse(session_id):
        return None

    monkeypatch.setattr(geopolitics, "run_tick", no_turn)
    monkeypatch.setattr(collapse, "check_for_collapse", no_collapse)


# ── A session with no resources row ─────────────────────────────────────


def test_a_session_without_a_resources_row_is_refused_before_anything_moves(monkeypatch,
                                                                           quiet_world):
    """`before` could be None and the economy line read before["credits"] anyway."""
    stub = _StubDB(resources_row=None)
    monkeypatch.setattr(chrono, "Database", stub)

    out = _run(chrono.execute_time_skip(30, "economy", session_id=5))

    assert "error" in out, out
    assert "No resources row for session 5" in out["error"]
    assert stub.writes == [], "a refused skip wrote to the database"


def test_a_skip_moves_the_treasury_and_the_calendar_together(monkeypatch, quiet_world):
    stub = _StubDB(resources_row={"credits": 1000, "alloys": 10, "fuel": 20,
                                  "aggregate_morale": 50}, day=2253)
    monkeypatch.setattr(chrono, "Database", stub)

    out = _run(chrono.execute_time_skip(30, "balanced", session_id=3))

    assert out["credits_before"] == 1000
    assert out["days_skipped"] == 30
    assert out["new_game_day"] == 2253
    assert stub.wrote("UPDATE maya_rp.resources")
    assert stub.wrote("UPDATE maya_rp.sessions SET game_day")


def test_an_unknown_focus_is_refused_instead_of_silently_balancing(monkeypatch, quiet_world):
    stub = _StubDB(resources_row={"credits": 1000, "alloys": 0, "fuel": 0,
                                  "aggregate_morale": 50})
    monkeypatch.setattr(chrono, "Database", stub)

    out = _run(chrono.execute_time_skip(30, "economy ", session_id=3))

    assert "Unknown focus" in out["error"], out
    assert stub.writes == [], "an unknown focus still moved the world"
    assert "economy" in out["error"], "the refusal does not name the accepted values"


def test_the_four_documented_focuses_are_the_four_accepted(monkeypatch, quiet_world):
    assert chrono.FOCUSES == ("balanced", "economy", "military", "research")
    for focus in chrono.FOCUSES:
        stub = _StubDB(resources_row={"credits": 1000, "alloys": 0, "fuel": 0,
                                      "aggregate_morale": 50})
        monkeypatch.setattr(chrono, "Database", stub)
        out = _run(chrono.execute_time_skip(30, focus, session_id=3))
        assert "error" not in out, (focus, out)


# ── The month length has one source ─────────────────────────────────────


def test_the_month_length_comes_from_the_calendar():
    """30 was written three times in this module and once in calendar_tkg."""
    import inspect

    source = inspect.getsource(chrono)
    assert "DAYS_PER_MONTH" in source
    assert "// 30" not in source and "% 30" not in source and "/ 30.0" not in source
    assert DAYS_PER_MONTH == 30


def test_the_montage_names_the_calendar_months():
    prompt = chrono._build_montage_prompt({
        "days_skipped": 65, "focus": "economy", "found": 0, "economy": "net +1C",
    })
    assert "2 months and 5 days" in prompt, prompt
    single = chrono._build_montage_prompt({"days_skipped": 30, "focus": "balanced"})
    assert "1 month has passed" in single, single


# ── Validation keeps its shape ──────────────────────────────────────────


def test_the_days_bounds_still_hold():
    out = _run(chrono.execute_time_skip(0, "balanced", session_id=3))
    assert "Days must be >= 1" in out["error"]
    with pytest.raises(ValueError, match="Max 365 days"):
        _run(chrono.execute_time_skip(366, "balanced", session_id=3))
