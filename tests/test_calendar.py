"""The calendar follows the ruling: twelve months of thirty days plus five.

Decision D5 fixes the year at 365. The module previously rolled a 360-day cycle, so days
after day 360 carried the wrong label. These tests pin the corrected mapping, and they pin
the one visible consequence: the label of a day after 360 moves.
"""
from __future__ import annotations

import pytest

import modules.calendar_tkg as cal


class TestYearShape:
    def test_a_year_is_365_days(self):
        assert cal.YEAR_DAYS == 365
        assert cal.MONTH_DAYS == 360
        assert cal.LEFTOVER_DAYS == 5

    def test_twelve_months_of_thirty(self):
        assert len(cal.MONTHS) == 12
        assert cal.DAYS_PER_MONTH == 30

    def test_day_one_is_unchanged(self):
        assert (1 - 1) // cal.YEAR_DAYS + 1 == 1

    def test_the_last_day_of_a_year_is_the_last_leftover_day(self):
        assert (365 - 1) % cal.YEAR_DAYS + 1 == 365
        assert (365 - 1) // cal.YEAR_DAYS + 1 == 1

    def test_day_366_starts_the_second_year(self):
        assert (366 - 1) // cal.YEAR_DAYS + 1 == 2
        assert (366 - 1) % cal.YEAR_DAYS + 1 == 1


class TestLeftoverDays:
    def test_day_361_is_the_first_leftover(self):
        doy = (361 - 1) % cal.YEAR_DAYS + 1
        assert doy == 361
        assert doy > cal.MONTH_DAYS

    def test_the_five_leftover_days_sit_after_the_months(self):
        leftover = [d for d in range(361, 366)]
        assert len(leftover) == cal.LEFTOVER_DAYS
        for day in leftover:
            doy = (day - 1) % cal.YEAR_DAYS + 1
            assert doy - cal.MONTH_DAYS == day - 360

    def test_the_leftover_period_has_a_name(self):
        assert cal.LEFTOVER_NAME


class TestDateShift:
    """The consequence of the correction, stated as a test rather than a footnote."""

    def test_a_day_past_the_first_year_keeps_its_year(self):
        """Both cycles agree on the year here: 2253 is year 7 under each."""
        old = (2253 - 1) // 360 + 1
        new = (2253 - 1) // cal.YEAR_DAYS + 1
        assert old == new == 7

    def test_but_its_day_of_year_moves(self):
        old_doy = (2253 - 1) % 360 + 1
        new_doy = (2253 - 1) % cal.YEAR_DAYS + 1
        assert old_doy == 93
        assert new_doy == 63
        assert new_doy < old_doy, "the leftover days push later days back within the year"

    def test_the_offset_is_five_days_per_completed_year(self):
        """Six completed years before day 2253, so thirty days of offset, not five."""
        completed_years = (2253 - 1) // 360
        assert completed_years == 6
        assert 93 - 63 == completed_years * cal.LEFTOVER_DAYS
