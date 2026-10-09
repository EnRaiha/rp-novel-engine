"""infrastructure and manufacturing fix 2: a build, an upgrade and a production line charge and write
in one transaction.

Every write lands in a scratch session (900-999). Sessions 3 and 5 are not touched, and
`Config.SESSION_ID` is pinned to the scratch id so a default cannot resolve to the live arc.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys
from contextlib import asynccontextmanager

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from asyncpg.exceptions import PostgresError  # noqa: E402

from core.config import Config  # noqa: E402
from core.db import Database  # noqa: E402
from modules import infrastructure as infra  # noqa: E402
from modules import manufacturing as mf  # noqa: E402

SURFACE_MINE = 1       # 10000 credits, 200 alloys
ASSEMBLY_PLANT = 17    # factory: an upgrade costs credits only
RECIPE = 9             # Alloy Ingot Smelting: Raw Ore 5 + Power Cell 1 -> Alloy Ingot 3


async def _wipe(session_id):
    await Database.execute(
        "DELETE FROM maya_rp.production_lines WHERE colony_id IN "
        "(SELECT id FROM maya_rp.colonies WHERE session_id=$1)", session_id)
    await Database.execute("DELETE FROM maya_rp.material_stockpiles WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.colonies WHERE session_id=$1", session_id)
    await Database.execute(
        "DELETE FROM maya_rp.infrastructure_production WHERE infrastructure_id IN "
        "(SELECT id FROM maya_rp.infrastructure_instances WHERE session_id=$1)", session_id)
    await Database.execute("DELETE FROM maya_rp.infrastructure_instances WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.story_log WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.resources WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", session_id)


@pytest_asyncio.fixture
async def sid(scratch_session, monkeypatch):
    """A scratch session on game day 10 with no rows in the tables this file writes."""
    monkeypatch.setattr(Config, "SESSION_ID", scratch_session)
    await Database.init()
    await _wipe(scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status, game_day) "
        "VALUES ($1, 'infra mf fix2', 'active', 10)", scratch_session)
    try:
        yield scratch_session
    finally:
        await _wipe(scratch_session)
        await Database.close()


async def _fund(session_id, credits=0, alloys=0):
    await Database.execute("DELETE FROM maya_rp.resources WHERE session_id=$1", session_id)
    await Database.execute(
        "INSERT INTO maya_rp.resources (session_id, credits, alloys, population) VALUES ($1, $2, $3, 0)",
        session_id, credits, alloys)


async def _credits(session_id):
    return await Database.fetchval("SELECT credits FROM maya_rp.resources WHERE session_id=$1", session_id)


async def _alloys(session_id):
    return await Database.fetchval("SELECT alloys FROM maya_rp.resources WHERE session_id=$1", session_id)


async def _instance(session_id, type_id, level):
    return await Database.fetchval(
        "INSERT INTO maya_rp.infrastructure_instances "
        "(session_id, infrastructure_type_id, name, level, status, built_at) "
        "VALUES ($1, $2, 'fix2 instance', $3, 'active', NOW()) RETURNING id", session_id, type_id, level)


async def _instances(session_id):
    return await Database.fetch(
        "SELECT id, level, production_bonus FROM maya_rp.infrastructure_instances WHERE session_id=$1",
        session_id)


async def _colony(session_id):
    return await Database.fetchval(
        "INSERT INTO maya_rp.colonies (session_id, name) VALUES ($1, 'fix2 colony') RETURNING id", session_id)


async def _stock(session_id, colony, name, qty):
    await Database.execute(
        "INSERT INTO maya_rp.material_stockpiles (session_id, colony_id, material_name, quantity) "
        "VALUES ($1, $2, $3, $4)", session_id, colony, name, qty)


async def _line(colony):
    return await Database.fetchval(
        "INSERT INTO maya_rp.production_lines (colony_id, recipe_id, status, efficiency) "
        "VALUES ($1, $2, 'running', 1.0) RETURNING id", colony, RECIPE)


async def _total(session_id, name):
    return await Database.fetchval(
        "SELECT COALESCE(SUM(quantity), 0) FROM maya_rp.material_stockpiles "
        "WHERE session_id=$1 AND material_name=$2", session_id, name)


async def _rows(session_id, name):
    return await Database.fetch(
        "SELECT quantity FROM maya_rp.material_stockpiles WHERE session_id=$1 AND material_name=$2",
        session_id, name)


async def _smelter(session_id):
    """A colony with a running line and the stock for exactly one batch of recipe 9."""
    colony = await _colony(session_id)
    await _line(colony)
    await _stock(session_id, colony, "Raw Ore", 5)
    await _stock(session_id, colony, "Power Cell", 1)
    return colony


async def _warm_pool():
    """Open several pool connections so a race test does not wait on connection set-up."""
    await asyncio.gather(*[Database.fetchval("SELECT pg_sleep(0.05)") for _ in range(4)])


def slow(real):
    """Wrap an async function so it pauses 0.2s first, which holds a race window open."""
    async def wrapper(*args, **kwargs):
        await asyncio.sleep(0.2)
        return await real(*args, **kwargs)
    return wrapper


class _RacyDatabase:
    """Delegates to `Database`. The input sufficiency read returns after a pause, so two ticks both pass it."""

    fetch = staticmethod(Database.fetch)
    fetchrow = staticmethod(Database.fetchrow)
    execute = staticmethod(Database.execute)
    transaction = staticmethod(Database.transaction)

    @staticmethod
    async def fetchval(sql, *args):
        value = await Database.fetchval(sql, *args)
        if "SUM(quantity-reserved)" in sql:
            await asyncio.sleep(0.2)
        return value


class _OutputFailsDatabase:
    """Delegates to `Database`. The first output INSERT raises, on the pool and on the transaction connection."""

    def __init__(self):
        self.tripped = False

    def _trip(self, sql):
        if "INSERT INTO maya_rp.material_stockpiles" in sql and not self.tripped:
            self.tripped = True
            raise RuntimeError("output side failed")

    async def fetch(self, sql, *args):
        return await Database.fetch(sql, *args)

    async def fetchrow(self, sql, *args):
        return await Database.fetchrow(sql, *args)

    async def fetchval(self, sql, *args):
        return await Database.fetchval(sql, *args)

    async def execute(self, sql, *args):
        self._trip(sql)
        return await Database.execute(sql, *args)

    @asynccontextmanager
    async def transaction(self):
        outer = self

        class _Conn:
            def __init__(self, conn):
                self._conn = conn

            async def fetch(self, sql, *args):
                return await self._conn.fetch(sql, *args)

            async def fetchrow(self, sql, *args):
                return await self._conn.fetchrow(sql, *args)

            async def fetchval(self, sql, *args):
                return await self._conn.fetchval(sql, *args)

            async def execute(self, sql, *args):
                outer._trip(sql)
                return await self._conn.execute(sql, *args)

        async with Database.transaction() as conn:
            yield _Conn(conn)


# -- build: the charge and the row commit together ----------------------------------------------------

async def test_build_charge_and_row_are_one_unit(sid):
    await _fund(sid, credits=20000, alloys=500)
    with pytest.raises(PostgresError):
        await infra.build_infrastructure(sid, SURFACE_MINE, name="x" * 101)
    assert await _credits(sid) == 20000
    assert await _alloys(sid) == 500
    assert await _instances(sid) == []


async def test_build_refuses_a_stale_check_without_raising(sid, monkeypatch):
    await _fund(sid, credits=10)

    async def stale(*_args, **_kwargs):
        return True, ""

    monkeypatch.setattr(infra, "_check_afford", stale)
    out = await infra.build_infrastructure(sid, SURFACE_MINE)
    assert "Insufficient resources" in out["error"], out
    assert await _instances(sid) == []
    assert await _credits(sid) == 10


async def test_build_charges_and_records(sid):
    await _fund(sid, credits=20000, alloys=500)
    out = await infra.build_infrastructure(sid, SURFACE_MINE)
    assert "error" not in out, out
    assert await _credits(sid) == 10000
    assert await _alloys(sid) == 300
    rows = await _instances(sid)
    assert len(rows) == 1 and rows[0]["level"] == 1


# -- upgrade: the claim, the charge and the level commit together -------------------------------------

async def test_upgrade_charge_and_level_are_one_unit(sid):
    await _fund(sid, credits=10**15)
    inst = await _instance(sid, ASSEMBLY_PLANT, 2147483647)
    with pytest.raises(PostgresError):
        await infra.upgrade_infrastructure(sid, inst)
    assert await _credits(sid) == 10**15
    assert (await _instances(sid))[0]["level"] == 2147483647


async def test_two_upgrades_of_one_level_charge_once(sid, monkeypatch):
    await _fund(sid, credits=1000000)
    inst = await _instance(sid, ASSEMBLY_PLANT, 1)
    monkeypatch.setattr(infra, "_deduct_resources", slow(infra._deduct_resources))
    await _warm_pool()
    results = await asyncio.gather(
        infra.upgrade_infrastructure(sid, inst), infra.upgrade_infrastructure(sid, inst))
    assert await _credits(sid) == 950000, results
    assert sorted("error" in r for r in results) == [False, True], results
    assert [r["new_level"] for r in results if "error" not in r] == [2]
    row = (await _instances(sid))[0]
    assert row["level"] == 2 and float(row["production_bonus"]) == pytest.approx(1.1)


async def test_a_short_upgrade_leaves_the_level(sid):
    await _fund(sid, credits=10)
    inst = await _instance(sid, ASSEMBLY_PLANT, 1)
    out = await infra.upgrade_infrastructure(sid, inst)
    assert "Insufficient resources for upgrade" in out["error"], out
    assert (await _instances(sid))[0]["level"] == 1
    assert await _credits(sid) == 10


# -- manufacturing: a line takes its inputs and writes its outputs in one transaction -----------------

async def test_two_ticks_consume_one_batch_once(sid, monkeypatch):
    await _smelter(sid)
    monkeypatch.setattr(mf, "Database", _RacyDatabase)
    await _warm_pool()
    results = await asyncio.gather(mf.run_tick(sid), mf.run_tick(sid))
    assert await _total(sid, "Alloy Ingot") == 3, results
    assert await _total(sid, "Raw Ore") == 0
    for name in ("Raw Ore", "Power Cell"):
        assert all(r["quantity"] >= 0 for r in await _rows(sid, name)), name
    assert sum(r["blocked"] for r in results) == 1, results


async def test_an_output_error_returns_the_inputs(sid, monkeypatch):
    await _smelter(sid)
    monkeypatch.setattr(mf, "Database", _OutputFailsDatabase())
    out = await mf.run_tick(sid)
    assert "output side failed" in out["error"], out
    assert await _total(sid, "Raw Ore") == 5
    assert await _total(sid, "Power Cell") == 1
    assert await _rows(sid, "Alloy Ingot") == []


async def test_a_tick_consumes_and_produces(sid):
    await _smelter(sid)
    out = await mf.run_tick(sid)
    assert "error" not in out, out
    assert await _total(sid, "Raw Ore") == 0
    assert await _total(sid, "Power Cell") == 0
    assert await _total(sid, "Alloy Ingot") == 3
