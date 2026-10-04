#!/usr/bin/env python3
"""The marks the story says these people carry, in the table that has never held a row.

`character_injuries` has a full schema and `modules/physical_state.py` heals it on the tick. It
held zero rows before this seed. What matters most here is that a scar is written as a scar and
not as an active wound, because the healer would then take it away.
"""
from __future__ import annotations

import pytest_asyncio

from core.db import Database
from modules import physical_state
from scripts.seed_character_injuries import MARKS, seed


async def _ensure_session(session: int, name: str = "Injury seed") -> None:
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1, $2, 'active')"
        " ON CONFLICT (id) DO NOTHING",
        session, name)


@pytest_asyncio.fixture
async def ward(scratch_session):
    """A session with a row and the two people the story names."""
    await Database.init()
    await _ensure_session(scratch_session)
    for name in ("Ruslan Bakar", "Ngesan Dorai"):
        await Database.execute(
            "INSERT INTO maya_rp.characters (session_id, name, status) VALUES ($1, $2, 'active')",
            scratch_session, name)
    await Database.execute(
        "DELETE FROM maya_rp.character_injuries WHERE session_id=$1", scratch_session)
    yield scratch_session
    await Database.execute("DELETE FROM maya_rp.character_injuries WHERE session_id=$1", scratch_session)
    await Database.execute("DELETE FROM maya_rp.characters WHERE session_id=$1", scratch_session)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", scratch_session)


async def test_a_dry_run_writes_nothing(ward):
    result = await seed(ward, write=False)

    assert sorted(result["created"]) == ["Ngesan Dorai", "Ruslan Bakar"]
    assert await Database.fetchval(
        "SELECT count(*) FROM maya_rp.character_injuries WHERE session_id=$1", ward) == 0


async def test_it_records_both_marks(ward):
    result = await seed(ward, write=True)

    assert sorted(result["created"]) == ["Ngesan Dorai", "Ruslan Bakar"]
    rows = await Database.fetch(
        "SELECT description, body_part, cause FROM maya_rp.character_injuries WHERE session_id=$1",
        ward)
    parts = {r["body_part"] for r in rows}
    assert parts == {"hands", "nose"}


async def test_a_mark_from_before_the_campaign_is_a_scar_not_a_wound(ward):
    """This is the assertion that matters. `run_tick` heals rows where `status='active'` and
    `heal_by_game_day <= game day`. A scar written as active would be healed away on the next
    tick, and the mark the prose gave a person would quietly vanish."""
    await seed(ward, write=True)

    rows = await Database.fetch(
        "SELECT status, became_scar, received_game_day, heal_by_game_day"
        " FROM maya_rp.character_injuries WHERE session_id=$1", ward)

    assert rows, "the seed recorded nothing"
    for row in rows:
        assert row["status"] == "scar", "a mark from before the story is not an open wound"
        assert row["became_scar"] is True
        assert row["received_game_day"] == 0, "it did not happen on a day this engine counts"


async def test_the_tick_does_not_take_the_scars_away(ward):
    """The integration that would have failed silently: seed, tick, and the mark is gone."""
    await seed(ward, write=True)

    tick = await physical_state.run_tick(session_id=ward)

    assert tick["processed"] == 0, "the healer found an open wound where there is a scar"
    assert await Database.fetchval(
        "SELECT count(*) FROM maya_rp.character_injuries WHERE session_id=$1 AND status='scar'",
        ward) == 2


async def test_get_state_shows_the_mark_to_the_gm(ward):
    await seed(ward, write=True)
    who = await Database.fetchval(
        "SELECT id FROM maya_rp.characters WHERE session_id=$1 AND name='Ruslan Bakar'", ward)

    state = await physical_state.get_state(who, session_id=ward)

    assert state["scars"] == [{"description": "Burn scars across both hands", "body_part": "hands"}]
    assert "hands" in state["visual"], state["visual"]


async def test_running_it_twice_leaves_the_records_alone(ward):
    await seed(ward, write=True)
    await Database.execute(
        "UPDATE maya_rp.character_injuries SET cause='changed by the campaign' WHERE session_id=$1",
        ward)

    second = await seed(ward, write=True)

    assert second["created"] == []
    assert sorted(second["kept"]) == ["Ngesan Dorai", "Ruslan Bakar"]
    assert await Database.fetchval(
        "SELECT count(*) FROM maya_rp.character_injuries WHERE session_id=$1 AND cause='furnace'",
        ward) == 0, "the re-run overwrote what the campaign had changed"


async def test_a_person_not_in_the_session_is_skipped(ward):
    await Database.execute("DELETE FROM maya_rp.characters WHERE session_id=$1 AND name='Ngesan Dorai'", ward)

    result = await seed(ward, write=True)

    assert result["no_character"] == ["Ngesan Dorai"]
    assert result["created"] == ["Ruslan Bakar"]


def test_every_mark_carries_its_source():
    for name, desc, severity, body, cause, source in MARKS:
        assert name and desc and body and cause
        assert severity in ("minor", "moderate", "severe", "permanent")
        assert len(source) > 60, f"{name} has no usable source sentence"
        assert "novel" in source or "turn" in source, f"{name}'s source does not say where it came from"
