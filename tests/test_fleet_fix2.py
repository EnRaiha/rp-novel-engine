"""fleet fix 2: assign_ship fills the first free slot, and the module resolves its session per call.

Every write lands in a scratch session (900-999). Sessions 3 and 5 are not touched.
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
from modules import fleet  # noqa: E402


async def _wipe(session_id):
    await Database.execute(
        "DELETE FROM maya_rp.fleet_members WHERE fleet_id IN "
        "(SELECT id FROM maya_rp.fleets WHERE session_id=$1)", session_id)
    await Database.execute("DELETE FROM maya_rp.fleets WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.ships WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", session_id)


@pytest_asyncio.fixture
async def sid(scratch_session, monkeypatch):
    """A scratch session with no fleets and no ships. The process default resolves to it."""
    await Database.init()
    await _wipe(scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status, game_day) "
        "VALUES ($1, 'fleet fix2 scratch', 'active', 10)", scratch_session)
    monkeypatch.setattr(core.config.Config, "SESSION_ID", scratch_session)
    monkeypatch.setenv("RP_SESSION", str(scratch_session))
    try:
        yield scratch_session
    finally:
        await _wipe(scratch_session)
        await Database.close()


async def _ship(session_id, name):
    return await Database.fetchval(
        "INSERT INTO maya_rp.ships (session_id, name, status) VALUES ($1,$2,'active') RETURNING id",
        session_id, name)


async def _positions(session_id, fleet_name):
    rows = await Database.fetch(
        "SELECT fm.position FROM maya_rp.fleet_members fm "
        "JOIN maya_rp.fleets f ON f.id=fm.fleet_id "
        "WHERE f.session_id=$1 AND f.name=$2 ORDER BY fm.position", session_id, fleet_name)
    return [r["position"] for r in rows]


async def test_a_default_assign_takes_slot_1(sid):
    await fleet.create_fleet("T3 Fleet A", "wall", sid)
    await _ship(sid, "T3 Ship 1")
    out = await fleet.assign_ship("T3 Ship 1", "T3 Fleet A", session_id=sid)
    assert out == {"assigned": True, "ship": "T3 Ship 1", "fleet": "T3 Fleet A", "position": 1}
    assert await _positions(sid, "T3 Fleet A") == [1]


async def test_a_second_ship_takes_slot_2(sid):
    await fleet.create_fleet("T3 Fleet A", "wall", sid)
    await _ship(sid, "T3 Ship 1")
    await _ship(sid, "T3 Ship 2")
    await fleet.assign_ship("T3 Ship 1", "T3 Fleet A", session_id=sid)
    out = await fleet.assign_ship("T3 Ship 2", "T3 Fleet A", session_id=sid)
    assert out["position"] == 2, out
    assert await _positions(sid, "T3 Fleet A") == [1, 2]


async def test_zero_from_the_cli_means_no_position(sid):
    await fleet.create_fleet("T3 Fleet A", "wall", sid)
    await _ship(sid, "T3 Ship 1")
    out = await fleet.assign_ship("T3 Ship 1", "T3 Fleet A", position=0, session_id=sid)
    assert out["position"] == 1, out
    assert await _positions(sid, "T3 Fleet A") == [1]


@pytest.mark.parametrize("bad", [11, -1, 2.5])
async def test_a_position_outside_1_to_10_is_refused(sid, bad):
    await fleet.create_fleet("T3 Fleet A", "wall", sid)
    await _ship(sid, "T3 Ship 1")
    out = await fleet.assign_ship("T3 Ship 1", "T3 Fleet A", position=bad, session_id=sid)
    assert "position must be an integer from 1 to 10" in out["error"], out
    assert await _positions(sid, "T3 Fleet A") == []


async def test_an_explicit_position_is_kept(sid):
    await fleet.create_fleet("T3 Fleet A", "wall", sid)
    await _ship(sid, "T3 Ship 1")
    out = await fleet.assign_ship("T3 Ship 1", "T3 Fleet A", position=7, session_id=sid)
    assert out["position"] == 7, out
    assert await _positions(sid, "T3 Fleet A") == [7]


async def test_a_full_fleet_is_refused(sid):
    await fleet.create_fleet("T3 Fleet A", "wall", sid)
    # Zero-padded: the ship lookup is a LIKE, so "T3 Ship 1" would also match "T3 Ship 10".
    for i in range(1, 12):
        await _ship(sid, f"T3 Ship {i:02d}")
    for i in range(1, 11):
        out = await fleet.assign_ship(f"T3 Ship {i:02d}", "T3 Fleet A", session_id=sid)
        assert out.get("position") == i, out
    out = await fleet.assign_ship("T3 Ship 11", "T3 Fleet A", session_id=sid)
    assert "is full" in out["error"], out
    assert await _positions(sid, "T3 Fleet A") == list(range(1, 11))


async def test_assigning_twice_keeps_one_row(sid):
    await fleet.create_fleet("T3 Fleet A", "wall", sid)
    await _ship(sid, "T3 Ship 1")
    await fleet.assign_ship("T3 Ship 1", "T3 Fleet A", session_id=sid)
    await fleet.assign_ship("T3 Ship 1", "T3 Fleet A", session_id=sid)
    assert await _positions(sid, "T3 Fleet A") == [1]


def test_the_module_never_reads_config_for_a_session():
    source = pathlib.Path(fleet.__file__).read_text()
    assert "Config.SESSION_ID" not in source, source


async def test_a_missing_session_resolves_at_call_time(sid, monkeypatch):
    """The import-time default points at the live arc. RP_SESSION names the scratch session."""
    monkeypatch.setattr(core.config.Config, "SESSION_ID", 5)
    monkeypatch.setenv("RP_SESSION", str(sid))
    await fleet.create_fleet("T3 Fleet A", "wall", sid)
    listed = await fleet.list_fleets()
    assert [f["name"] for f in listed] == ["T3 Fleet A"], listed
