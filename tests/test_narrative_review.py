"""Narrative review: what reading `modules/narrative.py` in full turned up.

The tick defaulted to the literal session 3 and returned None on every path, ending in a print.
Nothing here writes to session 3. The story
rows this file creates are tracked by id and removed in a `finally`; session 5 already holds 35
story_log rows of its own, so the test never deletes by session.
"""
from __future__ import annotations

import inspect
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from core.db import Database  # noqa: E402
from modules import narrative  # noqa: E402

SESSION = 5
MARKER = 987654322


async def _resources(age_hours):
    await Database.execute(
        "INSERT INTO maya_rp.resources (session_id, research_points, last_tick_at) "
        "VALUES ($1, 0, NOW() - make_interval(hours => $2::int))",
        SESSION, age_hours)


async def _drop_resources():
    await Database.execute(
        "DELETE FROM maya_rp.resources WHERE session_id = $1 AND research_points = 0 "
        "AND last_tick_at IS NOT NULL", SESSION)


async def _drop_row(table, row_id):
    """Delete one row by its own id. Never by `id > ceiling`, and never across tables.

    The earlier version of this file deleted `events` with a `story_log` id as the ceiling. The two
    tables number independently, the story_log id was far below the events ids, and the delete wiped
    169 `events` rows belonging to session 5. No backup carried that table.
    """
    await Database.execute(f"DELETE FROM maya_rp.{table} WHERE id = $1", row_id)


class TestTheNarrativeTick:
    def test_the_tick_does_not_default_to_the_frozen_campaign(self):
        default = inspect.signature(narrative.run_tick).parameters["session_id"].default
        assert default is None, default

    async def test_a_session_with_no_clock_answers_with_counts(self):
        """Every path used to return None, so a caller could not tell a quiet tick from a broken one."""
        await Database.init()
        try:
            out = await narrative.run_tick(SESSION)
            assert out == {"game_days": 0.0, "ambient": 0, "hooks": 0}, out
        finally:
            await Database.close()

    async def test_an_ambient_event_lands_in_its_own_campaign(self, monkeypatch):
        await Database.init()
        story_high = await Database.fetchval("SELECT COALESCE(MAX(id), 0) FROM maya_rp.story_log")
        event_high = await Database.fetchval("SELECT COALESCE(MAX(id), 0) FROM maya_rp.events")
        written = []
        try:
            await _resources(6)
            monkeypatch.setattr(narrative.random, "random", lambda: 0.0)
            monkeypatch.setattr(narrative.random, "choice", lambda seq: "economy")
            out = await narrative.run_tick(SESSION)
            assert out["ambient"] == 1, out
            row = await Database.fetchrow(
                "SELECT id, session_id, category FROM maya_rp.story_log WHERE id > $1 ORDER BY id",
                story_high)
            assert row is not None and row["session_id"] == SESSION, dict(row) if row else None
            assert row["category"] == "economy", dict(row)
            written.append(("story_log", row["id"]))
            new_events = await Database.fetch(
                "SELECT id FROM maya_rp.events WHERE id > $1", event_high)
            written.extend(("events", e["id"]) for e in new_events)
        finally:
            for table, row_id in written:
                await _drop_row(table, row_id)
            await _drop_resources()
            await Database.close()

    async def test_a_short_gap_does_not_write(self, monkeypatch):
        await Database.init()
        story_high = await Database.fetchval("SELECT COALESCE(MAX(id), 0) FROM maya_rp.story_log")
        written = []
        try:
            await _resources(0)
            monkeypatch.setattr(narrative.random, "random", lambda: 0.0)
            out = await narrative.run_tick(SESSION)
            assert out["ambient"] == 0, out
            rows = await Database.fetch(
                "SELECT id FROM maya_rp.story_log WHERE id > $1", story_high)
            written.extend(("story_log", r["id"]) for r in rows)
            assert written == [], written
        finally:
            for table, row_id in written:
                await _drop_row(table, row_id)
            await _drop_resources()
            await Database.close()


