"""The deterministic world models: stance bands and the scale allowance.

Only the pure functions are tested here. The database-writing paths in the three
scripts need integration tests against a scratch schema, and those are still owed.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


stance_model = _load("faction_stance")
scale_model = _load("faction_scale")


def _faction(**overrides) -> dict:
    base = {"trust": 50, "reputation": 50, "fear_of_player": 0, "trade_aggressiveness": 0.5,
            "pirate_aggressiveness": 0.5, "is_pirate": False, "doctrine": "balance",
            "origin": "imposed", "standing": "neutral", "status": "active"}
    base.update(overrides)
    return base


class TestStanceModel:
    def test_is_deterministic(self):
        faction = _faction(trust=71, reputation=33, standing="suspicious")
        assert stance_model.stance(faction) == stance_model.stance(faction)

    def test_declared_allied_reads_allied(self):
        assert stance_model.stance(_faction(standing="allied", trust=80))["band"] == "allied"

    def test_declared_hostile_reads_hostile(self):
        assert stance_model.stance(_faction(standing="hostile"))["band"] == "hostile"

    def test_piracy_drags_a_friendly_standing_down(self):
        free = stance_model.stance(_faction(standing="friendly"))["score"]
        pirate = stance_model.stance(_faction(standing="friendly", is_pirate=True,
                                              pirate_aggressiveness=0.9))["score"]
        assert pirate < free

    def test_score_stays_inside_the_band_range(self):
        for trust in (0, 50, 100):
            score = stance_model.stance(_faction(trust=trust, standing="allied"))["score"]
            assert -1.0 <= score <= 1.0

    def test_hired_pirate_can_still_read_wary(self):
        """The live case, values read from the row itself: Echo Nest Wraiths declares
        allied because the crown pays it, and the model still reads wary because its
        hulls keep raiding. trust is the string 'none' in that row, which is exactly the
        mixed-vocabulary problem the normalisation pass has to fix."""
        verdict = stance_model.stance(_faction(trust="none", reputation=0, fear_of_player=80,
                                               trade_aggressiveness=0.9, pirate_aggressiveness=0.71,
                                               is_pirate=True, doctrine="unaligned",
                                               origin="sponsored", standing="allied"))
        assert verdict["band"] == "wary"
        assert round(verdict["score"], 3) == -0.37


class TestScaleAllowance:
    @pytest.mark.parametrize("held,expected", [(1, 1), (9, 1), (10, 2), (19, 2), (20, 3), (109, 3)])
    def test_minor_cap(self, held, expected):
        assert scale_model.minor_allowance(held) == expected

    def test_major_factions_are_named_with_a_ceiling(self):
        assert max(scale_model.MAJOR.values()) <= 10
        assert all(value >= 5 for value in scale_model.MAJOR.values())

    def test_setia_is_not_established_in_both_spellings(self):
        assert "Setia Empire" in scale_model.NOT_ESTABLISHED
        assert "Setia Empire (Kingdom)" in scale_model.NOT_ESTABLISHED
