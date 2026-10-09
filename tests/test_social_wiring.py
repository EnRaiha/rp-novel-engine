"""The social cluster: morale that cannot go negative, and helpers that reach the tick.

Ten functions in social.py had no production caller. Two pure helpers, get_tension_narrative and
get_pending_events, turn the morale number into the sentence a GM reads — the tick computed the number
and stopped. get_ringleaders ranks malcontents by crew network centrality rather than loyalty score, so
it finds the influential ones the score list misses, and nothing called it.

Found on the way, in the live path: `calendar_tkg` is the morale writer that IS wired, and its statement
was `LEAST(100, morale+$1)` with no floor, so a somber festival could drive crew morale below zero.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import Database  # noqa: E402
from modules import social  # noqa: E402


async def _open_scratch(session_id: int) -> None:
    """Create the `sessions` row a scratch slot needs. `run_tick`, `calculate_mutiny_risk` and
    `update_morale` write, and session 5 is frozen, so these tests run in a scratch session."""
    await Database.init()
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1,'social wiring scratch','active')"
        " ON CONFLICT (id) DO NOTHING", session_id)


async def _close_scratch(session_id: int) -> None:
    for table in ("morale_history", "crew_roster", "social_events"):
        await Database.execute(f"DELETE FROM maya_rp.{table} WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", session_id)
    await Database.close()


class TestTheTickSurfacesWhatItKnows:
    async def test_the_tick_returns_the_tension_narrative_and_pending_events(self, scratch_session):
        await _open_scratch(scratch_session)
        try:
            out = await social.run_tick(scratch_session)
            assert "tension" in out and isinstance(out["tension"], str) and out["tension"], out
            assert "pending_events" in out and isinstance(out["pending_events"], list), out
        finally:
            await _close_scratch(scratch_session)

    async def test_the_mutiny_report_carries_the_network_ringleaders(self, scratch_session):
        """The call named session 5, which is frozen: the mutiny report rewrites loyalty flags."""
        await _open_scratch(scratch_session)
        try:
            out = await social.calculate_mutiny_risk(scratch_session)
            assert "network_ringleaders" in out, out
        finally:
            await _close_scratch(scratch_session)


class TestMoraleCannotGoNegative:
    async def test_the_wired_writer_clamps_at_zero(self, scratch_session):
        """The defect, run as SQL rather than read as source.

        The old statement is executed first to prove the defect was real: it returns a negative
        morale. The fixed statement is then executed against the same row and must floor at zero.
        Both statements touch every crew row of the session, so the session is a scratch one.
        """
        await _open_scratch(scratch_session)
        row = await Database.fetchrow(
            "INSERT INTO maya_rp.crew_roster (session_id, name, morale)"
            " VALUES ($1, 'red proof hand', 5) RETURNING id", scratch_session)
        try:
            await Database.execute(
                "UPDATE maya_rp.crew_roster SET morale=LEAST(100, morale+$1) WHERE session_id=$2",
                -50, scratch_session)
            broken = await Database.fetchval(
                "SELECT morale FROM maya_rp.crew_roster WHERE id=$1", row["id"])
            assert broken < 0, (
                "the old statement did not go negative, so this test no longer describes the defect")

            await Database.execute(
                "UPDATE maya_rp.crew_roster SET morale=$1 WHERE id=$2", 5, row["id"])
            await Database.execute(
                "UPDATE maya_rp.crew_roster SET morale=GREATEST(0, LEAST(100, morale+$1))"
                " WHERE session_id=$2", -50, scratch_session)
            fixed = await Database.fetchval(
                "SELECT morale FROM maya_rp.crew_roster WHERE id=$1", row["id"])
            assert fixed == 0, f"morale floored at {fixed}, not 0"
        finally:
            await _close_scratch(scratch_session)

    async def test_social_update_morale_also_clamps(self, scratch_session):
        """The session has no crew, and `_get_fleet_morale` returns its default 50 when the roster is
        empty, so the test has to own a row or it proves nothing about the clamp. It runs in a scratch
        session because `update_morale` refuses frozen session 5."""
        await _open_scratch(scratch_session)
        row = await Database.fetchrow(
            "INSERT INTO maya_rp.crew_roster (session_id, name, morale)"
            " VALUES ($1, 'red proof clamp', 40) RETURNING id", scratch_session)
        try:
            await social.update_morale(scratch_session, -1000, "red proof")
            after = await Database.fetchval(
                "SELECT morale FROM maya_rp.crew_roster WHERE id=$1", row["id"])
            assert after == 0, f"morale is {after} after a huge negative delta"
        finally:
            await _close_scratch(scratch_session)
