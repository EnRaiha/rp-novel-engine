"""geopolitics fix 2: a raid is scheduled once per faction and target until it resolves, and records its territory.

Real database. Every write lands in a scratch session (900-999). Sessions 3 and 5 are not touched.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

import core.config  # noqa: E402
from core.db import Database  # noqa: E402
from modules import geopolitics as geo  # noqa: E402

#: Tables this file writes, removed before the session row.
_TABLES = ("events", "incoming_raids", "factions", "territory")


async def _wipe(session_id):
    for table in _TABLES:
        await Database.execute(f"DELETE FROM maya_rp.{table} WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", session_id)


def _faction(session_id):
    # factions.name is unique across sessions, so the id is part of the name.
    return f"T3 Raiders {session_id}"


@pytest_asyncio.fixture
async def sid(scratch_session, monkeypatch):
    """A scratch session with one hostile faction at power 9000 and one Setia territory, T3-Kappa."""
    await Database.init()
    await _wipe(scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status, game_day) "
        "VALUES ($1, 'geopolitics fix2 scratch', 'active', 10)", scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.factions (session_id, name, standing, pirate_fleet_power) "
        "VALUES ($1, $2, 'hostile', 9000)", scratch_session, _faction(scratch_session))
    await Database.execute(
        "INSERT INTO maya_rp.territory (session_id, system_name, controlling_faction) "
        "VALUES ($1, 'T3-Kappa', 'Setia Empire')", scratch_session)
    monkeypatch.setattr(geo.random, "random", lambda: 0.0)
    monkeypatch.setattr(core.config.Config, "SESSION_ID", scratch_session)
    monkeypatch.setenv("RP_SESSION", str(scratch_session))
    try:
        yield scratch_session
    finally:
        await _wipe(scratch_session)
        await Database.close()


async def _tid(session_id):
    return await Database.fetchval(
        "SELECT id FROM maya_rp.territory WHERE session_id=$1 AND system_name='T3-Kappa'", session_id)


async def _raids(session_id):
    return await Database.fetch(
        "SELECT target_system, target_territory_id, enemy_power, ticks_remaining, detected "
        "FROM maya_rp.incoming_raids WHERE session_id=$1 ORDER BY id", session_id)


async def _pending_raid(session_id, responded=False, ticks=5):
    await Database.execute(
        "INSERT INTO maya_rp.incoming_raids (session_id, faction_name, target_system, enemy_power, "
        "ticks_remaining, detected, player_responded) VALUES ($1, $2, 'T3-Kappa', 7000, $3, false, $4)",
        session_id, _faction(session_id), ticks, responded)


async def test_a_raid_records_the_territory_it_targets(sid):
    await geo.run_tick(sid)
    raids = await _raids(sid)
    assert len(raids) == 1, raids
    raid = raids[0]
    assert raid["target_system"] == "T3-Kappa"
    assert raid["target_territory_id"] == await _tid(sid)
    assert raid["detected"] is False
    assert 5400 <= raid["enemy_power"] <= 9000, raid["enemy_power"]
    assert 3 <= raid["ticks_remaining"] <= 10, raid["ticks_remaining"]


async def test_repeated_ticks_keep_one_pending_raid(sid):
    first = await geo.run_tick(sid)
    second = await geo.run_tick(sid)
    third = await geo.run_tick(sid)
    assert first["events_generated"] == 1
    assert second["events_generated"] == 0
    assert third["events_generated"] == 0
    assert len(await _raids(sid)) == 1


async def test_a_pending_raid_blocks_a_duplicate(sid):
    await _pending_raid(sid)
    await geo.run_tick(sid)
    assert len(await _raids(sid)) == 1


@pytest.mark.parametrize("responded, ticks", [(True, 5), (False, 0)])
async def test_a_resolved_raid_does_not_block(sid, responded, ticks):
    await _pending_raid(sid, responded=responded, ticks=ticks)
    await geo.run_tick(sid)
    assert len(await _raids(sid)) == 2


async def test_power_at_5000_schedules_nothing(sid):
    await Database.execute(
        "UPDATE maya_rp.factions SET pirate_fleet_power=5000 WHERE session_id=$1", sid)
    await geo.run_tick(sid)
    assert await _raids(sid) == []


async def test_no_setia_territory_schedules_nothing(sid):
    await Database.execute("DELETE FROM maya_rp.territory WHERE session_id=$1", sid)
    await geo.run_tick(sid)
    assert await _raids(sid) == []


def test_the_module_never_reads_config_for_a_session():
    assert "Config.SESSION_ID" not in pathlib.Path(geo.__file__).read_text()
