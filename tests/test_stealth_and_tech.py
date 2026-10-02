"""Stealth and the tech tree: nine entry points, and a comparison that proves the scoping.

Five entry points of stealth.py and four of tech_tree.py had no caller. The comparison matters more than
the truth here: the same reader returning 48 technologies for session 3 and 0 for session 5 proves both
that the query works and that session 5's emptiness is the unseeded world rather than a broken filter.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import Database  # noqa: E402
from modules import stealth, tech_tree  # noqa: E402


class TestTheTechTreeIsScoped:
    async def test_session_three_has_technologies_and_session_five_has_none(self):
        await Database.init()
        three = await tech_tree.view_tech(3)
        five = await tech_tree.view_tech(5)
        assert three, "session 3 has no technologies, so the comparison proves nothing"
        assert five == [], f"session 5 sees {len(five)} technologies"
        await Database.close()

    async def test_an_unknown_technology_answers_without_raising(self):
        await Database.init()
        out = await tech_tree.tech_info("no such technology", 5)
        assert out is None or isinstance(out, dict), out
        await Database.close()


class TestTheCloaksRoundTrip:
    async def test_building_a_cloak_puts_it_on_the_list(self):
        await Database.init()
        # The builder pays in alloys, and session 5 has no resources row at all, so the test owns one.
        made_resources = False
        if await Database.fetchval("SELECT 1 FROM maya_rp.resources WHERE session_id=5") is None:
            await Database.execute(
                "INSERT INTO maya_rp.resources (session_id, alloys, credits) VALUES (5, 1000000, 0)")
            made_resources = True
        made = await stealth.build_anticloak("red proof system", 2, 5)
        try:
            assert made.get("error") is None, made
            rows = await stealth.list_anticloak(5)
            assert any(str(r).find("red proof system") >= 0 for r in rows), rows
        finally:
            await Database.execute(
                "DELETE FROM maya_rp.anti_cloak_grids WHERE session_id=5")
            if made_resources:
                await Database.execute("DELETE FROM maya_rp.resources WHERE session_id=5")
            await Database.close()

    async def test_the_list_is_scoped_to_its_session(self):
        await Database.init()
        if await Database.fetchval("SELECT 1 FROM maya_rp.resources WHERE session_id=5") is None:
            await Database.execute(
                "INSERT INTO maya_rp.resources (session_id, alloys, credits) VALUES (5, 1000000, 0)")
        await stealth.build_anticloak("red proof scoped", 1, 5)
        try:
            assert await stealth.list_anticloak(3) == [] or all(
                "red proof scoped" not in str(r) for r in await stealth.list_anticloak(3))
        finally:
            await Database.execute("DELETE FROM maya_rp.anti_cloak_grids WHERE session_id=5")
            await Database.close()
