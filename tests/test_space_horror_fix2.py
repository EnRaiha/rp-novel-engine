"""Space horror, second pass: types the live database returns, and a charge that was not atomic.

Every test writes only the scratch session. `spread_rate` is NUMERIC and arrives as Decimal,
`space_lanes.origin` is TEXT, `spread_progress` and `eradication_campaigns.progress` are INTEGER, and
`assets_assigned` is jsonb with no codec, so it arrives as a str.

Tests that pin `random.random` pin the process-wide function. `stochastic_round` and the tick's own
dice both read it, so a value is chosen to open or close each gate on purpose.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

from core.db import Database  # noqa: E402
from modules import space_horror  # noqa: E402
from modules._economy import InsufficientResources  # noqa: E402

SPORE_DRIFT = 1  # spread_rate 0.1 (Decimal), threat_level 1
MEASURE = "fix2 test measure"


@pytest_asyncio.fixture
async def world(scratch_session):
    """The scratch session with its `sessions` row, which every FK below needs.

    Teardown removes the rows without a cascade (lanes, sectors, resources), then the session row,
    which cascades to infestations, campaigns and the story log.
    """
    await Database.init()
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1, 'space-horror fix2 scratch', 'active')"
        " ON CONFLICT (id) DO NOTHING", scratch_session)
    yield scratch_session
    for table in ("space_lanes", "sectors", "resources"):
        await Database.execute(f"DELETE FROM maya_rp.{table} WHERE session_id = $1", scratch_session)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", scratch_session)
    await Database.close()


async def _sector(sid, name):
    return await Database.fetchval(
        "INSERT INTO maya_rp.sectors (session_id, name, x_coord, y_coord) VALUES ($1, $2, 0, 0) RETURNING id",
        sid, name)


async def _infestation(sid, sector_id, progress=0, biomass=100, contained=False, level=0):
    return await Database.fetchval(
        "INSERT INTO maya_rp.infestation_instances (session_id, sector_id, stage_id, biomass,"
        " spread_progress, contained, containment_level, status)"
        " VALUES ($1, $2, $3, $4, $5, $6, $7, 'active') RETURNING id",
        sid, sector_id, SPORE_DRIFT, biomass, progress, contained, level)


async def _campaign(sid, infestation_id, assets="[]", progress=0):
    return await Database.fetchval(
        "INSERT INTO maya_rp.eradication_campaigns (session_id, target_infestation_id, campaign_name,"
        " strategy, assets_assigned, status, progress)"
        " VALUES ($1, $2, 'fix2 campaign', 'systematic', $3::jsonb, 'active', $4) RETURNING id",
        sid, infestation_id, assets, progress)


async def _progress(iid):
    return await Database.fetchval(
        "SELECT spread_progress FROM maya_rp.infestation_instances WHERE id = $1", iid)


def _pin_random(monkeypatch, value):
    monkeypatch.setattr(space_horror.random, "random", lambda: value)


def _no_events(monkeypatch):
    """Keep `EventBus.emit` out of the database: its bus row is filed by payload, not by caller."""
    seen = []

    async def record(event_type, data):
        seen.append((event_type, data))

    monkeypatch.setattr(space_horror.EventBus, "emit", record)
    return seen


# ============================================================
# H4: the spread
# ============================================================

class TestTheSpread:
    async def test_a_decimal_rate_spreads_instead_of_raising(self, world, monkeypatch):
        """Spore Drift at 2 game days adds 0.1 * 2 * 5 = 1.0 progress and 1.0 biomass: whole numbers,
        so no dice decide the result."""
        _pin_random(monkeypatch, 0.999)
        iid = await _infestation(world, await _sector(world, "fix2 A"), biomass=100)
        await space_horror.spread_infestation(world, 2.0)
        row = await Database.fetchrow(
            "SELECT spread_progress, biomass FROM maya_rp.infestation_instances WHERE id = $1", iid)
        assert (row["spread_progress"], row["biomass"]) == (1, 101), dict(row)

    async def test_a_slow_rate_still_advances(self, world, monkeypatch):
        """0.1 * 0.5 * 5 = 0.25 per tick. Truncation stores 0 on every tick and the stage never escalates."""
        _pin_random(monkeypatch, 0.1)
        iid = await _infestation(world, await _sector(world, "fix2 A"))
        await space_horror.spread_infestation(world, 0.5)
        assert await _progress(iid) == 1

    async def test_a_slow_rate_does_not_advance_when_the_dice_say_no(self, world, monkeypatch):
        _pin_random(monkeypatch, 0.9)
        iid = await _infestation(world, await _sector(world, "fix2 A"))
        await space_horror.spread_infestation(world, 0.5)
        assert await _progress(iid) == 0

    async def test_the_tick_no_longer_aborts_on_an_active_infestation(self, world, monkeypatch):
        _pin_random(monkeypatch, 0.999)
        iid = await _infestation(world, await _sector(world, "fix2 A"))
        out = await space_horror.run_tick(world)
        assert out is None, out
        assert await _progress(iid) is not None

    async def test_a_lane_carries_the_horror_to_the_sector_it_names(self, world, monkeypatch):
        _pin_random(monkeypatch, 0.0)
        _no_events(monkeypatch)
        a, b = await _sector(world, "fix2 A"), await _sector(world, "fix2 B")
        await _infestation(world, a)
        await Database.execute(
            "INSERT INTO maya_rp.space_lanes (session_id, origin, destination) VALUES ($1, 'fix2 A', 'fix2 B')",
            world)
        await space_horror.spread_infestation(world, 1.0)
        reached = await Database.fetchval(
            "SELECT count(*) FROM maya_rp.infestation_instances WHERE session_id = $1 AND sector_id = $2",
            world, b)
        assert reached == 1

    async def test_a_lane_to_a_sector_outside_the_session_seeds_nothing(self, world, monkeypatch):
        """The destination name exists in session 3, not here. The join resolves inside the lane's session."""
        _pin_random(monkeypatch, 0.0)
        _no_events(monkeypatch)
        foreign = await Database.fetchrow(
            "SELECT id, name FROM maya_rp.sectors WHERE session_id = 3 ORDER BY id LIMIT 1")
        assert foreign is not None, "session 3 has no sector to name"
        await _infestation(world, await _sector(world, "fix2 A"))
        await Database.execute(
            "INSERT INTO maya_rp.space_lanes (session_id, origin, destination) VALUES ($1, 'fix2 A', $2)",
            world, foreign["name"])
        await space_horror.spread_infestation(world, 1.0)
        landed = await Database.fetchval(
            "SELECT count(*) FROM maya_rp.infestation_instances WHERE sector_id = $1", foreign["id"])
        assert landed == 0
        assert await Database.fetchval(
            "SELECT count(*) FROM maya_rp.infestation_instances WHERE session_id = $1", world) == 1

    async def test_seeding_files_its_event_in_the_infestations_session(self, world, monkeypatch):
        """The payload carried no session, so the bus filed the event in the active arc."""
        seen = _no_events(monkeypatch)
        sector = await _sector(world, "fix2 A")
        out = await space_horror.seed_infestation(world, sector)
        assert "infestation_id" in out, out
        assert [d.get("session_id") for t, d in seen if t == "infestation_seeded"] == [world], seen


# ============================================================
# H5: eradication
# ============================================================

class TestTheCampaign:
    @pytest.mark.parametrize("game_days, pin, expected", [
        (0.7, 0.0, 4),    # gain 3.5, fraction rounds up
        (0.7, 0.99, 3),   # gain 3.5, fraction rounds down
        (0.1, 0.0, 1),    # gain 0.5 would truncate to 0 and the campaign would never move
    ])
    async def test_progress_stores_the_rounded_step(self, world, monkeypatch, game_days, pin, expected):
        _pin_random(monkeypatch, pin)

        async def no_event(*args):
            return None

        monkeypatch.setattr(space_horror, "_generate_campaign_event", no_event)
        iid = await _infestation(world, await _sector(world, "fix2 A"), biomass=500)
        cid = await _campaign(world, iid)
        await space_horror.advance_eradication(world, game_days)
        progress = await Database.fetchval(
            "SELECT progress FROM maya_rp.eradication_campaigns WHERE id = $1", cid)
        assert progress == expected

    async def _fire_the_casualty_event(self, world, monkeypatch, assets_sql):
        """Run the `damage` event against a campaign whose `assets_assigned` is `assets_sql`."""
        monkeypatch.setattr(space_horror.random, "choice", lambda seq: seq[0])
        iid = await _infestation(world, await _sector(world, "fix2 A"))
        cid = await _campaign(world, iid, assets=assets_sql)
        camp = await Database.fetchrow("SELECT * FROM maya_rp.eradication_campaigns WHERE id = $1", cid)
        inf = await Database.fetchrow("SELECT * FROM maya_rp.infestation_instances WHERE id = $1", iid)
        await space_horror._generate_campaign_event(world, camp, inf)
        return await Database.fetchval(
            "SELECT assets_assigned FROM maya_rp.eradication_campaigns WHERE id = $1", cid)

    async def test_a_casualty_removes_one_asset_not_one_character(self, world, monkeypatch):
        stored = await self._fire_the_casualty_event(
            world, monkeypatch, '["flame frigate", "purifier squadron"]')
        left = json.loads(stored)
        assert len(left) == 1 and left[0] in ("flame frigate", "purifier squadron"), stored

    async def test_a_decoded_asset_list_loses_one_asset_too(self, world, monkeypatch):
        """A caller that already decoded the jsonb passes a list, and `list(camp[...])` copies it."""
        monkeypatch.setattr(space_horror.random, "choice", lambda seq: seq[0])
        iid = await _infestation(world, await _sector(world, "fix2 A"))
        cid = await _campaign(world, iid, assets='["a", "b", "c"]')
        camp = {"id": cid, "assets_assigned": ["a", "b", "c"]}
        await space_horror._generate_campaign_event(world, camp, {"id": iid})
        stored = await Database.fetchval(
            "SELECT assets_assigned FROM maya_rp.eradication_campaigns WHERE id = $1", cid)
        assert len(json.loads(stored)) == 2, stored
        assert camp["assets_assigned"] == ["a", "b", "c"], "the caller's list was mutated"

    @pytest.mark.parametrize("assets_sql", ["[]", "null"])
    async def test_a_casualty_with_no_assets_changes_nothing(self, world, monkeypatch, assets_sql):
        stored = await self._fire_the_casualty_event(world, monkeypatch, assets_sql)
        assert json.loads(stored) in ([], None), stored

    async def test_a_casualty_on_a_sql_null_column_does_not_raise(self, world, monkeypatch):
        monkeypatch.setattr(space_horror.random, "choice", lambda seq: seq[0])
        iid = await _infestation(world, await _sector(world, "fix2 A"))
        cid = await Database.fetchval(
            "INSERT INTO maya_rp.eradication_campaigns (session_id, target_infestation_id, strategy, status)"
            " VALUES ($1, $2, 'systematic', 'active') RETURNING id", world, iid)
        camp = await Database.fetchrow("SELECT * FROM maya_rp.eradication_campaigns WHERE id = $1", cid)
        await space_horror._generate_campaign_event(world, camp, {"id": iid})
        assert await Database.fetchval(
            "SELECT assets_assigned FROM maya_rp.eradication_campaigns WHERE id = $1", cid) is None


# ============================================================
# Containment purchase
# ============================================================

@pytest_asyncio.fixture
async def shop(world):
    """A treasury of 5000 credits, 50 fuel and 70 alloys, and a catalogue measure that costs
    1000 credits, 5 fuel and 7 alloys. The measure row is global, so it is removed here."""
    await Database.execute(
        "INSERT INTO maya_rp.resources (session_id, credits, fuel, alloys) VALUES ($1, 5000, 50, 70)"
        " ON CONFLICT (session_id) DO UPDATE SET credits = 5000, fuel = 50, alloys = 70", world)
    await Database.execute(
        "INSERT INTO maya_rp.containment_measures (name, effectiveness, cost_credits, cost_resources)"
        " VALUES ($1, 0.5, 1000, '{\"fuel\": 5, \"alloys\": 7}'::jsonb)"
        " ON CONFLICT (name) DO UPDATE SET effectiveness = 0.5, cost_credits = 1000,"
        " cost_resources = '{\"fuel\": 5, \"alloys\": 7}'::jsonb, research_required = NULL", MEASURE)
    iid = await _infestation(world, await _sector(world, "fix2 A"))
    try:
        yield world, iid
    finally:
        await Database.execute("DELETE FROM maya_rp.containment_measures WHERE name = $1", MEASURE)


async def _treasury(sid):
    row = await Database.fetchrow(
        "SELECT credits, fuel, alloys FROM maya_rp.resources WHERE session_id = $1", sid)
    return row["credits"], row["fuel"], row["alloys"]


async def _containment(iid):
    row = await Database.fetchrow(
        "SELECT contained, containment_level FROM maya_rp.infestation_instances WHERE id = $1", iid)
    return row["contained"], row["containment_level"]


class TestTheContainmentPurchase:
    async def test_a_measure_charges_and_applies(self, shop):
        sid, iid = shop
        out = await space_horror.apply_containment(sid, iid, MEASURE)
        assert out == {"success": True, "measure": MEASURE, "containment_level": 15}, out
        assert await _treasury(sid) == (4000, 45, 63)
        assert await _containment(iid) == (True, 15)

    async def test_a_measure_the_treasury_cannot_pay_is_refused_untouched(self, shop):
        sid, iid = shop
        await Database.execute("UPDATE maya_rp.resources SET credits = 10 WHERE session_id = $1", sid)
        out = await space_horror.apply_containment(sid, iid, MEASURE)
        assert out == {"error": "Insufficient: need 1000 credits, have 10"}, out
        assert await _treasury(sid) == (10, 50, 70)
        assert await _containment(iid) == (False, 0)

    async def test_a_shortage_found_at_the_charge_is_refused_not_raised(self, shop, monkeypatch):
        """The treasury looks sufficient, then the guarded debit finds it short: no pre-read decides."""
        sid, iid = shop

        async def short(session_id, costs, conn=None):
            raise InsufficientResources("need 1000 credits, have 999")

        monkeypatch.setattr(space_horror, "_deduct_resources", short)
        out = await space_horror.apply_containment(sid, iid, MEASURE)
        assert out == {"error": "Insufficient: need 1000 credits, have 999"}, out
        assert await _containment(iid) == (False, 0)

    async def test_the_charge_rolls_back_with_the_effect(self, shop, monkeypatch):
        """A fault after the debit takes the debit with it only when the debit ran on the transaction."""
        sid, iid = shop
        real = space_horror._deduct_resources

        async def charge_then_die(session_id, costs, conn=None):
            await real(session_id, costs, conn=conn)
            raise RuntimeError("effect died")

        monkeypatch.setattr(space_horror, "_deduct_resources", charge_then_die)
        with pytest.raises(RuntimeError, match="effect died"):
            await space_horror.apply_containment(sid, iid, MEASURE)
        assert await _treasury(sid) == (5000, 50, 70)
        assert await _containment(iid) == (False, 0)
