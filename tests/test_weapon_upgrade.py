"""Fitting an upgrade: charges once, changes something, refuses what it cannot apply.

Reviewed 2026-10-03 before wiring `apply_upgrade`, which had no caller. Three defects came out of
holding it up: nothing recorded that a fitting had been applied (so a second call charged again),
`effect_type` and `effect_value` were read and ignored (so it cost money and did nothing), and an
unknown effect type fell through silently. Every test builds its own weapon and upgrade inside a
transaction that is always rolled back, so the global catalogue tables are never written.
"""
from __future__ import annotations

import os
import pathlib
import sys
from contextlib import asynccontextmanager

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import Database  # noqa: E402

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


async def _with_upgrade(conn, effect_type: str, effect_value, cost: int):
    """Create a weapon, an upgrade and a treasury row on `conn`, and return the weapon and upgrade ids.

    The scratch session has no `resources` row until this inserts one.
    """
    await conn.execute(
        "INSERT INTO maya_rp.resources (session_id, credits) VALUES ($1, 1000000)", SID)
    # `kind` is a foreign key into weapon_kinds and `slot_size` is a size class with a check
    # constraint, so the test reads the catalogue instead of guessing at it.
    kind = await conn.fetchval("SELECT kind FROM maya_rp.weapon_kinds ORDER BY kind LIMIT 1")
    assert kind, "weapon_kinds is empty; the test cannot build a weapon"
    weapon = await conn.fetchrow(
        "INSERT INTO maya_rp.weapons (name, kind, slot_size, damage, range_m)"
        " VALUES ('red proof blade', $1, 'L', 10, 1) RETURNING id", kind)
    upgrade = await conn.fetchrow(
        "INSERT INTO maya_rp.weapon_upgrades (weapon_id, upgrade_name, effect_type, effect_value, cost)"
        " VALUES ($1, 'red proof edge', $2, $3, $4) RETURNING id",
        weapon["id"], effect_type, effect_value, cost)
    return int(weapon["id"]), int(upgrade["id"])


class TestFitting:
    async def test_a_damage_upgrade_raises_damage_and_charges_once(self, monkeypatch):
        from modules.weapon_design import apply_upgrade

        async with _rolled_back(monkeypatch) as conn:
            weapon_id, _ = await _with_upgrade(conn, "damage", 5, 0)
            credits_before = await conn.fetchval(
                "SELECT credits FROM maya_rp.resources WHERE session_id=$1", SID)
            first = await apply_upgrade(weapon_id, "red proof edge", session_id=SID)
            assert first.get("applied") == "red proof edge", first
            damage = await conn.fetchval("SELECT damage FROM maya_rp.weapons WHERE id=$1", weapon_id)
            assert damage == 15, f"the effect never landed: damage is {damage}"

            second = await apply_upgrade(weapon_id, "red proof edge", session_id=SID)
            assert "already fitted" in second.get("error", ""), second
            credits_after = await conn.fetchval(
                "SELECT credits FROM maya_rp.resources WHERE session_id=$1", SID)
            assert credits_after == credits_before, "the second call charged again"

    async def test_an_effect_type_the_engine_cannot_apply_is_refused(self, monkeypatch):
        from modules.weapon_design import apply_upgrade

        async with _rolled_back(monkeypatch) as conn:
            weapon_id, upgrade_id = await _with_upgrade(conn, "teleportation", 1, 0)
            result = await apply_upgrade(weapon_id, "red proof edge", session_id=SID)
            assert "cannot apply" in result.get("error", ""), result
            applied_at = await conn.fetchval(
                "SELECT applied_at FROM maya_rp.weapon_upgrades WHERE id=$1", upgrade_id)
            assert applied_at is None, "a refused upgrade must not be marked as fitted"

    async def test_an_unaffordable_upgrade_does_not_fit(self, monkeypatch):
        from modules.weapon_design import apply_upgrade

        async with _rolled_back(monkeypatch) as conn:
            weapon_id, upgrade_id = await _with_upgrade(conn, "damage", 5, 999_999_999)
            result = await apply_upgrade(weapon_id, "red proof edge", session_id=SID)
            assert "Need" in result.get("error", ""), result
            applied_at = await conn.fetchval(
                "SELECT applied_at FROM maya_rp.weapon_upgrades WHERE id=$1", upgrade_id)
            assert applied_at is None, "an unaffordable upgrade was marked as fitted"
