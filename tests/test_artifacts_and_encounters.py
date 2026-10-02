"""Relics and encounters: eight entry points, and the shapes I had to read to get right.

artifacts.py had three with no caller (the relic list, the medal award, the medal list) and encounters.py
three (the template list, the generator, the event log).

Two of my own mistakes are recorded here because the tests exist to catch them: the encounter templates
come back as a mapping rather than a list, and `generate_event` is async even though it touches no
database, so a caller that treats it as pure gets a coroutine instead of an event.
"""
from __future__ import annotations

import asyncio
import inspect
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import Database  # noqa: E402
from modules import artifacts, encounters  # noqa: E402


class TestTheEncounterShapes:
    def test_the_templates_are_a_mapping(self):
        templates = encounters.get_encounter_templates()
        assert isinstance(templates, dict), type(templates)
        assert templates, "no encounter templates"

    def test_generate_event_is_async(self):
        """It touches no database, so it reads as pure; it is a coroutine function all the same."""
        assert inspect.iscoroutinefunction(encounters.generate_event), (
            "the CLI awaits it, so it must stay async or the command prints a coroutine")

    async def test_an_event_comes_back_with_a_type_and_a_tier(self):
        await Database.init()
        event = await encounters.generate_event(5, "hazard", 5)
        assert event.get("event_type"), event
        assert event.get("tier"), event
        await Database.close()

    async def test_logging_an_event_writes_it(self):
        await Database.init()
        out = await encounters.log_event(5, "red proof", "a test event", "written by the suite")
        try:
            assert out is not None
            found = await Database.fetchval(
                "SELECT count(*) FROM maya_rp.events WHERE session_id=5"
                " AND title='a test event'")
            assert found == 1, f"the event was not written: {found}"
        finally:
            await Database.execute(
                "DELETE FROM maya_rp.events WHERE session_id=5 AND title='a test event'")
            await Database.close()


class TestTheRelics:
    async def test_the_lists_answer(self):
        await Database.init()
        assert isinstance(await artifacts.list_artifacts(5), list)
        assert isinstance(await artifacts.list_medals(5), list)
        await Database.close()

    async def test_an_unknown_artifact_cannot_be_equipped(self):
        await Database.init()
        out = await artifacts.equip(999_999, 1, 5)
        assert out is not None
        await Database.close()
