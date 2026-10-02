"""Communications latency, the unity ceiling and the stance drift.

`modules/unity.py` is pure arithmetic, so these tests check arithmetic. Four
carry the unit:

  * the latency law reuses `economy_physics.lane_hours` and holds no second copy
    of 24.0, 0.45 or 0.40, because `voyage.py` already carries two unreconciled
    rates and a third would be a defect;
  * the latency term is inert at lag 0, so the shipped formula is exactly the
    shipped formula plus nothing;
  * a natural faction pressed from outside reads more united than the same
    faction unpressed, and a larger faction never reads more united than a
    smaller one with the same inputs;
  * the drift term is bounded, never crosses zero, and returns its input
    unchanged at lag 0.

Worked rows are read-only measurements from 2026-10-02. They are fixtures here,
not assertions about the database: hull counts move between measurements (U8
recorded TKG 2,078 and Iron Concord 2,742; measured today 2,080 and 2,744).

    python3 scripts/cli.py query "SELECT f.id, f.name, f.origin, f.doctrine,
        f.stance_score, f.systems_held, count(s.id) AS hulls
        FROM maya_rp.factions f LEFT JOIN maya_rp.ships s ON s.faction_id=f.id
        GROUP BY 1,2,3,4,5,6"
      TKG            natural science_tech  +0.2633  1 system  2,080 hulls
      Iron Concord   imposed science_tech  -0.0753 79 systems 2,744 hulls
      Limbah Compact natural balance       +0.1933  0 systems 1,445 hulls
"""
from __future__ import annotations

import ast
import pathlib

import pytest

import modules.economy_physics as physics
import modules.unity as unity

MODULE_PATH = pathlib.Path(unity.__file__)


class TestLatency:
    def test_orthogonal_hop_is_one_day(self):
        assert unity.lane_latency_days("standard", 1.0) == 1.0

    def test_diagonal_hop_is_root_two_days(self):
        assert unity.lane_latency_days("standard", 2 ** 0.5) == pytest.approx(1.4142135623730951)

    def test_gate_is_the_type_override_not_the_distance(self):
        """40 units at 0.45 hours per unit is 18 hours: 0.75 day, not 40 days."""
        assert unity.lane_latency_days("gate", 40.0) == 0.75

    def test_hidden_thread_is_four_days(self):
        assert unity.lane_latency_days("hidden_thread", 240.0) == 4.0

    def test_zero_distance_is_zero(self):
        assert unity.lane_latency_days("standard", 0.0) == 0.0

    def test_ansible_is_explicit_and_ten_times_faster(self):
        courier = unity.lane_latency_days("standard", 1.0)
        ansible = unity.lane_latency_days("standard", 1.0, sigma=unity.SIGNAL_ANSIBLE)
        assert ansible == pytest.approx(courier / 10.0)

    def test_courier_is_the_default_sigma(self):
        assert unity.lane_latency_days("standard", 1.0) == unity.lane_latency_days(
            "standard", 1.0, sigma=unity.SIGNAL_COURIER
        )

    def test_zero_sigma_is_refused(self):
        with pytest.raises(ValueError):
            unity.lane_latency_days("standard", 1.0, sigma=0.0)

    def test_latency_from_hours_matches_the_lane_function(self):
        assert unity.latency_from_hours(24.0) == unity.lane_latency_days("standard", 1.0)

    def test_path_sums_its_lanes(self):
        path = [{"lane_type": "standard", "distance": 1.0},
                {"lane_type": "gate", "distance": 40.0},
                {"lane_type": "hidden_thread", "distance": 240.0}]
        assert unity.path_latency_days(path) == pytest.approx(1.0 + 0.75 + 4.0)

    def test_empty_path_is_zero(self):
        assert unity.path_latency_days([]) == 0.0

    def test_mean_of_an_empty_sequence_is_refused(self):
        with pytest.raises(ValueError):
            unity.mean_latency_days([])

    def test_days_ceil_rounds_up(self):
        assert unity.latency_days_ceil(1.0) == 1
        assert unity.latency_days_ceil(1.0001) == 2
        assert unity.latency_days_ceil(4.0) == 4

    def test_arrival_day_is_send_day_plus_whole_days(self):
        assert unity.arrival_game_day(100, 0.75) == 101
        assert unity.arrival_game_day(100, 4.0) == 104

    def test_lag_fraction_caps_at_one_month(self):
        assert unity.lag_fraction(15.0) == 0.5
        assert unity.lag_fraction(30.0) == 1.0
        assert unity.lag_fraction(33.185) == 1.0

    def test_lane_types_match_economy_physics(self):
        assert set(unity.LANE_TYPES) == set(physics.LANE_HOURS_PER_UNIT)

    def test_the_lane_law_is_reused_not_restated(self):
        """The lane law keeps exactly one home. The strongest proof is identity:
        the module's `lane_hours` is the same function object as the one in
        `economy_physics`. A second 24.0 literal is the same defect in a
        different place, and this module binds no lane rate under its own name.
        (0.45 is not scanned: it is also a legitimate `ORIGIN_BASE` value.)"""
        assert unity.lane_hours is physics.lane_hours
        assert unity.HOURS_PER_DAY == physics.HOURS_PER_DAY
        for name in ("LANE_HOURS_PER_UNIT", "HOURS_PER_UNIT",
                     "GATE_HOURS_PER_UNIT", "HIDDEN_HOURS_PER_UNIT"):
            assert not hasattr(unity, name), f"{name} is restated in modules/unity.py"
        tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
        for statement in tree.body:
            if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant):
                continue  # the docstring may name the constants
            for node in ast.walk(statement):
                if isinstance(node, ast.Constant) and isinstance(node.value, float):
                    assert node.value != 24.0, "24.0 is restated in modules/unity.py"

    def test_module_imports_no_io_and_no_randomness(self):
        source = MODULE_PATH.read_text(encoding="utf-8")
        for banned in ("import random", "import datetime", "import os", "psycopg2", "open("):
            assert banned not in source, f"{banned} in a module that must stay pure"


class TestUnity:
    TKG = dict(hull_count=2080, systems_held=1, stance_score=0.2633,
               origin="natural", doctrine="science_tech")
    IRON_CONCORD = dict(hull_count=2744, systems_held=79, stance_score=-0.0753,
                        origin="imposed", doctrine="science_tech")
    LIMBAH_COMPACT = dict(hull_count=1445, systems_held=0, stance_score=0.1933,
                          origin="natural", doctrine="balance")

    def test_worked_rows(self):
        assert unity.unity(**self.TKG) == 0.5386
        assert unity.unity(**self.IRON_CONCORD) == 0.0238
        assert unity.unity(**self.LIMBAH_COMPACT) == 0.4612

    def test_lag_zero_is_inert(self):
        """The distance half contributes nothing until a lag exists: the shipped
        formula is the non-distance formula and no more."""
        for row in (self.TKG, self.IRON_CONCORD, self.LIMBAH_COMPACT):
            assert unity.unity(**row, lag=0.0) == unity.unity(**row)
            assert unity.span(row["systems_held"], 0.0) == 0.6 * unity.reach(row["systems_held"])

    def test_lag_moves_a_big_faction_down(self):
        assert unity.unity(**self.IRON_CONCORD, lag=1.0) < unity.unity(**self.IRON_CONCORD)

    def test_larger_faction_never_reads_more_united(self):
        """Same inputs, more holdings: the logarithmic span can only subtract."""
        small = unity.unity(500, 1, 0.0, "natural", "balance")
        large = unity.unity(500, 40, 0.0, "natural", "balance")
        assert large <= small

    def test_natural_pressure_raises_unity(self):
        unpressed = unity.unity(**self.TKG, pressure=0.0)
        pressed = unity.unity(**self.TKG, pressure=1.0)
        assert pressed > unpressed
        assert pressed - unpressed == pytest.approx(unity.ORIGIN_PRESSURE_GAIN["natural"], abs=1e-4)

    def test_imposed_pressure_barely_moves(self):
        # 10 holdings, 200 hulls: enough headroom that neither end of the
        # pressure range hits the 0..1 clamp.
        row = dict(hull_count=200, systems_held=10, stance_score=-0.5,
                   origin="imposed", doctrine="science_tech")
        unpressed = unity.unity(**row, pressure=0.0)
        pressed = unity.unity(**row, pressure=1.0)
        assert pressed > unpressed
        assert pressed - unpressed == pytest.approx(unity.ORIGIN_PRESSURE_GAIN["imposed"], abs=1e-4)

    def test_sponsored_pressure_lowers_unity(self):
        patronised = dict(hull_count=200, systems_held=2, stance_score=-0.5,
                          origin="sponsored", doctrine="magic")
        assert unity.unity(**patronised, pressure=1.0) < unity.unity(**patronised, pressure=0.0)

    def test_default_pressure_comes_from_the_stance(self):
        assert unity.pressure_default(1.0) == 0.0
        assert unity.pressure_default(-1.0) == 1.0
        assert unity.pressure_default(0.0) == 0.5

    def test_pressure_is_clamped(self):
        assert unity.unity(**self.TKG, pressure=5.0) == unity.unity(**self.TKG, pressure=1.0)
        assert unity.unity(**self.TKG, pressure=-5.0) == unity.unity(**self.TKG, pressure=0.0)

    def test_grip_is_gated_on_a_holding(self):
        """Hulls garrison ground. With no ground the row gets no grip, which is
        what lets the dock quarrel with itself unpressed."""
        assert unity.grip(1445, 0) == 0.0
        assert unity.grip(1445, 0) < unity.grip(1445, 1)
        assert unity.grip(100_000, 1) == 1.0

    def test_reach_normalises_100_holdings(self):
        assert unity.reach(0) == 0.0
        assert unity.reach(99) == pytest.approx(1.0, abs=0.005)
        assert unity.reach(40) > unity.reach(4)

    def test_the_compact_quarrels_unpressed_and_agrees_pressed(self):
        unpressed = unity.unity(**self.LIMBAH_COMPACT, pressure=0.0)
        pressed = unity.unity(**self.LIMBAH_COMPACT, pressure=1.0)
        assert unity.unity_band(unpressed) == "fractured"
        assert unity.unity_band(pressed) == "unanimous"

    def test_bands_at_their_edges(self):
        assert unity.unity_band(1.0) == "unanimous"
        assert unity.unity_band(0.75) == "unanimous"
        assert unity.unity_band(0.7499) == "united"
        assert unity.unity_band(0.55) == "united"
        assert unity.unity_band(0.40) == "strained"
        assert unity.unity_band(0.25) == "divided"
        assert unity.unity_band(0.2499) == "fractured"
        assert unity.unity_band(0.0) == "fractured"

    def test_result_stays_inside_zero_and_one(self):
        for row in (self.TKG, self.IRON_CONCORD, self.LIMBAH_COMPACT,
                    dict(hull_count=0, systems_held=0, stance_score=-1.0,
                         origin="natural", doctrine="unaligned")):
            assert 0.0 <= unity.unity(**row) <= 1.0
        # The clamp is real at both ends, not decorative.
        assert unity.unity(0, 100, -1.0, "imposed", "unaligned") == 0.0
        assert unity.unity(10_000, 1, 1.0, "imposed", "science_tech") <= 1.0

    def test_unknown_origin_and_doctrine_fall_back(self):
        assert unity.unity(**{**self.TKG, "origin": None}) == unity.unity(
            **{**self.TKG, "origin": "imposed"}
        )
        assert unity.unity(**{**self.TKG, "doctrine": "heretic"}) == unity.unity(
            **{**self.TKG, "doctrine": unity.DEFAULT_DOCTRINE}
        )

    def test_a_missing_stance_reads_zero(self):
        assert unity.unity(**{**self.TKG, "stance_score": None}) == unity.unity(
            **{**self.TKG, "stance_score": 0.0}
        )

    def test_lag_is_capped(self):
        assert unity.unity(**self.IRON_CONCORD, lag=5.0) == unity.unity(**self.IRON_CONCORD, lag=1.0)


class TestDrift:
    def test_lag_zero_returns_the_score_unchanged(self):
        for score in (-1.0, -0.5700, -0.0753, 0.0, 0.1933, 0.8253, 1.0):
            assert unity.drift(score, 0.0) == score

    def test_full_lag_subtracts_the_constant_in_magnitude(self):
        assert unity.drift(0.8253, 1.0) == pytest.approx(0.4753)
        assert unity.drift(-0.5700, 1.0) == pytest.approx(-0.2200)
        assert unity.drift(-1.0000, 1.0) == pytest.approx(-0.6500)

    def test_a_small_score_reads_neutral(self):
        assert unity.drift(0.1933, 1.0) == 0.0
        assert unity.drift(-0.0753, 1.0) == 0.0

    def test_half_lag_subtracts_half(self):
        assert unity.drift(0.8253, 0.5) == pytest.approx(0.8253 - 0.5 * unity.DRIFT_PER_FULL_LAG)

    def test_the_term_is_bounded(self):
        for step in range(-200, 201):
            score = step / 200.0
            for lag in (0.0, 0.25, 0.5, 1.0, 3.0):
                out = unity.drift(score, lag)
                assert abs(out) <= abs(score)
                assert -1.0 <= out <= 1.0

    def test_it_never_crosses_zero(self):
        """Sign safety: a faction the capital calls friendly cannot become
        hostile just by being far away."""
        for step in range(-200, 201):
            score = step / 200.0
            out = unity.drift(score, 1.0)
            if score > 0:
                assert out >= 0.0
            elif score < 0:
                assert out <= 0.0
            else:
                assert out == 0.0

    def test_a_maximally_distant_enemy_still_reads_hostile(self):
        """0.35 clears the widest central band without flattening the hostile
        tail: The Den is -1.0000 live and stays hostile at a full lag."""
        assert unity.drift(-1.0, 1.0) == pytest.approx(-0.65)

    def test_lag_is_capped(self):
        assert unity.drift(0.9, 10.0) == unity.drift(0.9, 1.0)
