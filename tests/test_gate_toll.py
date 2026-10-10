"""Gate toll income tests — third-party pays, Setia collects (2026-08-15).

Izzat canon: "gate setia doesnt need exotic matter, only third party use it."
+ "the cost is smaller, but price is adjust for standardize" → Setia's own
fleet pays only the SMALLER internal cost (20% share); the PUBLIC price is
standardized at 25,000C and paid by common people / anyone else.

Card B-toll-semantics, owner answer O2: `faction_trade_deals.quantity` is the volume of the whole deal
over `duration_days` game days. A deal flows `quantity / duration_days` units per game day, and a tick
tolls `flow * game_days / 40` crossings at 25,000C each, rounded with `stochastic_round`.

The toll belongs to the diplomatic trade: it runs while the deal's faction pair stands in
`faction_relations`, and stops when that standing breaks (owner, 2026-10-10). No calendar term ends a
deal. Traffic that is not a diplomatic trade pays once per fleet trip instead, at the crossing
(`modules.voyage.gate_crossing_toll`).

The unit tests stub `Database.fetchval`. The deal tests write factions, deals, relations and resources
into the scratch session (900-999) only. Sessions 3 and 5 are never read or written.
"""
import asyncio
import random
import types
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio

from core.db import Database
from modules import economy, voyage
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


async def _deal(session_id, a, b, quantity, duration, *, active=True):
    """Insert one deal between factions `a` and `b`.

    `signed_at` takes the column default: no term is measured from it any more, so the tests do not
    set it. The deal pays while its diplomacy stands.
    """
    await Database.execute(
        "INSERT INTO maya_rp.faction_trade_deals (faction_a_id, faction_b_id, resource_type, quantity, price,"
        " duration_days, active, session_id) VALUES ($1, $2, 'alloys', $3, 100, $4, $5, $6)",
        a, b, quantity, duration, active, session_id)


async def _relation(session_id, a, b, standing):
    """Insert the standing between the two factions, in the order given.

    `faction_relations` is unique on `(session_id, faction_a, faction_b)`, so the reversed pair is a
    second row. `standing=None` writes a NULL marker.
    """
    await Database.execute(
        "INSERT INTO maya_rp.faction_relations (session_id, faction_a, faction_b, standing)"
        " VALUES ($1, $2, $3, $4)", session_id, a, b, standing)


@pytest_asyncio.fixture
async def world(scratch_campaign):
    """A scratch campaign with two Setia factions and two foreign ones. Faction names are unique table-wide.

    The teardown removes this campaign's relations first. `faction_relations` references `factions`
    with no cascade, so `scratch_session`'s own cleanup can fail on the FK when it reaches `factions`
    before `faction_relations`, and the campaign then survives the run.
    """
    await Database.init()
    await _clear_session_rows(scratch_campaign)
    yield types.SimpleNamespace(
        session=scratch_campaign,
        setia=await _faction(scratch_campaign, f"Setia Toll Scratch {scratch_campaign}"),
        other_setia=await _faction(scratch_campaign, f"Setia Toll Scratch Two {scratch_campaign}"),
        foreign=await _faction(scratch_campaign, f"Foreign Toll Scratch {scratch_campaign}"),
        third=await _faction(scratch_campaign, f"Third Toll Scratch {scratch_campaign}"))
    await Database.execute(
        "DELETE FROM maya_rp.faction_relations WHERE session_id = $1", scratch_campaign)


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


# ── The toll follows the diplomacy, not a calendar ───────────────────────
#
# A deal pays while its faction pair's `faction_relations.standing` stands, and stops when the
# standing breaks. `duration_days` sets the flow, never the stop.

@pytest.mark.parametrize("broken", ["hostile", "enemy"])
async def test_a_broken_standing_stops_the_toll(world, crossings, broken):
    await _relation(world.session, world.setia, world.foreign, broken)
    await _deal(world.session, world.setia, world.foreign, 400, 20)
    assert await gate_toll_income(world.session, game_days=2.0) == 0
    assert crossings == [0]


@pytest.mark.parametrize("standing", ["allied", "friendly", "neutral", "suspicious"])
async def test_a_standing_diplomacy_keeps_the_toll_running(world, crossings, standing):
    await _relation(world.session, world.setia, world.foreign, standing)
    await _deal(world.session, world.setia, world.foreign, 400, 20)
    assert await gate_toll_income(world.session, game_days=2.0) == GATE_TOLL_RATE
    assert crossings == [pytest.approx(1.0)]


async def test_the_relation_is_read_in_either_column_order(world, crossings):
    # The pair is stored one way and the deal can name the factions the other way.
    await _relation(world.session, world.foreign, world.setia, "hostile")
    await _deal(world.session, world.setia, world.foreign, 400, 20)
    assert await gate_toll_income(world.session, game_days=2.0) == 0


async def test_a_missing_relation_row_keeps_the_toll_running(world, crossings):
    # No record of a broken diplomacy is not a break: the deal pays, as it did before the rule.
    await _deal(world.session, world.setia, world.foreign, 400, 20)
    assert await gate_toll_income(world.session, game_days=2.0) == GATE_TOLL_RATE


async def test_a_null_standing_keeps_the_toll_running(world, crossings):
    await _relation(world.session, world.setia, world.foreign, None)
    await _deal(world.session, world.setia, world.foreign, 400, 20)
    assert await gate_toll_income(world.session, game_days=2.0) == GATE_TOLL_RATE


async def test_a_deal_with_no_active_marker_pays_nothing(world, crossings):
    # `active` is the deal's own switch. Only an explicit true pays.
    await _relation(world.session, world.setia, world.foreign, "friendly")
    await _deal(world.session, world.setia, world.foreign, 400, 20, active=None)
    assert await gate_toll_income(world.session, game_days=2.0) == 0
    assert crossings == [0]


async def test_a_broken_relation_between_other_factions_does_not_stop_the_toll(world, crossings):
    await _relation(world.session, world.setia, world.third, "hostile")
    await _deal(world.session, world.setia, world.foreign, 400, 20)
    assert await gate_toll_income(world.session, game_days=2.0) == GATE_TOLL_RATE


async def test_a_broken_standing_in_another_campaign_does_not_stop_the_toll(world, crossings):
    # The relation lookup is scoped to the deal's session.
    other = scratch_id(__name__ + ".other")
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1, 'rp-engine test scratch', 'active')"
        " ON CONFLICT (id) DO NOTHING", other)
    try:
        await _relation(other, world.setia, world.foreign, "hostile")
        await _deal(world.session, world.setia, world.foreign, 400, 20)
        assert await gate_toll_income(world.session, game_days=2.0) == GATE_TOLL_RATE
    finally:
        await _clear_session_rows(other)
        await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", other)


async def test_a_deal_keeps_paying_past_its_duration(world, crossings):
    # Signed 400 real days ago with a 20 game day duration: nothing ends it. The old rule stopped it.
    await _deal(world.session, world.setia, world.foreign, 400, 20)
    await Database.execute(
        "UPDATE maya_rp.faction_trade_deals SET signed_at = (NOW() AT TIME ZONE 'UTC') - interval '400 days'"
        " WHERE session_id = $1", world.session)
    assert await gate_toll_income(world.session, game_days=2.0) == GATE_TOLL_RATE
    assert crossings == [pytest.approx(1.0)]


# ── The tick pays the period once, and stops when the diplomacy breaks ───

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


async def test_a_tick_pays_the_toll_for_a_deal_past_its_duration(world, monkeypatch):
    await _deal(world.session, world.setia, world.foreign, 400, 20)
    await Database.execute(
        "UPDATE maya_rp.faction_trade_deals SET signed_at = (NOW() AT TIME ZONE 'UTC') - interval '400 days'"
        " WHERE session_id = $1", world.session)
    credits = await _credits_after_two_overlapping_ticks(world, monkeypatch)
    assert credits == 1000 + 200_000 * 2 + GATE_TOLL_RATE


async def test_a_tick_adds_no_toll_for_a_broken_diplomacy(world, monkeypatch):
    await _relation(world.session, world.setia, world.foreign, "hostile")
    await _deal(world.session, world.setia, world.foreign, 400, 20)
    credits = await _credits_after_two_overlapping_ticks(world, monkeypatch)
    assert credits == 1000 + 200_000 * 2


# ── Other transit pays once per fleet trip, at the crossing ──────────────
#
# The one-off belongs where the crossing is booked: `modules.voyage.register` charges one toll per
# voyage, and the travel days do not scale it. A diplomatic trade deal is never charged there. The
# economy tick collects its flow per game day instead.

def test_the_crossing_toll_is_one_price_per_trip():
    assert voyage.gate_crossing_toll(25_000) == int(25_000 * GATE_INTERNAL_COST_SHARE) == 5_000
    assert voyage.gate_crossing_toll(25_000, own_fleet=False) == 25_000
    assert voyage.gate_crossing_toll(None) == 0
    assert voyage.gate_crossing_toll(0, own_fleet=False) == 0


async def _gate_lane(z1, z2, session_id=None):
    """A public gate lane: 25,000C per crossing over 40 travel days."""
    return {"name": "Scratch Gate", "distance": 10, "travel_time_hours": 40 * 24,
            "hidden": False, "lane_type": "gate", "toll_credits": 25_000, "pirate_density": 0.05}


async def _hidden_lane(z1, z2, session_id=None):
    """A hidden thread: no toll, high density."""
    return {"name": "Scratch Thread", "distance": 10, "travel_time_hours": 40 * 24,
            "hidden": True, "lane_type": "hidden_thread", "toll_credits": 0, "pirate_density": 0.65}


def _install_register_fakes(monkeypatch, charges):
    """Answer `register` without a database and record every treasury statement it runs."""
    inserted = []

    class FakeConn:
        async def fetchval(self, sql, *args):
            if "UPDATE maya_rp.resources" in sql:
                charges.append((" ".join(sql.split()), args))
                return 1_000_000      # RETURNING credits: the statement found the row
            if "SELECT 1 FROM maya_rp.resources" in sql:
                return 1
            if "INSERT INTO maya_rp.voyages" in sql:
                inserted.append(args)
                return 42
            return None

        async def execute(self, sql, *args):
            return "OK"

        async def fetch(self, sql, *args):
            return []

        async def fetchrow(self, sql, *args):
            return None

    @asynccontextmanager
    async def transaction():
        yield FakeConn()

    async def fetchval(sql, *args):
        return 100 if "game_day" in sql else None

    async def fetchrow(sql, *args):
        return None

    monkeypatch.setattr(voyage.Database, "fetchval", fetchval)
    monkeypatch.setattr(voyage.Database, "fetchrow", fetchrow)
    monkeypatch.setattr(voyage.Database, "transaction", transaction)
    return charges, inserted


async def _register_trip(monkeypatch, charges, *, name, own_fleet, lane=_gate_lane):
    """Book one fleet trip through the gate lane, returning the result and the inserted voyage rows."""
    _charges, inserted = _install_register_fakes(monkeypatch, charges)
    monkeypatch.setattr(voyage, "gate_crossing", lane)
    r = await voyage.register(name, "20,250,3", "25,12,2", ship_count=4, fleet_tag="TRIP",
                              session_id=SID, own_fleet=own_fleet)
    return r, inserted


async def test_other_transit_pays_the_public_price_once(monkeypatch):
    charges = []
    r, inserted = await _register_trip(monkeypatch, charges, name="Public Trip", own_fleet=False)
    assert r["lane_type"] == "gate"
    assert r["toll_paid"] == GATE_TOLL_RATE
    assert r["toll_charged"] is True
    assert len(charges) == 1, f"the crossing charged {len(charges)} times, not once: {charges}"
    assert "+ $1" in charges[0][0], f"a trip that is not the owner's fleet must credit the treasury: {charges[0][0]}"
    assert charges[0][1] == (GATE_TOLL_RATE, SID)
    assert len(inserted) == 1, "the voyage row did not commit with the toll"


async def test_the_trip_toll_does_not_scale_with_the_travel_days(monkeypatch):
    # The lane alone adds 40 travel days and the trip runs over 270: one toll, not one per day.
    charges = []
    r, _inserted = await _register_trip(monkeypatch, charges, name="Long Trip", own_fleet=False)
    assert r["travel_days"] > 40
    assert len(charges) == 1, f"one trip paid more than one toll: {charges}"
    assert charges[0][1][0] == GATE_TOLL_RATE


async def test_two_trips_pay_twice(monkeypatch):
    charges = []
    await _register_trip(monkeypatch, charges, name="Trip One", own_fleet=False)
    await _register_trip(monkeypatch, charges, name="Trip Two", own_fleet=False)
    assert [args[0] for _sql, args in charges] == [GATE_TOLL_RATE, GATE_TOLL_RATE]


async def test_the_owners_own_fleet_pays_the_internal_cost_once(monkeypatch):
    charges = []
    r, _inserted = await _register_trip(monkeypatch, charges, name="Setia Trip", own_fleet=True)
    assert r["toll_paid"] == int(GATE_TOLL_RATE * GATE_INTERNAL_COST_SHARE) == 5_000
    assert len(charges) == 1
    assert "- $1" in charges[0][0], "the owner's own fleet pays the internal cost, not income"
    assert charges[0][1] == (5_000, SID)


async def test_a_lane_that_is_not_a_gate_pays_no_crossing_toll(monkeypatch):
    charges = []
    r, _inserted = await _register_trip(monkeypatch, charges, name="Smuggler Trip", own_fleet=False,
                                        lane=_hidden_lane)
    assert r["lane_type"] == "hidden_thread"
    assert r["toll_paid"] == 0
    assert charges == []
