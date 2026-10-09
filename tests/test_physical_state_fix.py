"""Real-database tests for modules/physical_state.py. Scratch session only."""
from __future__ import annotations

import pytest_asyncio

from core.config import Config
from core.db import Database
from modules import physical_state


async def _wipe(session_id: int) -> None:
    await Database.execute("DELETE FROM maya_rp.character_injuries WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.characters WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", session_id)


@pytest_asyncio.fixture
async def sid(scratch_session, monkeypatch):
    """(scratch session id, character id) on game day 10. `Config.SESSION_ID` points at the scratch id."""
    monkeypatch.setattr(Config, "SESSION_ID", scratch_session)
    await Database.init()
    await _wipe(scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status, game_day) VALUES ($1,'physical fix scratch','active',10)",
        scratch_session)
    cid = await Database.fetchval(
        "INSERT INTO maya_rp.characters (session_id, name) VALUES ($1,'Test Subject') RETURNING id",
        scratch_session)
    yield scratch_session, cid
    await _wipe(scratch_session)
    await Database.close()


async def _injury(session_id, character_id, status="active", heal_by=50, scar=False,
                  body="arm", severity="moderate") -> int:
    return await Database.fetchval(
        "INSERT INTO maya_rp.character_injuries(session_id,character_id,description,severity,body_part,"
        "cause,received_game_day,heal_by_game_day,became_scar,status) "
        "VALUES($1,$2,'a test wound',$3,$4,'combat',1,$5,$6,$7) RETURNING id",
        session_id, character_id, severity, body, heal_by, scar, status)


async def test_an_unhealed_scar_flagged_wound_is_listed_once(sid):
    session_id, cid = sid
    await _injury(session_id, cid, heal_by=50, scar=True)

    out = await physical_state.get_state(cid, session_id)

    assert out["scars"] == [], out
    assert len(out["active_injuries"]) == 1, out
    assert out["visual"] == "They bear a bandaged injury.", out


async def test_a_due_scar_shows_once_in_the_same_call(sid):
    session_id, cid = sid
    iid = await _injury(session_id, cid, heal_by=5, scar=True)

    out = await physical_state.get_state(cid, session_id)

    assert len(out["scars"]) == 1, out
    assert out["healed"] == 1, out
    assert out["visual"] == "They bear a scar on the arm.", out
    assert await Database.fetchval(
        "SELECT status FROM maya_rp.character_injuries WHERE id=$1", iid) == "scar"


async def test_a_missing_session_is_an_error_not_a_crash(sid):
    session_id, cid = sid

    out = await physical_state.apply(cid, "a cut", session_id=session_id + 1000)

    assert "not found" in out["error"], out


async def test_a_blank_description_is_refused(sid):
    session_id, cid = sid

    out = await physical_state.apply(cid, "  ", session_id=session_id)

    assert "description" in out["error"], out
    assert await Database.fetchval(
        "SELECT count(*) FROM maya_rp.character_injuries WHERE session_id=$1", session_id) == 0


async def test_a_long_body_part_is_cut_to_fifty(sid):
    session_id, cid = sid

    out = await physical_state.apply(cid, "a cut", "minor", "x" * 80, session_id=session_id)

    assert out["injury_id"], out
    stored = await Database.fetchval(
        "SELECT body_part FROM maya_rp.character_injuries WHERE id=$1", out["injury_id"])
    assert len(stored) == 50
