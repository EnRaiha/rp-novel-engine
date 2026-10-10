"""M2: the crew producer reads the academy campus of the calling campaign.

Real database, scratch sessions only (900-999). Session A and session B own one academy campus each,
sized so their outputs differ: 32 crew per tick for A and 12 for B. A read that forgets `session_id`
returns the sum of every campus in `maya_rp`, so every assertion below fails on the pre-fix tree.
Session C owns a ledger row and no campus: the reference campaign's campuses must not fill it.

The credit is one session-scoped UPDATE. Each test reads the other campaigns' pools as well, so a
production that lands in the wrong ledger is caught by the number, not only by the source list.
"""
from __future__ import annotations

import pytest_asyncio

from core.db import Database
from modules import crew_system
from tests.conftest import _clear_session_rows

#: `scratch_session` is session A. B sits 50 ids away, C sits 70 away, and all three stay inside 900-999.
SECOND_OFFSET = 50
THIRD_OFFSET = 70

#: Campus size and the output it must produce. `_academy_output` pays 8% of `max_students` times the
#: prestige bonus, so 200/100 gives 32 and 100/50 gives 12. The two numbers differ, which is what makes
#: a cross-campaign read visible in the assertion rather than in a comment.
BIG_STUDENTS, BIG_PRESTIGE, BIG_OUTPUT = 200, 100, 32
SMALL_STUDENTS, SMALL_PRESTIGE, SMALL_OUTPUT = 100, 50, 12

#: One game day per scratch campaign. `produce_crew` stamps the day it reads on the production log.
DAY_A = 150
DAY_B = 90
DAY_C = 60


async def _seed_campaign(session_id: int, name: str, game_day: int) -> None:
    """A scratch session row and its ledger row. `resources.crew_pool` defaults to 0."""
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status, game_day) VALUES ($1, $2, 'active', $3)"
        " ON CONFLICT (id) DO UPDATE SET game_day = EXCLUDED.game_day",
        session_id, name, game_day)
    await Database.execute(
        "INSERT INTO maya_rp.resources (session_id) VALUES ($1) ON CONFLICT (session_id) DO NOTHING",
        session_id)


async def _seed_campus(session_id: int, name: str, students: int, prestige: int) -> int:
    """One academy campus owned by `session_id`. The table carries no foreign key to `sessions`."""
    return await Database.fetchval(
        "INSERT INTO maya_rp.academy_campuses (name, session_id, max_students, prestige, level)"
        " VALUES ($1, $2, $3, $4, 1) RETURNING id",
        name, session_id, students, prestige)


async def _pool(session_id: int) -> int:
    return await Database.fetchval(
        "SELECT crew_pool FROM maya_rp.resources WHERE session_id = $1", session_id) or 0


async def _drop_scratch(session_id: int) -> None:
    await _clear_session_rows(session_id)
    await Database.init()
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", session_id)


@pytest_asyncio.fixture
async def two_academies(scratch_session):
    """Sessions A, B and C: one academy campus for A and B, none for C."""
    session_b = 900 + (scratch_session - 900 + SECOND_OFFSET) % 100
    session_c = 900 + (scratch_session - 900 + THIRD_OFFSET) % 100
    await Database.init()
    for session_id in (scratch_session, session_b, session_c):
        await _clear_session_rows(session_id)
    await _seed_campaign(scratch_session, "crew campus A", DAY_A)
    await _seed_campaign(session_b, "crew campus B", DAY_B)
    await _seed_campaign(session_c, "crew session C", DAY_C)
    campus_a = await _seed_campus(scratch_session, "crew campus A", BIG_STUDENTS, BIG_PRESTIGE)
    campus_b = await _seed_campus(session_b, "crew campus B", SMALL_STUDENTS, SMALL_PRESTIGE)
    owned = await Database.fetch(
        "SELECT id, session_id FROM maya_rp.academy_campuses WHERE id = ANY($1::int[])",
        [campus_a, campus_b])
    # The seed owns the leak claim: a campus row that landed in another session measures nothing.
    assert {r["id"]: r["session_id"] for r in owned} == {campus_a: scratch_session, campus_b: session_b}, (
        "a seeded campus landed in another session, so this test measures the wrong row")
    try:
        yield scratch_session, session_b, session_c, campus_a, campus_b
    finally:
        for session_id in (scratch_session, session_b, session_c):
            await _drop_scratch(session_id)


async def test_a_campaign_counts_only_its_own_academy_campus(two_academies):
    session_a, session_b, _session_c, _campus_a, _campus_b = two_academies

    out_a = await crew_system.produce_crew(session_a)

    assert out_a["produced"] == BIG_OUTPUT, (
        f"session A produced {out_a['produced']} from {out_a['sources']}: the academy read is not "
        f"scoped to the calling campaign")
    assert out_a["sources"] == [("academy:crew campus A", BIG_OUTPUT)], out_a
    assert await _pool(session_a) == BIG_OUTPUT
    assert await _pool(session_b) == 0, "session A's production reached session B's ledger"

    out_b = await crew_system.produce_crew(session_b)

    assert out_b["produced"] == SMALL_OUTPUT, (
        f"session B produced {out_b['produced']} from {out_b['sources']}: the academy read is not "
        f"scoped to the calling campaign")
    assert out_b["sources"] == [("academy:crew campus B", SMALL_OUTPUT)], out_b
    assert await _pool(session_b) == SMALL_OUTPUT
    assert await _pool(session_a) == BIG_OUTPUT, "session B's production reached session A's ledger"


async def test_a_campaign_with_no_academy_produces_nothing_from_another(two_academies):
    _session_a, _session_b, session_c, _campus_a, _campus_b = two_academies

    out = await crew_system.produce_crew(session_c)

    assert out["produced"] == 0, (
        f"a campaign with no academy campus produced {out['produced']} from {out['sources']}")
    assert out["sources"] == [], out
    assert await _pool(session_c) == 0


async def test_the_backfill_rate_counts_only_the_calling_campaigns_campus(two_academies):
    """`backfill_history` reads the academy campus a second time, for its daily rate."""
    session_a, session_b, session_c, _campus_a, _campus_b = two_academies

    out_a = await crew_system.backfill_history(session_a, start_day=26, end_day=126)
    out_b = await crew_system.backfill_history(session_b, start_day=26, end_day=126)
    out_c = await crew_system.backfill_history(session_c, start_day=26, end_day=126)

    assert out_a["daily_rate"] == BIG_OUTPUT, out_a
    assert out_b["daily_rate"] == SMALL_OUTPUT, out_b
    assert out_c["daily_rate"] == 0, out_c
