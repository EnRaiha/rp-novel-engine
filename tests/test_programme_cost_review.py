"""Programme cost review: the module read in full, formula by formula.

No defect was found in this module. The review walked the twelve-item checklist and the contract
below is what it checked: every formula the docstring states, at its boundary, against the constants
the module declares. One finding goes to the lead rather than into the module: `payer_named` is
called by nothing, in this engine or in its test suite, which is why it is exercised here.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

import modules.programme_cost as cost  # noqa: E402


class TestTheCalendar:
    def test_the_year_is_the_one_the_docstring_names(self):
        assert cost.DAYS_PER_YEAR == 365
        assert cost.RP_PER_TIER == 5 * cost.DAYS_PER_YEAR == 1825

    def test_the_tier_range_is_closed_at_both_ends(self):
        assert cost.target_days(5) == 1825
        assert cost.target_days(9) == 1825 * 5
        for outside in (4, 10, 0, -1):
            with pytest.raises(ValueError):
                cost.target_days(outside)

    def test_days_are_monotonic_in_tier(self):
        days = [cost.target_days(t) for t in range(5, 10)]
        assert days == sorted(days) and len(set(days)) == 5


class TestTheRate:
    def test_a_missing_lead_is_the_only_zero(self):
        assert cost.progress_per_day(False, 3, "science_tech") == 0
        assert cost.progress_per_day(True, 0, "magic") == 1

    def test_the_lab_stops_at_the_declared_cap(self):
        assert cost.progress_per_day(True, cost.LAB_LEVEL_CAP, "") == 1 + cost.LAB_LEVEL_CAP
        assert cost.progress_per_day(True, cost.LAB_LEVEL_CAP + 4, "") == 1 + cost.LAB_LEVEL_CAP
        assert cost.progress_per_day(True, -2, "") == 1

    def test_doctrine_never_lowers_the_rate(self):
        for lab in range(0, 5):
            assert cost.progress_per_day(True, lab, "science_tech") >= cost.progress_per_day(True, lab, "magic")

    def test_the_ceiling_is_five_programme_days_a_day(self):
        assert cost.progress_per_day(True, cost.LAB_LEVEL_CAP, "science_tech") == 5


class TestTheAdvance:
    def test_the_same_game_day_twice_adds_nothing(self):
        once = cost.advance(100, 10, 20, 3, 1825)
        twice = cost.advance(once, 20, 20, 3, 1825)
        assert once == 130 and twice == once

    def test_a_clock_that_goes_backwards_adds_nothing(self):
        assert cost.advance(100, 20, 10, 3, 1825) == 100

    def test_progress_stops_at_the_target(self):
        assert cost.advance(1820, 0, 999, 5, 1825) == 1825

    def test_a_stalled_programme_still_clamps_to_its_target(self):
        assert cost.advance(9999, 0, 5, 0, 1825) == 1825
        assert cost.advance(100, 0, 5, 0, 1825) == 100


class TestTheCredit:
    def test_the_price_is_the_rate_times_the_days_plus_the_lab_plant(self):
        assert cost.target_credits(5, 0) == 20 * 1825
        assert cost.target_credits(5, 3) == 20 * 1825 + 2000 * 3

    def test_the_default_lab_count_is_the_cap(self):
        assert cost.target_credits(5) == cost.target_credits(5, cost.LAB_LEVEL_CAP)

    def test_the_price_carries_the_tier_refusal(self):
        with pytest.raises(ValueError):
            cost.target_credits(4)
        with pytest.raises(ValueError):
            cost.target_credits(5, -1)


class TestTheKnife:
    def test_the_score_is_the_documented_sum(self):
        assert cost.kill_score(2, False, False, 1) == 60
        assert cost.kill_score(2, True, False, 1) == 80
        assert cost.kill_score(2, True, True, 5) == 60 + 20 - 25 - 15

    def test_importance_only_counts_from_the_declared_rung(self):
        assert cost.kill_score(2, False, False, cost.GUARD_IMPORTANCE_AT - 1) == 60
        assert cost.kill_score(2, False, False, cost.GUARD_IMPORTANCE_AT) == 45

    def test_spend_outside_the_range_is_refused(self):
        for step in (0, 4, -1):
            with pytest.raises(ValueError):
                cost.kill_score(step, False, False, 1)

    def test_every_outcome_is_reachable_from_the_score_alone(self):
        assert cost.kill_outcome(cost.KILL_COMPLETE_AT) == "complete"
        assert cost.kill_outcome(cost.KILL_ATTEMPTED_AT) == "attempted"
        assert cost.kill_outcome(cost.KILL_ATTEMPTED_AT - 1) == "failed"

    def test_a_full_spend_on_a_bare_target_completes(self):
        assert cost.kill_outcome(cost.kill_score(3, True, False, 1)) == "complete"


class TestTheSetback:
    def test_the_caps_are_the_ones_the_docstring_names(self):
        assert cost.setback_days(99999, "complete") == 1825
        assert cost.setback_days(99999, "attempted") == 912
        assert cost.setback_days(99999, "failed") == 0

    def test_a_programme_that_barely_started_loses_only_what_it_had(self):
        assert cost.setback_days(10, "complete") == 10
        assert cost.setback_days(0, "complete") == 0

    def test_an_outcome_outside_the_vocabulary_is_refused(self):
        with pytest.raises(ValueError):
            cost.setback_days(10, "nearly")

    def test_five_years_is_the_complete_setback_at_rate_one(self):
        assert cost.lost_years(cost.setback_days(99999, "complete"), 1) == 5.0

    def test_a_stalled_programme_loses_no_wall_clock_years(self):
        assert cost.lost_years(1825, 0) == 0.0


class TestTheInvestigation:
    def test_the_score_is_the_documented_sum(self):
        assert cost.investigation_score(False, False, "complete") == 20
        assert cost.investigation_score(True, False, "complete") == 60
        assert cost.investigation_score(True, True, "failed") == 100

    def test_the_two_thresholds_are_the_declared_ones(self):
        assert cost.case_opens(40) is True and cost.case_opens(39) is False
        assert cost.payer_named(60) is True and cost.payer_named(59) is False

    def test_a_registered_payer_names_him_before_any_death_is_weighed(self):
        score = cost.investigation_score(True, False, "complete")
        assert cost.case_opens(score) and cost.payer_named(score)

    def test_an_outcome_outside_the_vocabulary_is_refused(self):
        with pytest.raises(ValueError):
            cost.investigation_score(True, True, "nearly")
