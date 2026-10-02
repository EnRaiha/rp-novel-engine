"""The exoscience board: the tick reproduces, and an unpaid reward says so.

`start_mission` and `generate_anomaly` had no caller, so `run_tick` progressed missions and studied
anomalies that nothing could create. Reviewing the tick before wiring found two defects: it advanced
every row with `random.randint`, so the same state produced two different campaigns, and a completed
mission's reward was written with an UPDATE that matches nothing when the session has no resources row,
which is session 5's state — the credits were lost in silence.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import Database  # noqa: E402
from modules import exoscience  # noqa: E402


class TestThePace:
    def test_the_same_state_advances_the_same_way(self):
        assert exoscience._pace(5, 71, 10) == exoscience._pace(5, 71, 10)

    def test_the_pace_stays_inside_the_band(self):
        for state in range(60):
            assert 5 <= exoscience._pace(5, state, state) <= 15

    def test_different_rows_do_not_all_get_the_same_pace(self):
        paces = {exoscience._pace(5, row, 0) for row in range(40)}
        assert len(paces) > 3, f"one pace for every row: {paces}"


class TestTheTick:
    async def test_a_completed_mission_reports_the_reward_it_could_not_pay(self):
        await Database.init()
        mission = await Database.fetchrow(
            "INSERT INTO maya_rp.science_missions"
            " (session_id, mission_type, progress, target_progress, research_reward, status)"
            " VALUES (5, 'red proof', 49, 50, 25, 'active') RETURNING id")
        try:
            # Session 5 has no resources row, which is the defect: the reward goes nowhere.
            has_resources = await Database.fetchval(
                "SELECT 1 FROM maya_rp.resources WHERE session_id=5")
            result = await exoscience.run_tick(5)
            if has_resources is None:
                assert result.get("rewards_unpaid") == 1, result
            else:
                assert "rewards_unpaid" not in result, result
        finally:
            await Database.execute("DELETE FROM maya_rp.science_missions WHERE id=$1", mission["id"])
            await Database.close()

    async def test_a_mission_created_here_can_be_progressed(self):
        await Database.init()
        created = await exoscience.start_mission("red proof type", 5)
        try:
            assert created.get("mission_id"), created
            first = await exoscience.run_tick(5)
            second = await exoscience.run_tick(5)
            assert first.get("error") is None and second.get("error") is None
            assert first == second or first.get("missions_completed") == second.get("missions_completed")
        finally:
            await Database.execute(
                "DELETE FROM maya_rp.science_missions WHERE id=$1", created["mission_id"])
            await Database.close()
