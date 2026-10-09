"""locations: a character moves before its presence is logged, and long location names fit the
`character_presence_log.new_presence` (varchar 20) and `player_context.current_focus` (varchar 50) columns.

Every test runs on a scratch session with its own `sessions`, `characters` and `player_context` rows.
`Config.SESSION_ID` and `RP_SESSION` point at the scratch id so no default can reach session 3 or 5.
"""
from __future__ import annotations

import pathlib
import sys

import pytest
import pytest_asyncio

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import core.config  # noqa: E402
from core.db import Database  # noqa: E402
from modules import locations  # noqa: E402

#: A character id that exists in no session.
GHOST_ID = 2000000000

LONG_NAMES = ["rumah_agung_sayap_timur", "pelabuhan_tujuh_belas", "koloni_sembilan_belas"]


async def _clear(sid: int) -> None:
    ids = [r["id"] for r in await Database.fetch(
        "SELECT id FROM maya_rp.characters WHERE session_id = $1", sid)]
    await Database.execute(
        "DELETE FROM maya_rp.character_presence_log WHERE character_id = ANY($1::int[])",
        ids + [GHOST_ID])
    await Database.execute("DELETE FROM maya_rp.player_context WHERE session_id = $1", sid)
    await Database.execute("DELETE FROM maya_rp.characters WHERE session_id = $1", sid)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", sid)


@pytest_asyncio.fixture
async def sid(scratch_session, monkeypatch):
    monkeypatch.setattr(core.config.Config, "SESSION_ID", scratch_session)
    monkeypatch.setenv("RP_SESSION", str(scratch_session))
    await Database.init()
    await _clear(scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status, game_day) "
        "VALUES ($1, 'locations fix2 scratch', 'active', 10)", scratch_session)
    yield scratch_session
    await _clear(scratch_session)
    await Database.close()


async def _char(sid: int) -> int:
    return await Database.fetchval(
        "INSERT INTO maya_rp.characters (session_id, name) VALUES ($1, 'T3 Walker') RETURNING id", sid)


async def _log(cid: int) -> list[str]:
    rows = await Database.fetch(
        "SELECT new_presence FROM maya_rp.character_presence_log WHERE character_id = $1 ORDER BY id", cid)
    return [r["new_presence"] for r in rows]


async def _scene_location(cid: int):
    return await Database.fetchval("SELECT scene_location FROM maya_rp.characters WHERE id = $1", cid)


@pytest.mark.parametrize("name", LONG_NAMES)
async def test_a_long_catalog_name_moves_the_character(sid, name):
    """The log column holds 20 characters. The move keeps the full name and the log keeps a prefix."""
    cid = await _char(sid)
    await locations.set_character_presence(cid, name, sid)
    assert await _scene_location(cid) == name
    assert await _log(cid) == [name[:20]]


async def test_a_short_name_is_logged_whole(sid):
    cid = await _char(sid)
    await locations.set_character_presence(cid, "medbay", sid)
    assert await _scene_location(cid) == "medbay"
    assert await _log(cid) == ["medbay"]


async def test_a_character_from_another_session_leaves_no_log_row(sid):
    await locations.set_character_presence(GHOST_ID, "medbay", sid)
    assert await _log(GHOST_ID) == []


async def test_the_player_focus_fits_its_column(sid):
    await locations.set_player_location(sid, "pelabuhan_tujuh_belas", "Imperial Dreadnought Magnificent")
    row = await Database.fetchrow(
        "SELECT location, current_focus FROM maya_rp.player_context WHERE session_id = $1", sid)
    assert row["location"] == "pelabuhan_tujuh_belas"
    assert len(row["current_focus"]) == 50, row["current_focus"]


async def test_a_short_focus_is_unchanged(sid):
    await locations.set_player_location(sid, "bridge", "Flagship")
    focus = await Database.fetchval(
        "SELECT current_focus FROM maya_rp.player_context WHERE session_id = $1", sid)
    assert focus == "Location: bridge on Flagship"


def test_the_module_never_reads_config_for_a_session():
    source = pathlib.Path(locations.__file__).read_text()
    assert "Config.SESSION_ID" not in source
