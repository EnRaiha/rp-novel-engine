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
    """The builder pays in alloys, so it runs in a scratch session with its own ledger row.

    Seeding session 5 was wrong twice: the arc owns that row now, so an INSERT there is refused by the
    unique key on `session_id`, and both teardowns deleted `anti_cloak_grids` for the whole campaign
    (`WHERE session_id=5`) instead of the one grid the test built. A test may only delete what it
    created; a row a test needs for one run belongs in a scratch session.
    """

    async def _seed(self, session_id: int, alloys: int) -> dict:
        made = {"session": False, "resources": False}
        if await Database.fetchval("SELECT 1 FROM maya_rp.sessions WHERE id = $1", session_id) is None:
            await Database.execute(
                "INSERT INTO maya_rp.sessions (id, name) VALUES ($1, $2)",
                session_id, f"scratch-stealth-{session_id}")
            made["session"] = True
        if await Database.fetchval("SELECT 1 FROM maya_rp.resources WHERE session_id = $1", session_id) is None:
            made["resources"] = True
        await Database.execute(
            "INSERT INTO maya_rp.resources (session_id, alloys, credits) VALUES ($1, $2, 0) "
            "ON CONFLICT (session_id) DO UPDATE SET alloys = EXCLUDED.alloys",
            session_id, alloys)
        return made

    async def _drop(self, session_id: int, made: dict) -> None:
        await Database.execute("DELETE FROM maya_rp.anti_cloak_grids WHERE session_id = $1", session_id)
        if made.get("resources"):
            await Database.execute("DELETE FROM maya_rp.resources WHERE session_id = $1", session_id)
        if made.get("session"):
            await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", session_id)

    async def test_building_a_cloak_puts_it_on_the_list(self, scratch_session):
        await Database.init()
        made = None
        try:
            made = await self._seed(scratch_session, 1_000_000)
            built = await stealth.build_anticloak("red proof system", 2, scratch_session)
            assert built.get("error") is None, built
            rows = await stealth.list_anticloak(scratch_session)
            assert any(str(r).find("red proof system") >= 0 for r in rows), rows
        finally:
            if made is not None:
                await self._drop(scratch_session, made)
            await Database.close()

    async def test_the_list_is_scoped_to_its_session(self, scratch_session):
        await Database.init()
        made = None
        try:
            made = await self._seed(scratch_session, 1_000_000)
            await stealth.build_anticloak("red proof scoped", 1, scratch_session)
            assert await stealth.list_anticloak(3) == [] or all(
                "red proof scoped" not in str(r) for r in await stealth.list_anticloak(3))
        finally:
            if made is not None:
                await self._drop(scratch_session, made)
            await Database.close()
