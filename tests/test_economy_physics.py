"""The economy physics in modules/economy_physics.py.

Every number here is arithmetic, so the tests check arithmetic, not vibes. Three
carry the unit:

  * the major-faction boundary is exact at 10 systems and at 1000 hulls, because
    a threshold that is not exact is a threshold that has already rotted;
  * a zero-speed hull is refused, because a fleet that moves at the speed of its
    slowest hull cannot be timed when the slowest hull cannot move;
  * the declared lane constant and the rows themselves derive the same hours per
    unit, independently.

Measured rows quoted below come from session 3, read-only, 2026-10-02:

    python3 scripts/cli.py query "SELECT lane_type, distance, travel_time_hours
        FROM maya_rp.sector_connections WHERE session_id=3 AND lane_type='standard'
        ORDER BY id LIMIT 1"
      id 7519 · distance 1.1047186081576141 · travel_time_hours 26.51324659578274

    python3 scripts/cli.py query "SELECT sum(distance), sum(travel_time_hours)
        FROM maya_rp.sector_connections WHERE session_id=3
        AND lane_type IN ('standard','hazardous','unstable')"
      sum distance 5652.616360642954 · sum hours 135662.79265543108

    python3 scripts/cli.py query "SELECT id, name, ship_type, crew, crew_current,
        status FROM maya_rp.ships WHERE id=444"
      TKG Simpanan · cargo_freighter · crew 29 · crew_current 0 · lost
"""
from __future__ import annotations

import inspect

import pytest

import modules.economy_physics as physics


# The four lane rows the ladder law is checked against, as stored.
STORED_LANES = (
    ("standard", 0.800, 19.20),
    ("standard", 1.697, 40.73),
    ("gate", 40.000, 18.00),
    ("hidden_thread", 240.000, 96.00),
)


class TestMajorFaction:
    def test_ten_systems_is_major_at_the_boundary(self):
        assert physics.is_major(physics.MAJOR_SYSTEMS, 0) is True

    def test_nine_systems_with_a_small_fleet_is_not_major(self):
        assert physics.is_major(physics.MAJOR_SYSTEMS - 1, physics.MAJOR_HULLS - 1) is False

    def test_a_thousand_hulls_is_major_at_the_boundary(self):
        assert physics.is_major(0, physics.MAJOR_HULLS) is True

    def test_nine_hundred_ninety_nine_hulls_is_not_major(self):
        assert physics.is_major(0, physics.MAJOR_HULLS - 1) is False

    def test_either_side_of_the_rule_makes_a_faction_major(self):
        assert physics.is_major(physics.MAJOR_SYSTEMS, 0) == physics.is_major(0, physics.MAJOR_HULLS)

    def test_the_rule_is_a_threshold_not_a_name(self):
        """A name list rots; the module owns no faction names."""
        assert not hasattr(physics, "MAJOR_NAMES")

    def test_negative_counts_are_refused(self):
        with pytest.raises(ValueError):
            physics.is_major(-1, 0)
        with pytest.raises(ValueError):
            physics.is_major(0, -1)

    def test_the_rule_reproduces_the_measured_owner_table(self):
        """Three measured owners: Iron Concord, TKG on hulls alone, a small raider."""
        assert physics.is_major(79, 2742) is True
        assert physics.is_major(1, 2078) is True
        assert physics.is_major(0, 306) is False


class TestBuildableLadder:
    def test_a_major_faction_tops_out_at_tier_four(self):
        assert physics.tier_cap(True) == physics.MAJOR_TIER_CAP == 4

    def test_everyone_else_tops_out_at_tier_three(self):
        assert physics.tier_cap(False) == physics.MINOR_TIER_CAP == 3

    def test_tier_five_is_never_allocated(self):
        assert physics.tier_cap(True) < physics.FROZEN_TIER
        assert physics.FROZEN_TIER not in physics.tier_targets(100_000, True)

    @pytest.mark.parametrize("hull_count", [0, 1, 49, 50, 265, 2742, 44263])
    def test_the_bands_always_sum_to_the_fleet(self, hull_count):
        for major in (True, False):
            targets = physics.tier_targets(hull_count, major)
            assert sum(targets.values()) == hull_count

    def test_a_minor_faction_never_reaches_tier_four(self):
        for hull_count in (0, 49, 265, 2742):
            assert physics.tier_targets(hull_count, False)[4] == 0

    def test_the_tier_four_band_starts_at_fifty_hulls_for_a_major_faction(self):
        assert physics.tier_targets(49, True)[4] == 0
        assert physics.tier_targets(50, True)[4] == 1

    def test_iron_concord_splits_2742_hulls_as_measured(self):
        assert physics.tier_targets(2742, True) == {1: 905, 2: 1371, 3: 412, 4: 54}

    def test_a_small_raider_holds_no_tier_four_hull(self):
        assert physics.tier_targets(306, False) == {1: 101, 2: 153, 3: 52, 4: 0}

    def test_negative_hull_counts_are_refused(self):
        with pytest.raises(ValueError):
            physics.tier_targets(-1, True)

    def test_allocation_returns_one_tier_per_hull(self):
        plan = physics.allocate_tiers(2742, True)
        assert len(plan) == 2742
        assert set(plan) <= set(physics.BUILDABLE_TIERS)

    def test_the_best_hull_is_placed_first(self):
        """Rank 0 is the faction's heaviest hull and takes the top band."""
        plan = physics.allocate_tiers(1000, True)
        assert plan[0] == 4
        assert plan == sorted(plan, reverse=True)

    def test_a_minor_faction_plan_never_reaches_tier_four(self):
        assert 4 not in physics.allocate_tiers(1000, False)

    def test_allocation_matches_the_band_sizes(self):
        plan = physics.allocate_tiers(2742, True)
        targets = physics.tier_targets(2742, True)
        for tier, size in targets.items():
            assert plan.count(tier) == size


class TestLossLedger:
    def test_a_listed_hull_type_prices_from_the_live_table(self):
        assert physics.hull_loss_cost("cargo_freighter") == (1_500_000, 700, 3)
        assert physics.hull_loss_cost("battle_cruiser") == (25_000_000, 12_000, 8)

    def test_an_unlisted_hull_type_falls_back(self):
        assert physics.hull_loss_cost("Reaver") == physics.DEFAULT_HULL_COST

    def test_a_positive_crew_current_is_the_loss(self):
        """A short-handed hull is not billed at full complement."""
        assert physics.crew_at_loss(200, 120) == 120

    def test_a_zeroed_crew_current_falls_back_to_the_complement(self):
        """Measured: all 437 destroyed and lost hulls carry crew_current = 0."""
        assert physics.crew_at_loss(29, 0) == 29

    def test_negative_crew_is_refused(self):
        with pytest.raises(ValueError):
            physics.crew_at_loss(-1, 0)
        with pytest.raises(ValueError):
            physics.crew_at_loss(10, -1)

    @pytest.mark.parametrize(
        "lost, recovered",
        [(0, 0), (1, 0), (10, 7), (29, 20), (30, 21), (402, 281), (1273, 891)],
    )
    def test_survivability_is_seventy_percent_floored(self, lost, recovered):
        assert physics.crew_recovered(lost) == recovered

    def test_the_replaced_crew_are_the_remainder(self):
        for lost in (0, 1, 29, 402, 1273):
            assert physics.crew_recovered(lost) + physics.crew_replaced(lost) == lost

    def test_the_split_totals_the_complement(self):
        split = physics.crew_split(402)
        assert split == {"lost": 402, "recovered": 281, "replaced": 121}
        assert split["recovered"] + split["replaced"] == split["lost"]

    def test_one_real_lost_cargo_freighter_prices_exactly(self):
        """Ship 444, TKG Simpanan, cargo_freighter, crew 29, crew_current 0."""
        ledger = physics.loss_cost("cargo_freighter", 29, 0)
        assert ledger == {
            "hull_type": "cargo_freighter",
            "credit_cost": 1_500_000,
            "alloy_cost": 700,
            "build_days": 3,
            "crew_lost": 29,
            "crew_recovered": 20,
            "crew_replaced": 9,
        }

    def test_an_unlisted_hull_still_yields_a_whole_ledger_row(self):
        ledger = physics.loss_cost("Reaver", 30, 0)
        assert ledger["credit_cost"] == physics.DEFAULT_HULL_COST[0]
        assert ledger["crew_lost"] == 30
        assert ledger["crew_replaced"] == 9

    def test_negative_crew_lost_is_refused(self):
        with pytest.raises(ValueError):
            physics.crew_recovered(-1)


class TestLaneHours:
    @pytest.mark.parametrize("lane_type, distance, stored", STORED_LANES)
    def test_the_stored_column_agrees_with_the_declared_law(self, lane_type, distance, stored):
        """Derivation one: the declared rate. Derivation two: the stored row."""
        assert round(physics.lane_hours(lane_type, distance), 2) == stored

    def test_the_measured_row_7519_is_exact(self):
        hours = physics.lane_hours("standard", 1.1047186081576141)
        assert hours == 26.51324659578274

    def test_all_three_ordinary_lane_types_share_one_rate(self):
        rates = {physics.LANE_HOURS_PER_UNIT[t] for t in ("standard", "hazardous", "unstable")}
        assert rates == {physics.HOURS_PER_UNIT} == {24.0}

    def test_a_gate_moves_forty_units_in_eighteen_hours(self):
        assert physics.lane_hours("gate", 40.0) == 18.0

    def test_a_hidden_thread_moves_two_forty_units_in_ninety_six_hours(self):
        assert physics.lane_hours("hidden_thread", 240.0) == 96.0

    def test_a_zero_distance_lane_takes_no_time(self):
        assert physics.lane_hours("standard", 0.0) == 0.0

    def test_an_unknown_lane_type_is_refused(self):
        with pytest.raises(ValueError):
            physics.lane_hours("wormhole", 1.0)

    def test_a_negative_distance_is_refused(self):
        with pytest.raises(ValueError):
            physics.lane_hours("standard", -1.0)

    def test_the_fitted_rate_matches_the_declared_rate(self):
        """The two independent derivations, on the measured aggregate."""
        fitted = physics.fitted_hours_per_unit([(5652.616360642954, 135662.79265543108)])
        assert fitted == pytest.approx(physics.HOURS_PER_UNIT, rel=1e-12)

    def test_the_fitted_rate_matches_every_lane_type(self):
        assert physics.fitted_hours_per_unit([(160.0, 72.0)]) == pytest.approx(0.45, rel=1e-12)
        assert physics.fitted_hours_per_unit([(720.0, 288.0)]) == pytest.approx(0.40, rel=1e-12)

    def test_the_fitted_rate_reproduces_a_clean_sample(self):
        assert physics.fitted_hours_per_unit([(1.0, 24.0), (0.5, 12.0)]) == 24.0

    def test_an_empty_or_zero_distance_sample_is_refused(self):
        with pytest.raises(ValueError):
            physics.fitted_hours_per_unit([])
        with pytest.raises(ValueError):
            physics.fitted_hours_per_unit([(0.0, 0.0)])


class TestClassAndFleetSpeed:
    def test_the_corvette_is_the_reference(self):
        assert physics.class_factor(physics.REFERENCE_SPEED) == 1.0

    def test_half_the_reference_speed_takes_twice_the_time(self):
        assert physics.class_factor(50.0) == 2.0

    def test_a_starforged_worldship_is_twenty_times_slower(self):
        """Measured: class Starforged, base_speed 5, 203 hulls at tiers 1 to 4."""
        assert physics.class_factor(5.0) == 20.0

    def test_a_zero_speed_hull_is_refused(self):
        with pytest.raises(ValueError):
            physics.class_factor(0)

    def test_a_negative_speed_is_refused(self):
        with pytest.raises(ValueError):
            physics.class_factor(-5)

    def test_one_hull_crosses_at_its_own_class_factor(self):
        assert physics.hull_transit_hours(24.0, physics.REFERENCE_SPEED) == 24.0
        assert physics.hull_transit_hours(24.0, 5.0) == 480.0

    def test_a_fleet_moves_at_its_slowest_hull(self):
        fleet = physics.fleet_transit_hours(24.0, [100.0, 120.0, 5.0])
        assert fleet == physics.hull_transit_hours(24.0, 5.0)

    def test_a_fleet_of_corvettes_pays_no_slowdown(self):
        assert physics.fleet_transit_hours(24.0, [100.0, 100.0]) == 24.0

    def test_the_slowest_hull_decides_regardless_of_order(self):
        a = physics.fleet_transit_hours(24.0, [5.0, 100.0, 100.0])
        b = physics.fleet_transit_hours(24.0, [100.0, 100.0, 5.0])
        assert a == b

    def test_an_empty_fleet_is_refused(self):
        with pytest.raises(ValueError):
            physics.fleet_transit_hours(24.0, [])

    def test_a_fleet_with_a_zero_speed_hull_is_refused(self):
        with pytest.raises(ValueError):
            physics.fleet_transit_hours(24.0, [100.0, 0.0])

    def test_a_negative_lane_time_is_refused(self):
        with pytest.raises(ValueError):
            physics.hull_transit_hours(-1.0, 100.0)

    def test_the_declared_tier_table_covers_the_buildable_tiers(self):
        assert set(physics.TIER_REF_SPEED) >= set(physics.BUILDABLE_TIERS)
        assert all(speed > 0 for speed in physics.TIER_REF_SPEED.values())

    def test_the_tier_figure_is_exactly_the_class_factor_on_the_declared_speed(self):
        """Reporting only: tier is not speed in the data, so the table is declared."""
        assert physics.tier_transit_hours(24.0, 1) == 24.0
        assert physics.tier_transit_hours(24.0, 5) == 24.0 * (100.0 / 70.0)

    def test_an_undeclared_tier_is_refused(self):
        with pytest.raises(ValueError):
            physics.tier_transit_hours(24.0, 11)

    def test_a_day_is_twenty_four_hours(self):
        assert physics.hours_to_days(48.0) == 2.0
        assert physics.hours_to_days(0.0) == 0.0

    def test_a_negative_duration_is_refused(self):
        with pytest.raises(ValueError):
            physics.hours_to_days(-1.0)


class TestPurity:
    def test_the_module_imports_no_world(self):
        source = inspect.getsource(physics)
        for banned in (
            "import random",
            "import psycopg2",
            "import asyncpg",
            "import os",
            "import pathlib",
            "open(",
        ):
            assert banned not in source

    def test_the_module_exposes_no_randomness(self):
        assert not hasattr(physics, "random")
        assert not hasattr(physics, "seed")
