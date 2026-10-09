"""population_sentiment fix: refresh keeps shifts within a capped step, revolt risk reads as a percent,
shift and the faction filter are exact, and the conflict index has a migration.

Every write lands in a scratch session (900-999). Sessions 3 and 5 are never written.
Neutral drivers (morale 50, tax 0.05, crisis 0, performance 50, no governor) give the targets
approval 55, fear 10, trust 45, sentiment 26.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest_asyncio  # noqa: E402

from core.config import Config  # noqa: E402
from core.db import Database  # noqa: E402
from modules import population_sentiment as ps  # noqa: E402

MIGRATION = ROOT / "migrations" / "139_population_sentiment_unique.sql"


async def _wipe(session_id):
    await Database.execute("DELETE FROM maya_rp.population_sentiment WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.territory WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", session_id)


@pytest_asyncio.fixture
async def sid(scratch_session, monkeypatch):
    """A scratch session row. `Config.SESSION_ID` points at it, so no default can reach session 3 or 5."""
    await Database.init()
    await _wipe(scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status, game_day) "
        "VALUES ($1, 'sentiment fix scratch', 'active', 10)", scratch_session)
    monkeypatch.setattr(Config, "SESSION_ID", scratch_session)
    try:
        yield scratch_session
    finally:
        await _wipe(scratch_session)
        await Database.close()


async def _territory(sid, name="fix sentiment system", morale=50, tax=0.05, crisis=0,
                     performance=50, revolt=0):
    # The id is taken well above max(id): a concurrent run can insert into this table between the
    # subquery and the insert.
    # title_performance is set explicitly: its column default is 0, which is not the 50 the driver
    # formula falls back to when the column is NULL.
    return await Database.fetchval(
        "INSERT INTO maya_rp.territory (id, session_id, system_name, controlling_faction, morale, "
        "tax_rate, crisis_level, title_performance, slave_revolt_risk) "
        "VALUES ((SELECT COALESCE(MAX(id), 0) + 500000 FROM maya_rp.territory), $1, $2, 'Iron Concord', "
        "$3, $4, $5, $6, $7) RETURNING id",
        sid, name, morale, tax, crisis, performance, revolt)


async def _sentiment(sid, territory_id, faction="Iron Concord", sentiment=5):
    return await Database.fetchval(
        "INSERT INTO maya_rp.population_sentiment "
        "(session_id, territory_id, faction_name, sentiment, approval, fear, trust, bias) "
        "VALUES ($1, $2, $3, $4, 55, 10, 45, 0) RETURNING id",
        sid, territory_id, faction, sentiment)


async def _row(row_id):
    return await Database.fetchrow(
        "SELECT sentiment, approval, fear, trust, last_shift FROM maya_rp.population_sentiment WHERE id=$1",
        row_id)


class TestTheConflictIndex:
    def test_the_migration_names_the_conflict_columns(self):
        text = MIGRATION.read_text()
        assert "CREATE UNIQUE INDEX IF NOT EXISTS pop_sentiment_session_territory_faction_key" in text
        assert "(session_id, territory_id, faction_name)" in text

    async def test_the_live_index_matches_the_migration(self, sid):
        defs = [r["indexdef"] for r in await Database.fetch(
            "SELECT indexdef FROM pg_indexes WHERE schemaname='maya_rp' AND tablename='population_sentiment'")]
        assert any("UNIQUE" in d and "(session_id, territory_id, faction_name)" in d for d in defs), defs


class TestRefreshMovesTowardTheDrivers:
    async def test_revolt_risk_is_read_as_a_percent(self, sid):
        tid = await _territory(sid, revolt=50)
        row_id = await _sentiment(sid, tid)
        await ps.refresh(sid, tid)
        row = await _row(row_id)
        # fear target 10 + 0.5 * 10 = 15, move round(5 * 0.25) = 1
        assert row["fear"] == 11, dict(row)
        # sentiment target round(55 * 0.55 - 15 * 0.45) = 24, move round(19 * 0.25) = 5
        assert row["sentiment"] == 10, dict(row)

    async def test_the_reason_prints_the_revolt_risk_as_a_percent(self, sid):
        tid = await _territory(sid, revolt=50)
        row_id = await _sentiment(sid, tid)
        await ps.refresh(sid, tid)
        reason = await Database.fetchval(
            "SELECT last_shift_reason FROM maya_rp.population_sentiment WHERE id=$1", row_id)
        assert "revolt 50%" in reason, reason

    async def test_refresh_keeps_part_of_a_manual_shift(self, sid):
        tid = await _territory(sid)
        row_id = await _sentiment(sid, tid, sentiment=26)
        assert (await ps.shift(sid, tid, "Iron Concord", 8, "t"))["sentiment"] == 34
        await ps.refresh(sid, tid)
        row = await _row(row_id)
        assert row["sentiment"] == 32, dict(row)  # 34 + round((26 - 34) * 0.25)
        assert row["last_shift"] == -2, dict(row)

    async def test_a_refresh_step_is_capped(self, sid):
        tid = await _territory(sid)
        row_id = await _sentiment(sid, tid, sentiment=-100)
        await ps.refresh(sid, tid)
        row = await _row(row_id)
        assert row["sentiment"] == -90, dict(row)  # uncapped move is round(126 * 0.25) = 32

    async def test_a_dry_run_writes_nothing(self, sid):
        tid = await _territory(sid)
        row_id = await _sentiment(sid, tid, sentiment=5)
        out = await ps.refresh(sid, tid, dry_run=True)
        assert out["dry_run"] is True and out["updated"] == 0, out
        assert len(out["deltas"]) == 1, out
        assert out["deltas"][0]["id"] == row_id and out["deltas"][0]["sentiment"] == 5, out
        assert (await _row(row_id))["sentiment"] == 5

    async def test_a_normal_refresh_returns_only_the_count(self, sid):
        tid = await _territory(sid)
        await _sentiment(sid, tid)
        assert await ps.refresh(sid, tid) == {"updated": 1}


class TestShift:
    async def test_concurrent_shifts_all_land(self, sid):
        tid = await _territory(sid)
        row_id = await _sentiment(sid, tid, sentiment=0)
        await asyncio.gather(*[ps.shift(sid, tid, "Iron Concord", 1, "r") for _ in range(10)])
        assert (await _row(row_id))["sentiment"] == 10

    async def test_a_shift_returns_the_stored_value(self, sid):
        tid = await _territory(sid)
        await _sentiment(sid, tid, sentiment=95)
        out = await ps.shift(sid, tid, "Iron Concord", 40, "t")
        assert out == {"territory_id": tid, "faction": "Iron Concord", "sentiment": 100,
                       "delta": 40, "reason": "t"}, out


class TestTheFactionFilter:
    async def test_a_faction_filter_escapes_wildcards(self, sid):
        tid = await _territory(sid)
        await _sentiment(sid, tid, faction="Iron Concord")
        await _sentiment(sid, tid, faction="Iron_Concord")
        rows = await ps.status(sid, faction_name="Iron_C")
        assert [r["faction_name"] for r in rows] == ["Iron_Concord"], rows
