"""Council module review: what reading `modules/council.py` in full turned up.

Six fixes, each with a test that fails against the module as it stood before. Nothing here writes to
session 3, and every row this file creates in session 5 is removed in a `finally`.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from core.db import Database  # noqa: E402
from modules import council  # noqa: E402

SESSION = 5


async def _conspiracy(**over):
    cols = {
        "session_id": SESSION,
        "plot_type": "sabotage",
        "target": "review target",
        # current_phase is a text column in the live schema, so the index rides as a string.
        "current_phase": "0",
        "difficulty": 5,
        "status": "active",
        "details": "{}",
    }
    cols.update(over)
    keys = ", ".join(cols)
    marks = ", ".join(f"${i + 1}" for i in range(len(cols)))
    # The id sequence for maya_rp.conspiracies is behind the rows already in the table, so an insert that
    # lets the sequence choose an id collides. The engine's own inserts hit this too.
    return await Database.fetchrow(
        f"INSERT INTO maya_rp.conspiracies (id, {keys}) "
        f"VALUES ((SELECT COALESCE(MAX(id), 0) + 1 FROM maya_rp.conspiracies), {marks}) RETURNING id",
        *cols.values())


async def _territory(**over):
    cols = {
        "session_id": SESSION,
        "system_name": "review-system",
        "controlling_faction": "Federation",
        "crisis_level": 0,
        "development_level": 1,
        "governor_name": "Review Governor",
        "revocation_risk": 5,
        "title_performance": 0,
    }
    cols.update(over)
    keys = ", ".join(cols)
    marks = ", ".join(f"${i + 1}" for i in range(len(cols)))
    # The id sequence for maya_rp.territory is behind the rows already in the table, so an insert that
    # lets the sequence choose an id collides. The engine's own inserts hit this too.
    return await Database.fetchrow(
        f"INSERT INTO maya_rp.territory (id, {keys}) "
        f"VALUES ((SELECT COALESCE(MAX(id), 0) + 1 FROM maya_rp.territory), {marks}) RETURNING id",
        *cols.values())


class TestTheThwart:
    async def test_a_plot_from_another_campaign_is_not_thwarted(self, monkeypatch):
        """The update ran by id alone, so any session could thwart any session's plot."""
        await Database.init()
        row = await _conspiracy()
        try:
            monkeypatch.setattr(council.random, "random", lambda: 0.0)
            out = await council.thwart_plot(row["id"], "arrest_asset", session_id=3)
            assert out.get("success") is False, out
            assert "not found" in out.get("error", ""), out
            status = await Database.fetchval(
                "SELECT status FROM maya_rp.conspiracies WHERE id = $1", row["id"])
            assert status == "active", "another campaign thwarted this plot"
        finally:
            await Database.execute("DELETE FROM maya_rp.conspiracies WHERE id = $1", row["id"])
            await Database.close()

    async def test_a_conspiracy_that_does_not_exist_is_refused(self, monkeypatch):
        """An id that resolved to nothing was answered with a success roll against no row."""
        await Database.init()
        try:
            monkeypatch.setattr(council.random, "random", lambda: 0.0)
            out = await council.thwart_plot(999999999, "arrest_asset", session_id=SESSION)
            assert out["success"] is False, out
            assert "not found" in out["error"], out
        finally:
            await Database.close()

    async def test_a_thwarted_plot_is_written(self, monkeypatch):
        await Database.init()
        row = await _conspiracy()
        try:
            monkeypatch.setattr(council.random, "random", lambda: 0.0)
            out = await council.thwart_plot(row["id"], "arrest_asset", session_id=SESSION)
            assert out["success"] is True, out
            assert out["moral_cost"] == 0
            status = await Database.fetchval(
                "SELECT status FROM maya_rp.conspiracies WHERE id = $1", row["id"])
            assert status == "thwarted"
            method = await Database.fetchval(
                "SELECT details->'thwarted_by'->>'method' FROM maya_rp.conspiracies WHERE id = $1",
                row["id"])
            assert method == "arrest_asset"
        finally:
            await Database.execute("DELETE FROM maya_rp.conspiracies WHERE id = $1", row["id"])
            await Database.close()

    async def test_an_unknown_method_names_the_value_and_the_alternatives(self):
        await Database.init()
        try:
            out = await council.thwart_plot(1, "bribe-them", session_id=SESSION)
            assert "bribe-them" in out["error"], out
            assert out["available"] == sorted(council.THWART_METHODS)
        finally:
            await Database.close()


class TestTheMeeting:
    async def test_an_unknown_meeting_type_is_refused_by_name(self):
        out = council.convene_meeting("standup")
        assert "standup" in out.get("error", ""), out
        assert out["available"] == sorted(council.MEETING_TYPES)

    async def test_a_known_meeting_still_carries_its_agenda(self):
        out = council.convene_meeting("war_council", {"attendees": ["Commander"]})
        assert out["type"] == "war_council"
        assert out["agenda"] == council.MEETING_AGENDAS["war_council"]
        assert out["attendees"] == ["Commander"]


class TestTheAgendaTable:
    def test_the_two_names_are_one_table(self):
        """A byte-identical copy of the agenda table is a second place for it to drift."""
        assert council.DEFAULT_AGENDAS is council.MEETING_AGENDAS


class TestTheTick:
    async def test_a_failing_tick_is_logged_as_a_fault(self, monkeypatch):
        seen = []

        async def boom(session_id):
            raise RuntimeError("cabinet query died")

        monkeypatch.setattr(council, "get_cabinet_seats", boom)
        monkeypatch.setattr(council, "error", lambda module, message: seen.append(message))
        out = await council.run_tick(SESSION)
        assert "cabinet query died" in out["error"], out
        assert seen, "a failing tick returned a dict and said nothing at fault level"


class TestThePerformanceLedger:
    async def test_a_performance_only_change_is_written(self):
        """The write was gated on `risk` alone while the same statement wrote `perf` too."""
        await Database.init()
        row = await _territory(revocation_risk=5, title_performance=0, crisis_level=0,
                               development_level=1, governor_name="Review Governor")
        try:
            await council.check_title_revocation(SESSION)
            perf = await Database.fetchval(
                "SELECT title_performance FROM maya_rp.territory WHERE id = $1", row["id"])
            assert perf == 1, "an earned performance point was thrown away by the write gate"
        finally:
            await Database.execute("DELETE FROM maya_rp.territory WHERE id = $1", row["id"])
            await Database.close()

    async def test_a_territory_with_no_governor_gains_no_performance(self):
        await Database.init()
        row = await _territory(governor_name=None, revocation_risk=0, title_performance=0)
        try:
            await council.check_title_revocation(SESSION)
            perf = await Database.fetchval(
                "SELECT title_performance FROM maya_rp.territory WHERE id = $1", row["id"])
            risk = await Database.fetchval(
                "SELECT revocation_risk FROM maya_rp.territory WHERE id = $1", row["id"])
            assert perf == 0, perf
            assert risk == 2, risk  # +2 for the empty seat
        finally:
            await Database.execute("DELETE FROM maya_rp.territory WHERE id = $1", row["id"])
            await Database.close()


class TestTheAgent:
    async def test_an_invalid_role_names_the_value_and_the_alternatives(self):
        await Database.init()
        try:
            out = await council.assign_agent(SESSION, 1, "spymaster")
            assert "Invalid role" in out["error"], out
            assert "spymaster" in out["error"], out
            assert out["available"] == ["watcher", "networker", "interrogator"]
        finally:
            await Database.close()
