"""Population sentiment review: what reading `modules/population_sentiment.py` in full turned up.

Two defects. Every row this file creates belongs to `scratch_campaign` and is removed in a `finally`.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from core.db import Database  # noqa: E402
from modules import population_sentiment as ps  # noqa: E402


async def _territory(sid, name="review sentiment system", morale=50, tax=0.05, crisis=0,
                performance=50):
    # The id is taken well above max(id): a concurrent run can insert into this table between the
    # subquery and the insert, and the sequence itself is behind max(id).
    # title_performance is set explicitly: its column default is 0, which is not the 50 the driver
    # formula falls back to when the column is NULL.
    return await Database.fetchval(
        "INSERT INTO maya_rp.territory (id, session_id, system_name, controlling_faction, morale, "
        "tax_rate, crisis_level, title_performance) "
        "VALUES ((SELECT COALESCE(MAX(id), 0) + 500000 FROM maya_rp.territory), $1, $2, 'Iron Concord', "
        "$3, $4, $5, $6) RETURNING id",
        sid, name, morale, tax, crisis, performance)


async def _sentiment(sid, territory_id, faction="Iron Concord", sentiment=5):
    return await Database.fetchval(
        "INSERT INTO maya_rp.population_sentiment "
        "(session_id, territory_id, faction_name, sentiment, approval, fear, trust, bias) "
        "VALUES ($1, $2, $3, $4, 55, 10, 45, 0) RETURNING id",
        sid, territory_id, faction, sentiment)


async def _drop(territory_id):
    await Database.execute(
        "DELETE FROM maya_rp.population_sentiment WHERE territory_id = $1", territory_id)
    await Database.execute("DELETE FROM maya_rp.territory WHERE id = $1", territory_id)


class TestTheStatusQuery:
    async def test_a_faction_filter_without_a_territory_is_answerable(self, scratch_campaign):
        """The placeholder was $3 in a query that bound one argument, so this raised."""
        await Database.init()
        tid = await _territory(scratch_campaign)
        await _sentiment(scratch_campaign, tid)
        try:
            rows = await ps.status(scratch_campaign, faction_name="Iron Concord")
            assert [r["territory_id"] for r in rows] == [tid], rows
        finally:
            await _drop(tid)
            await Database.close()

    async def test_all_four_filter_shapes_answer(self, scratch_campaign):
        await Database.init()
        tid = await _territory(scratch_campaign)
        await _sentiment(scratch_campaign, tid)
        try:
            assert len(await ps.status(scratch_campaign)) == 1
            assert len(await ps.status(scratch_campaign, territory_id=tid)) == 1
            assert len(await ps.status(scratch_campaign, faction_name="Iron")) == 1
            assert len(await ps.status(scratch_campaign, territory_id=tid, faction_name="Iron")) == 1
        finally:
            await _drop(tid)
            await Database.close()

    async def test_a_filter_that_matches_nothing_answers_empty(self, scratch_campaign):
        await Database.init()
        try:
            assert await ps.status(scratch_campaign, faction_name="nobody at all") == []
        finally:
            await Database.close()


class TestTheSessionIsResolvedAtCallTime:
    async def test_the_default_session_is_not_frozen_at_import(self, monkeypatch):
        seen = []

        async def fake_fetch(query, *args):
            seen.append(args[0] if args else None)
            return []

        monkeypatch.setattr(ps.Database, "fetch", fake_fetch)
        monkeypatch.setattr(ps.Config, "SESSION_ID", 5)
        await ps.status()
        monkeypatch.setattr(ps.Config, "SESSION_ID", 3)
        await ps.status()
        assert seen == [5, 3], seen

    def test_no_module_level_session_constant_survives(self):
        assert not hasattr(ps, "SID"), "SID is back and it pins every default to one campaign"


class TestTheDrivers:
    async def test_refresh_moves_approval_with_the_drivers(self, scratch_campaign, monkeypatch):
        """Each value moves a quarter of the way to its driver target, capped at 10."""
        await Database.init()
        tid = await _territory(scratch_campaign, morale=70, tax=0.05, crisis=0)
        sid = await _sentiment(scratch_campaign, tid)
        try:
            out = await ps.refresh(scratch_campaign, tid)
            assert out == {"updated": 1}, out
            row = await Database.fetchrow(
                "SELECT sentiment, approval, fear, trust FROM maya_rp.population_sentiment WHERE id = $1",
                sid)
            assert row["approval"] == 57, dict(row)  # target 63 (55 + 20 * 0.4), move round(8 * 0.25) = 2
            assert row["fear"] == 10, dict(row)
            assert row["trust"] == 45, dict(row)
            assert row["sentiment"] == 11, dict(row)  # target 30 (63 * 0.55 - 10 * 0.45), move round(25 * 0.25) = 6
        finally:
            await _drop(tid)
            await Database.close()

    async def test_a_failing_territory_stays_out_of_another_session(self, scratch_campaign):
        await Database.init()
        tid = await _territory(scratch_campaign)
        await _sentiment(scratch_campaign, tid)
        try:
            assert await ps.refresh(7, tid) == {"updated": 0}
        finally:
            await _drop(tid)
            await Database.close()

    async def test_a_manual_shift_is_clamped_and_named(self, scratch_campaign):
        await Database.init()
        tid = await _territory(scratch_campaign)
        sid = await _sentiment(scratch_campaign, tid, sentiment=95)
        try:
            out = await ps.shift(scratch_campaign, tid, "Iron Concord", 40, "review")
            assert out["sentiment"] == 100, out
            assert out["delta"] == 40
            stored = await Database.fetchval(
                "SELECT last_shift FROM maya_rp.population_sentiment WHERE id = $1", sid)
            assert stored == 5, stored  # 100 - 95
        finally:
            await _drop(tid)
            await Database.close()

    async def test_a_shift_with_no_row_is_refused(self, scratch_campaign):
        await Database.init()
        try:
            out = await ps.shift(scratch_campaign, 999999999, "nobody", 5, "review")
            assert "no sentiment row" in out["error"], out
        finally:
            await Database.close()
