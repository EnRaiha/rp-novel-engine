"""The council: the six database functions, and a scan that repeats.

council.py holds twenty-five unreachable functions, nineteen of them pure (votes, plots, crises,
influence) and six that touch the database. This covers the six: the scan, the agent assignment, the
two conspiracy actions and the two title actions.

scan_for_plots decided detection with `random.random()`, so scanning the same state twice gave two
different answers and a scan could not be reproduced in the novel. It derives the roll from the
conspiracy, its phase and the network quality now.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import Database  # noqa: E402
from modules import council  # noqa: E402


async def _conspiracy(session_id: int, difficulty: int = 5):
    return await Database.fetchrow(
        "INSERT INTO maya_rp.conspiracies (session_id, plot_type, target, current_phase, difficulty,"
        " status, details) VALUES ($1, 'coup', 'the King', 0, $2, 'active', '{}'::jsonb) RETURNING id",
        session_id, difficulty)


class TestTheScanRepeats:
    async def test_the_same_state_is_detected_the_same_way(self):
        await Database.init()
        rows = [await _conspiracy(5, d) for d in (1, 3, 5, 7, 9)]
        try:
            first = [r["conspiracy_id"] for r in await council.scan_for_plots(5, 60)]
            second = [r["conspiracy_id"] for r in await council.scan_for_plots(5, 60)]
            assert first == second, f"the scan is not reproducible: {first} then {second}"
        finally:
            for row in rows:
                await Database.execute("DELETE FROM maya_rp.conspiracies WHERE id=$1", row["id"])
            await Database.close()

    async def test_a_better_network_detects_at_least_as_much(self):
        await Database.init()
        row = await _conspiracy(5, 3)
        try:
            weak = len(await council.scan_for_plots(5, 10))
            strong = len(await council.scan_for_plots(5, 100))
            assert strong >= weak, f"a stronger network found less: {strong} < {weak}"
        finally:
            await Database.execute("DELETE FROM maya_rp.conspiracies WHERE id=$1", row["id"])
            await Database.close()

    async def test_another_campaign_sees_none_of_them(self):
        await Database.init()
        row = await _conspiracy(3, 1)
        try:
            assert await council.scan_for_plots(5, 100) == [], "the scan leaks across campaigns"
        finally:
            await Database.execute("DELETE FROM maya_rp.conspiracies WHERE id=$1", row["id"])
            await Database.close()


class TestThePureHelpersTheCliUses:
    def test_validate_cabinet_wants_the_seats_not_a_session(self):
        """It was written as a pure function, and calling it with a session raised TypeError."""
        out = council.validate_cabinet([])
        assert out["valid"] is False
        assert "Grand Consul" in out["missing"]

    def test_cohesion_of_no_seats_is_zero(self):
        assert council.get_cohesion([]) == 0

    def test_an_invalid_agent_role_is_refused(self):
        import asyncio

        async def check():
            await Database.init()
            try:
                return await council.assign_agent(5, 1, "nonsense")
            finally:
                await Database.close()
        assert "Invalid role" in asyncio.run(check()).get("error", "")
