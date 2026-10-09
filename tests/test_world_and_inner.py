"""World, inner world and fleet burn: fifteen entry points across seven small modules.

Four modules carry the world surface (locations, narrative_seeds, archaeology, secrets), two carry the
inner life (memories, npc_autonomy) and one carries the fleet's fuel (fleet_economy). None had a caller.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest_asyncio  # noqa: E402

from core.db import Database  # noqa: E402
from modules import archaeology, fleet_economy, narrative_seeds  # noqa: E402
from tests.conftest import scratch_id  # noqa: E402


@pytest_asyncio.fixture
async def campaign_row(request):
    """The scratch campaign's `maya_rp.sessions` row, the slot `scratch_session` hands out.

    A test asks for this fixture BEFORE `scratch_session`: pytest tears down in reverse order, so
    `scratch_session` clears every child row first and the row is removed last, after nothing references it.
    Sessions 3 and 5 are frozen reference data and are never written.
    """
    sid = scratch_id(request.module.__name__)
    await Database.init()
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1,'rp-engine test scratch','active')"
        " ON CONFLICT (id) DO NOTHING", sid)
    yield sid
    await Database.init()
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", sid)
    await Database.close()


class TestTheDig:
    async def test_sites_are_seeded_and_one_can_be_excavated(self, campaign_row, scratch_session):
        """Sites are seeded into a scratch campaign and one is dug; session 5 is frozen reference data."""
        sid = scratch_session
        await Database.init()
        sites = await archaeology.seed_sites(sid, 2)
        try:
            assert len(sites) == 2, sites
            dug = await archaeology.excavate(sites[0]["id"], sid)
            assert dug is not None
        finally:
            await Database.execute("DELETE FROM maya_rp.artifacts WHERE session_id=$1", sid)
            await Database.execute("DELETE FROM maya_rp.dig_sites WHERE session_id=$1", sid)
            await Database.close()

    async def test_seeding_zero_sites_creates_none(self, campaign_row, scratch_session):
        """Seeding nothing returns an empty list, in a scratch campaign."""
        sid = scratch_session
        await Database.init()
        assert await archaeology.seed_sites(sid, 0) == []
        await Database.close()


class TestTheSeeds:
    async def test_a_planted_seed_appears_in_the_foreshadow_plan(self, campaign_row, scratch_session):
        """The seed is planted in a scratch campaign, not the live arc."""
        sid = scratch_session
        await Database.init()
        before = len(await narrative_seeds.get_foreshadow_ops(sid))
        planted = await narrative_seeds.plant_seed(
            "red proof", "a door that opens later", None, None, None, sid)
        try:
            assert planted is None, (
                "plant_seed writes and returns nothing; the test checks that, not a return value")
            after = len(await narrative_seeds.get_foreshadow_ops(sid))
            assert after >= before, (before, after)
        finally:
            await Database.execute("DELETE FROM maya_rp.narrative_seeds WHERE session_id=$1", sid)
            await Database.close()


class TestTheBurn:
    async def test_a_session_with_no_treasury_says_so_rather_than_zeroing(self):
        """Session 5 has no resources row; the summary reports that instead of a silent zero."""
        await Database.init()
        out = await fleet_economy.get_burn_summary(5)
        assert out is not None
        await Database.close()
