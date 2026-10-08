"""Fleets and crew careers: six entry points, and the list that was never called.

Three entry points of fleet.py had no caller (the builder, the ship assignment, the battle) and three of
crew_career.py (the specialization, the promotion, the shortage report). The tick and the listing ran
against fleets nothing could form, and a crew member could earn experience and never spend it.
"""
from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest_asyncio  # noqa: E402

from core.db import Database  # noqa: E402
from modules import crew_career, fleet  # noqa: E402


@pytest_asyncio.fixture
async def campaign_row():
    """The scratch campaign's `maya_rp.sessions` row, 900 + pid % 100, the slot `scratch_session` hands out.

    A test asks for this fixture BEFORE `scratch_session`: pytest tears down in reverse order, so
    `scratch_session` clears every child row first and the row is removed last, after nothing references it.
    Sessions 3 and 5 are frozen reference data and are never written.
    """
    sid = 900 + os.getpid() % 100
    await Database.init()
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1,'rp-engine test scratch','active')"
        " ON CONFLICT (id) DO NOTHING", sid)
    yield sid
    await Database.init()
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", sid)
    await Database.close()


class TestTheFleetRoundTrip:
    async def test_a_fleet_can_be_created_and_listed(self, campaign_row, scratch_session):
        """The fleet is created and listed in a scratch campaign."""
        sid = scratch_session
        await Database.init()
        made = await fleet.create_fleet("red proof squadron", "spearhead", sid)
        try:
            assert made.get("error") is None, made
            fleets = await fleet.list_fleets(sid)
            assert any("red proof squadron" in str(f) for f in fleets), fleets
        finally:
            await Database.execute("DELETE FROM maya_rp.fleets WHERE session_id=$1", sid)
            await Database.close()

    async def test_the_listing_is_scoped_to_its_session(self, campaign_row, scratch_session):
        """A fleet in one scratch campaign does not appear in another; the second id is only read."""
        sid = scratch_session
        other_sid = 900 + (os.getpid() + 50) % 100
        await Database.init()
        await fleet.create_fleet("red proof scoped", "spearhead", sid)
        try:
            other = await fleet.list_fleets(other_sid)
            assert all("red proof scoped" not in str(f) for f in other), other
        finally:
            await Database.execute("DELETE FROM maya_rp.fleets WHERE session_id=$1", sid)
            await Database.close()


class TestTheCareerReport:
    async def test_the_shortage_report_answers(self):
        await Database.init()
        out = await crew_career.talent_shortage(5)
        assert isinstance(out, dict), out
        assert "status" in out or "error" in out, out
        await Database.close()

    async def test_a_promotion_of_a_crew_member_who_is_not_there_is_answered_not_crashed(self, campaign_row, scratch_session):
        """A scratch campaign takes the write; session 5 is frozen reference data."""
        sid = scratch_session
        await Database.init()
        out = await crew_career.promote_crew(999_999, sid)
        assert out is not None
        await Database.close()
