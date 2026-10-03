#!/usr/bin/env python3
"""Review of `core/scene_stack.py`.

Three defects, all reachable through the two functions that have no caller yet — which is why
nothing noticed them.

1. `push` read the game day as `SELECT COALESCE(game_day,1) ... WHERE id=$1`. The COALESCE only
   ever answers for a session row that exists: an unknown session returns no row at all, so the day
   arrived as None and the insert stored a NULL `pushed_at_game_day`. `pop` then computed
   `gd - None` and raised TypeError on the row it had just read. Same shape as `world_react`'s
   `gd + delay` and `pacing`'s COALESCE-inside-the-SELECT.
2. `pop` resumed its row with `WHERE id=$1` alone, and the table carries a session.
3. `pop` computed `gd = ... or 0` off another COALESCE-inside-the-SELECT, so a missing session read
   as game day zero and a scene was dated in the negative and reported as fresh.

Every test writes to a per-process scratch session and removes the ids it created: for the three
scoped tables the difference between the ids present before and after the test is what gets deleted.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from core.db import Database  # noqa: E402
from core import scene_stack  # noqa: E402


async def _ids(session_id: int) -> set[int]:
    rows = await Database.fetch(
        "SELECT id FROM maya_rp.scene_stack WHERE session_id=$1", session_id)
    return {int(r["id"]) for r in rows}


async def _give_session(session_id: int, game_day: int = 40) -> bool:
    made = await Database.fetchval(
        "SELECT 1 FROM maya_rp.sessions WHERE id=$1", session_id) is None
    if made:
        await Database.execute(
            "INSERT INTO maya_rp.sessions (id, name, game_day) VALUES ($1, $2, $3)",
            session_id, f"scratch-scene-stack-{session_id}", game_day)
    return made


async def _drop(session_id: int, before: set[int], made_session: bool) -> None:
    created = (await _ids(session_id)) - before
    if created:
        await Database.execute(
            "DELETE FROM maya_rp.scene_stack WHERE id = ANY($1::int[])", sorted(created))
    if made_session:
        await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", session_id)


class TestPushRefusesASceneItCannotDate:
    async def test_push_refuses_a_session_with_no_row(self, scratch_session):
        """A NULL `pushed_at_game_day` is what made the matching `pop` raise."""
        await Database.init()
        before: set[int] = set()
        made_session = False
        try:
            before = await _ids(scratch_session)
            with pytest.raises(ValueError) as exc:
                await scene_stack.push("interrupt", {"what_was_happening": "review"}, scratch_session)
            assert str(scratch_session) in str(exc.value), exc.value
            assert await _ids(scratch_session) == before, "a row was written with no game day"
        finally:
            await _drop(scratch_session, before, made_session)
            await Database.close()

    async def test_push_dates_the_row_it_writes(self, scratch_session):
        await Database.init()
        before: set[int] = set()
        made_session = False
        try:
            before = await _ids(scratch_session)
            made_session = await _give_session(scratch_session, game_day=40)
            await scene_stack.push("interrupt", {"what_was_happening": "review push"}, scratch_session)
            row = await Database.fetchrow(
                "SELECT pushed_at_game_day, status FROM maya_rp.scene_stack"
                " WHERE session_id=$1 AND status='suspended' ORDER BY id DESC LIMIT 1",
                scratch_session)
            assert row is not None and row["pushed_at_game_day"] == 40, row
        finally:
            await _drop(scratch_session, before, made_session)
            await Database.close()


class TestPopAnswersInsteadOfRaising:
    async def test_a_null_pushed_at_reports_an_unknown_age(self, scratch_session):
        """Rows written before the date was required carry NULL, and `gd - None` raised."""
        await Database.init()
        before: set[int] = set()
        made_session = False
        try:
            before = await _ids(scratch_session)
            made_session = await _give_session(scratch_session, game_day=40)
            await Database.execute(
                "INSERT INTO maya_rp.scene_stack"
                " (session_id, interrupt_type, context_jsonb, pushed_at_game_day, status)"
                " VALUES ($1, 'legacy', '{\"what\": \"old row\"}', NULL, 'suspended')",
                scratch_session)
            out = await scene_stack.pop(scratch_session)
            assert out is not None and out["games_ago"] is None, out
            assert out["stale"] is False, out
            assert out["context"] == {"what": "old row"}, out
        finally:
            await _drop(scratch_session, before, made_session)
            await Database.close()

    async def test_an_age_is_counted_from_the_game_day(self, scratch_session):
        await Database.init()
        before: set[int] = set()
        made_session = False
        try:
            before = await _ids(scratch_session)
            made_session = await _give_session(scratch_session, game_day=40)
            await Database.execute(
                "INSERT INTO maya_rp.scene_stack"
                " (session_id, interrupt_type, context_jsonb, pushed_at_game_day, status)"
                " VALUES ($1, 'interrupt', '{\"what\": \"recent\"}', 35, 'suspended')",
                scratch_session)
            out = await scene_stack.pop(scratch_session)
            assert out["games_ago"] == 5 and out["stale"] is False, out
        finally:
            await _drop(scratch_session, before, made_session)
            await Database.close()

    async def test_pop_cannot_resume_another_campaigns_row(self, scratch_session, monkeypatch):
        """`pop` found its row by session and then resumed it by id alone.

        The scoped SELECT is what stops a foreign id arriving, so the test hands `pop` one directly
        through the only door it uses, and then reads the other campaign's row back from disk.
        """
        await Database.init()
        other = scratch_session + 500
        before: set[int] = set()
        made_session = False
        made_other_session = False
        foreign_id = None
        try:
            before = await _ids(scratch_session)
            made_session = await _give_session(scratch_session, game_day=40)
            made_other_session = await _give_session(other, game_day=50)
            foreign_id = await Database.fetchval(
                "INSERT INTO maya_rp.scene_stack"
                " (session_id, interrupt_type, context_jsonb, pushed_at_game_day, status)"
                " VALUES ($1, 'foreign', '{\"what\": \"other campaign\"}', 7, 'suspended')"
                " RETURNING id", other)

            async def foreign_row(*_a, **_kw):
                return {"id": foreign_id, "interrupt_type": "foreign",
                        "context_jsonb": '{"what": "other campaign"}', "pushed_at_game_day": 7}

            monkeypatch.setattr(scene_stack.Database, "fetchrow", foreign_row)
            out = await scene_stack.pop(scratch_session)
            assert out is not None and out["id"] == foreign_id, out

            status = await Database.fetchval(
                "SELECT status FROM maya_rp.scene_stack WHERE id=$1", foreign_id)
            assert status == "suspended", (
                "pop resumed a row belonging to another campaign through a bare id")
        finally:
            if foreign_id is not None:
                await Database.execute(
                    "DELETE FROM maya_rp.scene_stack WHERE id=$1", foreign_id)
            await _drop(scratch_session, before, made_session)
            if made_other_session:
                await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", other)
            await Database.close()


class TestTheSummaryItDoesUse:
    async def test_the_summary_reports_every_suspended_row_and_parses_its_context(
            self, scratch_session):
        """`get_stack_summary` is the only function here with a caller. jsonb arrives as text."""
        await Database.init()
        before: set[int] = set()
        made_session = False
        try:
            before = await _ids(scratch_session)
            made_session = await _give_session(scratch_session)
            for what, day in (("first", 10), ("second", 11)):
                await Database.execute(
                    "INSERT INTO maya_rp.scene_stack"
                    " (session_id, interrupt_type, context_jsonb, pushed_at_game_day, status)"
                    " VALUES ($1, 'interrupt', $2, $3, 'suspended')",
                    scratch_session, '{"what": "%s"}' % what, day)
            await Database.execute(
                "INSERT INTO maya_rp.scene_stack"
                " (session_id, interrupt_type, context_jsonb, pushed_at_game_day, status)"
                " VALUES ($1, 'interrupt', '{\"what\": \"done\"}', 12, 'resumed')", scratch_session)
            rows = await scene_stack.get_stack_summary(scratch_session)
            assert [r["context"]["what"] for r in rows] == ["first", "second"], rows
            assert [r["pushed_at_game_day"] for r in rows] == [10, 11], rows
        finally:
            await _drop(scratch_session, before, made_session)
            await Database.close()
