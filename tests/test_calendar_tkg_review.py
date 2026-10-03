"""Module review tests for modules/calendar_tkg.py (2026-10-03).

The database is stubbed everywhere. The calendar also has 2253 days of printed
history in session 3, and nothing here writes to it.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.calendar_tkg as cal  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


class _StubDB:
    def __init__(self, game_day=2253, rows=True):
        self.game_day = game_day
        self.rows = rows
        self.reads = []
        self.writes = []

    async def fetchrow(self, sql, *args):
        self.reads.append((sql, args))
        if "FROM maya_rp.sessions" in sql:
            return {"game_day": self.game_day} if self.rows else None
        if "UPDATE maya_rp.crew_roster" in sql:
            return {"id": 1} if self.rows else None
        if "UPDATE maya_rp.resources" in sql:
            return {"credits": 1} if self.rows else None
        return None

    async def fetchval(self, sql, *args):
        self.reads.append((sql, args))
        if "FROM maya_rp.sessions" in sql:
            return self.game_day
        return 0

    async def fetch(self, sql, *args):
        self.reads.append((sql, args))
        return []

    async def execute(self, sql, *args):
        self.writes.append((sql, args))
        return "OK"


# ── The date lookup must not edit the calendar ──────────────────────────


def test_reading_a_holiday_does_not_stamp_the_module_table(monkeypatch):
    """`HOLIDAYS[key]` was handed straight out, and days_until was written into it."""
    stub = _StubDB(game_day=1)          # day 1 is (1,1), Hari Harapan
    monkeypatch.setattr(cal, "Database", stub)
    before = dict(cal.HOLIDAYS[(1, 1)])

    date = _run(cal.get_game_date(3))

    assert date["holiday"]["name"] == "Hari Harapan"
    assert date["holiday"]["days_until"] == 0
    assert cal.HOLIDAYS[(1, 1)] == before, "the lookup wrote into the shared table"


def test_the_calendar_arithmetic_matches_canon_d5():
    """Twelve months of thirty days, then five leftover days, 365 days."""
    assert cal.YEAR_DAYS == 365
    assert cal.MONTH_DAYS == 360
    assert cal.LEFTOVER_DAYS == cal.YEAR_DAYS - cal.MONTH_DAYS

    async def check():
        return [await cal.get_game_date(3, day) for day in (1, 30, 31, 360, 361, 365, 366)]

    day1, day30, day31, day360, day361, day365, day366 = _run(check())
    assert (day1["month"], day1["day"], day1["year"]) == ("Harapan", 1, 1)
    assert (day30["month"], day30["day"]) == ("Harapan", 30)
    assert (day31["month"], day31["day"]) == ("Lautan", 1)
    assert (day360["month"], day360["day"]) == ("Malam", 30)
    assert day361["leftover"] is True and day361["month"] == cal.LEFTOVER_NAME
    assert day365["leftover"] is True and day365["day"] == 5
    assert (day366["year"], day366["month"], day366["day"]) == (2, "Harapan", 1)


def test_leftover_days_carry_no_holiday_and_their_own_season():
    async def check():
        return [await cal.get_game_date(3, day) for day in (360, 361)]

    last, leftover = _run(check())
    assert leftover["holiday"] is None
    assert leftover["season"] == "leftover"
    assert last["season"] == cal.SEASONS["Malam"]


def test_upcoming_keeps_the_lookahead_and_skips_leftover_days(monkeypatch):
    stub = _StubDB(game_day=358)
    monkeypatch.setattr(cal, "Database", stub)
    events = _run(cal.get_upcoming(3, 10))
    names = [e["name"] for e in events]
    assert "Malam Hitam" in names, events
    for event in events:
        assert 0 <= event["days_until"] < 10
        assert "Hari Sisa" not in event["date"]


# ── A holiday that nobody can pay for says so ───────────────────────────


def test_a_holiday_says_when_the_treasury_row_is_missing(monkeypatch):
    stub = _StubDB(rows=False)
    monkeypatch.setattr(cal, "Database", stub)
    logged = []
    monkeypatch.setattr(cal, "info", lambda *a: logged.append(a[-1]))

    date = _run(cal.get_game_date(3, 1))
    _run(cal.apply_holiday(date, 5))

    assert any("no resources row for session 5" in line for line in logged), logged
    assert any("no crew row for session 5" in line for line in logged), logged


def test_a_holiday_charges_the_crown_and_lifts_the_crew(monkeypatch):
    stub = _StubDB(game_day=1)
    monkeypatch.setattr(cal, "Database", stub)

    date = _run(cal.get_game_date(3, 1))
    _run(cal.apply_holiday(date, 3))

    crew = [args for sql, args in stub.reads if "UPDATE maya_rp.crew_roster" in sql]
    spend = [args for sql, args in stub.reads if "UPDATE maya_rp.resources" in sql]
    assert crew and crew[0][0] == 5, crew          # Hari Harapan bonus
    assert spend and spend[0][0] == 5 * 2000, spend
    event = [args for sql, args in stub.writes if "INSERT INTO maya_rp.events" in sql]
    assert event and event[0][0] == 3


def test_a_somber_holiday_costs_the_crown_nothing(monkeypatch):
    stub = _StubDB(game_day=360)                    # (12,30) Malam Hitam, bonus -2
    monkeypatch.setattr(cal, "Database", stub)
    date = _run(cal.get_game_date(3, 360))
    assert date["holiday"]["name"] == "Malam Hitam"
    _run(cal.apply_holiday(date, 3))
    assert [sql for sql, _ in stub.reads if "UPDATE maya_rp.resources" in sql] == []


def test_a_day_with_no_holiday_applies_nothing(monkeypatch):
    stub = _StubDB(game_day=5)
    monkeypatch.setattr(cal, "Database", stub)
    date = _run(cal.get_game_date(3, 5))
    assert date["holiday"] is None
    _run(cal.apply_holiday(date, 3))
    assert stub.writes == []
