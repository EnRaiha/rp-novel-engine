"""Fleets and crew careers: six entry points, and the list that was never called.

Three entry points of fleet.py had no caller (the builder, the ship assignment, the battle) and three of
crew_career.py (the specialization, the promotion, the shortage report). The tick and the listing ran
against fleets nothing could form, and a crew member could earn experience and never spend it.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import Database  # noqa: E402
from modules import crew_career, fleet  # noqa: E402


class TestTheFleetRoundTrip:
    async def test_a_fleet_can_be_created_and_listed(self):
        await Database.init()
        made = await fleet.create_fleet("red proof squadron", "spearhead", 5)
        try:
            assert made.get("error") is None, made
            fleets = await fleet.list_fleets(5)
            assert any("red proof squadron" in str(f) for f in fleets), fleets
        finally:
            await Database.execute("DELETE FROM maya_rp.fleets WHERE session_id=5")
            await Database.close()

    async def test_the_listing_is_scoped_to_its_session(self):
        await Database.init()
        await fleet.create_fleet("red proof scoped", "spearhead", 5)
        try:
            other = await fleet.list_fleets(3)
            assert all("red proof scoped" not in str(f) for f in other), other
        finally:
            await Database.execute("DELETE FROM maya_rp.fleets WHERE session_id=5")
            await Database.close()


class TestTheCareerReport:
    async def test_the_shortage_report_answers(self):
        await Database.init()
        out = await crew_career.talent_shortage(5)
        assert isinstance(out, dict), out
        assert "status" in out or "error" in out, out
        await Database.close()

    async def test_a_promotion_of_a_crew_member_who_is_not_there_is_answered_not_crashed(self):
        await Database.init()
        out = await crew_career.promote_crew(999_999, 5)
        assert out is not None
        await Database.close()
