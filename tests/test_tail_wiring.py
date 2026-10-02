"""The last ten: one caller-less function in each of ten modules.

ship_generation, session_rituals, image_gen, physical_state, decision_models, dramatic_structure,
name_gen, memory, campaign and refit. Each was the only door its module was missing.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import campaign, dramatic_structure, memory, session_rituals  # noqa: E402
from core.db import Database  # noqa: E402
from core.decision_models import pirate_event_features  # noqa: E402
from modules import image_gen, physical_state, refit, ship_generation  # noqa: E402


class TestTheRituals:
    async def test_the_close_is_a_sentence(self):
        await Database.init()
        out = await session_rituals.generate_close(5)
        assert isinstance(out, str) and out, out
        await Database.close()

    async def test_session_start_answers(self):
        await Database.init()
        out = await dramatic_structure.session_start(5)
        assert out is None or isinstance(out, dict), out
        await Database.close()


class TestTheGenerators:
    async def test_an_image_prompt_names_a_scene_type(self):
        await Database.init()
        out = await image_gen.generate_prompt(5)
        assert isinstance(out, dict) and out.get("scene_type"), out
        await Database.close()

    async def test_the_physical_state_reader_answers(self):
        await Database.init()
        out = await physical_state.get_state(1, 5)
        assert isinstance(out, dict), out
        await Database.close()

    async def test_a_ship_batch_can_be_generated_and_removed(self):
        await Database.init()
        made = await ship_generation.generate_batch("Cruiser", 2, "warship", 2, "RedProof", 5)
        try:
            assert made is not None
        finally:
            await Database.execute("DELETE FROM maya_rp.ships WHERE session_id=5 AND name LIKE 'RedProof%'")
            await Database.close()


class TestTheModels:
    def test_pirate_features_come_from_a_record(self):
        out = pirate_event_features({"name": "Red Proof Raider", "tier": 2, "aggression": 7})
        assert out is not None

    def test_an_empty_pirate_record_is_handled(self):
        assert pirate_event_features({}) is not None


class TestTheLastThree:
    async def test_triggered_endings_answers(self):
        await Database.init()
        out = await campaign.triggered_endings(5)
        assert isinstance(out, list), out
        await Database.close()

    async def test_recall_answers(self):
        await Database.init()
        out = await memory.store_and_recall(999_999, "t", "d", "q", 5)
        assert out is not None
        await Database.close()

    async def test_refitting_an_unknown_ship_is_answered(self):
        await Database.init()
        out = await refit.upgrade_ship("no such ship at all", 5)
        assert out is not None
        await Database.close()
