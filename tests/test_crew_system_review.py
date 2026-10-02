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
    async def test_a_session_with_no_resources_row_is_told_nothing_was_credited(self):
        """Before the fix this returned produced=401 and wrote nothing anywhere."""
        await Database.init()
        has_row = await Database.fetchval(
            "SELECT 1 FROM maya_rp.resources WHERE session_id=5")
        assert has_row is None, "this test assumes session 5 has no resources row"
        out = await crew_system.produce_crew(5)
        assert out["produced"] == 0, out
        assert out.get("unpaid"), out
        assert out.get("would_produce", 0) > 0, out
        await Database.close()


class TestTheShipIsScoped:
    async def test_crew_cannot_be_consumed_for_another_campaigns_ship(self):
        await Database.init()
        foreign = await Database.fetchval("SELECT id FROM maya_rp.ships WHERE session_id=3 LIMIT 1")
        if foreign is None:
            await Database.close()
            return
        out = await crew_system.consume_crew(5, int(foreign), 10)
        assert "not in session 5" in out.get("error", ""), out
        await Database.close()

    async def test_a_missing_ship_is_refused_by_name(self):
        await Database.init()
        out = await crew_system.consume_crew(5, 999_999, 10)
        assert "not in session 5" in out.get("error", ""), out
        await Database.close()


class TestTheReport:
    async def test_the_report_answers_for_a_session_with_nothing(self):
        await Database.init()
        out = await crew_system.crew_report(5)
        assert out["crew_pool"] == 0 and out["named_officers"] == 0, out
        await Database.close()
