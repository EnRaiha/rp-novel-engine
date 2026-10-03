"""Well al-Wakr and Aegis Sight review: what reading `modules/well_aegis.py` in full turned up.

One defect, and one finding the module cannot fix from where it sits.

The module is pure arithmetic: no database, no files, no randomness. Its own docstring carries every
formula, so the contract test below walks those formulas rather than describing them again.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

import modules.well_aegis as powers  # noqa: E402


class TestTheTwoSpellingsOfOneBarrier:
    """`AEGIS_NOT_READ` says `a_construct`; `AEGIS_BLOCKED_BY` says `construct`."""

    def test_the_refusal_vocabulary_blocks_the_read(self):
        for name in powers.AEGIS_NOT_READ:
            if name in ("thoughts", "names", "feelings", "the_future"):
                continue  # what the eye cannot answer is not a barrier to light
            out = powers.aegis_read(5.0, 3, name)
            assert out["band"] == "none" or "one clean layer" in out["why"], (name, out)

    def test_both_spellings_answer_the_same_way(self):
        def verdict(name):
            out = powers.aegis_read(5.0, 3, name)
            return out["band"], out["subjects"], out["field"]

        assert verdict("construct") == verdict("a_construct")
        assert verdict("dead_body") == verdict("a_dead_body")
        assert verdict("facade") == verdict("a_working_facade")

    def test_the_alias_table_names_only_the_two_lists_it_reconciles(self):
        spelled = set(powers.AEGIS_NOT_READ) & set(powers.AEGIS_BLOCKED_ALIASES)
        assert spelled == {"a_construct", "a_dead_body", "a_working_facade"}, spelled

    def test_an_unblocked_read_is_unchanged(self):
        out = powers.aegis_read(5.0, 3)
        assert out["band"] == "full" and out["subjects"] == 3 and out["field"] is False


class TestTheFormulasTheDocstringStates:
    def test_the_reserve_is_a_sum_over_the_day_with_a_floor_of_zero(self):
        assert powers.well_spent_drops([]) == 0
        assert powers.well_spent_drops([1, 3, 13]) == 17
        assert powers.well_reserve(0) == powers.WELL_RESERVE_DROPS
        assert powers.well_reserve(powers.WELL_RESERVE_DROPS + 50) == 0

    def test_the_two_pools_cost_eighty_four_percent_of_a_day(self):
        assert powers.well_pour_drops(100800) == 336
        assert powers.well_pour_drops(0) == 0
        assert powers.well_pour_drops(1) == 1, "a partial drop is a whole drop"

    def test_a_spend_or_a_distance_below_zero_raises(self):
        with pytest.raises(ValueError):
            powers.well_spent_drops([-1])
        with pytest.raises(ValueError):
            powers.aegis_band(-1)
        with pytest.raises(ValueError):
            powers.mark_report(-1)

    def test_the_vessel_never_spends_on_heat_and_never_heals_itself(self):
        assert powers.well_cost("heat") == 0
        assert powers.well_can_heal("heat", 0) is True
        assert powers.well_can_heal("minor", 0) is False
        assert powers.well_can_heal("minor", 400, target_is_izzat=True) is False

    def test_an_unknown_cause_refuses_rather_than_pricing_at_zero(self):
        with pytest.raises(ValueError):
            powers.well_cost("a_sunburn")
        with pytest.raises(ValueError):
            powers.well_can_heal("a_sunburn", 400)

    def test_recovery_is_monotonic_and_capped(self):
        assert powers.well_recover(0, 0) == 0
        assert powers.well_recover(10, 1) == powers.WELL_RESERVE_DROPS
        assert powers.well_recover(300, 0) == 300
        with pytest.raises(ValueError):
            powers.well_recover(10, -1)

    def test_the_bands_do_not_overlap(self):
        assert powers.aegis_band(25) == "full"
        assert powers.aegis_band(25.1) == "hue"
        assert powers.aegis_band(60) == "hue"
        assert powers.aegis_band(60.1) == "none"

    def test_a_crowd_past_thirty_is_one_field(self):
        assert powers.aegis_subjects(30) == (30, False)
        assert powers.aegis_subjects(31) == (30, True)

    def test_the_mark_answers_by_where_the_body_is(self):
        assert powers.mark_report(500) == "exact"
        assert powers.mark_report(5000) == "band"
        assert powers.mark_report(200000) == "direction"
        assert powers.mark_report(500, same_world=False) == "direction"
        assert powers.mark_report(500, same_system=False) == "none"
