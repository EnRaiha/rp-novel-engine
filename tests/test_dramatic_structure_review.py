#!/usr/bin/env python3
"""Review of `core/dramatic_structure.py`.

Four defects, all on the paths a live campaign runs:

1. `advance_phase` did `PHASE_ORDER.index(arc["phase"])`, so a phase the list does not hold raised
   `ValueError` out of the tick. `get_current_arc` twenty lines up resolves the *same* value to
   `setup` (`PHASES.get(arc["phase"], PHASES["setup"])`), so the module held two answers for one
   value. `advance_phase` refuses by name in the shape it already uses for a missing arc.
2. `session_start` did `PHASES[arc["phase"]]`, a KeyError for that same value, one line after
   `get_current_arc` had already resolved it into `phase_config`. It reads the resolved config now.
3. `sessions_in_phase` and `total_sessions` are nullable and the write was `sessions_in_phase+1`.
   `NULL + 1` is NULL in SQL, so one NULL row kept the counter NULL for ever: the phase could never
   advance, and the read below raised TypeError at every later session start.
4. Three `UPDATE ... WHERE id=$1` statements wrote rows read with a session filter. The table
   carries `session_id`, so they name it.

Reported, not changed: `get_current_arc` **writes**. It inserts an arc when none is active, and the
title and theme come from `random.choice`, so `cli briefing` (through
`core/master_briefing.py:26`) creates an arc and picks its theme. Adding a read-only door means
changing that caller, which is the lead's file.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import Database  # noqa: E402
from core import dramatic_structure  # noqa: E402


async def _give_session(session_id: int) -> bool:
    made = await Database.fetchval(
        "SELECT 1 FROM maya_rp.sessions WHERE id=$1", session_id) is None
    if made:
        await Database.execute(
            "INSERT INTO maya_rp.sessions (id, name) VALUES ($1, $2)",
            session_id, f"scratch-dramatic-{session_id}")
    return made


async def _give_arc(session_id: int, phase: str, sessions_in_phase=0) -> int:
    return int(await Database.fetchval(
        "INSERT INTO maya_rp.story_arcs (session_id, title, theme, central_conflict,"
        " stakes_description, phase, sessions_in_phase, total_sessions, status)"
        " VALUES ($1, 'Review Arc', 'review', 'review conflict', 'review stakes', $2, $3, 0, 'active')"
        " RETURNING id", session_id, phase, sessions_in_phase))


async def _drop(session_id: int, arc_ids: list[int], made_session: bool) -> None:
    for arc_id in arc_ids:
        await Database.execute("DELETE FROM maya_rp.story_arcs WHERE id=$1", arc_id)
    left = await Database.fetchval(
        "SELECT count(*) FROM maya_rp.story_arcs WHERE session_id=$1", session_id)
    if made_session:
        await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", session_id)
    print(f"cleanup: scratch {session_id} arcs left = {left}")
    assert left == 0, "the scratch session's arc was not removed"


class TestOneValueHasOneAnswer:
    async def test_an_unknown_phase_is_refused_by_name_not_raised(self, scratch_session):
        await Database.init()
        made_session = False
        arcs: list[int] = []
        try:
            made_session = await _give_session(scratch_session)
            arcs.append(await _give_arc(scratch_session, "not_a_phase"))
            out = await dramatic_structure.advance_phase(scratch_session)
            assert "error" in out and "not_a_phase" in out["error"], out
            phase = await Database.fetchval(
                "SELECT phase FROM maya_rp.story_arcs WHERE id=$1", arcs[0])
            assert phase == "not_a_phase", "a refusal moved the row"
        finally:
            await _drop(scratch_session, arcs, made_session)
            await Database.close()

    async def test_session_start_reads_the_phase_config_get_current_arc_resolved(
            self, scratch_session):
        """`PHASES[arc["phase"]]` raised KeyError for a phase `get_current_arc` had resolved."""
        await Database.init()
        made_session = False
        arcs: list[int] = []
        try:
            made_session = await _give_session(scratch_session)
            arcs.append(await _give_arc(scratch_session, "not_a_phase"))
            assert await dramatic_structure.session_start(scratch_session) is None
            row = await Database.fetchrow(
                "SELECT sessions_in_phase, total_sessions FROM maya_rp.story_arcs WHERE id=$1",
                arcs[0])
            assert row["sessions_in_phase"] == 1 and row["total_sessions"] == 1, row
        finally:
            await _drop(scratch_session, arcs, made_session)
            await Database.close()

    async def test_a_null_counter_advances_instead_of_staying_null(self, scratch_session):
        """`sessions_in_phase+1` on a NULL column is NULL for ever, and the read then raised."""
        await Database.init()
        made_session = False
        arcs: list[int] = []
        try:
            made_session = await _give_session(scratch_session)
            arcs.append(await _give_arc(scratch_session, "setup", sessions_in_phase=None))
            assert await dramatic_structure.session_start(scratch_session) is None
            row = await Database.fetchrow(
                "SELECT sessions_in_phase, total_sessions FROM maya_rp.story_arcs WHERE id=$1",
                arcs[0])
            assert row["sessions_in_phase"] == 1, row
            assert row["total_sessions"] == 1, row
        finally:
            await _drop(scratch_session, arcs, made_session)
            await Database.close()

    async def test_a_known_phase_advances_the_way_it_did(self, scratch_session):
        await Database.init()
        made_session = False
        arcs: list[int] = []
        try:
            made_session = await _give_session(scratch_session)
            arcs.append(await _give_arc(scratch_session, "setup"))
            out = await dramatic_structure.advance_phase(scratch_session)
            assert out == {"old_phase": "setup", "new_phase": "rising_action"}, out
            assert await Database.fetchval(
                "SELECT sessions_in_phase FROM maya_rp.story_arcs WHERE id=$1", arcs[0]) == 0
        finally:
            await _drop(scratch_session, arcs, made_session)
            await Database.close()


class TestTheWritesNameTheirSession:
    async def test_advance_phase_cannot_advance_another_campaigns_arc(
            self, scratch_session, monkeypatch):
        """The arc id is read with a session filter; this is the only door a foreign one uses."""
        await Database.init()
        other = scratch_session + 500
        made_session = False
        made_other = False
        foreign_id = None
        try:
            made_session = await _give_session(scratch_session)
            made_other = await _give_session(other)
            foreign_id = await _give_arc(other, "setup")

            async def foreign_row(*_a, **_kw):
                return {"id": foreign_id, "phase": "setup", "sessions_in_phase": 0}

            monkeypatch.setattr(dramatic_structure.Database, "fetchrow", foreign_row)
            out = await dramatic_structure.advance_phase(scratch_session)
            assert out.get("new_phase") == "rising_action", out

            phase = await Database.fetchval(
                "SELECT phase FROM maya_rp.story_arcs WHERE id=$1", foreign_id)
            assert phase == "setup", "advance_phase moved another campaign's arc"
        finally:
            if foreign_id is not None:
                await Database.execute("DELETE FROM maya_rp.story_arcs WHERE id=$1", foreign_id)
            await _drop(scratch_session, [], made_session)
            if made_other:
                await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", other)
            await Database.close()


class TestThePromptItRenders:
    async def test_the_prompt_carries_the_instruction_and_both_lists(self, scratch_session):
        await Database.init()
        made_session = False
        arcs: list[int] = []
        try:
            made_session = await _give_session(scratch_session)
            arcs.append(await _give_arc(scratch_session, "setup"))
            arc = await dramatic_structure.get_current_arc(scratch_session)
            prompt = dramatic_structure.get_prompt(arc)
            assert "[STORY ARC: Review Arc]" in prompt, prompt
            assert "INTRODUCE" in prompt, prompt
            assert "Introduce: threat, key_npc, stakes" in prompt, prompt
            assert "Avoid: climax, major_death" in prompt, prompt
        finally:
            await _drop(scratch_session, arcs, made_session)
            await Database.close()
