"""M4: the graduation marker is per session, so a campus follows its own clock.

Real database, scratch sessions only (900-999). Session A's game day sits below every live campus
marker, and the fixture asserts that floor before it writes, so a pre-fix read cannot graduate a
reference row or move its marker. The two seeded campuses differ only in the session that owns them, and
both are due on session A's clock: a read that forgets `session_id` moves session B's marker on session
A's tick.
"""
from __future__ import annotations

import pytest_asyncio

from core.db import Database
from modules import crew_system
from tests.conftest import _clear_session_rows

#: `scratch_session` is session A. Session B sits 50 ids away and stays inside 900-999.
SECOND_OFFSET = 50

#: Session A's clock, and its campus marker. Both campuses carry the same marker, so both are due on
#: session A's marker. The whole scratch clock stays below the live campus clock (2225).
DAY_A = 150
DAY_B = 90
CAMPUS_LAST = 120
CYCLE_DAYS = 30


async def _seed_campaign(session_id: int, game_day: int, name: str) -> int:
    """One scratch session with a ledger row and one campus whose marker is due on session A's clock."""
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status, game_day) VALUES ($1, $2, 'active', $3)"
        " ON CONFLICT (id) DO UPDATE SET game_day = EXCLUDED.game_day",
        session_id, name, game_day)
    await Database.execute(
        "INSERT INTO maya_rp.resources (session_id) VALUES ($1) ON CONFLICT (session_id) DO NOTHING",
        session_id)
    return await Database.fetchval(
        "INSERT INTO maya_rp.university_campuses"
        " (name, session_id, level, prestige, research_rate, graduation_cycle_days, last_graduation_day)"
        " VALUES ($1, $2, 1, 0, 1.0, $3, $4) RETURNING id",
        name, session_id, CYCLE_DAYS, CAMPUS_LAST)


async def _marker(campus_id: int):
    return await Database.fetchval(
        "SELECT last_graduation_day FROM maya_rp.university_campuses WHERE id = $1", campus_id)


async def _drop_scratch(session_id: int) -> None:
    await _clear_session_rows(session_id)
    await Database.init()
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", session_id)


@pytest_asyncio.fixture
async def two_clocks(scratch_session):
    """Session A and session B, one due campus each."""
    session_b = 900 + (scratch_session - 900 + SECOND_OFFSET) % 100
    await Database.init()
    # The pre-fix read sees every campus in `maya_rp`. This floor keeps it off the reference rows:
    # no live campus is due at the scratch marker, so that read can only graduate the two below.
    floor = await Database.fetchval(
        "SELECT min(last_graduation_day) FROM maya_rp.university_campuses"
        " WHERE session_id <> ALL($1::int[])", [scratch_session, session_b])
    assert floor is None or floor > DAY_A, (
        f"a live campus is due at day {DAY_A} (lowest marker {floor}). A pre-fix read would move a "
        "reference row: choose a scratch marker below the live campus clock.")
    await _clear_session_rows(scratch_session)
    await _clear_session_rows(session_b)
    campus_a = await _seed_campaign(scratch_session, DAY_A, "graduation scratch A")
    campus_b = await _seed_campaign(session_b, DAY_B, "graduation scratch B")
    try:
        yield scratch_session, session_b, campus_a, campus_b
    finally:
        await _drop_scratch(scratch_session)
        await _drop_scratch(session_b)


async def test_session_b_campus_does_not_graduate_on_session_a_marker(two_clocks):
    session_a, _session_b, campus_a, campus_b = two_clocks

    out = await crew_system.graduation_cycle(session_a)

    assert await _marker(campus_b) == CAMPUS_LAST, (
        "session B's campus graduated on session A's marker: the campus read or the marker write is "
        "not scoped to the session")
    assert await _marker(campus_a) == DAY_A, "session A's own campus did not graduate on its marker"
    assert out["campuses"] == 1, out
    assert out["graduated"] > 0, out
