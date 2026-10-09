"""Module review: crew_system.py.

Two defects, and one thing that looked like a defect and was not. `produce_crew` credited a pool that
no session had: the update matched nothing and the function still returned the campus output as produced.
`consume_crew` found and updated a ship by id alone, while ships carries a session, so crew could be
consumed for another campaign's hull. And the campus tables carry no session at all, so their unscoped
read is correct and was cleared by the schema rather than by argument.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import Database  # noqa: E402
from modules import crew_system  # noqa: E402


class TestTheCreditIsReported:
    async def test_a_session_with_no_resources_row_is_told_nothing_was_credited(self, scratch_session):
        """Before the fix this returned produced=401 and wrote nothing anywhere.

        The case is "a campaign with no ledger row", and session 5 is no longer one: the arc owns a
        row now. A scratch session has none by definition, so the test names that instead of pinning
        the live arc's state.
        """
        await Database.init()
        try:
            has_row = await Database.fetchval(
                "SELECT 1 FROM maya_rp.resources WHERE session_id=$1", scratch_session)
            assert has_row is None, "a scratch session must have no resources row"
            out = await crew_system.produce_crew(scratch_session)
            assert out["produced"] == 0, out
            assert out.get("unpaid"), out
            assert out.get("would_produce", 0) > 0, out
        finally:
            await Database.close()


class TestTheShipIsScoped:
    async def test_crew_cannot_be_consumed_for_another_campaigns_ship(self, scratch_session):
        await Database.init()
        try:
            foreign = await Database.fetchval("SELECT id FROM maya_rp.ships WHERE session_id=3 LIMIT 1")
            if foreign is None:
                return
            out = await crew_system.consume_crew(scratch_session, int(foreign), 10)
            assert f"not in session {scratch_session}" in out.get("error", ""), out
        finally:
            await Database.close()

    async def test_a_missing_ship_is_refused_by_name(self, scratch_session):
        await Database.init()
        try:
            out = await crew_system.consume_crew(scratch_session, 999_999, 10)
            assert f"not in session {scratch_session}" in out.get("error", ""), out
        finally:
            await Database.close()


class TestTheReport:
    async def test_the_report_answers_for_a_session_with_nothing(self, scratch_session):
        await Database.init()
        try:
            out = await crew_system.crew_report(scratch_session)
            assert out["crew_pool"] == 0 and out["named_officers"] == 0, out
        finally:
            await Database.close()
