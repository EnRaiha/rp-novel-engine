"""The forge: a blueprint name belongs to one campaign, and the fitting has a door.

Six entry points of weapon_design.py had no caller. `apply_upgrade` had been repaired earlier in this
review and still had none, which is the state a repair alone does not fix.

`design_blueprint` checked whether a name already existed with no session filter, so the first campaign
to invent a name blocked every other campaign from inventing it.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import Database  # noqa: E402
from modules import weapon_design as wd  # noqa: E402


async def _credits(session_id: int) -> bool:
    return await Database.fetchval(
        "SELECT 1 FROM maya_rp.resources WHERE session_id=$1", session_id) is not None


class TestTheArmouryIsShared:
    """`weapon_blueprints` has no session_id, so a name is global. My first version of this test asserted
    the opposite and the schema said no."""

    async def test_the_same_name_twice_is_refused_anywhere(self):
        await Database.init()
        made_resources = False
        try:
            if not await _credits(5):
                await Database.execute(
                    "INSERT INTO maya_rp.resources (session_id, credits) VALUES (5, 50000000)")
                made_resources = True
            first = await wd.design_blueprint("red proof twice", "Special", 0, 1, "L", 1, 5)
            assert first.get("error") is None, first
            second = await wd.design_blueprint("red proof twice", "Special", 0, 1, "L", 1, 5)
            assert "already exists" in second.get("error", ""), second
        finally:
            await Database.execute(
                "DELETE FROM maya_rp.weapon_blueprints WHERE LOWER(name)=LOWER($1)", "red proof twice")
            if made_resources:
                await Database.execute("DELETE FROM maya_rp.resources WHERE session_id=5")
            await Database.close()


class TestTheProductionLine:
    async def test_an_unknown_blueprint_is_refused(self):
        await Database.init()
        out = await wd.produce_weapons("no such blueprint anywhere", 1, 5)
        assert "not found" in out.get("error", ""), out
        await Database.close()
