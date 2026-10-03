"""Module review tests for modules/economy_physics.py.

The module is pure arithmetic with its own test file already, and reading it
whole under the protocol found no wrong number. It found two structural
defects that a value test cannot see:

1. `HULL_COST`, `DEFAULT_HULL_COST` and the 0.7 survivability fraction are a
   SECOND copy of the live price list in `scripts/fleet_refill.py`, with nothing
   asserting the two agree. A hull repriced in the live script would desync the
   ledger in silence. These tests pin the parity.
2. The lane law (24.0 hours per unit) was restated in `modules/voyage.py` as
   `GRID_HOURS_PER_UNIT = 24.0`. `modules/unity.py` calls a third copy of that
   constant a defect, so voyage now imports the one this module owns.

The copies also disagree about rounding, which the docstring did not say:
`fleet_refill.py` writes `round(c * 0.7)` and this module floors. The last test
pins that divergence so it stays visible.

No database, no writes: every assertion is arithmetic or source text.
"""
from __future__ import annotations

import inspect

import pytest

import modules.economy_physics as physics
from scripts.fleet_refill import COST as SCRIPT_COST
from scripts.fleet_refill import SURVIVABILITY as SCRIPT_SURVIVABILITY


# ── 1. The duplicate price list is pinned to its live copy ───────────────

def test_the_price_list_matches_the_live_refill_script():
    assert physics.HULL_COST == SCRIPT_COST, (
        "the ledger and scripts/fleet_refill.py disagree about what a hull costs")


def test_the_fallback_price_matches_the_script():
    source = inspect.getsource(__import__("scripts.fleet_refill", fromlist=["x"]))
    assert "(1_500_000, 800, 3)" in source or "(1500000, 800, 3)" in source
    assert physics.DEFAULT_HULL_COST == (1_500_000, 800, 3)


def test_the_survivability_fraction_is_shared():
    fraction = physics.CREW_SURVIVABILITY_NUM / physics.CREW_SURVIVABILITY_DEN
    assert fraction == SCRIPT_SURVIVABILITY == 0.7


def test_the_two_copies_round_the_shared_fraction_differently():
    """The divergence the docstring now declares, kept visible on purpose.

    This module floors: a 5-crew hull recovers 3. `fleet_refill.py` rounds the
    same hull to 4. Reconciling them is a campaign decision, so the test pins
    both answers rather than choosing one.
    """
    diverging = [c for c in range(0, 60)
                 if physics.crew_recovered(c) != round(c * SCRIPT_SURVIVABILITY)]
    assert diverging, "the two copies agreed; the docstring note is now stale"
    assert physics.crew_recovered(5) == 3
    assert round(5 * SCRIPT_SURVIVABILITY) == 4


# ── 2. One owner for the lane law ────────────────────────────────────────

def test_voyage_imports_the_lane_law_instead_of_restating_it():
    import ast

    from modules import voyage

    assert voyage.GRID_HOURS_PER_UNIT == physics.HOURS_PER_UNIT
    tree = ast.parse(inspect.getsource(voyage))
    assignments = [
        node for node in tree.body
        if isinstance(node, ast.Assign)
        and any(getattr(t, "id", None) == "GRID_HOURS_PER_UNIT" for t in node.targets)
    ]
    assert len(assignments) == 1, "more than one definition of the lane law"
    value = assignments[0].value
    assert isinstance(value, ast.Name) and value.id == "HOURS_PER_UNIT", ast.dump(value)


def test_voyage_divides_by_the_shared_day_length():
    from modules import voyage

    source = inspect.getsource(voyage)
    assert "/ 24.0" not in source, "a second copy of the day length is back"
    assert "HOURS_PER_DAY" in source


def test_unity_keeps_reading_the_same_constant():
    import modules.unity as unity

    assert unity.HOURS_PER_DAY == physics.HOURS_PER_DAY
    assert unity.lane_hours("gate", 40.0) == physics.lane_hours("gate", 40.0)


# ── Contract the module claims ───────────────────────────────────────────

@pytest.mark.parametrize("hull_count", [0, 1, 49, 50, 67, 100, 999, 1000, 2742, 44269, 10**6])
@pytest.mark.parametrize("major", [False, True])
def test_the_bands_always_sum_to_the_fleet(hull_count, major):
    bands = physics.tier_targets(hull_count, major)
    assert sum(bands.values()) == hull_count
    assert min(bands.values()) >= 0


def test_the_fourth_tier_band_is_two_percent_of_the_fleet():
    # Declared: n4 = floor(0.02 N) for a major faction, 0 for a minor one.
    assert physics.tier_targets(49, True)[4] == 0
    assert physics.tier_targets(50, True)[4] == 1
    assert physics.tier_targets(99, True)[4] == 1
    assert physics.tier_targets(100, True)[4] == 2
    assert physics.tier_targets(2742, True)[4] == 54          # 2742 // 50
    assert physics.tier_targets(2742, False)[4] == 0


def test_the_ladder_is_exact_across_a_wide_range():
    for major in (False, True):
        for n in range(0, 3000):
            bands = physics.tier_targets(n, major)
            assert sum(bands.values()) == n, (n, major, bands)


def test_a_minor_faction_never_holds_a_fourth_tier_and_a_major_one_tops_at_four():
    assert physics.tier_targets(5000, major=False)[4] == 0
    assert physics.tier_cap(False) == 3 and physics.tier_cap(True) == 4
    assert max(physics.allocate_tiers(5000, True)) == 4


def test_one_ledger_row_is_whole_for_one_hull():
    row = physics.loss_cost("cargo_freighter", 29, 0)
    assert row["hull_type"] == "cargo_freighter"
    assert (row["credit_cost"], row["alloy_cost"], row["build_days"]) == physics.HULL_COST["cargo_freighter"]
    assert row["crew_recovered"] + row["crew_replaced"] == row["crew_lost"] == 29


def test_a_hull_type_outside_the_live_list_prices_at_the_shared_fallback():
    # heavy_cruiser and science_vessel exist in maya_rp.ships and in neither copy
    # of the price list. The fallback is the same in both, which is what matters.
    assert physics.hull_loss_cost("heavy_cruiser") == physics.DEFAULT_HULL_COST
    assert physics.hull_loss_cost("heavy_cruiser") == physics.hull_loss_cost("not a hull at all")


def test_the_lane_law_reproduces_the_rows_it_was_derived_from():
    # sum(distance) 5652.616360642954 · sum(hours) 135662.79265543108, session 3
    fitted = physics.fitted_hours_per_unit([(5652.616360642954, 135662.79265543108)])
    assert fitted == pytest.approx(physics.HOURS_PER_UNIT)


def test_a_gate_is_not_priced_at_the_ordinary_lane_rate():
    assert physics.lane_hours("gate", 40.0) == 18.0
    assert physics.lane_hours("hidden_thread", 240.0) == 96.0
    assert physics.lane_hours("standard", 1.0) == 24.0
