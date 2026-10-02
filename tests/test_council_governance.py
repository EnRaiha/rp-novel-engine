"""The governance surface: decrees, crises and the briefing.

The remaining council functions assemble their own state or take plain arguments, so they need a door
rather than a driver. issue_decree fetches the cabinet itself; the crisis pair passes a dict between
them; the briefing takes three lists.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import Database  # noqa: E402
from modules import council  # noqa: E402


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
    async def test_a_decree_without_a_consul_is_refused(self):
        """Session 5 has no cabinet, so the decree route answers rather than crashing."""
        await Database.init()
        out = await council.issue_decree(5, "tax")
        assert out.get("issued") is False, out
        assert "Grand Consul" in out.get("reason", ""), out
        await Database.close()


class TestTheMeeting:
    def test_a_meeting_answers_with_a_shape(self):
        out = council.convene_meeting("emergency", {"session_id": 5})
        assert isinstance(out, dict), out
