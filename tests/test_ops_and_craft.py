"""Operations and crafting: eleven entry points across six modules.

darkops.py (2), espionage.py (2), alchemy.py (2), corporations.py (2), academy.py (1) and crew_system.py
(1). The engine could plan operations, brew recipes, sell blueprints and enrol cadets, and nothing could
ask it to.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import Database  # noqa: E402
from modules import academy, alchemy, corporations, crew_system, darkops, espionage  # noqa: E402


class TestTheRecipeBook:
    async def test_the_recipes_are_readable_and_one_transmutes(self):
        await Database.init()
        recipes = await alchemy.list_recipes()
        assert recipes, "no recipes"
        name = recipes[0]["name"] if isinstance(recipes[0], dict) else recipes[0]
        out = await alchemy.transmute(name, 1, 5)
        assert out is not None, "transmute answered nothing"
        await Database.close()

    async def test_an_unknown_recipe_is_answered_not_crashed(self):
        await Database.init()
        out = await alchemy.transmute("no such recipe at all", 1, 5)
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

    async def test_an_unknown_operation_is_answered_not_crashed(self):
        await Database.init()
        out = await darkops.run_op("no such operation", "nobody", 5)
        assert out is not None
        await Database.close()


class TestTheSales:
    async def test_the_saleable_list_answers(self):
        await Database.init()
        assert isinstance(await corporations.list_saleable_blueprints(5), list)
        await Database.close()

    async def test_selling_a_project_that_does_not_exist_is_answered(self):
        await Database.init()
        out = await corporations.sell_blueprint(5, 999_999, "nobody", 0)
        assert out is not None
        await Database.close()


class TestTheAcademyAndTheCrew:
    async def test_enrolling_into_a_program_that_does_not_exist_is_answered(self):
        await Database.init()
        out = await academy.enroll_crew(999_999, 999_999, 999_999, 5)
        assert out is not None
        await Database.close()

    async def test_producing_crew_answers(self, scratch_session):
        # A scratch session, not session 5: this test used to credit the live arc's crew_pool and then
        # delete the roster row it had just written. The fixture owns the cleanup now.
        await Database.init()
        out = await crew_system.produce_crew(scratch_session)
        assert out is not None
        await Database.close()
