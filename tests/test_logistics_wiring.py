"""Cargo that exists, and the guards that keep it real.

`create_cargo` and `transport` both had no production caller. `run_tick` delivered missions nothing
could create, and the cargo table held zero rows, so the feature had never moved anything. Reviewing
`create_cargo` before wiring found no validation at all: a negative quantity was accepted, which is
cargo lighter than nothing, and an empty location type was accepted, which is cargo that is nowhere.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import Database  # noqa: E402
from modules import logistics  # noqa: E402


class TestCreateCargo:
    async def test_negative_quantity_is_refused(self):
        await Database.init()
        out = await logistics.create_cargo("grain", -5, "ship", 1, 5)
        assert "greater than zero" in out.get("error", ""), out
        await Database.close()

    async def test_cargo_with_no_location_is_refused(self):
        await Database.init()
        out = await logistics.create_cargo("grain", 5, "  ", 1, 5)
        assert "nowhere" in out.get("error", ""), out
        await Database.close()

    async def test_real_cargo_lands(self):
        await Database.init()
        out = await logistics.create_cargo("red proof grain", 12, "ship", 7, 5)
        try:
            assert out.get("cargo_id"), out
            qty = await Database.fetchval(
                "SELECT quantity FROM maya_rp.cargo WHERE id=$1", out["cargo_id"])
            assert float(qty) == 12.0, qty
        finally:
            await Database.execute("DELETE FROM maya_rp.cargo WHERE id=$1", out["cargo_id"])
            await Database.close()


class TestTransport:
    async def test_cargo_that_does_not_exist_is_refused(self):
        await Database.init()
        out = await logistics.transport(999_999, "sector", 3, 1, 5)
        assert "does not exist" in out.get("error", ""), out
        await Database.close()

    async def test_a_destination_needs_both_halves(self):
        await Database.init()
        out = await logistics.transport(1, "", 3, 1, 5)
        assert "destination" in out.get("error", ""), out
        await Database.close()
