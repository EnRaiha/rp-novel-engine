"""Space Horror review: what reading `modules/space_horror.py` in full turned up.

The tick functions took a session and never put it in a query, so one campaign's horror advanced on
another campaign's turn. Nothing here writes to session 3, and every row this file creates in session
5 is removed in a `finally`.
"""
from __future__ import annotations

import inspect
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from core.db import Database  # noqa: E402
from modules import space_horror  # noqa: E402

SESSION = 5
SECTOR_NAME = "review sector"


async def _sector():
    return await Database.fetchval(
        "INSERT INTO maya_rp.sectors (id, session_id, name, x_coord, y_coord) "
        "VALUES ((SELECT COALESCE(MAX(id), 0) + 1 FROM maya_rp.sectors), $1, $2, 0, 0) "
        "RETURNING id", SESSION, SECTOR_NAME)


async def _infestation(session_id=SESSION, sector_id=None, stage_id=1, progress=0, biomass=100):
    return await Database.fetchval(
        "INSERT INTO maya_rp.infestation_instances "
        "(session_id, sector_id, stage_id, biomass, spread_progress, status) "
        "VALUES ($1, $2, $3, $4, $5, 'active') RETURNING id",
        session_id, sector_id, stage_id, biomass, progress)


async def _campaign(infestation_id, session_id=SESSION, progress=0):
    return await Database.fetchval(
        "INSERT INTO maya_rp.eradication_campaigns "
        "(session_id, target_infestation_id, campaign_name, strategy, assets_assigned, status, progress) "
        "VALUES ($1, $2, 'review campaign', 'systematic', '[]'::jsonb, 'active', $3) RETURNING id",
        session_id, infestation_id, progress)


async def _drop(sector_id, iid=None, cid=None):
    if cid is not None:
        await Database.execute("DELETE FROM maya_rp.eradication_campaigns WHERE id = $1", cid)
    await Database.execute(
        "DELETE FROM maya_rp.infestation_instances WHERE session_id = $1 AND sector_id = $2",
        SESSION, sector_id)
    await Database.execute("DELETE FROM maya_rp.sectors WHERE id = $1", sector_id)


class TestTheTickStaysInItsCampaign:
    async def test_spreading_ignores_another_campaign(self):
        await Database.init()
        sector = await _sector()
        iid = await _infestation(sector_id=sector, progress=10)
        try:
            await space_horror.spread_infestation(7, 1.0)
            progress = await Database.fetchval(
                "SELECT spread_progress FROM maya_rp.infestation_instances WHERE id = $1", iid)
            assert float(progress) == 10.0, "another campaign's tick spread this infestation"
        finally:
            await _drop(sector, iid)
            await Database.close()

    async def test_eradication_ignores_another_campaign(self):
        await Database.init()
        sector = await _sector()
        iid = await _infestation(sector_id=sector, biomass=500)
        cid = await _campaign(iid, progress=0)
        try:
            await space_horror.advance_eradication(7, 1.0)
            progress = await Database.fetchval(
                "SELECT progress FROM maya_rp.eradication_campaigns WHERE id = $1", cid)
            assert float(progress) == 0.0, "another campaign's tick advanced this campaign"
        finally:
            await _drop(sector, iid, cid)
            await Database.close()

    async def test_eradication_advances_its_own_campaign(self):
        await Database.init()
        sector = await _sector()
        iid = await _infestation(sector_id=sector, biomass=500)
        cid = await _campaign(iid, progress=0)
        try:
            await space_horror.advance_eradication(SESSION, 1.0)
            progress = await Database.fetchval(
                "SELECT progress FROM maya_rp.eradication_campaigns WHERE id = $1", cid)
            assert float(progress) > 0.0, progress
        finally:
            await _drop(sector, iid, cid)
            await Database.close()


class TestTheDefaultCampaign:
    def test_the_tick_does_not_default_to_the_frozen_campaign(self):
        default = inspect.signature(space_horror.run_tick).parameters["session_id"].default
        assert default is None, default

    async def test_the_detail_read_answers_without_a_session_argument(self):
        """`Config` was used here and never imported, so the default path raised NameError."""
        await Database.init()
        try:
            assert await space_horror.get_infestation_detail(999999999) == {}
        finally:
            await Database.close()


class TestTheTickSpeaks:
    async def test_a_failing_tick_is_logged_as_a_fault(self, monkeypatch):
        seen = []

        async def boom(session_id, game_days=0.5):
            raise RuntimeError("infestation query died")

        monkeypatch.setattr(space_horror, "spread_infestation", boom)
        monkeypatch.setattr(space_horror, "error", lambda module, message: seen.append(message))
        out = await space_horror.run_tick(SESSION)
        assert "infestation query died" in out["error"], out
        assert seen, "a failing tick printed and said nothing at fault level"


class TestTheDoors:
    async def test_containment_on_an_unknown_infestation_is_refused(self):
        await Database.init()
        try:
            out = await space_horror.apply_containment(SESSION, 999999999, "quarantine")
            assert "not found" in out["error"], out
        finally:
            await Database.close()

    async def test_launching_against_an_unknown_infestation_is_refused(self):
        await Database.init()
        try:
            out = await space_horror.launch_eradication(SESSION, 999999999)
            assert "not found" in out["error"], out
        finally:
            await Database.close()
