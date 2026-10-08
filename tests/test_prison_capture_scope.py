"""Prisoners belong to a campaign, including the ones the live paths touch.

Twelve lookups in prison.py went by prisoner id alone. Five sat inside live code, including
`interrogate` and `check_conversion`, so one campaign could interrogate or convert another campaign's
prisoner. Four of the functions had no session parameter at all, which is why scoping them was not a
matter of adding a WHERE clause.

The mechanical patch that scoped them is worth a note. It left five calls passing one argument to a
query that asks for two, and the suite stayed green because nothing exercises those paths. The tests
below run two of them, so the next patch of that kind fails instead of shipping.
"""
from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

from core.db import Database  # noqa: E402
from modules import prison  # noqa: E402

#: Scratch campaigns. Sessions 3 and 5 are frozen reference data and are never written.
SESSION = 900 + os.getpid() % 100
OTHER = 900 + (os.getpid() + 50) % 100


async def _purge(session_id: int) -> None:
    """Remove one scratch session's rows in foreign-key order."""
    q = Database.execute
    await q("DELETE FROM maya_rp.interrogation_log WHERE session_id=$1", session_id)
    await q("DELETE FROM maya_rp.prisoners WHERE session_id=$1", session_id)
    await q("DELETE FROM maya_rp.sessions WHERE id=$1", session_id)


@pytest_asyncio.fixture(autouse=True)
async def _scratch_sessions():
    """Create both scratch `sessions` rows, and remove everything they own afterwards."""
    await Database.init()
    for s in (SESSION, OTHER):
        await _purge(s)
        await Database.execute(
            "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1,'Prison scope scratch','active') "
            "ON CONFLICT DO NOTHING", s)
    try:
        yield
    finally:
        await Database.init()
        for s in (OTHER, SESSION):
            await _purge(s)
        await Database.close()


async def _prisoner(session_id: int):
    return await Database.fetchrow(
        "INSERT INTO maya_rp.prisoners (session_id, name, faction, rank, intel_value, resistance,"
        " status, cell_security, interrogations_count, intel_extracted)"
        " VALUES ($1, 'red proof prisoner', 'Iron Concord', 'Private', 2, 40, 'captured',"
        " 'standard', 0, '{}'::jsonb) RETURNING id", session_id)


class TestTheLivePathsRun:
    async def test_check_conversion_runs_and_answers(self):
        """This call is the one the bad patch broke: two parameters, one passed."""
        await Database.init()
        row = await _prisoner(SESSION)
        try:
            out = await prison.check_conversion(row["id"], SESSION)
            assert out is None or isinstance(out, dict), out
        finally:
            await Database.execute("DELETE FROM maya_rp.prisoners WHERE id=$1", row["id"])
            await Database.close()

    async def test_interrogate_runs_against_its_own_prisoner(self):
        await Database.init()
        row = await _prisoner(SESSION)
        try:
            out = await prison.interrogate(row["id"], "standard", session_id=SESSION)
            assert isinstance(out, dict), out
        finally:
            await Database.execute(
                "DELETE FROM maya_rp.interrogation_log WHERE prisoner_id=$1", row["id"])
            await Database.execute("DELETE FROM maya_rp.prisoners WHERE id=$1", row["id"])
            await Database.close()


class TestTheGate:
    async def test_a_prisoner_from_another_campaign_is_refused(self):
        await Database.init()
        row = await _prisoner(OTHER)
        try:
            assert await prison.check_conversion(row["id"], SESSION) is None, "the read leaks"
            assert await prison.get_available_intimacy_paths(row["id"], session_id=SESSION) == [], "leaks"
            escape = await prison.calculate_escape_risk(row["id"], session_id=SESSION)
            assert "not found" in str(escape.get("error", "")), escape
        finally:
            await Database.execute("DELETE FROM maya_rp.prisoners WHERE id=$1", row["id"])
            await Database.close()
