#!/usr/bin/env python3
"""Review of `core/reputation.py`.

This module has **no caller anywhere in the tree**: no import of `core.reputation`, and no
`Reputation(...)` or `.apply(...)` outside this file and this test. The `reputation` the rest of the
engine talks about is a column on `maya_rp.factions`, written by diplomacy, espionage, darkops and
threat modules. So the three-axis engine has never scored a single deed, and its caller-less status
is pinned here rather than wired from inside a review: choosing the caller changes what the engine
does and that is the King's call, the same treatment `core/briefing.py` and `BattleEngine` got.

Two real defects, both reachable the day it is wired:

1. The outer band of every label map ended at a number: fame stopped at 100, brutality at 998. Fame
   is never clamped and grows by 10 a victory, so a campaign walks past the last tuple and `_find`
   answered `"Unknown"` for its title.
2. `IMPACTS.get(action_type, {}).get(severity, {zeroes})` turned an unknown action, and an unknown
   severity for a known action, into a no-op that returned the unchanged state as though the deed
   had been recorded. Severities are per-action (`mercy` has only `standard`), so a typo is the
   ordinary way in.

Reported, not changed, with a test that pins the current rule: `dark_deeds` records three of the
twelve actions, and `execute_leader` and `family_executed` cost the same brutality as `execute`
without being recorded. Which deeds count as dark is a design decision.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from core.reputation import IMPACTS, Reputation  # noqa: E402


class TestTheLabelsHaveNoCeiling:
    def test_a_fame_beyond_the_last_tuple_still_has_a_title(self):
        """Fame is never clamped, so 101 is not an edge case, it is the next victory."""
        for fame, title in ((74, "Respected"), (75, "Legendary Hero"),
                            (100, "Legendary Hero"), (101, "Legendary Hero"),
                            (5_000, "Legendary Hero")):
            rep = Reputation(fame=fame)
            assert rep._public()["title"] == title, (fame, rep._public())

    def test_a_fame_below_the_floor_still_has_a_title(self):
        rep = Reputation(fame=-5_000)
        assert rep._public()["title"] == "Galactic Terror", rep._public()

    def test_brutality_above_the_last_tuple_still_has_a_label(self):
        rep = Reputation(brutality=5_000)
        assert rep._public()["brutality_label"] == "Unforgivable", rep._public()

    def test_the_floor_of_each_map_is_still_what_it_was(self):
        assert Reputation(brutality=0)._public()["brutality_label"] == "Clean"
        assert Reputation(brutality=999)._public()["brutality_label"] == "Unforgivable"
        assert Reputation(moral=100)._public()["alignment"] == "Paragon"
        assert Reputation(moral=0)._public()["alignment"] == "Monster"
        assert Reputation(fame=-75)._public()["title"] == "Galactic Terror"


class TestAnUnknownValueIsRefusedByName:
    def test_an_unknown_action_names_itself(self):
        rep = Reputation()
        with pytest.raises(ValueError) as exc:
            rep.apply("tortur", "standard")
        assert "tortur" in str(exc.value), exc.value
        assert "torture" in str(exc.value), exc.value
        assert rep.fame == 0 and rep.moral == 50 and rep.brutality == 0, "state moved on a refusal"

    def test_an_unknown_severity_names_the_action_and_what_it_accepts(self):
        rep = Reputation()
        with pytest.raises(ValueError) as exc:
            rep.apply("mercy", "brutal")
        message = str(exc.value)
        assert "brutal" in message and "mercy" in message and "standard" in message, message
        assert rep.moral == 50, "state moved on a refusal"


class TestTheReportsItClaims:
    def test_a_public_deed_moves_all_three_axes_and_reports_them(self):
        rep = Reputation(fame=0, moral=50, brutality=0)
        out = rep.apply("execute", "brutal", context="the council saw it")
        assert rep.fame == -15 and rep.moral == 30 and rep.brutality == 30, rep
        assert out["public"]["title"] == "Neutral", out
        assert out["public"]["brutality_label"] == "Bloodstained", out
        assert out["private"]["dark_deeds"] == 1, out

    def test_a_secret_deed_moves_hidden_brutality_and_not_the_public_axes(self):
        rep = Reputation(fame=0, moral=50, brutality=0)
        out = rep.apply("torture", "enhanced", secrecy="secret")
        assert rep.fame == 0 and rep.moral == 50 and rep.brutality == 0, rep
        assert rep.hidden_brutality == 5, rep
        assert out["private"]["hidden_brutality"] == 5, out

    def test_moral_is_clamped_and_brutality_is_floored(self):
        rep = Reputation(moral=2, brutality=0)
        rep.apply("torture", "brutal")   # moral -12 floors at 0, brutality +15
        assert rep.moral == 0 and rep.brutality == 15, rep
        rep.apply("mercy", "standard")   # brutality -3 → 12, moral +5 → 5
        assert rep.moral == 5 and rep.brutality == 12, rep

    def test_the_dark_deed_rule_covers_three_of_the_twelve_actions(self):
        """Pins the rule as it stands, not as it should be.

        `execute_leader` (`brutal`: brutality +20, moral -18) and `family_executed` (brutality +15)
        cost what `execute` costs and are not recorded as dark deeds. Which deeds count is a design
        decision, so the current rule is pinned and the finding goes to the lead.
        """
        recorded = set()
        for action in IMPACTS:
            rep = Reputation()
            for severity in IMPACTS[action]:
                rep.apply(action, severity)
            if rep.dark_deeds:
                recorded.add(action)
        assert recorded == {"torture", "execute", "betrayal"}, recorded
        assert rep_darkness()["execute_leader"] > rep_darkness()["betrayal"], (
            "execute_leader is the milder deed, so the rule may be deliberate; re-measure")

    def test_the_redemption_field_has_no_writer(self):
        """`self_redemption` is read by `_private` and written by nothing, so the percent is 0."""
        rep = Reputation(hidden_brutality=10)
        assert rep._private()["redemption_pct"] == 0, rep._private()
        assert rep._private()["redemption_pct"] == min(
            100, int(rep.self_redemption / max(1, rep.hidden_brutality) * 100))


def rep_darkness() -> dict:
    """The brutality each action's darkest severity costs, for the comparison above."""
    return {action: max(v["brutality"] for v in IMPACTS[action].values()) for action in IMPACTS}


class TestItHasNoCaller:
    def test_no_production_module_imports_it(self):
        """The pin that says the engine has never scored a deed through this module.

        The `reputation` the rest of the engine uses is a column on `maya_rp.factions`. Wiring this
        engine in changes play, so the decision goes to the King and this test fails the day someone
        wires it, which is the signal that the pin can be replaced by tests of the real paths.
        """
        users = []
        for folder in ("modules", "core", "scripts"):
            for path in sorted((ROOT / folder).glob("*.py")):
                if path.name == "reputation.py":
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                if "core.reputation" in text or "core import reputation" in text:
                    users.append(str(path.relative_to(ROOT)))
        assert users == [], f"reputation now has a caller; test the path instead: {users}"
