"""Module review: crew_system.py.

Two defects, and one read the schema has since closed. `produce_crew` credited a pool that no session
had: the update matched nothing and the function still returned the campus output as produced.
`consume_crew` found and updated a ship by id alone, while ships carries a session, so crew could be
consumed for another campaign's hull. And the campus tables carried no session when this file was
written, so their unscoped read was correct then. Migration 138 binds a campus to a session, so the
academy read is scoped too, and the first test below seeds its own campus: a scratch campaign that
owns no campus produces nothing and measures nothing.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import Database  # noqa: E402
from modules import crew_system  # noqa: E402

#: Campus size of the seeded campus. `_academy_output` pays 8% of `max_students` times the prestige
#: bonus, so this campus produces 32 crew per tick and a wrong read shows up as a bigger number.
CAMPUS_STUDENTS = 200
CAMPUS_PRESTIGE = 100


async def _seed_campus(session_id: int, name: str) -> int:
    """One academy campus owned by `session_id`.

    `academy_campuses` carries no foreign key to `sessions`, so the row stands on its own and the
    `scratch_session` fixture removes it by its `session_id`.
    """
    return await Database.fetchval(
        "INSERT INTO maya_rp.academy_campuses (name, session_id, max_students, prestige, level)"
        " VALUES ($1, $2, $3, $4, 1) RETURNING id",
        name, session_id, CAMPUS_STUDENTS, CAMPUS_PRESTIGE)


class TestTheCreditIsReported:
    async def test_a_session_with_no_resources_row_is_told_nothing_was_credited(self, scratch_session):
        """Before the fix this returned produced=401 and wrote nothing anywhere.

        The case is "a campaign with no ledger row", and session 5 is no longer one: the arc owns a
        row now. A scratch session has none by definition, so the test names that instead of pinning
        the live arc's state. The campus it measures is the scratch session's own: `produce_crew`
        reads the campus of the calling campaign, so a scratch session without one would report
        `would_produce = 0` and the assertion below would measure nothing.
        """
        await Database.init()
        try:
            await _seed_campus(scratch_session, "review scratch academy")
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
