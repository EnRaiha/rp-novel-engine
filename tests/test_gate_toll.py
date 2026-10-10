"""Gate toll income tests — third-party pays, Setia collects (2026-08-15).

Izzat canon: "gate setia doesnt need exotic matter, only third party use it."
+ "the cost is smaller, but price is adjust for standardize" → Setia's own
fleet pays only the SMALLER internal cost (20% share); the PUBLIC price is
standardized at 25,000C and paid by common people / anyone else, credited to
the treasury via the economy tick.

Card B-toll-semantics, owner answer O2: `faction_trade_deals.quantity` is the volume of the whole deal
over `duration_days` game days. A deal flows `quantity / duration_days` units per game day, and a tick
tolls `flow * game_days / 40` crossings at 25,000C each, rounded with `stochastic_round`.

The unit tests stub `Database.fetchval`. The deal tests write factions, deals and resources into the
scratch session (900-999) only. Sessions 3 and 5 are never read or written.
"""
import asyncio
import random
import types
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio

from core.config import Config
from core.db import Database
from modules import economy
from modules.economy import gate_toll_income, GATE_TOLL_RATE
from modules.voyage import GATE_INTERNAL_COST_SHARE
from tests.conftest import _clear_session_rows, scratch_id

SID = scratch_id(__name__)


@pytest.fixture
def crossings(monkeypatch):
    """Replace `stochastic_round` with a spy: it records the exact crossings value and returns its floor."""
    seen = []

    def spy(value):
        seen.append(value)
        return int(value)

    monkeypatch.setattr(economy, "stochastic_round", spy, raising=False)
    return seen


def _stub_flow(monkeypatch, flow):
    """Answer the toll query with `flow` and record every (sql, args) it receives."""
    calls = []

    async def fetchval(sql, *args):
        calls.append((sql, args))
        return flow

    monkeypatch.setattr("modules.economy.Database.fetchval", fetchval)
    return calls


# ── The flow arithmetic, with a stubbed query ────────────────────────────

async def test_no_third_party_no_income(monkeypatch):
    async def fetchval(sql, *args):
        return 0
    monkeypatch.setattr("modules.economy.Database.fetchval", fetchval)
    assert await gate_toll_income() == 0


async def test_the_toll_is_the_flow_over_forty_per_game_day(monkeypatch, crossings):
    # 160 units a day, 2 game days: 320 units = 8 crossings = 200,000C
    _stub_flow(monkeypatch, Decimal("160"))
    assert await gate_toll_income(SID, game_days=2.0) == 8 * GATE_TOLL_RATE
    assert crossings == [pytest.approx(8.0)]


async def test_the_toll_doubles_with_the_game_days(monkeypatch):
    monkeypatch.setattr(economy, "stochastic_round", round, raising=False)
    _stub_flow(monkeypatch, Decimal("160"))
    one = await gate_toll_income(SID, game_days=1.0)
    two = await gate_toll_income(SID, game_days=2.0)
    assert (one, two) == (4 * GATE_TOLL_RATE, 8 * GATE_TOLL_RATE)


async def test_one_game_day_is_the_default_period(monkeypatch):
    _stub_flow(monkeypatch, Decimal("160"))
    assert await gate_toll_income(SID) == 4 * GATE_TOLL_RATE


@pytest.mark.parametrize("game_days,expected", [
    (1.0, 150.4 / 40 * GATE_TOLL_RATE),         # a full game day: 3.76 crossings
    (1 / 6, 150.4 / 6 / 40 * GATE_TOLL_RATE),   # an hourly tick at TIME_MULTIPLIER 4: 0.627 crossings
])
async def test_a_part_crossing_pays_in_expectation(monkeypatch, game_days, expected):
    # `random.random` returns 1000 evenly spaced values, so the mean of the draws is exact to 1/1000.
    draws = iter([(i + 0.5) / 1000 for i in range(1000)])
    monkeypatch.setattr(random, "random", lambda: next(draws))
    _stub_flow(monkeypatch, Decimal("150.4"))
    paid = [await gate_toll_income(SID, game_days=game_days) for _ in range(1000)]
    assert sum(paid) / 1000 == pytest.approx(expected, abs=GATE_TOLL_RATE / 1000)
    assert set(paid) <= {int(expected // GATE_TOLL_RATE) * GATE_TOLL_RATE,
                         (int(expected // GATE_TOLL_RATE) + 1) * GATE_TOLL_RATE}


def test_public_price_standardized():
    # the "appropriate fair" — affordable enough that traders prefer the gate
    assert 10000 <= GATE_TOLL_RATE <= 100000
    assert GATE_TOLL_RATE == 25000


def test_internal_cost_smaller_than_public():
    # fleet internal cost is a SMALLER share of the standardized public price
    assert 0 < GATE_INTERNAL_COST_SHARE < 1
    assert 25000 * GATE_INTERNAL_COST_SHARE < 25000
    assert 25000 * GATE_INTERNAL_COST_SHARE == 5000


# ── The deals, in a scratch campaign ─────────────────────────────────────

async def _faction(session_id, name):
    return await Database.fetchval(
        "INSERT INTO maya_rp.factions (session_id, name) VALUES ($1, $2) RETURNING id", session_id, name)


async def _deal(session_id, a, b, quantity, duration, *, active=True, signed_days_ago=0.0):
    """Insert one deal between factions `a` and `b`, signed `signed_days_ago` real days ago.

    `signed_at` is a `timestamp` in the server's local time, so the insert subtracts from LOCALTIMESTAMP.
    `signed_days_ago=None` leaves `signed_at` NULL.
    """
    await Database.execute(
        "INSERT INTO maya_rp.faction_trade_deals (faction_a_id, faction_b_id, resource_type, quantity, price,"
        " duration_days, active, signed_at, session_id) VALUES ($1, $2, 'alloys', $3, 100, $4, $5,"
        " LOCALTIMESTAMP - $6::float8 * interval '1 day', $7)",
        a, b, quantity, duration, active, signed_days_ago, session_id)


@pytest_asyncio.fixture
async def world(scratch_campaign):
    """A scratch campaign with two Setia factions and two foreign ones. Faction names are unique table-wide."""
    await Database.init()
    await _clear_session_rows(scratch_campaign)
    return types.SimpleNamespace(
        session=scratch_campaign,
        setia=await _faction(scratch_campaign, f"Setia Toll Scratch {scratch_campaign}"),
        other_setia=await _faction(scratch_campaign, f"Setia Toll Scratch Two {scratch_campaign}"),
        foreign=await _faction(scratch_campaign, f"Foreign Toll Scratch {scratch_campaign}"),
        third=await _faction(scratch_campaign, f"Third Toll Scratch {scratch_campaign}"))


@pytest.mark.parametrize("duration", [0, None])
async def test_a_deal_with_no_duration_pays_nothing(world, crossings, duration):
    await _deal(world.session, world.setia, world.foreign, 400, duration)
    assert await gate_toll_income(world.session, game_days=2.0) == 0
    assert crossings == [0]


async def test_a_deal_with_no_duration_leaves_the_other_deals_paying(world, crossings):
    # Without NULLIF the zero divisor aborts the whole SUM, and the error handler zeroes every deal.
    await _deal(world.session, world.setia, world.foreign, 400, 20)
    await _deal(world.session, world.setia, world.third, 100, 0)
    await _deal(world.session, world.setia, world.third, 100, None)
    assert await gate_toll_income(world.session, game_days=2.0) == GATE_TOLL_RATE
    assert crossings == [pytest.approx(1.0)]


async def test_each_deal_flows_by_its_own_duration(world, crossings):
    # 400 over 20 days = 20 a day, 1000 over 100 days = 10 a day: 30 a day, 2 days = 1.5 crossings
    await _deal(world.session, world.setia, world.foreign, 400, 20)
    await _deal(world.session, world.foreign, world.setia, 1000, 100)
    await gate_toll_income(world.session, game_days=2.0)
    assert crossings == [pytest.approx(1.5)]


@pytest.mark.parametrize("pair", [("setia", "other_setia"), ("foreign", "third")])
async def test_the_toll_is_zero_with_no_foreign_deal(world, crossings, pair):
    # Setia pays no toll to itself, and a deal between two foreign factions crosses no Setia gate.
    await _deal(world.session, getattr(world, pair[0]), getattr(world, pair[1]), 400, 20)
    assert await gate_toll_income(world.session, game_days=2.0) == 0
    assert crossings == [0]


async def test_an_inactive_deal_pays_nothing(world, crossings):
    await _deal(world.session, world.setia, world.foreign, 400, 20, active=False)
    assert await gate_toll_income(world.session, game_days=2.0) == 0
    assert crossings == [0]


# ── A deal expires when its term has run out ─────────────────────────────
#
# The term is `duration_days` game days from `signed_at`. At TIME_MULTIPLIER 4, 20 game days are 5 real days.

async def test_a_deal_pays_while_its_term_runs(world, crossings):
    # 1 real day in = 4 of 20 game days. Flow 20 a day, 2 game days = 1 crossing.
    await _deal(world.session, world.setia, world.foreign, 400, 20, signed_days_ago=1.0)
    assert await gate_toll_income(world.session, game_days=2.0) == GATE_TOLL_RATE


async def test_a_deal_pays_nothing_once_its_term_has_run_out(world, crossings):
    # 6 real days in = 24 of 20 game days.
    await _deal(world.session, world.setia, world.foreign, 400, 20, signed_days_ago=6.0)
    assert await gate_toll_income(world.session, game_days=2.0) == 0
    assert crossings == [0]


@pytest.mark.parametrize("real_days,pays", [(5 - 0.01, True), (5 + 0.01, False)])
async def test_the_term_ends_at_duration_days_game_days(world, crossings, real_days, pays):
    await _deal(world.session, world.setia, world.foreign, 400, 20, signed_days_ago=real_days)
    assert await gate_toll_income(world.session, game_days=2.0) == (GATE_TOLL_RATE if pays else 0)


async def test_the_term_is_measured_at_the_configured_multiplier(world, crossings, monkeypatch):
    # 3 real days in: 12 game days at x4 (term running), 24 game days at x8 (term over).
    await _deal(world.session, world.setia, world.foreign, 400, 20, signed_days_ago=3.0)
    assert await gate_toll_income(world.session, game_days=2.0) == GATE_TOLL_RATE
    monkeypatch.setattr(Config, "TIME_MULTIPLIER", 8)
    assert await gate_toll_income(world.session, game_days=2.0) == 0


async def test_an_expired_deal_does_not_stop_a_live_one(world, crossings):
    await _deal(world.session, world.setia, world.foreign, 400, 20, signed_days_ago=1.0)
    await _deal(world.session, world.setia, world.third, 4000, 20, signed_days_ago=6.0)
    await gate_toll_income(world.session, game_days=2.0)
    assert crossings == [pytest.approx(1.0)]


async def test_a_deal_with_no_signing_time_pays_nothing(world, crossings):
    await _deal(world.session, world.setia, world.foreign, 400, 20, signed_days_ago=None)
    assert await gate_toll_income(world.session, game_days=2.0) == 0
    assert crossings == [0]


# ── The tick pays the period once, and stops at the end of the term ──────

async def _credits_after_two_overlapping_ticks(world, monkeypatch):
    """Fund the scratch campaign with 1000C and a tick period of 2.0 game days, then run two ticks at once."""
    start = datetime.now(timezone.utc) - timedelta(days=1)
    monkeypatch.setattr(economy, "calc_game_days", lambda when: 2.0 if when == start else 0.0)
    await Database.execute(
        "INSERT INTO maya_rp.resources (session_id, credits, alloys, fuel, population, last_tick_at)"
        " VALUES ($1, 1000, 0, 0, 0, $2)", world.session, start)
    await asyncio.gather(economy.run_tick(world.session), economy.run_tick(world.session))
    return await Database.fetchval(
        "SELECT credits FROM maya_rp.resources WHERE session_id=$1", world.session)


async def test_a_tick_pays_the_toll_once_per_period(world, monkeypatch):
    # 400 units over 20 game days = 20 a day. Two game days = 40 units = exactly 1 crossing = 25,000C.
    # The old toll charged the lifetime volume (400 units): 10 crossings = 250,000C on each tick.
    await _deal(world.session, world.setia, world.foreign, 400, 20)
    credits = await _credits_after_two_overlapping_ticks(world, monkeypatch)
    assert credits == 1000 + 200_000 * 2 + GATE_TOLL_RATE


async def test_a_tick_adds_no_toll_for_an_expired_deal(world, monkeypatch):
    await _deal(world.session, world.setia, world.foreign, 400, 20, signed_days_ago=6.0)
    credits = await _credits_after_two_overlapping_ticks(world, monkeypatch)
    assert credits == 1000 + 200_000 * 2
