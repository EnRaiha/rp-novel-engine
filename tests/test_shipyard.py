"""The shipyard: a capacity answer that used to be swallowed, and a hull nothing could lay down.

Four entry points of ship_building.py had no caller: the builder, the capacity check, the crew
assignment and the shortage report. The CLI also discarded the capacity answer, because it assumed every
function returns a dict and `or {}` turned False into an empty one.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import Database  # noqa: E402
from modules import ship_building  # noqa: E402


class TestTheCapacityAnswer:
    async def test_no_crew_cannot_crew_a_ship_and_the_answer_is_a_bool(self):
        await Database.init()
        answer = await ship_building.check_crew_capacity(5, 1)
        assert answer is False, answer
        assert await ship_building.check_crew_capacity(5, 0) is True
        await Database.close()


class TestTheReports:
    async def test_the_shortage_report_answers_with_its_own_shape(self):
        await Database.init()
        out = await ship_building.crew_shortage_report(5)
        assert isinstance(out, dict), out
        assert out, "an empty report is not an answer"
        await Database.close()

    async def test_assigning_crew_to_a_ship_that_does_not_exist_is_answered(self):
        await Database.init()
        out = await ship_building.assign_crew_to_ship(5, 999_999, 10)
        assert isinstance(out, dict), out
        assert out.get("error") or out.get("status"), out
        await Database.close()
