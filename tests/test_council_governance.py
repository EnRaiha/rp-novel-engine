"""The governance surface: decrees, crises and the briefing.

The remaining council functions assemble their own state or take plain arguments, so they need a door
rather than a driver. issue_decree fetches the cabinet itself; the crisis pair passes a dict between
them; the briefing takes three lists.
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


class TestTheCrisis:
    def test_a_crisis_carries_a_narrative_and_a_stage(self):
        crisis = council.trigger_crisis("invasion")
        assert crisis.get("narrative"), crisis
        assert "stage" in crisis or "current_stage" in crisis, crisis

    def test_escalating_moves_the_stage_forward(self):
        crisis = council.trigger_crisis("invasion")
        before = crisis.get("current_stage", crisis.get("stage", 0))
        after = council.escalate_crisis(crisis, 1)
        now = after.get("current_stage", after.get("stage", 0))
        assert now > before, f"the stage did not advance: {before} then {now}"


class TestTheBriefing:
    def test_an_empty_briefing_still_answers(self):
        out = council.situation_briefing([], [], [])
        assert isinstance(out, str) and out.startswith("CABINET BRIEFING"), out

    def test_a_briefing_with_a_decree_names_it(self):
        # The briefing renders `title` and `delegated_to`. Two earlier versions of this fixture used
        # `decree_type` and then `type`, and the briefing printed "? (?)" for both: it was reading the
        # names correctly and I was writing the wrong ones.
        out = council.situation_briefing(
            [{"title": "tax the ports", "delegated_to": "Finance Minister", "status": "executing"}],
            [], [])
        assert "tax the ports" in out, out
        assert "Finance Minister" in out, out


class TestTheDecree:
    async def test_a_decree_without_a_consul_is_refused(self, scratch):
        """A session with no cabinet gets an answer from the decree route, not a crash."""
        out = await council.issue_decree(SESSION, "tax")
        assert out.get("issued") is False, out
        assert "Grand Consul" in out.get("reason", ""), out


class TestTheMeeting:
    def test_a_meeting_answers_with_a_shape(self):
        out = council.convene_meeting("emergency", {"session_id": SESSION})
        assert isinstance(out, dict), out
