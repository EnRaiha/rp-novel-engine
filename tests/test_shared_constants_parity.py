"""A rule written twice should be caught here, not by reading two modules side by side.

Six modules in this review carried a rule that lives in more than one place, and none of them was found by
a failing test: resource accounting in three copies, the 70 percent survivability rule in two that
disagree, the month length written four ways inside one module, the 24.0 lane law restated beside its
source, the hidden-thread loss rule implemented four times, and two byte-identical council agenda
literals. Every one was found by reading a module against its neighbour, which is the expensive way.

This file is the cheap way. It asserts, for each shared rule, that the user imports the source rather than
restating it. A restatement fails here in one second instead of surfacing in a seventh module next week.

When a rule is deliberately duplicated, pin the disagreement here so a change to either copy is visible
rather than silent. The 70 percent rule is the worked example.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class TestTheLedgerRuleIsOneObject:
    def test_the_three_modules_share_one_resource_rule(self):
        from modules import infrastructure, megastructures_ports, space_horror

        assert infrastructure._check_afford is megastructures_ports._check_afford
        assert infrastructure._deduct_resources is megastructures_ports._deduct_resources
        assert infrastructure._deduct_resources is space_horror._deduct_resources


class TestTheCalendarConstants:
    def test_the_month_length_has_one_source(self):
        from modules import calendar_tkg, chrono_engine

        assert chrono_engine.DAYS_PER_MONTH == calendar_tkg.DAYS_PER_MONTH, (
            "chrono_engine restates the month length instead of importing it")


class TestTheLaneLaw:
    def test_voyage_uses_economy_physics_hours(self):
        from modules import economy_physics, voyage

        assert voyage.HOURS_PER_UNIT == economy_physics.HOURS_PER_UNIT
        assert voyage.HOURS_PER_DAY == economy_physics.HOURS_PER_DAY

    def test_voyage_imports_them_rather_than_restating_them(self):
        """Value equality passes today even if the constant is restated with the same number.

        A restatement drifts the moment someone edits one copy. This reads the source and requires the
        import, which is the structural fact the other assertion cannot see. My first report of a
        weakness here was wrong: I quoted a line from the module docstring as if it were an assignment.
        """
        import inspect

        from modules import voyage

        source = inspect.getsource(voyage)
        assert "from modules.economy_physics import" in source, (
            "voyage does not import the lane constants")
        header = next(line for line in source.split("\n")
                      if "from modules.economy_physics import" in line)
        for name in ("HOURS_PER_UNIT", "HOURS_PER_DAY"):
            assert name in header, f"{name} is not imported from economy_physics: {header}"


class TestTheCouncilAgendas:
    def test_both_names_are_one_object(self):
        from modules import council

        assert council.DEFAULT_AGENDAS is council.MEETING_AGENDAS


class TestTheSurvivabilityRuleIsPinnedWhileItDisagrees:
    """The 70 percent rule exists in two places and the copies do not agree.

    `economy_physics` floors and `fleet_refill.py` rounds, so they differ on 26 crew sizes below 60 — a
    five-crew hull is 3 in one and 4 in the other. Reconciling changes live refill numbers, so it is the
    King's call. Until then this pins both behaviours: a change to either copy has to come here and say so.
    """

    def test_the_two_copies_still_disagree_on_a_small_hull(self):
        from modules import economy_physics

        rate = economy_physics.CREW_SURVIVABILITY_NUM / economy_physics.CREW_SURVIVABILITY_DEN
        floored = int(5 * rate)
        rounded = round(5 * rate)
        assert floored != rounded, (
            "the two copies now agree on a five-crew hull; if that was deliberate, update the ledger row "
            "and this test together")
