"""Auto-queue review: what reading `modules/auto_queue.py` in full turned up.

Three defects, one of them a stockpile that could be driven negative. Nothing here writes to sessions
3 or 5: the live-database tests run in two scratch sessions, created and removed by the autouse fixture
below, and every row they create is also removed in a `finally`.
"""
from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

from core.db import Database  # noqa: E402
from modules import auto_queue as aq  # noqa: E402

SESSION = 900 + os.getpid() % 100
OTHER = 900 + (os.getpid() + 50) % 100
MATERIAL = aq.MEDICAL_SUPPLY_COMMODITY


@pytest_asyncio.fixture(autouse=True)
async def _scratch_sessions():
    """Create both scratch sessions and remove everything they own, in FK order."""
    await Database.init()
    for sid in (SESSION, OTHER):
        await Database.execute(
            "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1,'auto_queue scratch','active')"
            " ON CONFLICT (id) DO NOTHING", sid)
    yield
    await Database.init()
    for sid in (SESSION, OTHER):
        await Database.execute(
            "DELETE FROM maya_rp.corporate_assets WHERE corporation_id IN "
            "(SELECT id FROM maya_rp.corporations WHERE session_id = $1)", sid)
        for table in ("corporations", "production_queue", "auto_queue", "material_stockpiles",
                      "commodities"):
            await Database.execute(f"DELETE FROM maya_rp.{table} WHERE session_id = $1", sid)
        await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", sid)


async def _pile(quantity, reserved=0):
    return await Database.fetchval(
        "INSERT INTO maya_rp.material_stockpiles (id, session_id, material_name, quantity, reserved) "
        "VALUES ((SELECT COALESCE(MAX(id), 0) + 500000 FROM maya_rp.material_stockpiles), "
        "$1, $2, $3, $4) RETURNING id",
        SESSION, MATERIAL, quantity, reserved)


async def _corp(session_id=SESSION, treasury=0):
    # A failed run can leave this row behind, and (session_id, name) is unique: clear it first.
    await Database.execute(
        "DELETE FROM maya_rp.corporate_assets WHERE corporation_id IN "
        "(SELECT id FROM maya_rp.corporations WHERE session_id = $1 AND name = 'review pharma')",
        session_id)
    await Database.execute(
        "DELETE FROM maya_rp.corporations WHERE session_id = $1 AND name = 'review pharma'",
        session_id)
    return await Database.fetchval(
        "INSERT INTO maya_rp.corporations (id, session_id, name, industry, treasury) "
        "VALUES ((SELECT COALESCE(MAX(id), 0) + 500000 FROM maya_rp.corporations), "
        "$1, 'review pharma', 'pharmaceutical', $2) RETURNING id",
        session_id, treasury)


async def _asset(corp_id, income=0, asset_type="medical_distribution_hub"):
    return await Database.fetchval(
        "INSERT INTO maya_rp.corporate_assets "
        "(id, corporation_id, asset_type, status, income_per_day) "
        "VALUES ((SELECT COALESCE(MAX(id), 0) + 500000 FROM maya_rp.corporate_assets), "
        "$1, $2, 'active', $3) RETURNING id",
        corp_id, asset_type, income)


async def _commodity(supply=0):
    return await Database.fetchval(
        "INSERT INTO maya_rp.commodities (id, session_id, name, category, supply) "
        "VALUES ((SELECT COALESCE(MAX(id), 0) + 500000 FROM maya_rp.commodities), "
        "$1, $2, 'medical', $3) RETURNING id",
        SESSION, MATERIAL, supply)


async def _dropped(*corp_ids):
    await Database.execute(
        "DELETE FROM maya_rp.material_stockpiles WHERE session_id = $1 AND material_name = $2",
        SESSION, MATERIAL)
    await Database.execute(
        "DELETE FROM maya_rp.commodities WHERE session_id = $1 AND name = $2", SESSION, MATERIAL)
    for cid in corp_ids:
        await Database.execute(
            "DELETE FROM maya_rp.corporate_assets WHERE corporation_id = $1", cid)
        await Database.execute("DELETE FROM maya_rp.corporations WHERE id = $1", cid)


class TestTheTransfer:
    async def test_a_pile_is_never_driven_negative(self):
        """The budget came from the SUM of every pile and was taken out of the lowest-id row."""
        await Database.init()
        corp = await _corp()
        small = await _pile(100)
        await _commodity(0)
        try:
            out = await aq._pharma_tick(SESSION)
            assert out["medical_supply_added"] == 100, out
            left = await Database.fetchval(
                "SELECT quantity FROM maya_rp.material_stockpiles WHERE id = $1", small)
            assert left == 0, left
        finally:
            await _dropped(corp)
            await Database.close()

    async def test_the_budget_spends_across_piles(self):
        await Database.init()
        corp = await _corp()
        first = await _pile(100)
        second = await _pile(400)
        await _commodity(0)
        try:
            out = await aq._pharma_tick(SESSION)
            assert out["medical_supply_added"] == 500, out
            assert await Database.fetchval(
                "SELECT quantity FROM maya_rp.material_stockpiles WHERE id = $1", first) == 0
            assert await Database.fetchval(
                "SELECT quantity FROM maya_rp.material_stockpiles WHERE id = $1", second) == 0
        finally:
            await _dropped(corp)
            await Database.close()

    async def test_reserved_stock_never_moves(self):
        await Database.init()
        corp = await _corp()
        pile = await _pile(500, reserved=450)
        await _commodity(0)
        try:
            out = await aq._pharma_tick(SESSION)
            assert out["medical_supply_added"] == 50, out
            assert await Database.fetchval(
                "SELECT quantity FROM maya_rp.material_stockpiles WHERE id = $1", pile) == 450
        finally:
            await _dropped(corp)
            await Database.close()

    async def test_the_per_tick_budget_is_the_cap(self):
        await Database.init()
        corp = await _corp()
        await _pile(50000)
        await _commodity(0)
        try:
            out = await aq._pharma_tick(SESSION)
            assert out["medical_supply_added"] == aq.MEDICAL_TRANSFER_PER_TICK, out
        finally:
            await _dropped(corp)
            await Database.close()

    async def test_the_market_is_credited_what_left_the_pile(self):
        await Database.init()
        corp = await _corp()
        await _pile(300)
        cid = await _commodity(supply=10)
        try:
            await aq._pharma_tick(SESSION)
            supply = await Database.fetchval(
                "SELECT supply FROM maya_rp.commodities WHERE id = $1", cid)
            assert supply == 310, supply
        finally:
            await _dropped(corp)
            await Database.close()


class TestTheCorporateScope:
    async def test_another_campaigns_corp_earns_nothing(self):
        """`corporations` carries a session_id and the read had no filter on it."""
        await Database.init()
        cid = asset = None
        try:
            cid = await _corp(session_id=OTHER)
            asset = await _asset(cid, income=400)
            out = await aq._pharma_tick(SESSION)
            # One shape for every path: the empty answer carries the same keys as the full one.
            assert out == {"corps": 0, "treasury_income": 0, "hub_throughput": 0,
                           "medical_supply_added": 0, "note": "no pharmaceutical corporations"}, out
            treasury = await Database.fetchval(
                "SELECT treasury FROM maya_rp.corporations WHERE id = $1", cid)
            assert treasury == 0, "another campaign's corporation earned during this campaign's tick"
        finally:
            await _dropped()
            await Database.execute("DELETE FROM maya_rp.corporate_assets WHERE id = $1", asset)
            await Database.execute("DELETE FROM maya_rp.corporations WHERE id = $1", cid)
            await Database.close()


class TestTheYardScope:
    async def test_the_name_count_is_this_campaigns(self):
        """The prefix count ran with no session filter and numbered against another campaign."""
        await Database.init()
        await Database.execute(
            "INSERT INTO maya_rp.production_queue "
            "(session_id, ship_name, ship_type, hull_class, status, priority, assigned_yard) "
            "VALUES ($1, 'review-hull-001', 'frigate', 'light', 'planned', 1, 'review yard')", OTHER)
        order = await Database.fetchval(
            "INSERT INTO maya_rp.auto_queue "
            "(session_id, yard, ship_type, hull_class, quota, ship_name_prefix, priority, active) "
            "VALUES ($1, 'review yard', 'frigate', 'light', 1, 'review-hull-', 1, TRUE) "
            "RETURNING id",
            SESSION)
        try:
            out = await aq._yard_auto_queue(SESSION)
            assert out == {"orders": 1, "enqueued": 1}, out
            name = await Database.fetchval(
                "SELECT ship_name FROM maya_rp.production_queue "
                "WHERE session_id = $1 AND assigned_yard = 'review yard'", SESSION)
            assert name == "review-hull-001", name
        finally:
            await Database.execute(
                "DELETE FROM maya_rp.production_queue WHERE assigned_yard = 'review yard'")
            await Database.execute("DELETE FROM maya_rp.auto_queue WHERE id = $1", order)
            await Database.close()


class TestTheTick:
    async def test_a_failing_half_is_logged_and_the_other_still_runs(self, monkeypatch):
        seen = []

        async def boom(session_id):
            raise RuntimeError("yard query died")

        async def fine(session_id):
            return {"corps": 0}

        monkeypatch.setattr(aq, "_yard_auto_queue", boom)
        monkeypatch.setattr(aq, "_pharma_tick", fine)
        monkeypatch.setattr(aq, "error", lambda module, message: seen.append(message))
        out = await aq.run_tick(SESSION)
        assert "yard query died" in out["yard"]["error"], out
        assert out["pharma"] == {"corps": 0}, out
        assert seen, "a half-failed tick returned a dict and said nothing at fault level"
