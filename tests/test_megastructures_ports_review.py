"""Megastructures & Ports review: what reading the module in full turned up.

The tick took a session and never put it in its read, and the port upgrade resolved its port by id
alone. Nothing here writes to session 3, and every row this file creates in session 5 is removed in a
`finally`.
"""
from __future__ import annotations

import inspect
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from core.db import Database  # noqa: E402
from modules import megastructures_ports as mp  # noqa: E402

SESSION = 5
TYPE_ID = 1          # Dyson Sphere: two phases, phase 1 costs fuel, alloys and dream essence
PORT_TYPE_ID = 1     # Spaceport: upgrades large_spaceport, shipyard
UPGRADE = "large_spaceport"


async def _construction(session_id=SESSION, progress=0, phase=1):
    return await Database.fetchval(
        "INSERT INTO maya_rp.megastructure_construction "
        "(session_id, megastructure_type_id, current_phase, progress_pct, status, started_at) "
        "VALUES ($1, $2, $3, $4, 'construction', NOW()) RETURNING id",
        session_id, TYPE_ID, phase, progress)


async def _port(session_id=SESSION, level=1):
    return await Database.fetchval(
        "INSERT INTO maya_rp.ports (session_id, port_type_id, name, level, status) "
        "VALUES ($1, $2, 'review port', $3, 'active') RETURNING id",
        session_id, PORT_TYPE_ID, level)


async def _drop_construction(cid):
    await Database.execute("DELETE FROM maya_rp.megastructure_construction WHERE id = $1", cid)


async def _drop_port(pid):
    await Database.execute("DELETE FROM maya_rp.port_upgrades WHERE port_id = $1", pid)
    await Database.execute("DELETE FROM maya_rp.ports WHERE id = $1", pid)


class TestTheTickStaysInItsCampaign:
    async def test_advancing_ignores_another_campaign(self):
        """One phase is 365 game days, so 365 days in one call is the call that would pause it."""
        await Database.init()
        cid = await _construction(progress=0)
        try:
            await mp.advance_megastructure(7, 365.0)
            status = await Database.fetchval(
                "SELECT status FROM maya_rp.megastructure_construction WHERE id = $1", cid)
            assert status == "construction", "another campaign's tick paused this construction site"
        finally:
            await _drop_construction(cid)
            await Database.close()

    async def test_advancing_its_own_site_reports_what_it_did(self):
        await Database.init()
        cid = await _construction(progress=0)
        try:
            tally = await mp.advance_megastructure(SESSION, 365.0)
            assert tally == {"advanced": 1, "paused": 1, "completed": 0}, tally
            row = await Database.fetchrow(
                "SELECT status, progress_pct FROM maya_rp.megastructure_construction WHERE id = $1", cid)
            assert row["status"] == "paused", dict(row)
        finally:
            await _drop_construction(cid)
            await Database.close()

    async def test_a_short_tick_stores_nothing_at_all(self):
        """`progress_pct` is an integer column and the advance is a fraction of a percent.

        Reported, not fixed: the write truncates, so a 0.5 game-day tick against a 365-day phase
        stores 0 and the construction never moves. A whole-number column is a migration.
        """
        await Database.init()
        cid = await _construction(progress=0)
        try:
            await mp.advance_megastructure(SESSION, 0.5)
            progress = await Database.fetchval(
                "SELECT progress_pct FROM maya_rp.megastructure_construction WHERE id = $1", cid)
            assert progress == 0
        finally:
            await _drop_construction(cid)
            await Database.close()

    async def test_the_tick_does_not_default_to_the_frozen_campaign(self):
        default = inspect.signature(mp.run_tick).parameters["session_id"].default
        assert default is None, default

    async def test_a_failing_tick_is_logged_as_a_fault(self, monkeypatch):
        seen = []

        async def boom(session_id, game_days=0.5):
            raise RuntimeError("construction query died")

        monkeypatch.setattr(mp, "advance_megastructure", boom)
        monkeypatch.setattr(mp, "error", lambda module, message: seen.append(message))
        out = await mp.run_tick(SESSION)
        assert "construction query died" in out["error"], out
        assert seen, "a failing tick printed and said nothing at fault level"


class TestThePorts:
    async def test_upgrading_another_campaigns_port_is_refused(self):
        await Database.init()
        pid = await _port()
        try:
            out = await mp.upgrade_port(7, pid, UPGRADE)
            assert "not found in session 7" in out.get("error", ""), out
            level = await Database.fetchval("SELECT level FROM maya_rp.ports WHERE id = $1", pid)
            assert level == 1, "another campaign raised this port"
        finally:
            await _drop_port(pid)
            await Database.close()

    async def test_a_port_without_the_upgrade_is_refused(self):
        await Database.init()
        pid = await _port()
        try:
            out = await mp.upgrade_port(SESSION, pid, "orbital_cathedral")
            assert "not available" in out.get("error", ""), out
        finally:
            await _drop_port(pid)
            await Database.close()


class TestTheStatusReaders:
    async def test_both_readers_answer_without_a_session_argument(self):
        """`Config` is read here and the module never imported it: the default path was NameError."""
        await Database.init()
        try:
            assert await mp.get_megastructure_status() == []
            assert await mp.get_port_overview() == []
        finally:
            await Database.close()

    async def test_a_construction_in_another_session_is_invisible(self):
        await Database.init()
        cid = await _construction()
        try:
            assert await mp.get_megastructure_status(7) == []
            assert len(await mp.get_megastructure_status(SESSION)) == 1
        finally:
            await _drop_construction(cid)
            await Database.close()


class TestTheDoors:
    async def test_an_unknown_type_is_refused(self):
        await Database.init()
        try:
            out = await mp.start_construction(SESSION, 999999999)
            assert "not found" in out["error"], out
        finally:
            await Database.close()
