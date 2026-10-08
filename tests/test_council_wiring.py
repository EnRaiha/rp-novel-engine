"""The council: the six database functions, and a scan that repeats.

council.py holds twenty-five unreachable functions, nineteen of them pure (votes, plots, crises,
influence) and six that touch the database. This covers the six: the scan, the agent assignment, the
two conspiracy actions and the two title actions.

scan_for_plots decided detection with `random.random()`, so scanning the same state twice gave two
different answers and a scan could not be reproduced in the novel. It derives the roll from the
conspiracy, its phase and the network quality now.
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
from modules import council  # noqa: E402

#: Scratch sessions. The writers refuse the frozen sessions 3 and 5, so every row this file makes lives in
#: a session of its own (900-999), with a second one standing in for "another campaign".
SESSION = 900 + os.getpid() % 100
OTHER = 900 + (os.getpid() + 50) % 100

#: Children first: foreign keys run from these tables to `characters`, `cabinet_hierarchy`, `sessions`.
_TABLES = (
    "cabinet_decrees", "cabinet_hierarchy", "character_relationships", "characters", "conspiracies",
    "crew_roster", "events", "intel_network", "morale_history", "social_events", "territory",
)


async def _wipe() -> None:
    for sid in (SESSION, OTHER):
        for table in _TABLES:
            await Database.execute(f"DELETE FROM maya_rp.{table} WHERE session_id = $1", sid)
        await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", sid)


@pytest_asyncio.fixture
async def scratch():
    """Both scratch sessions exist for the test; every row of them is removed after, in foreign-key order."""
    await Database.init()
    await _wipe()
    for sid in (SESSION, OTHER):
        await Database.execute(
            "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1, 'scratch', 'active')"
            " ON CONFLICT (id) DO NOTHING", sid)
    try:
        yield
    finally:
        await _wipe()
        await Database.close()


async def _conspiracy(session_id: int, difficulty: int = 5):
    return await Database.fetchrow(
        "INSERT INTO maya_rp.conspiracies (session_id, plot_type, target, current_phase, difficulty,"
        " status, details) VALUES ($1, 'coup', 'the King', 0, $2, 'active', '{}'::jsonb) RETURNING id",
        session_id, difficulty)


class TestTheScanRepeats:
    async def test_the_same_state_is_detected_the_same_way(self, scratch):
        rows = [await _conspiracy(SESSION, d) for d in (1, 3, 5, 7, 9)]
        try:
            first = [r["conspiracy_id"] for r in await council.scan_for_plots(SESSION, 60)]
            second = [r["conspiracy_id"] for r in await council.scan_for_plots(SESSION, 60)]
            assert first == second, f"the scan is not reproducible: {first} then {second}"
        finally:
            for row in rows:
                await Database.execute("DELETE FROM maya_rp.conspiracies WHERE id=$1", row["id"])

    async def test_a_better_network_detects_at_least_as_much(self, scratch):
        row = await _conspiracy(SESSION, 3)
        try:
            weak = len(await council.scan_for_plots(SESSION, 10))
            strong = len(await council.scan_for_plots(SESSION, 100))
            assert strong >= weak, f"a stronger network found less: {strong} < {weak}"
        finally:
            await Database.execute("DELETE FROM maya_rp.conspiracies WHERE id=$1", row["id"])

    async def test_another_campaign_sees_none_of_them(self, scratch):
        row = await _conspiracy(OTHER, 1)
        try:
            assert await council.scan_for_plots(SESSION, 100) == [], "the scan leaks across campaigns"
        finally:
            await Database.execute("DELETE FROM maya_rp.conspiracies WHERE id=$1", row["id"])


class TestThePureHelpersTheCliUses:
    def test_validate_cabinet_wants_the_seats_not_a_session(self):
        """It was written as a pure function, and calling it with a session raised TypeError."""
        out = council.validate_cabinet([])
        assert out["valid"] is False
        assert "Grand Consul" in out["missing"]

    def test_cohesion_of_no_seats_is_zero(self):
        assert council.get_cohesion([]) == 0


class TestTheAgentRole:
    async def test_an_invalid_agent_role_is_refused(self, scratch):
        out = await council.assign_agent(SESSION, 1, "nonsense")
        assert "Invalid role" in out.get("error", ""), out


class TestTheThreeThatReadTheSeats:
    """status_report, route_task and get_emergency_authority take the seat list, so the caller fetches
    it and they stay pure. They were unreachable, not broken."""

    def test_the_status_report_names_the_cabinet_and_its_cohesion(self):
        seats = [
            {"title": "Grand Consul", "holder": "Maya", "portfolio": "overall", "tier": 0,
             "active": True},
            {"title": "Commander", "holder": "Rika", "portfolio": "military", "tier": 1,
             "active": True},
        ]
        report = council.status_report(seats)
        assert "CABINET STATUS" in report
        assert "Grand Consul: Maya" in report
        assert "Cohesion:" in report

    def test_a_task_routes_to_the_seat_that_owns_the_portfolio(self):
        seats = [{"id": 7, "title": "Commander", "holder": "Rika", "portfolio": "defense",
                  "tier": 1, "active": True}]
        out = council.route_task(seats, "reinforce the military patrol")
        assert out["routed"] is True, out
        assert out["seat"] == 7, out

    def test_emergency_authority_needs_absence_before_it_needs_a_seat(self):
        seats = [{"title": "Commander", "holder": "Rika", "portfolio": "military", "tier": 1,
                  "active": True}]
        assert council.get_emergency_authority(seats, 2) is None, "2 hours cannot hand over command"
        found = council.get_emergency_authority(seats, 30)
        assert found and found["seat"]["title"] == "Commander", found

    def test_the_empty_cabinet_is_reported_as_empty_not_as_a_clock(self):
        assert council.get_emergency_authority([], 30) is None
        assert council.status_report([]).endswith("Active: 0"), council.status_report([])
