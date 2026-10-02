"""The Well and Aegis arithmetic in modules/well_aegis.py.

Every number here is arithmetic, so the tests check arithmetic, not vibes. The
four that matter most:

- the reserve floors at zero (a vessel cannot be overdrawn);
- a closed gash is cheaper than a major wound (the ladder is monotonic in
  severity, and both are whole drops);
- an empty reserve refuses a healing (the reserve is a real constraint, not a
  flavour text);
- no Aegis constant is a compulsion and none of them reads a mind.

The module is pure. It imports no database, no file, and no random.
"""
from __future__ import annotations

import inspect

import pytest

import modules.well_aegis as powers


class TestReserve:
    def test_the_reserve_is_full_before_anything_is_spent(self):
        assert powers.well_reserve(0) == powers.WELL_RESERVE_DROPS

    def test_the_reserve_never_goes_negative(self):
        assert powers.well_reserve(powers.WELL_RESERVE_DROPS) == 0
        assert powers.well_reserve(powers.WELL_RESERVE_DROPS * 10) == 0

    def test_a_negative_spend_is_refused(self):
        with pytest.raises(ValueError):
            powers.well_reserve(-1)

    def test_drops_and_litres_are_the_same_reserve(self):
        assert powers.WELL_RESERVE_LITRES == (
            powers.WELL_RESERVE_DROPS * powers.LITRES_PER_DROP
        )
        assert powers.WELL_RESERVE_LITRES == 120_000

    def test_the_well_anchors_are_pinned_to_the_page(self):
        """`the-sunrise.md` fixes these, so a silent drift must fail here."""
        assert powers.WELL_RESERVE_DROPS == 400
        assert powers.LITRES_PER_DROP == 300
        assert powers.WELL_RESERVE_LITRES == 120_000
        assert powers.well_cost("heat") == 0
        assert powers.well_cost("minor") == 1
        assert powers.well_cost("failing") == 40
        assert powers.WELL_REACH_PACES == 3
        assert powers.WELL_CHARGE_DECAY_OPEN_DAYS == 3
        assert powers.WELL_CHARGE_DECAY_SEALED_DAYS == 30

    def test_the_days_spends_sum(self):
        assert powers.well_spent_drops([1, 4, 13]) == 18
        assert powers.well_spent_drops([]) == 0

    def test_a_negative_spend_in_the_list_is_refused(self):
        with pytest.raises(ValueError):
            powers.well_spent_drops([1, -2])


class TestCosts:
    def test_a_closed_gash_costs_less_than_a_major_wound(self):
        gash = powers.well_cost("moderate")
        major = powers.well_cost("severe")
        assert gash < major

    def test_the_ladder_never_gets_cheaper_as_severity_rises(self):
        ladder = ["minor", "moderate", "severe", "failing"]
        costs = [powers.well_cost(cause) for cause in ladder]
        assert costs == sorted(costs)
        assert costs[0] < costs[-1]

    def test_the_burn_costs_nothing_because_the_body_stops_it(self):
        """Novel rule 1: the vessel turns toward the heat, it does not absorb it."""
        assert powers.well_cost("heat") == 0

    def test_costs_are_whole_drops_of_one_reserve(self):
        for cause in powers.WELL_COST_DROPS:
            assert isinstance(powers.well_cost(cause), int)
            assert powers.well_cost(cause) >= 0

    def test_a_cost_in_litres_is_the_drop_cost(self):
        assert powers.well_cost_litres("minor") == powers.LITRES_PER_DROP
        assert powers.well_cost_litres("failing") == 12_000

    def test_an_unknown_cause_is_refused(self):
        with pytest.raises(ValueError):
            powers.well_cost("amputation")


class TestHealing:
    def test_an_empty_reserve_refuses_healing(self):
        assert powers.well_can_heal("minor", 0) is False
        assert powers.well_can_heal("severe", 0) is False

    def test_a_reserve_at_the_price_allows_the_healing(self):
        assert powers.well_can_heal("minor", powers.well_cost("minor")) is True
        assert powers.well_can_heal("minor", powers.well_cost("minor") - 1) is False

    def test_he_cannot_heal_himself(self):
        assert powers.well_can_heal(
            "minor", powers.WELL_RESERVE_DROPS, target_is_izzat=True
        ) is False

    def test_restoration_never_becomes_transformation(self):
        for cause in powers.WELL_CANNOT:
            assert powers.well_can_heal(
                cause, powers.WELL_RESERVE_DROPS
            ) is False

    def test_death_and_the_permanent_ladder_are_in_the_refusal_list(self):
        for cause in ("death", "permanent", "scar", "ageing"):
            assert cause in powers.WELL_CANNOT


class TestPourAndCharge:
    def test_the_two_pools_cost_336_drops(self):
        """14 x 3 x 1.2 m each, so 100800 L, so 336 drops, so 84% of one day."""
        pools_litres = 2 * 14 * 3 * 1.2 * 1000
        assert pools_litres == 100_800
        assert powers.well_pour_drops(int(pools_litres)) == 336
        assert powers.well_reserve(336) == 64

    def test_pouring_rounds_a_partial_drop_up(self):
        assert powers.well_pour_drops(1) == 1
        assert powers.well_pour_drops(powers.LITRES_PER_DROP) == 1
        assert powers.well_pour_drops(powers.LITRES_PER_DROP + 1) == 2

    def test_pouring_nothing_costs_nothing(self):
        assert powers.well_pour_drops(0) == 0

    def test_a_charge_restores_whole_bodies_only(self):
        assert powers.well_charge_bodies(336) == 25
        assert powers.well_charge_bodies(powers.WELL_COST_DROPS["immersion"] - 1) == 0


class TestRecovery:
    def test_the_daily_recovery_is_monotonic(self):
        levels = [powers.well_recover(0, day) for day in range(0, 5)]
        assert levels == sorted(levels)
        assert levels[1] > levels[0]

    def test_recovery_never_passes_the_reserve(self):
        assert powers.well_recover(0, 100) == powers.WELL_RESERVE_DROPS

    def test_one_rollover_refills_the_vessel(self):
        assert powers.well_recover(0, 1) == powers.WELL_RESERVE_DROPS
        assert powers.well_recover(powers.well_reserve(336), 1) == powers.WELL_RESERVE_DROPS

    def test_nothing_banks_into_a_bigger_future_reserve(self):
        assert powers.WELL_BANKS_UNSPENT is False
        assert powers.well_recover(powers.WELL_RESERVE_DROPS, 5) == powers.WELL_RESERVE_DROPS

    def test_negative_time_and_negative_reserve_are_refused(self):
        with pytest.raises(ValueError):
            powers.well_recover(0, -1)
        with pytest.raises(ValueError):
            powers.well_recover(-1, 1)


class TestAegisLimits:
    def test_the_bands_are_the_declared_numbers(self):
        assert powers.aegis_band(powers.AEGIS_FULL_M) == "full"
        assert powers.aegis_band(powers.AEGIS_FULL_M + 1) == "hue"
        assert powers.aegis_band(powers.AEGIS_HUE_ONLY_M) == "hue"
        assert powers.aegis_band(powers.AEGIS_HUE_ONLY_M + 1) == "none"

    def test_the_aegis_ceiling_numbers_are_pinned(self):
        assert powers.AEGIS_FULL_M == 25
        assert powers.AEGIS_HUE_ONLY_M == 60
        assert powers.AEGIS_SUBJECTS_PER_LOOK == 30
        assert powers.AEGIS_READS_PER_DAY == 300
        assert powers.MARK_EXACT_M == 1_000
        assert powers.MARK_BAND_M == 100_000

    def test_a_crowd_past_thirty_reads_as_one_field(self):
        resolved, field = powers.aegis_subjects(powers.AEGIS_SUBJECTS_PER_LOOK)
        assert resolved == powers.AEGIS_SUBJECTS_PER_LOOK
        assert field is False
        resolved, field = powers.aegis_subjects(890)
        assert resolved == powers.AEGIS_SUBJECTS_PER_LOOK
        assert field is True

    def test_no_compulsion(self):
        assert powers.AEGIS_NEVER_COMPELS is True
        read = powers.aegis_read(10, 3)
        assert "action" not in read
        assert "command" not in read

    def test_no_thought_reading(self):
        for forbidden in ("thoughts", "names", "feelings", "the_future"):
            assert forbidden in powers.AEGIS_NOT_READ

    def test_the_read_returns_the_three_declared_fields(self):
        assert powers.AEGIS_READS == ("hue", "pulse", "layers")
        read = powers.aegis_read(10, 5)
        assert set(read) == {"band", "subjects", "field", "why"}

    def test_a_hull_blocks_the_read_and_a_facade_does_not_advertise_itself(self):
        assert powers.aegis_read(5, 5, "bulkhead")["band"] == "none"
        facade = powers.aegis_read(5, 5, "facade")
        assert facade["band"] == "full"
        assert "one clean layer" in facade["why"]

    def test_attention_runs_out_at_a_declared_threshold(self):
        assert powers.aegis_fatigued(powers.AEGIS_READS_PER_DAY - 1) is False
        assert powers.aegis_fatigued(powers.AEGIS_READS_PER_DAY) is True

    def test_the_limit_table_matches_the_constants(self):
        table = dict(powers.aegis_limit_table())
        assert table["full read: hue, pulse, layers"] == powers.AEGIS_FULL_M
        assert table["subjects resolved per look"] == powers.AEGIS_SUBJECTS_PER_LOOK
        assert table["mark reports an exact figure up to"] == powers.MARK_EXACT_M


class TestMark:
    def test_a_mark_takes_only_on_the_bond_action(self):
        assert powers.aegis_mark_takes(True) is True
        assert powers.aegis_mark_takes(False) is False

    def test_the_mark_reports_distance_inside_one_world(self):
        assert powers.mark_report(300) == "exact"
        assert powers.mark_report(powers.MARK_EXACT_M) == "exact"
        assert powers.mark_report(powers.MARK_EXACT_M + 1) == "band"
        assert powers.mark_report(powers.MARK_BAND_M) == "band"
        assert powers.mark_report(powers.MARK_BAND_M + 1) == "direction"

    def test_the_mark_never_crosses_a_system(self):
        assert powers.MARK_CROSSES_SYSTEM is False
        assert powers.mark_report(300, same_system=False) == "none"

    def test_another_world_in_the_same_system_gives_direction_only(self):
        assert powers.mark_report(300, same_world=False) == "direction"

    def test_the_mark_carries_no_name_and_no_feeling(self):
        for forbidden in ("name", "thought", "feeling", "future"):
            assert forbidden in powers.MARK_NEVER_REPORTS
        for reported in powers.MARK_REPORTS:
            assert reported not in powers.MARK_NEVER_REPORTS


class TestPurity:
    def test_the_module_imports_no_random(self):
        source = inspect.getsource(powers)
        assert "import random" not in source
        assert "random." not in source
        assert not hasattr(powers, "random")

    def test_the_same_input_gives_the_same_output(self):
        assert powers.well_reserve(336) == powers.well_reserve(336)
        assert powers.mark_report(5000) == powers.mark_report(5000)
        assert powers.aegis_read(10, 40) == powers.aegis_read(10, 40)
