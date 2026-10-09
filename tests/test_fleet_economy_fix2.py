"""fleet_economy fix 2: bill real ships only, once per game day, through the guarded ledger.

Every write lands in a scratch session (900-999). Sessions 3 and 5 are not touched.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest_asyncio  # noqa: E402

from core.db import Database  # noqa: E402
from modules import fleet_economy as fe  # noqa: E402

#: Children of `sessions` this file writes, removed before the session row.
_TABLES = ("events", "ships", "resources")


async def _wipe(session_id):
    for table in _TABLES:
        await Database.execute(f"DELETE FROM maya_rp.{table} WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", session_id)


@pytest_asyncio.fixture
async def sid(scratch_session):
    """A scratch session on game day 10 with a funded treasury and no ships."""
    await Database.init()
    await _wipe(scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status, game_day) "
        "VALUES ($1, 'fleet economy fix2 scratch', 'active', 10)", scratch_session)
    await _fund(scratch_session, fuel=1000, alloys=500, credits=5000)
    try:
        yield scratch_session
    finally:
        await _wipe(scratch_session)
        await Database.close()


async def _fund(session_id, fuel, alloys, credits):
    await Database.execute("DELETE FROM maya_rp.resources WHERE session_id=$1", session_id)
    await Database.execute(
        "INSERT INTO maya_rp.resources (session_id, fuel, alloys, credits, population) "
        "VALUES ($1, $2, $3, $4, 0)", session_id, fuel, alloys, credits)


async def _ship(session_id, status, crew):
    await Database.execute(
        "INSERT INTO maya_rp.ships (session_id, name, status, crew_current) VALUES ($1, $2, $3, $4)",
        session_id, f"fix2 {status} {crew}", status, crew)


async def _treasury(session_id):
    row = await Database.fetchrow(
        "SELECT fuel, alloys, credits FROM maya_rp.resources WHERE session_id=$1", session_id)
    return row["fuel"], row["alloys"], row["credits"]


async def _events(session_id, event_type):
    return await Database.fetch(
        "SELECT title, description, tags, importance FROM maya_rp.events "
        "WHERE session_id=$1 AND event_type=$2 ORDER BY id", session_id, event_type)


class TestOnlyRealShipsAreBilled:
    async def test_a_fleet_of_hostile_hulls_burns_nothing(self, sid):
        for status in ("hostile", "hostile", "destroyed", "lost", "in_build"):
            await _ship(sid, status, 0)
        for _ in range(3):
            out = await fe.run_tick(sid)
            assert out["skipped"] == "no billed ships", out
        assert await _treasury(sid) == (1000, 500, 5000)
        assert await _events(sid, "fleet_burn") == []
        burn = await fe.calculate_daily_burn(sid)
        assert burn == {"fuel": 0, "food": 0, "alloy": 0, "credits": 0, "active_ships": 0, "crew": 0}

    async def test_a_session_with_no_ships_burns_nothing(self, sid):
        out = await fe.run_tick(sid)
        assert out["burn"]["fuel"] == 0 and out["burn"]["credits"] == 0, out
        assert await _treasury(sid) == (1000, 500, 5000)

    async def test_the_burn_counts_billed_hulls_and_their_crew_only(self, sid):
        await _ship(sid, "active", 10)
        await _ship(sid, "patrol", 20)
        await _ship(sid, "damaged", 0)
        await _ship(sid, "undercrewed", 5)
        await _ship(sid, "hostile", 99)
        await _ship(sid, "destroyed", 50)
        burn = await fe.calculate_daily_burn(sid)
        assert burn["active_ships"] == 4 and burn["crew"] == 35, burn
        assert burn["fuel"] == 4 * 10 + 50
        assert burn["credits"] == 100 + 35 * 2


class TestTheBurnIsClaimedPerGameDay:
    async def test_repeated_ticks_on_one_game_day_bill_once(self, sid):
        await _ship(sid, "active", 10)
        await _ship(sid, "active", 20)
        first = await fe.run_tick(sid)
        assert first["charged"] == {"fuel": 70, "credits": 160}, first
        assert first["fuel_remaining"] == 930 and first["credits_remaining"] == 4840
        for _ in range(3):
            again = await fe.run_tick(sid)
            assert again["skipped"] == "game day 10 already billed", again
        assert await _treasury(sid) == (930, 500, 4840)
        claims = await _events(sid, "fleet_burn")
        assert len(claims) == 1 and json.loads(claims[0]["tags"]) == ["fleet_burn", "day:10"]

    async def test_the_next_game_day_bills_again(self, sid):
        await _ship(sid, "active", 0)
        await fe.run_tick(sid)
        await Database.execute("UPDATE maya_rp.sessions SET game_day=11 WHERE id=$1", sid)
        out = await fe.run_tick(sid)
        assert out["charged"] == {"fuel": 60, "credits": 100}, out
        assert await _treasury(sid) == (1000 - 120, 500, 5000 - 200)
        assert len(await _events(sid, "fleet_burn")) == 2

    async def test_overlapping_ticks_bill_one_day(self, sid):
        await _ship(sid, "active", 10)
        results = await asyncio.gather(*[fe.apply_burn(sid) for _ in range(6)])
        billed = [r for r in results if "charged" in r]
        skipped = [r for r in results if "skipped" in r]
        assert len(billed) == 1 and len(skipped) == 5, results
        assert await _treasury(sid) == (1000 - 60, 500, 5000 - 120)
        assert len(await _events(sid, "fleet_burn")) == 1


class TestAShortTreasuryIsRecordedNotClamped:
    async def test_the_resource_it_cannot_cover_is_left_and_reported(self, sid):
        await _fund(sid, fuel=30, alloys=500, credits=5000)
        await _ship(sid, "active", 10)
        out = await fe.run_tick(sid)
        assert out["shortfall"] == {"fuel": {"due": 60, "held": 30}}, out
        assert out["charged"] == {"credits": 120}, out
        assert await _treasury(sid) == (30, 500, 4880)
        short = await _events(sid, "fleet_shortfall")
        assert len(short) == 1 and short[0]["importance"] == 3
        assert "fuel 60 (held 30)" in short[0]["description"], short[0]["description"]
        assert len(await _events(sid, "fleet_burn")) == 1

    async def test_the_unpaid_day_is_not_retried_or_reported_twice(self, sid):
        await _fund(sid, fuel=0, alloys=0, credits=0)
        await _ship(sid, "active", 0)
        await fe.run_tick(sid)
        again = await fe.run_tick(sid)
        assert again["skipped"] == "game day 10 already billed", again
        assert await _treasury(sid) == (0, 0, 0)
        assert len(await _events(sid, "fleet_shortfall")) == 1

    async def test_a_covered_burn_reports_no_shortfall(self, sid):
        await _ship(sid, "active", 0)
        out = await fe.run_tick(sid)
        assert "shortfall" not in out, out
        assert await _events(sid, "fleet_shortfall") == []


class TestTheRowsItNeedsMustExist:
    async def test_a_session_with_no_resources_row_is_refused(self, sid):
        await Database.execute("DELETE FROM maya_rp.resources WHERE session_id=$1", sid)
        await _ship(sid, "active", 0)
        out = await fe.run_tick(sid)
        assert f"No resources row for session {sid}" in out["error"], out
        assert await _events(sid, "fleet_burn") == []

    async def test_a_session_with_no_session_row_is_refused(self, sid):
        await Database.execute("DELETE FROM maya_rp.events WHERE session_id=$1", sid)
        await Database.execute("DELETE FROM maya_rp.ships WHERE session_id=$1", sid)
        await Database.execute("DELETE FROM maya_rp.resources WHERE session_id=$1", sid)
        await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", sid)
        out = await fe.run_tick(sid)
        assert f"No session row for session {sid}" in out["error"], out
