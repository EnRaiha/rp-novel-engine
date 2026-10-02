"""Fitting an upgrade: charges once, changes something, refuses what it cannot apply.

Reviewed 2026-10-03 before wiring `apply_upgrade`, which had no caller. Three defects came out of
holding it up: nothing recorded that a fitting had been applied (so a second call charged again),
`effect_type` and `effect_value` were read and ignored (so it cost money and did nothing), and an
unknown effect type fell through silently. The catalogue is empty, so these tests build their own row
and take it away again.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import Database  # noqa: E402


async def _with_upgrade(effect_type: str, effect_value, cost: int):
    """Create a weapon and an upgrade, yield their ids, then remove both.

    Session 5 has no `resources` row at all, which the guard in `apply_upgrade` surfaces as
    "no resources row for session 5". The test creates one and takes it away again, and the gap itself
    is reported rather than papered over.
    """
    await Database.init()
    created_resources = False
    if await Database.fetchval("SELECT 1 FROM maya_rp.resources WHERE session_id=5") is None:
        await Database.execute(
            "INSERT INTO maya_rp.resources (session_id, credits) VALUES (5, 1000000)")
        created_resources = True
    # `kind` is a foreign key into weapon_kinds and `slot_size` is a size class with a check
    # constraint, so the test reads the catalogue instead of guessing at it. Two rounds of guessing
    # produced a NOT NULL violation and then a check violation.
    kind = await Database.fetchval("SELECT kind FROM maya_rp.weapon_kinds ORDER BY kind LIMIT 1")
    assert kind, "weapon_kinds is empty; the test cannot build a weapon"
    weapon = await Database.fetchrow(
        "INSERT INTO maya_rp.weapons (name, kind, slot_size, damage, range_m)"
        " VALUES ('red proof blade', $1, 'L', 10, 1) RETURNING id", kind)
    upgrade = await Database.fetchrow(
        "INSERT INTO maya_rp.weapon_upgrades (weapon_id, upgrade_name, effect_type, effect_value, cost)"
        " VALUES ($1, 'red proof edge', $2, $3, $4) RETURNING id",
        weapon["id"], effect_type, effect_value, cost)
    return int(weapon["id"]), int(upgrade["id"]), created_resources


async def _cleanup(weapon_id: int, upgrade_id: int, created_resources: bool = False) -> None:
    await Database.execute("DELETE FROM maya_rp.weapon_upgrades WHERE id=$1", upgrade_id)
    await Database.execute("DELETE FROM maya_rp.weapons WHERE id=$1", weapon_id)
    if created_resources:
        await Database.execute("DELETE FROM maya_rp.resources WHERE session_id=5")
    await Database.close()


class TestFitting:
    async def test_a_damage_upgrade_raises_damage_and_charges_once(self):
        from modules.weapon_design import apply_upgrade

        weapon_id, upgrade_id, made = await _with_upgrade("damage", 5, 0)
        credits_before = await Database.fetchval(
            "SELECT credits FROM maya_rp.resources WHERE session_id=5")
        try:
            first = await apply_upgrade(weapon_id, "red proof edge", session_id=5)
            assert first.get("applied") == "red proof edge", first
            damage = await Database.fetchval(
                "SELECT damage FROM maya_rp.weapons WHERE id=$1", weapon_id)
            assert damage == 15, f"the effect never landed: damage is {damage}"

            second = await apply_upgrade(weapon_id, "red proof edge", session_id=5)
            assert "already fitted" in second.get("error", ""), second
            credits_after = await Database.fetchval(
                "SELECT credits FROM maya_rp.resources WHERE session_id=5")
            assert credits_after == credits_before, "the second call charged again"
        finally:
            await _cleanup(weapon_id, upgrade_id, made)

    async def test_an_effect_type_the_engine_cannot_apply_is_refused(self):
        from modules.weapon_design import apply_upgrade

        weapon_id, upgrade_id, made = await _with_upgrade("teleportation", 1, 0)
        try:
            result = await apply_upgrade(weapon_id, "red proof edge", session_id=5)
            assert "cannot apply" in result.get("error", ""), result
            applied_at = await Database.fetchval(
                "SELECT applied_at FROM maya_rp.weapon_upgrades WHERE id=$1", upgrade_id)
            assert applied_at is None, "a refused upgrade must not be marked as fitted"
        finally:
            await _cleanup(weapon_id, upgrade_id, made)

    async def test_an_unaffordable_upgrade_does_not_fit(self):
        from modules.weapon_design import apply_upgrade

        weapon_id, upgrade_id, made = await _with_upgrade("damage", 5, 999_999_999)
        try:
            result = await apply_upgrade(weapon_id, "red proof edge", session_id=5)
            assert "Need" in result.get("error", ""), result
        finally:
            await _cleanup(weapon_id, upgrade_id, made)
