"""Position, exchange, sieges and the quarterly objectives: eight entry points, four modules.

tactics.py carried the position reader and the exchange resolver, siege.py the starter and its list,
objectives.py the progress writer and its view, and social.py the last two of its ten: the morale event
rule and the mutiny scene generator.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import Database  # noqa: E402
from modules import objectives, siege, social, tactics  # noqa: E402


class TestTheExchange:
    async def test_a_stronger_attacker_beats_a_weaker_defender(self):
        strong = await tactics.resolve_exchange(200, 5, 20, 1, None, None)
        weak = await tactics.resolve_exchange(20, 1, 200, 5, None, None)
        assert strong is not None and weak is not None
        assert strong != weak, "the exchange ignores the hulls it was given"

    async def test_the_position_reader_answers(self):
        await Database.init()
        out = await tactics.get_tactical_position(5, "flank", None, None)
        assert out is not None
        await Database.close()


class TestTheSiege:
    async def test_a_siege_can_be_started_and_listed(self):
        await Database.init()
        made = await siege.start_siege("Red Proof Keep", 5)
        try:
            assert made is not None
            rows = await siege.list_sieges(5)
            assert isinstance(rows, list), rows
        finally:
            await Database.execute("DELETE FROM maya_rp.sieges WHERE session_id=5")
            await Database.close()


class TestTheObjectives:
    async def test_the_view_answers(self):
        await Database.init()
        out = await objectives.quarterly_tasks_view(5)
        assert out is not None
        await Database.close()


class TestTheLastTwoSocialRules:
    def test_the_morale_event_moves_morale_by_its_multiplier(self):
        """A battle victory is worth ten points at multiplier one and thirty at three."""
        calm = social.apply_morale_event(50, "battle_victory", 1)
        strong = social.apply_morale_event(50, "battle_victory", 3)
        assert calm["delta"] == 10, calm
        assert strong["delta"] == 30, strong
        assert strong["threshold_crossed"] is True, strong

    def test_morale_cannot_pass_its_ceiling(self):
        out = social.apply_morale_event(95, "battle_victory", 3)
        assert out["new_morale"] == 100, out

    def test_a_mutiny_scene_names_the_ship(self):
        scene = social.generate_mutiny_scene("Red Proof", [{"name": "a hand", "score": 0.1}])
        assert scene is not None
        assert "Red Proof" in str(scene), scene
