"""megastructures_ports fix 2: a phase, a port and a completion are charged and applied in one transaction.

Every write lands in a scratch session (900-999). Sessions 3 and 5 are not touched.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from asyncpg.exceptions import PostgresError  # noqa: E402

from core.config import Config  # noqa: E402
from core.db import Database  # noqa: E402
from modules import megastructures_ports as mp  # noqa: E402

DYSON, WORLDFORGE, AETHER_NEXUS, STELLAR_FORGE = 1, 3, 4, 5
SPACEPORT = 1
_RESOURCES = ("credits", "alloys", "fuel", "dream_essence", "rare_earth", "starsteel",
              "void_crystal", "aetherium")


async def _wipe(session_id):
    await Database.execute(
        "DELETE FROM maya_rp.port_upgrades WHERE port_id IN"
        " (SELECT id FROM maya_rp.ports WHERE session_id=$1)", session_id)
    for table in ("ports", "megastructure_construction", "story_log", "territory", "resources"):
        await Database.execute(f"DELETE FROM maya_rp.{table} WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", session_id)


@pytest_asyncio.fixture
async def sid(scratch_session, monkeypatch):
    """A scratch session with no resources row. The default session resolves to the scratch id too."""
    monkeypatch.setattr(Config, "SESSION_ID", scratch_session)
    await Database.init()
    await _wipe(scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status, game_day) "
        "VALUES ($1, 'mega callers fix2', 'active', 500)", scratch_session)
    try:
        yield scratch_session
    finally:
        await _wipe(scratch_session)
        await Database.close()


async def _fund(session_id, **cols):
    unknown = set(cols) - set(_RESOURCES)
    assert not unknown, unknown
    await Database.execute("DELETE FROM maya_rp.resources WHERE session_id=$1", session_id)
    await Database.execute(
        f"INSERT INTO maya_rp.resources (session_id, {', '.join(_RESOURCES)}) "
        f"VALUES ($1, {', '.join(f'${n}' for n in range(2, len(_RESOURCES) + 2))})",
        session_id, *(cols.get(c, 0) for c in _RESOURCES))


async def _site(session_id, type_id, phase, progress, status="construction", territory_id=None):
    return await Database.fetchval(
        "INSERT INTO maya_rp.megastructure_construction (session_id, megastructure_type_id,"
        " territory_id, current_phase, progress_pct, started_at, status)"
        " VALUES ($1, $2, $3, $4, $5, NOW(), $6) RETURNING id",
        session_id, type_id, territory_id, phase, progress, status)


async def _territory(session_id, name, morale=50):
    return await Database.fetchval(
        "INSERT INTO maya_rp.territory (session_id, system_name, controlling_faction, morale)"
        " VALUES ($1, $2, 'test faction', $3) RETURNING id", session_id, name, morale)


async def _site_state(cid):
    row = await Database.fetchrow(
        "SELECT current_phase, progress_pct, status FROM maya_rp.megastructure_construction"
        " WHERE id=$1", cid)
    return row["current_phase"], row["progress_pct"], row["status"]


async def _balance(session_id, column):
    return await Database.fetchval(
        f"SELECT {column} FROM maya_rp.resources WHERE session_id=$1", session_id)


async def _morale(territory_id):
    return await Database.fetchval("SELECT morale FROM maya_rp.territory WHERE id=$1", territory_id)


async def _count(table, session_id):
    return await Database.fetchval(
        f"SELECT count(*) FROM maya_rp.{table} WHERE session_id=$1", session_id)


def _slow(monkeypatch, name):
    """Wrap `mp.<name>` so it yields for 0.2 s first, long enough for an overlapping call to start."""
    real = getattr(mp, name)

    async def slow(sid_, *a, **k):
        await asyncio.sleep(0.2)
        return await real(sid_, *a, **k)

    monkeypatch.setattr(mp, name, slow)


class TestThePhaseCharge:
    async def test_two_ticks_charge_the_next_phase_once(self, sid, monkeypatch):
        await _fund(sid, alloys=450000, rare_earth=2000)
        cid = await _site(sid, DYSON, 1, 100)
        _slow(monkeypatch, "_deduct_resources")
        await asyncio.gather(mp.advance_megastructure(sid, 1.0), mp.advance_megastructure(sid, 1.0))
        assert await _balance(sid, "alloys") == 250000
        assert await _balance(sid, "rare_earth") == 1000
        assert (await _site_state(cid))[0] == 2

    async def test_an_unpaid_phase_rolls_the_claim_back(self, sid):
        await _fund(sid, alloys=1000)
        cid = await _site(sid, DYSON, 1, 100)
        await mp.advance_megastructure(sid, 1.0)
        assert await _site_state(cid) == (1, 100, "paused")
        assert await _balance(sid, "alloys") == 1000

    async def test_an_unchargeable_phase_pauses_the_site(self, sid, monkeypatch):
        await _fund(sid, alloys=250000, rare_earth=1000)
        cid = await _site(sid, DYSON, 1, 100)
        errors = []

        async def refuse(session_id, costs, conn=None):
            raise ValueError("cost names resources the ledger cannot charge: ['food']")

        monkeypatch.setattr(mp, "_deduct_resources", refuse)
        monkeypatch.setattr(mp, "error", lambda module, msg: errors.append(msg))
        tally = await mp.advance_megastructure(sid, 1.0)
        assert tally["paused"] == 1, tally
        assert (await _site_state(cid))[2] == "paused"
        assert len(errors) == 1 and "cannot be charged" in errors[0], errors

    async def test_a_stale_snapshot_cannot_touch_a_site_that_moved_on(self, sid, monkeypatch):
        cid = await _site(sid, DYSON, 2, 0)
        phases = json.loads(await Database.fetchval(
            "SELECT construction_phases FROM maya_rp.megastructure_types WHERE id=$1", DYSON))
        stale = {"id": cid, "status": "construction", "current_phase": 1, "progress_pct": 100,
                 "megastructure_type_id": DYSON, "territory_id": None, "name": "Dyson Sphere",
                 "construction_phases": phases}

        class Stale:
            """Answers the tick's read with the snapshot and passes every write to the real pool."""

            @staticmethod
            async def fetch(sql, *args):
                return [stale]

            @staticmethod
            async def execute(sql, *args):
                return await Database.execute(sql, *args)

            @staticmethod
            async def fetchval(sql, *args):
                return await Database.fetchval(sql, *args)

            @staticmethod
            async def fetchrow(sql, *args):
                return await Database.fetchrow(sql, *args)

            @staticmethod
            def transaction():
                return Database.transaction()

        monkeypatch.setattr(mp, "Database", Stale)
        await mp.advance_megastructure(sid, 1.0)
        assert await _site_state(cid) == (2, 0, "construction")


class TestTheCompletion:
    async def test_completion_and_benefits_commit_together(self, sid, monkeypatch):
        cid = await _site(sid, WORLDFORGE, 2, 100)

        async def boom(session_id, const, conn=None):
            raise RuntimeError("benefit failed")

        monkeypatch.setattr(mp, "_apply_benefits", boom)
        with pytest.raises(RuntimeError):
            await mp.advance_megastructure(sid, 1.0)
        assert (await _site_state(cid))[2] == "construction"

    async def test_a_completion_applies_its_benefits_once(self, sid, monkeypatch):
        await _fund(sid, starsteel=0, rare_earth=0)
        await _site(sid, STELLAR_FORGE, 2, 100)
        _slow(monkeypatch, "_apply_benefits")
        # A cold pool opens the second connection after the first tick has already completed the site,
        # so the second tick would not see it. Open four connections first so both ticks read it.
        await asyncio.gather(*(Database.fetchval("SELECT pg_sleep(0.05)") for _ in range(4)))
        await asyncio.gather(mp.advance_megastructure(sid, 1.0), mp.advance_megastructure(sid, 1.0))
        assert await _balance(sid, "starsteel") == 10
        assert await _balance(sid, "rare_earth") == 50

    async def test_the_alloy_stockpile_is_not_multiplied(self, sid, monkeypatch):
        await _fund(sid, alloys=1000000)
        await _site(sid, WORLDFORGE, 2, 100)
        warnings = []
        monkeypatch.setattr(mp, "warn", lambda module, msg: warnings.append(msg), raising=False)
        await mp.advance_megastructure(sid, 1.0)
        assert await _balance(sid, "alloys") == 1000000
        assert any("production_mult" in w for w in warnings), warnings

    async def test_morale_reaches_only_the_site_territory(self, sid):
        first, second = await _territory(sid, "first"), await _territory(sid, "second")
        await _site(sid, AETHER_NEXUS, 2, 100, territory_id=first)
        await mp.advance_megastructure(sid, 1.0)
        assert await _morale(first) == 70
        assert await _morale(second) == 50

    async def test_a_site_without_a_territory_moves_no_morale(self, sid):
        first, second = await _territory(sid, "first"), await _territory(sid, "second")
        await _site(sid, AETHER_NEXUS, 2, 100, territory_id=None)
        await mp.advance_megastructure(sid, 1.0)
        assert await _morale(first) == 50
        assert await _morale(second) == 50


class TestBuildPort:
    async def test_build_port_charge_and_row_are_one_unit(self, sid):
        await _fund(sid, credits=100000, alloys=1000)
        with pytest.raises(PostgresError):
            await mp.build_port(sid, 999999999, SPACEPORT)
        assert await _balance(sid, "credits") == 100000
        assert await _balance(sid, "alloys") == 1000
        assert await _count("ports", sid) == 0

    async def test_build_port_refuses_a_stale_check_without_raising(self, sid, monkeypatch):
        await _fund(sid, credits=10)
        territory = await _territory(sid, "port site")

        async def stale_ok(*a, **k):
            return True, ""

        monkeypatch.setattr(mp, "_check_afford", stale_ok)
        out = await mp.build_port(sid, territory, SPACEPORT)
        assert "Insufficient resources" in out["error"], out
        assert await _count("ports", sid) == 0
        assert await _balance(sid, "credits") == 10

    async def test_build_port_charges_and_records(self, sid):
        await _fund(sid, credits=100000, alloys=1000)
        territory = await _territory(sid, "port site")
        out = await mp.build_port(sid, territory, SPACEPORT)
        assert "error" not in out, out
        assert await _balance(sid, "credits") == 50000
        assert await _balance(sid, "alloys") == 500
        assert await _count("ports", sid) == 1


async def _port(session_id, level):
    return await Database.fetchval(
        "INSERT INTO maya_rp.ports (session_id, port_type_id, name, level, status)"
        " VALUES ($1, $2, 'fix2 port', $3, 'active') RETURNING id", session_id, SPACEPORT, level)


class TestUpgradePort:
    async def test_upgrade_port_charge_and_level_are_one_unit(self, sid):
        """100000 * 30000 overflows `port_upgrades.cost_credits` (INTEGER): the insert raises after the charge."""
        await _fund(sid, credits=5000000000)
        pid = await _port(sid, 30000)
        with pytest.raises(PostgresError):
            await mp.upgrade_port(sid, pid, "large_spaceport")
        level = await Database.fetchval("SELECT level FROM maya_rp.ports WHERE id=$1", pid)
        assert level == 30000
        assert await _balance(sid, "credits") == 5000000000
        assert await Database.fetchval(
            "SELECT count(*) FROM maya_rp.port_upgrades WHERE port_id=$1", pid) == 0

    async def test_two_upgrades_of_one_level_charge_once(self, sid, monkeypatch):
        await _fund(sid, credits=1000000)
        pid = await _port(sid, 1)
        _slow(monkeypatch, "_deduct_resources")
        results = await asyncio.gather(mp.upgrade_port(sid, pid, "large_spaceport"),
                                       mp.upgrade_port(sid, pid, "shipyard"))
        assert sorted("new_level" in r for r in results) == [False, True], results
        assert sorted("error" in r for r in results) == [False, True], results
        port = await Database.fetchrow(
            "SELECT level, upgrades_applied FROM maya_rp.ports WHERE id=$1", pid)
        assert port["level"] == 2
        assert await _balance(sid, "credits") == 900000
        assert len(json.loads(port["upgrades_applied"])) == 1
