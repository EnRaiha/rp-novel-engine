"""Operations and crafting: eleven entry points across six modules.

darkops.py (2), espionage.py (2), alchemy.py (2), corporations.py (2), academy.py (1) and crew_system.py
(1). The engine could plan operations, brew recipes, sell blueprints and enrol cadets, and nothing could
ask it to.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest_asyncio  # noqa: E402

from core.db import Database  # noqa: E402
from modules import academy, alchemy, corporations, crew_system, darkops, espionage  # noqa: E402
from tests.conftest import scratch_id  # noqa: E402


@pytest_asyncio.fixture
async def campaign_row(request):
    """The scratch campaign's `maya_rp.sessions` row, the slot `scratch_session` hands out.

    A test asks for this fixture BEFORE `scratch_session`: pytest tears down in reverse order, so
    `scratch_session` clears every child row first and the row is removed last, after nothing references it.
    Sessions 3 and 5 are frozen reference data and are never written.
    """
    sid = scratch_id(request.module.__name__)
    await Database.init()
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1,'rp-engine test scratch','active')"
        " ON CONFLICT (id) DO NOTHING", sid)
    yield sid
    await Database.init()
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", sid)
    await Database.close()


class TestTheRecipeBook:
    async def test_the_recipes_are_readable_and_one_transmutes(self, campaign_row, scratch_session):
        """The recipe table is only read. The inputs are stocked in the scratch campaign, so the brew runs there."""
        sid = scratch_session
        await Database.init()
        recipes = await alchemy.list_recipes()
        assert recipes, "no recipes"
        name = recipes[0]["name"] if isinstance(recipes[0], dict) else recipes[0]
        row = await Database.fetchrow(
            "SELECT inputs FROM maya_rp.alchemy_recipes WHERE name=$1 ORDER BY id LIMIT 1", name)
        inputs = row["inputs"] if row else {}
        inputs = json.loads(inputs) if isinstance(inputs, str) else (inputs or {})
        try:
            for material in inputs:
                await Database.execute(
                    "INSERT INTO maya_rp.material_stockpiles (session_id, material_name, quantity)"
                    " VALUES ($1,$2,$3)", sid, material, 1_000_000)
            out = await alchemy.transmute(name, 1, sid)
            assert out is not None, "transmute answered nothing"
        finally:
            await Database.execute("DELETE FROM maya_rp.material_stockpiles WHERE session_id=$1", sid)
            await Database.close()

    async def test_an_unknown_recipe_is_answered_not_crashed(self, campaign_row, scratch_session):
        """A scratch campaign takes the write; session 5 is frozen reference data."""
        sid = scratch_session
        await Database.init()
        out = await alchemy.transmute("no such recipe at all", 1, sid)
        assert out is not None
        await Database.close()


class TestTheOperations:
    async def test_the_darkops_log_answers(self):
        await Database.init()
        assert isinstance(await darkops.list_darkops(5), list)
        await Database.close()

    async def test_the_espionage_log_answers(self):
        await Database.init()
        assert isinstance(await espionage.list_espionage_log(5), list)
        await Database.close()

    async def test_an_unknown_operation_is_answered_not_crashed(self, campaign_row, scratch_session):
        """The operation is run against a scratch campaign."""
        sid = scratch_session
        await Database.init()
        out = await darkops.run_op("no such operation", "nobody", sid)
        assert out is not None
        await Database.close()


class TestTheSales:
    async def test_the_saleable_list_answers(self):
        await Database.init()
        assert isinstance(await corporations.list_saleable_blueprints(5), list)
        await Database.close()

    async def test_selling_a_project_that_does_not_exist_is_answered(self, campaign_row, scratch_session):
        """A scratch campaign takes the write; session 5 is frozen reference data."""
        sid = scratch_session
        await Database.init()
        out = await corporations.sell_blueprint(sid, 999_999, "nobody", 0)
        assert out is not None
        await Database.close()


class TestTheAcademyAndTheCrew:
    async def test_enrolling_into_a_program_that_does_not_exist_is_answered(self, campaign_row, scratch_session):
        """A scratch campaign takes the write; session 5 is frozen reference data."""
        sid = scratch_session
        await Database.init()
        out = await academy.enroll_crew(999_999, 999_999, 999_999, sid)
        assert out is not None
        await Database.close()

    async def test_producing_crew_answers(self, scratch_session):
        # A scratch session, not session 5: this test used to credit the live arc's crew_pool and then
        # delete the roster row it had just written. The fixture owns the cleanup now.
        await Database.init()
        out = await crew_system.produce_crew(scratch_session)
        assert out is not None
        await Database.close()
