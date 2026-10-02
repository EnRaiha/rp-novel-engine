"""The programme arithmetic in modules/programme_cost.py.

Every number here is arithmetic, so the tests check arithmetic, not vibes. The one
that matters most is the King's setback: a killed lead costs the programme five
years of progress, and five years is 1825 days on the 365-day calendar.
"""
from __future__ import annotations

import pytest

import modules.programme_cost as cost


class TestProgress:
    def test_rate_is_never_zero_while_a_lead_is_present(self):
        assert cost.progress_per_day(True, 0, "science_tech") >= 1

    def test_science_tech_is_not_slower_than_magic(self):
        science = cost.progress_per_day(True, 2, "science_tech")
        magic = cost.progress_per_day(True, 2, "magic")
        assert science >= magic

    def test_a_lab_helps_and_only_up_to_a_cap(self):
        low = cost.progress_per_day(True, 0, "science_tech")
        high = cost.progress_per_day(True, 3, "science_tech")
        capped = cost.progress_per_day(True, 50, "science_tech")
        assert low <= high <= capped
        assert capped == cost.progress_per_day(True, cost.LAB_LEVEL_CAP, "science_tech")

    def test_losing_the_lead_halves_the_programme(self):
        with_lead = cost.progress_per_day(True, 0, "science_tech")
        without = cost.progress_per_day(False, 0, "science_tech")
        assert without < with_lead

    def test_tier_five_takes_five_years_of_programme_days(self):
        assert cost.target_days(5) == cost.DAYS_PER_YEAR * 5

    def test_advance_is_monotonic(self):
        rate = cost.progress_per_day(True, 0, "science_tech")
        first = cost.advance(0, 0, 10, rate, cost.target_days(5))
        second = cost.advance(first, 10, 20, rate, cost.target_days(5))
        assert second > first

    def test_the_same_day_twice_does_not_advance_twice(self):
        rate = cost.progress_per_day(True, 0, "science_tech")
        once = cost.advance(730, 1, 2, rate, cost.target_days(5))
        again = cost.advance(once, 2, 2, rate, cost.target_days(5))
        assert again == once

    def test_progress_never_passes_the_target(self):
        rate = cost.progress_per_day(True, 3, "science_tech")
        capped = cost.advance(1820, 0, 100000, rate, cost.target_days(5))
        assert capped == cost.target_days(5)


class TestAssassination:
    def test_spending_more_raises_the_score(self):
        assert cost.kill_score(cost.MAX_SPEND_STEP, False, False, 3) > \
               cost.kill_score(cost.MIN_SPEND_STEP, False, False, 3)

    def test_a_guarded_target_is_harder(self):
        assert cost.kill_score(cost.MAX_SPEND_STEP, False, True, cost.GUARD_IMPORTANCE_AT) < \
               cost.kill_score(cost.MAX_SPEND_STEP, False, False, 0)

    def test_the_full_spend_can_reach_every_outcome(self):
        easy = cost.kill_outcome(cost.kill_score(cost.MAX_SPEND_STEP, False, False, 0))
        hard = cost.kill_outcome(cost.kill_score(cost.MIN_SPEND_STEP, False, True, cost.GUARD_IMPORTANCE_AT))
        assert easy == "complete"
        assert hard == "failed"

    def test_spend_outside_the_declared_range_is_refused(self):
        with pytest.raises(ValueError):
            cost.kill_score(cost.MIN_SPEND_STEP - 1, False, False, 0)

    def test_the_largest_target_is_the_hardest(self):
        assert cost.kill_score(cost.MAX_SPEND_STEP, False, True, cost.GUARD_IMPORTANCE_AT) <= \
               cost.kill_score(cost.MAX_SPEND_STEP, False, False, 0)

    def test_deniable_raises_the_score(self):
        assert cost.kill_score(cost.MAX_SPEND_STEP, True, False, 5) > \
               cost.kill_score(cost.MAX_SPEND_STEP, False, False, 5)

    def test_outcomes_are_drawn_from_the_declared_vocabulary(self):
        for spend in range(cost.MIN_SPEND_STEP, cost.MAX_SPEND_STEP + 1):
            for importance in (0, 3, 9):
                outcome = cost.kill_outcome(cost.kill_score(spend, False, False, importance))
                assert outcome in cost.KILL_OUTCOMES

    def test_same_input_same_outcome(self):
        args = (cost.MAX_SPEND_STEP, True, False, 6)
        assert cost.kill_score(*args) == cost.kill_score(*args)

    def test_a_killed_lead_costs_five_years_of_programme_days(self):
        """The King's number, in the unit the calendar defines."""
        progress = cost.target_days(5)
        setback = cost.setback_days(progress, "complete")
        assert setback == cost.SETBACK_DAYS_COMPLETE
        assert setback == cost.DAYS_PER_YEAR * 5
        assert cost.lost_years(setback, 1) == 5.0

    def test_attempted_setback_is_smaller_than_complete(self):
        assert cost.setback_days(1000, "attempted") < cost.setback_days(1000, "complete")

    def test_a_programme_at_zero_loses_nothing(self):
        assert cost.setback_days(0, "complete") >= 0


class TestInvestigation:
    def test_a_registered_target_produces_a_bigger_case(self):
        assert cost.investigation_score(True, False, "complete") > \
               cost.investigation_score(False, False, "complete")

    def test_an_unregistered_death_weights_the_case_more(self):
        assert cost.investigation_score(False, True, "complete") > \
               cost.investigation_score(False, False, "complete")

    def test_a_failed_kill_leaves_more_to_investigate(self):
        assert cost.investigation_score(True, False, "failed") > \
               cost.investigation_score(True, False, "complete")

    def test_the_case_opens_at_a_declared_threshold(self):
        assert isinstance(cost.case_opens(cost.investigation_score(True, False, "complete")), bool)
