"""Narrative review: what reading `modules/narrative.py` in full turned up.

The tick defaulted to the literal session 3 and returned None on every path, ending in a print. Every
path answers with counts now, and the default is the resolver rather than a campaign.

This file drives the tick in its own scratch session, never in session 5. It has to seed a `resources`
row and walk its clock backwards to make the tick fire, and doing that to the live arc is wrong twice
over: the arc owns that row now, so the seed INSERT is refused by the unique key on `session_id`, and
the teardown that used to follow it deleted `WHERE research_points = 0 AND last_tick_at IS NOT NULL`,
which is a shape rather than an identity — it matched the arc's own row and removed it on every run.
A test may only delete what it created, by id; a row a test needs for one run belongs in a scratch
session, which is what `scratch_session` hands out.

`test_the_tick_does_not_default_to_the_frozen_campaign` reads the signature and writes nothing, so it
does not need a session at all.
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

#: The campaign the review read. Read-only assertions may name it; nothing here writes to it.
SESSION = 5


async def _seed_clock(session_id: int, age_hours: float | None) -> dict:
    """Give the scratch session a clock this test controls, and say which rows it created.

    `age_hours=None` leaves `last_tick_at` NULL, which is the quiet-session case. Returns the
    `made` dict `_drop_scratch` needs, so the teardown removes only what this call created.
    """
    made = {"session": False, "resources": False}
    if await Database.fetchval("SELECT 1 FROM maya_rp.sessions WHERE id = $1", session_id) is None:
        await Database.execute(
            "INSERT INTO maya_rp.sessions (id, name) VALUES ($1, $2)",
            session_id, f"scratch-narrative-{session_id}")
        made["session"] = True
    if await Database.fetchval("SELECT 1 FROM maya_rp.resources WHERE session_id = $1", session_id) is None:
        made["resources"] = True
    await Database.execute(
        "INSERT INTO maya_rp.resources (session_id, research_points, last_tick_at) "
        "VALUES ($1, 0, CASE WHEN $2::int IS NULL THEN NULL ELSE NOW() - make_interval(hours => $2::int) END) "
        "ON CONFLICT (session_id) DO UPDATE SET research_points = 0, last_tick_at = EXCLUDED.last_tick_at",
        session_id, age_hours)
    return made


async def _drop_scratch(session_id: int, made: dict | None) -> None:
    """Remove the rows `_seed_clock` created, by id. Never by shape, and never the live arc."""
    if not made:
        return
    if made.get("resources"):
        await Database.execute("DELETE FROM maya_rp.resources WHERE session_id = $1", session_id)
    if made.get("session"):
        await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", session_id)


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

    async def test_a_session_with_no_clock_answers_with_counts(self, scratch_session):
        """Every path used to return None, so a caller could not tell a quiet tick from a broken one."""
        await Database.init()
        made = None
        try:
            made = await _seed_clock(scratch_session, None)
            out = await narrative.run_tick(scratch_session)
            assert out == {"game_days": 0.0, "ambient": 0, "hooks": 0}, out
        finally:
            await _drop_scratch(scratch_session, made)
            await Database.close()

    async def test_an_ambient_event_lands_in_its_own_campaign(self, monkeypatch, scratch_session):
        await Database.init()
        story_high = await Database.fetchval("SELECT COALESCE(MAX(id), 0) FROM maya_rp.story_log")
        event_high = await Database.fetchval("SELECT COALESCE(MAX(id), 0) FROM maya_rp.events")
        written = []
        made = None
        try:
            made = await _seed_clock(scratch_session, 6)
            monkeypatch.setattr(narrative.random, "random", lambda: 0.0)
            monkeypatch.setattr(narrative.random, "choice", lambda seq: "economy")
            out = await narrative.run_tick(scratch_session)
            assert out["ambient"] == 1, out
            row = await Database.fetchrow(
                "SELECT id, session_id, category FROM maya_rp.story_log WHERE id > $1 ORDER BY id",
                story_high)
            assert row is not None and row["session_id"] == scratch_session, dict(row) if row else None
            assert row["category"] == "economy", dict(row)
            written.append(("story_log", row["id"]))
            new_events = await Database.fetch(
                "SELECT id FROM maya_rp.events WHERE id > $1", event_high)
            written.extend(("events", e["id"]) for e in new_events)
        finally:
            for table, row_id in written:
                await _drop_row(table, row_id)
            await _drop_scratch(scratch_session, made)
            await Database.close()

    async def test_a_short_gap_does_not_write(self, monkeypatch, scratch_session):
        await Database.init()
        story_high = await Database.fetchval("SELECT COALESCE(MAX(id), 0) FROM maya_rp.story_log")
        written = []
        made = None
        try:
            made = await _seed_clock(scratch_session, 0)
            monkeypatch.setattr(narrative.random, "random", lambda: 0.0)
            out = await narrative.run_tick(scratch_session)
            assert out["ambient"] == 0, out
            rows = await Database.fetch(
                "SELECT id FROM maya_rp.story_log WHERE id > $1", story_high)
            written.extend(("story_log", r["id"]) for r in rows)
            assert written == [], written
        finally:
            for table, row_id in written:
                await _drop_row(table, row_id)
            await _drop_scratch(scratch_session, made)
            await Database.close()
