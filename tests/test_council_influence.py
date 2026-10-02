"""The influence and role rules: six more council functions, and a field that never existed.

`generate_mystery_hooks` reads `cabinet_control` from each territory. The territory table has no such
column, so fed real rows the function always saw its default of 100 and could never produce a hook. The
CLI computes the control with the module's own `calculate_territory_control` rather than inventing it,
which also wires the two functions to each other.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules import council  # noqa: E402


class TestTheHookGenerator:
    def test_a_territory_the_cabinet_barely_holds_produces_a_hook(self):
        hooks = council.generate_mystery_hooks(
            [{"system_name": "Red Proof Reach", "cabinet_control": 10}])
        assert len(hooks) == 1, hooks
        assert "Red Proof Reach" in hooks[0]["hook"], hooks

    def test_a_well_held_territory_produces_none(self):
        assert council.generate_mystery_hooks(
            [{"system_name": "Quiet Anchorage", "cabinet_control": 80}]) == []

    def test_the_control_it_reads_is_the_one_the_sibling_computes(self):
        """The two functions agree, which is what makes the CLI's enrichment honest."""
        territory = {"status": "controlled", "controlling_faction": "Federation",
                     "governor_name": "Maya", "fleet_presence": 0}
        control = council.calculate_territory_control(territory, [])
        assert control >= 50, control
        hooks = council.generate_mystery_hooks([{**territory, "system_name": "Held", "cabinet_control": control}])
        assert hooks == [], hooks


class TestTheWifeModes:
    def test_a_seat_that_is_not_a_wife_is_simply_executing(self):
        assert council.get_wife_status({"is_wife": False}) == council.WIFE_MODES["EXECUTING"]

    def test_absence_hands_the_seat_emergency_mode(self):
        assert council.get_wife_status({"is_wife": True}, 0, 24) == council.WIFE_MODES["EMERGENCY"]

    def test_active_decrees_mean_the_wife_is_executing(self):
        assert council.get_wife_status({"is_wife": True}, 1, 0) == council.WIFE_MODES["EXECUTING"]


class TestTheInfluenceRules:
    def test_exposure_risk_rises_with_the_shadow(self):
        low = council.shadow_exposure_risk(10, 90)
        high = council.shadow_exposure_risk(90, 10)
        assert high["exposure_chance"] > low["exposure_chance"], (low, high)

    def test_only_a_grand_consul_may_override(self):
        assert council.consul_override(None)["can_override"] is False
        assert council.consul_override({"tier": 1})["can_override"] is False
        assert council.consul_override({"tier": 0})["can_override"] is True
