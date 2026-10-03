"""Proof that `scratch_session` performs the teardown its docstring promises.

The fixture used to end at `yield session_id`. A generator with no code after its yield performs no
teardown at all, while the docstring told eleven test files they could skip their own `finally`. A
cleanup helper that reports work it does not do is worse than no helper: it is the helper that stops
the author writing the cleanup themselves, and it was named as the remedy for the very hazard that
destroyed the live arc's resources row.

The proof is a pair of tests. The first writes rows for its own scratch session and does NOT clean up.
The second reads the database directly, after the fixture has finalised the first test, and requires
zero rows. The second test refuses to run when the first did not write, so an isolated or reordered
run cannot report a pass it did not measure.
"""
from __future__ import annotations

import pytest_asyncio

from core.db import Database

#: Tables that carry a `session_id` column, hold no foreign key on it, and need no other column.
#: Two of them, so the fixture has to find the rows by discovery rather than from one hardcoded name.
PROBE_TABLES = ("complaint_boxes", "crew_xp_log")

#: Written by the first test, read by the second. Empty means the writer never ran.
WROTE: list[int] = []


@pytest_asyncio.fixture(autouse=True)
async def _pool():
    """The fixture's teardown needs a live pool, and this fixture finalises after it, not before."""
    await Database.init()
    yield
    await Database.close()


async def test_a_test_can_leave_rows_behind(scratch_session):
    for table in PROBE_TABLES:
        await Database.execute(
            f'INSERT INTO maya_rp."{table}" (session_id) VALUES ($1)', scratch_session)
        present = await Database.fetchval(
            f'SELECT count(*) FROM maya_rp."{table}" WHERE session_id = $1', scratch_session)
        assert present == 1, f"the probe wrote nothing to {table}, so the check would be vacuous"
    WROTE.append(scratch_session)


async def test_the_fixture_deleted_them(scratch_session):
    assert WROTE, ("the writer did not run before this check, so a pass would prove nothing: "
                   "run the whole file")
    assert WROTE[0] == scratch_session, "the two tests did not share a scratch session"
    for table in PROBE_TABLES:
        remaining = await Database.fetchval(
            f'SELECT count(*) FROM maya_rp."{table}" WHERE session_id = $1', scratch_session)
        assert remaining == 0, (
            f"scratch_session left {remaining} row(s) in {table} for session {scratch_session}; "
            "the teardown its docstring promises did not run")
