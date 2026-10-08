"""The forge: a blueprint name belongs to one campaign, and the fitting has a door.

Six entry points of weapon_design.py had no caller. `apply_upgrade` had been repaired earlier in this
review and still had none, which is the state a repair alone does not fix.

`design_blueprint` checked whether a name already existed with no session filter, so the first campaign
to invent a name blocked every other campaign from inventing it.
"""
from __future__ import annotations

import os
import pathlib
import sys
from contextlib import asynccontextmanager

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import Database  # noqa: E402
from modules import weapon_design as wd  # noqa: E402

SID = 900 + os.getpid() % 100


@asynccontextmanager
async def _rolled_back(monkeypatch):
    """Run a test inside one transaction that is always rolled back.

    `weapons`, `weapon_blueprints` and `weapon_upgrades` are global catalogue tables, so nothing a test
    writes may commit. Every `Database` call and every module transaction goes through one connection.
    The module's own `transaction()` becomes a savepoint on it. The scratch session and its `resources`
    row are inserted inside the same transaction.
    """
    await Database.init()
    pool = await Database._ensure_pool()
    async with pool.acquire() as conn:
        outer = conn.transaction()
        await outer.start()
        try:
            @asynccontextmanager
            async def savepoint():
                async with conn.transaction():
                    yield conn

            async def fetchval(sql, *args):
                return await conn.fetchval(sql, *args)

            async def fetchrow(sql, *args):
                return await conn.fetchrow(sql, *args)

            async def fetch(sql, *args):
                return await conn.fetch(sql, *args)

            async def execute(sql, *args):
                return await conn.execute(sql, *args)

            monkeypatch.setattr(Database, "transaction", savepoint)
            monkeypatch.setattr(Database, "fetchval", fetchval)
            monkeypatch.setattr(Database, "fetchrow", fetchrow)
            monkeypatch.setattr(Database, "fetch", fetch)
            monkeypatch.setattr(Database, "execute", execute)
            await conn.execute(
                "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1,'weapon review scratch','active') "
                "ON CONFLICT (id) DO NOTHING", SID)
            yield conn
        finally:
            await outer.rollback()
    await Database.close()


class TestTheArmouryIsShared:
    """`weapon_blueprints` has no session_id, so a name is global. The whole test runs in a transaction
    that is rolled back, so the blueprint, the session and the treasury row never reach the database."""

    async def test_the_same_name_twice_is_refused_anywhere(self, monkeypatch):
        async with _rolled_back(monkeypatch) as conn:
            await conn.execute(
                "INSERT INTO maya_rp.resources (session_id, credits) VALUES ($1, 50000000)", SID)
            first = await wd.design_blueprint("red proof twice", "Special", 1, 1, "L", 1, SID)
            assert first.get("error") is None, first
            second = await wd.design_blueprint("red proof twice", "Special", 1, 1, "L", 1, SID)
            assert "already exists" in second.get("error", ""), second
            held = await conn.fetchval(
                "SELECT COUNT(*) FROM maya_rp.weapon_blueprints WHERE LOWER(name)='red proof twice'")
            assert held == 1, f"the armoury holds {held} copies of one blueprint name"


class TestTheProductionLine:
    async def test_an_unknown_blueprint_is_refused(self, monkeypatch):
        async with _rolled_back(monkeypatch):
            out = await wd.produce_weapons("no such blueprint anywhere", 1, SID)
            assert "not found" in out.get("error", ""), out
