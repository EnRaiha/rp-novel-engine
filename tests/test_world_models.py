"""The deterministic world models: stance bands and the scale allowance.

Only the pure functions are tested here. The database-writing paths in the three
scripts need integration tests against a scratch schema, and those are still owed.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

import modules.unity as unity

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


# The published weights as they stood before Fasa 5.3. The drift term is added
# to the table, not to this list: every one of these values is unchanged.
PUBLISHED_WEIGHTS = {
    "trust": +0.30, "reputation": +0.10, "fear_of_player": -0.15,
    "trade_aggressiveness": -0.20, "pirate_aggressiveness": -0.25, "is_pirate": -0.40,
    "doctrine:science_tech": +0.05, "doctrine:magic": 0.00, "doctrine:balance": +0.10,
    "doctrine:unaligned": -0.05, "origin:natural": +0.10, "origin:imposed": +0.05,
    "origin:sponsored": -0.10, "standing:kingdom": +0.35, "standing:friendly": +0.40,
    "standing:allied": +0.60, "standing:neutral": 0.00, "standing:suspicious": -0.20,
    "standing:hostile": -0.55, "standing:unknown": -0.10,
}


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


class TestStanceDrift:
    """Fasa 5.3: the drift term shrinks a stance toward zero by distance.

    The install is inert at lag 0, and that is the property that makes it safe:
    every live stance is reproduced to 4 decimals with the term switched off.
    """

    # Every fixture below is the shape `_faction()` builds. Named rows in the
    # doc are the live ones; these are the same input vectors, so the test does
    # not need the database.
    ROWS = {
        "friendly": _faction(),
        "allied": _faction(standing="allied", trust=80),
        "hostile": _faction(standing="hostile"),
        "wary": _faction(standing="suspicious"),
        "hired_pirate": _faction(trust="none", reputation=0, fear_of_player=80,
                                 trade_aggressiveness=0.9, pirate_aggressiveness=0.71,
                                 is_pirate=True, doctrine="unaligned", origin="sponsored",
                                 standing="allied"),
    }

    def test_lag_zero_reproduces_the_model_exactly(self):
        for name, row in self.ROWS.items():
            assert stance_model.stance(row, lag=0.0) == stance_model.stance(row), name

    def test_lag_zero_is_the_default_argument(self):
        row = self.ROWS["friendly"]
        assert stance_model.stance(row) == stance_model.stance(row, lag=0.0)

    def test_lag_zero_reproduces_a_sweep_of_rows(self):
        """A grid, not one row: origin and doctrine both move the raw sum, and
        the drift must be a no-op on all of it."""
        for origin in ("natural", "imposed", "sponsored"):
            for doctrine in ("science_tech", "magic", "balance", "unaligned"):
                for standing in ("allied", "friendly", "neutral", "suspicious", "hostile"):
                    row = _faction(origin=origin, doctrine=doctrine, standing=standing)
                    assert stance_model.stance(row, lag=0.0) == stance_model.stance(row)

    def test_a_nonzero_lag_moves_some_bands(self):
        moved = {name for name, row in self.ROWS.items()
                 if stance_model.stance(row, lag=1.0)["band"] != stance_model.stance(row)["band"]}
        assert moved == {"friendly", "hostile", "hired_pirate"}

    @pytest.mark.parametrize("name,base_band,lagged_band", [
        ("friendly", "friendly", "neutral"),
        ("hostile", "hostile", "wary"),
        ("hired_pirate", "wary", "neutral"),
        ("allied", "allied", "allied"),
        ("wary", "neutral", "neutral"),
    ])
    def test_band_at_zero_and_at_full_lag(self, name, base_band, lagged_band):
        row = self.ROWS[name]
        assert stance_model.stance(row)["band"] == base_band
        assert stance_model.stance(row, lag=1.0)["band"] == lagged_band

    def test_the_drift_shrinks_by_the_declared_constant(self):
        row = self.ROWS["allied"]
        base = stance_model.stance(row)["score"]
        lagged = stance_model.stance(row, lag=1.0)["score"]
        assert base - lagged == pytest.approx(stance_model.DRIFT_PER_FULL_LAG)

    def test_the_drift_never_crosses_zero(self):
        for row in self.ROWS.values():
            base = stance_model.stance(row)["score"]
            lagged = stance_model.stance(row, lag=1.0)["score"]
            assert (lagged > 0) == (base > 0) or lagged == 0.0

    def test_a_full_lag_cannot_flip_a_friend_into_an_enemy(self):
        """The live shape: a faction the capital calls friendly reads neutral at
        a month out, never hostile."""
        row = _faction(standing="friendly")
        assert stance_model.stance(row)["score"] > 0
        assert stance_model.stance(row, lag=1.0)["score"] >= 0.0

    def test_a_lag_beyond_one_is_capped(self):
        row = self.ROWS["allied"]
        assert stance_model.stance(row, lag=5.0) == stance_model.stance(row, lag=1.0)

    def test_every_published_weight_is_unchanged(self):
        for key, value in PUBLISHED_WEIGHTS.items():
            assert stance_model.WEIGHTS[key] == value, key

    def test_the_drift_is_published_in_the_same_table(self):
        assert stance_model.WEIGHTS["drift:lag"] == -stance_model.DRIFT_PER_FULL_LAG
        assert stance_model.NORMALISER == 0.75

    def test_the_drift_is_a_second_stage_not_a_summed_term(self):
        """The table publishes it, the raw sum does not read it. Without this
        distinction the 0.35 would be summed 1:1 and the whole model would move."""
        assert len(PUBLISHED_WEIGHTS) + 1 == len(stance_model.WEIGHTS)
        assert "drift:lag" not in PUBLISHED_WEIGHTS

    def test_the_drift_law_has_one_home(self):
        assert stance_model.drift is unity.drift
        assert stance_model.DRIFT_PER_FULL_LAG == unity.DRIFT_PER_FULL_LAG


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
