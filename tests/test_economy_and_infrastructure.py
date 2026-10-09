"""One ledger rule, and facilities that belong to a session.

`_check_afford` and `_deduct_resources` existed as three copies, in infrastructure, space_horror and
megastructures_ports. The column whitelist is the part that must not drift: an unlisted resource is
skipped by the deduction, so a building could be paid for with nothing and no error would appear. And
the view the facility reads go through exposed no session_id at all, so listing them returned every
campaign's buildings.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import Database  # noqa: E402
from modules import infrastructure  # noqa: E402
from modules._economy import _deduct_resources  # noqa: E402


class TestTheSharedLedger:
    async def test_an_unlisted_resource_is_refused_and_named(self):
        """Skipping was the old contract: it charged nothing for `unicorns` and
        said so under a `#skipped` string key inside a dict of amounts, which is
        a mixed-type payload and a building paid for with nothing."""
        import pytest as _pytest

        await Database.init()
        with _pytest.raises(ValueError, match="unicorns"):
            await _deduct_resources(3, {"credits": 0, "unicorns": 5})
        await Database.close()

    async def test_a_charge_is_reported_rather_than_silent(self):
        """The old body returned nothing, so a session with no resources row paid nothing in silence."""
        await Database.init()
        charged = await _deduct_resources(3, {"credits": 0})
        assert charged.get("credits") == 0, charged
        await Database.close()

    def test_all_three_modules_share_one_copy(self):
        from modules import megastructures_ports, space_horror

        # The check that means something: the three names are one object, so no copy can drift.
        assert infrastructure._deduct_resources is megastructures_ports._deduct_resources
        assert infrastructure._deduct_resources is space_horror._deduct_resources


class TestSessionScope:
    async def test_a_facility_built_in_one_session_is_invisible_to_another(self, scratch_campaign):
        mine_sid = scratch_campaign
        other_sid = 900 + (mine_sid - 900 + 50) % 100
        await Database.init()
        kind = await Database.fetchval(
            "SELECT id FROM maya_rp.infrastructure_types ORDER BY id LIMIT 1")
        assert kind, "no infrastructure type to build"
        row = await Database.fetchrow(
            "INSERT INTO maya_rp.infrastructure_instances"
            " (session_id, infrastructure_type_id, name, level, status)"
            " VALUES ($1, $2, 'red proof yard', 1, 'active') RETURNING id", mine_sid, kind)
        try:
            mine = await infrastructure.list_infrastructure(mine_sid)
            theirs = await infrastructure.list_infrastructure(other_sid)
            assert any(r["id"] == row["id"] for r in mine), "a session cannot see its own facility"
            assert not any(r["id"] == row["id"] for r in theirs), "another session sees this facility"
            opened = await infrastructure.get_infrastructure(row["id"], other_sid)
            assert opened == {}, "the detail read leaks across sessions"
        finally:
            await Database.execute(
                "DELETE FROM maya_rp.infrastructure_instances WHERE id=$1", row["id"])
            await Database.close()
