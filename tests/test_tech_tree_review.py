"""Tech tree review: what reading `modules/tech_tree.py` in full turned up.

Three defects. Every test runs in two scratch sessions (900 + pid % 100 and 900 + (pid + 50) % 100)
that the `scratch` fixture creates, and every row of both is removed in FK order after the test.
Sessions 3 and 5 are never written.
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
from modules import tech_tree  # noqa: E402

SESSION = 900 + os.getpid() % 100
OTHER = 900 + (os.getpid() + 50) % 100

_SCRUB = [
    "DELETE FROM maya_rp.scientist_assignments WHERE lab_id IN (SELECT rl.id FROM maya_rp.research_labs rl "
    "JOIN maya_rp.colonies c ON c.id=rl.colony_id WHERE c.session_id=$1)",
    "DELETE FROM maya_rp.scientist_assignments WHERE character_id IN "
    "(SELECT id FROM maya_rp.characters WHERE session_id=$1)",
    "DELETE FROM maya_rp.research_labs WHERE colony_id IN (SELECT id FROM maya_rp.colonies WHERE session_id=$1)",
    "DELETE FROM maya_rp.colonies WHERE session_id=$1",
    "DELETE FROM maya_rp.characters WHERE session_id=$1",
    "DELETE FROM maya_rp.technologies WHERE session_id=$1",
    "DELETE FROM maya_rp.resources WHERE session_id=$1",
    "DELETE FROM maya_rp.sessions WHERE id=$1",
]


async def _scrub(session_id):
    assert session_id not in (3, 5), "tests never touch the frozen campaigns"
    for sql in _SCRUB:
        await Database.execute(sql, session_id)


@pytest_asyncio.fixture(autouse=True)
async def scratch():
    """Two empty scratch sessions; both are scrubbed again after the test."""
    await Database.init()
    for sid in (SESSION, OTHER):
        await _scrub(sid)
        await Database.execute(
            "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1,'tech tree review scratch','active') "
            "ON CONFLICT (id) DO NOTHING", sid)
    try:
        yield
    finally:
        for sid in (SESSION, OTHER):
            await _scrub(sid)
        await Database.close()


async def _colony(session_id=SESSION, name="review colony"):
    await Database.execute(
        "DELETE FROM maya_rp.research_labs WHERE colony_id IN "
        "(SELECT id FROM maya_rp.colonies WHERE session_id = $1 AND name = $2)",
        session_id, name)
    await Database.execute(
        "DELETE FROM maya_rp.colonies WHERE session_id = $1 AND name = $2", session_id, name)
    return await Database.fetchval(
        "INSERT INTO maya_rp.colonies (id, session_id, name, population, status) "
        "VALUES ((SELECT COALESCE(MAX(id), 0) + 500000 FROM maya_rp.colonies), $1, $2, 0, 'active') "
        "RETURNING id",
        session_id, name)


async def _lab(colony_id, name="review lab"):
    return await Database.fetchval(
        "INSERT INTO maya_rp.research_labs (id, colony_id, name, level, research_field, research_rate) "
        "VALUES ((SELECT COALESCE(MAX(id), 0) + 500000 FROM maya_rp.research_labs), $1, $2, 1, 'physics', 1.0) "
        "RETURNING id",
        colony_id, name)


async def _character(session_id=SESSION, name="review scientist"):
    await Database.execute(
        "DELETE FROM maya_rp.scientist_assignments WHERE character_id IN "
        "(SELECT id FROM maya_rp.characters WHERE session_id = $1 AND name = $2)", session_id, name)
    await Database.execute(
        "DELETE FROM maya_rp.characters WHERE session_id = $1 AND name = $2", session_id, name)
    return await Database.fetchval(
        "INSERT INTO maya_rp.characters (id, session_id, name, status) "
        "VALUES ((SELECT COALESCE(MAX(id), 0) + 500000 FROM maya_rp.characters), $1, $2, 'active') "
        "RETURNING id",
        session_id, name)


async def _drop(lab_id, character_id, colony_id):
    if character_id:
        await Database.execute(
            "DELETE FROM maya_rp.scientist_assignments WHERE character_id = $1", character_id)
        await Database.execute("DELETE FROM maya_rp.characters WHERE id = $1", character_id)
    if lab_id:
        await Database.execute("DELETE FROM maya_rp.research_labs WHERE id = $1", lab_id)
    if colony_id:
        await Database.execute("DELETE FROM maya_rp.colonies WHERE id = $1", colony_id)


class TestTheLabBelongsToItsCampaign:
    async def test_another_campaigns_lab_is_refused(self):
        """`research_labs` carries no session_id; the bare id check let a scientist cross campaigns."""
        colony = lab = character = None
        try:
            colony = await _colony(session_id=OTHER, name="review colony other")
            lab = await _lab(colony, "review lab other")
            character = await _character(SESSION)
            out = await tech_tree.assign_scientist("review scientist", lab, "physics", SESSION)
            assert f"not found in session {SESSION}" in out.get("error", ""), out
            count = await Database.fetchval(
                "SELECT COUNT(*) FROM maya_rp.scientist_assignments WHERE character_id = $1",
                character)
            assert count == 0, "a scientist from one campaign was assigned to another's lab"
        finally:
            await _drop(lab, character, colony)

    async def test_its_own_lab_accepts_the_scientist(self):
        colony = lab = character = None
        try:
            colony = await _colony()
            lab = await _lab(colony)
            character = await _character()
            out = await tech_tree.assign_scientist("review scientist", lab, "physics", SESSION)
            assert out["lab_id"] == lab, out
            assigned = await Database.fetchval(
                "SELECT lab_id FROM maya_rp.scientist_assignments WHERE character_id = $1",
                character)
            assert assigned == lab, assigned
        finally:
            await _drop(lab, character, colony)

    async def test_an_unknown_lab_is_refused(self):
        character = None
        try:
            character = await _character()
            out = await tech_tree.assign_scientist("review scientist", 999999999, "physics", SESSION)
            assert "not found" in out.get("error", ""), out
        finally:
            await _drop(None, character, None)


class TestTheTickContract:
    async def test_a_session_with_nothing_in_progress_carries_every_key(self):
        """One path answered with `active_projects` alone, so a caller reading `completed` raised."""
        out = await tech_tree.run_tick(SESSION)
        assert out == {"active": 0, "completed": 0, "active_projects": 0}, out

    async def test_a_failing_tick_is_logged_as_a_fault(self, monkeypatch):
        seen = []

        async def boom(*args, **kwargs):
            raise RuntimeError("tech query died")

        monkeypatch.setattr(tech_tree.Database, "fetch", boom)
        monkeypatch.setattr(tech_tree, "error", lambda module, message: seen.append(message))
        out = await tech_tree.run_tick(SESSION)
        assert "tech query died" in out["error"], out
        assert seen, "a failing tick returned a dict and said nothing at fault level"


class TestTheReads:
    async def test_the_view_is_scoped_to_its_session(self):
        assert await tech_tree.view_tech(SESSION) == [], "a scratch session lists technologies"
        assert await tech_tree.tech_info("anything", SESSION) is None

    async def test_listing_labs_is_scoped_through_the_colony(self):
        colony = lab = None
        try:
            colony = await _colony()
            lab = await _lab(colony)
            assert [r["id"] for r in await tech_tree.list_labs(SESSION)] == [lab]
            assert await tech_tree.list_labs(OTHER) == []
        finally:
            await _drop(lab, None, colony)
