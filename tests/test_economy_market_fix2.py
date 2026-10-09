"""economy and market fix 2: an overlapping tick pays the period once, a commodity prices once per game day.

Every write lands in a scratch session (900-999). Sessions 3 and 5 are not touched, and
`Config.SESSION_ID` points at the scratch id so no default can reach them.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest_asyncio  # noqa: E402

from core.config import Config  # noqa: E402
from core.db import Database  # noqa: E402
from modules import economy, market  # noqa: E402

GAME_DAY = 10


async def _wipe(session_id):
    await Database.execute(
        "DELETE FROM maya_rp.price_history WHERE commodity_id IN "
        "(SELECT id FROM maya_rp.commodities WHERE session_id=$1)", session_id)
    for table in ("commodities", "events", "territory", "resources"):
        await Database.execute(f"DELETE FROM maya_rp.{table} WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", session_id)


@pytest_asyncio.fixture
async def sid(scratch_session, monkeypatch):
    """A scratch session on game day 10 with no resources row, no territory and no commodity."""
    monkeypatch.setattr(Config, "SESSION_ID", scratch_session)
    await Database.init()
    await _wipe(scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status, game_day) "
        "VALUES ($1, 'econ market fix2', 'active', $2)", scratch_session, GAME_DAY)
    try:
        yield scratch_session
    finally:
        await _wipe(scratch_session)
        await Database.close()


async def _fund(session_id, last_tick):
    await Database.execute(
        "INSERT INTO maya_rp.resources (session_id, credits, alloys, fuel, population, last_tick_at) "
        "VALUES ($1, 1000, 0, 0, 0, $2)", session_id, last_tick)


def _a_day_ago():
    return datetime.now(timezone.utc) - timedelta(days=1)


def _one_period_since(start):
    """A `calc_game_days` stand-in: 2.0 game days since `start`, none since any later stamp.

    A constant 2.0 lets a tick that reads the stamp another tick just wrote pay a full period again.
    The real function returns about 0 for a stamp that new.
    """
    return lambda when: 2.0 if when == start else 0.0


async def _treasury(session_id):
    row = await Database.fetchrow(
        "SELECT credits, alloys, fuel, last_tick_at FROM maya_rp.resources WHERE session_id=$1", session_id)
    return row["credits"], row["alloys"], row["fuel"], row["last_tick_at"]


async def _water_ice(session_id):
    await Database.execute(
        "INSERT INTO maya_rp.commodities (session_id, name, category, base_price, current_price, "
        "volatility, supply, demand, last_tick_at) "
        "VALUES ($1, 'Water Ice', 'essentials', 0.8, 0.8, 0.06, 3000000, 2600000, 5)", session_id)


async def _history_rows(session_id):
    return await Database.fetchval(
        "SELECT count(*) FROM maya_rp.price_history WHERE commodity_id IN "
        "(SELECT id FROM maya_rp.commodities WHERE session_id=$1)", session_id)


async def _assert_priced_once(session_id):
    assert await _history_rows(session_id) == 13
    row = await Database.fetchrow(
        "SELECT last_tick_at, supply, demand FROM maya_rp.commodities "
        "WHERE session_id=$1 AND name='Water Ice'", session_id)
    assert row["last_tick_at"] == GAME_DAY
    assert row["supply"] == int(3000000.0 * (1 + 2.0 * 0.005))
    assert row["demand"] == int(2600000.0 * (1 + 2.0 * 0.006))


async def test_overlapping_economy_ticks_pay_the_period_once(sid, monkeypatch):
    start = _a_day_ago()
    monkeypatch.setattr(economy, "calc_game_days", _one_period_since(start))
    await _fund(sid, start)
    await asyncio.gather(economy.run_tick(sid), economy.run_tick(sid))
    credits, alloys, fuel, _ = await _treasury(sid)
    assert (credits, alloys, fuel) == (401000, 300000, 240000)


async def test_a_paid_tick_moves_last_tick_at_forward(sid, monkeypatch):
    start = _a_day_ago()
    monkeypatch.setattr(economy, "calc_game_days", _one_period_since(start))
    await _fund(sid, start)
    await economy.run_tick(sid)
    last_tick_at = (await _treasury(sid))[3]
    assert abs((datetime.now(timezone.utc) - last_tick_at).total_seconds()) < 60


async def test_a_null_last_tick_at_pays_and_prices_nothing(sid):
    await _fund(sid, None)
    assert await economy.run_tick(sid) is None
    assert await market.run_tick(sid) == {"skipped": "no last_tick_at"}
    credits, _, _, last_tick_at = await _treasury(sid)
    assert credits == 1000
    assert last_tick_at is None
    assert await Database.fetchval(
        "SELECT count(*) FROM maya_rp.commodities WHERE session_id=$1", sid) == 0


async def test_a_commodity_prices_once_per_game_day(sid, monkeypatch):
    monkeypatch.setattr(market, "calc_game_days", lambda when: 2.0)
    await _fund(sid, _a_day_ago())
    await _water_ice(sid)
    await market.run_tick(sid)
    await market.run_tick(sid)
    await _assert_priced_once(sid)


async def test_overlapping_market_ticks_price_once(sid, monkeypatch):
    monkeypatch.setattr(market, "calc_game_days", lambda when: 2.0)
    await _fund(sid, _a_day_ago())
    await _water_ice(sid)
    await asyncio.gather(market.run_tick(sid), market.run_tick(sid))
    await _assert_priced_once(sid)


async def test_a_commodity_seeded_by_the_tick_prices_on_that_tick(sid, monkeypatch):
    monkeypatch.setattr(market, "calc_game_days", lambda when: 2.0)
    await _fund(sid, _a_day_ago())
    await market.run_tick(sid)
    assert await _history_rows(sid) == 13
    markers = await Database.fetch(
        "SELECT last_tick_at FROM maya_rp.commodities WHERE session_id=$1", sid)
    assert len(markers) == 13
    assert {r["last_tick_at"] for r in markers} == {GAME_DAY}
