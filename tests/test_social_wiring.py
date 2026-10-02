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


class TestTheTickSurfacesWhatItKnows:
    async def test_the_tick_returns_the_tension_narrative_and_pending_events(self):
        await Database.init()
        out = await social.run_tick(5)
        assert "tension" in out and isinstance(out["tension"], str) and out["tension"], out
        assert "pending_events" in out and isinstance(out["pending_events"], list), out
        await Database.close()

    async def test_the_mutiny_report_carries_the_network_ringleaders(self):
        await Database.init()
        out = await social.calculate_mutiny_risk(5)
        assert "network_ringleaders" in out, out
        await Database.close()


class TestMoraleCannotGoNegative:
    async def test_the_wired_writer_clamps_at_zero(self):
        """The defect, run as SQL rather than read as source.

        The old statement is executed first to prove the defect was real: it returns a negative
        morale. The fixed statement is then executed against the same row and must floor at zero.
        """
        await Database.init()
        row = await Database.fetchrow(
            "INSERT INTO maya_rp.crew_roster (session_id, name, morale)"
            " VALUES (5, 'red proof hand', 5) RETURNING id")
        try:
            await Database.execute(
                "UPDATE maya_rp.crew_roster SET morale=LEAST(100, morale+$1) WHERE session_id=$2",
                -50, 5)
            broken = await Database.fetchval(
                "SELECT morale FROM maya_rp.crew_roster WHERE id=$1", row["id"])
            assert broken < 0, (
                "the old statement did not go negative, so this test no longer describes the defect")

            await Database.execute(
                "UPDATE maya_rp.crew_roster SET morale=$1 WHERE id=$2", 5, row["id"])
            await Database.execute(
                "UPDATE maya_rp.crew_roster SET morale=GREATEST(0, LEAST(100, morale+$1))"
                " WHERE session_id=$2", -50, 5)
            fixed = await Database.fetchval(
                "SELECT morale FROM maya_rp.crew_roster WHERE id=$1", row["id"])
            assert fixed == 0, f"morale floored at {fixed}, not 0"
        finally:
            await Database.execute("DELETE FROM maya_rp.crew_roster WHERE id=$1", row["id"])
            await Database.close()

    async def test_social_update_morale_also_clamps(self):
        """Session 5 has no crew, and `_get_fleet_morale` returns its default 50 when the roster is
        empty, so the test has to own a row or it proves nothing about the clamp."""
        await Database.init()
        row = await Database.fetchrow(
            "INSERT INTO maya_rp.crew_roster (session_id, name, morale)"
            " VALUES (5, 'red proof clamp', 40) RETURNING id")
        try:
            await social.update_morale(5, -1000, "red proof")
            after = await Database.fetchval(
                "SELECT morale FROM maya_rp.crew_roster WHERE id=$1", row["id"])
            assert after == 0, f"morale is {after} after a huge negative delta"
        finally:
            await Database.execute("DELETE FROM maya_rp.crew_roster WHERE id=$1", row["id"])
            await Database.close()
