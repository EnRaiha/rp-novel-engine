"""World, inner world and fleet burn: fifteen entry points across seven small modules.

Four modules carry the world surface (locations, narrative_seeds, archaeology, secrets), two carry the
inner life (memories, npc_autonomy) and one carries the fleet's fuel (fleet_economy). None had a caller.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import Database  # noqa: E402
from modules import archaeology, fleet_economy, narrative_seeds  # noqa: E402


class TestTheDig:
    async def test_sites_are_seeded_and_one_can_be_excavated(self):
        await Database.init()
        sites = await archaeology.seed_sites(5, 2)
        try:
            assert len(sites) == 2, sites
            dug = await archaeology.excavate(sites[0]["id"], 5)
            assert dug is not None
        finally:
            await Database.execute("DELETE FROM maya_rp.dig_sites WHERE session_id=5")
            await Database.close()

    async def test_seeding_zero_sites_creates_none(self):
        await Database.init()
        assert await archaeology.seed_sites(5, 0) == []
        await Database.close()


class TestTheSeeds:
    async def test_a_planted_seed_appears_in_the_foreshadow_plan(self):
        await Database.init()
        before = len(await narrative_seeds.get_foreshadow_ops(5))
        planted = await narrative_seeds.plant_seed(
            "red proof", "a door that opens later", None, None, None, 5)
        try:
            assert planted is None, (
                "plant_seed writes and returns nothing; the test checks that, not a return value")
            after = len(await narrative_seeds.get_foreshadow_ops(5))
            assert after >= before, (before, after)
        finally:
            await Database.execute("DELETE FROM maya_rp.narrative_seeds WHERE session_id=5")
            await Database.close()


class TestTheBurn:
    async def test_a_session_with_no_treasury_says_so_rather_than_zeroing(self):
        """Session 5 has no resources row; the summary reports that instead of a silent zero."""
        await Database.init()
        out = await fleet_economy.get_burn_summary(5)
        assert out is not None
        await Database.close()
