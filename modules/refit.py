#!/usr/bin/env python3
"""Refit/Upgrade — Ported from Rust refit.rs. Module install, tier upgrade, list config."""
from __future__ import annotations
from typing import Any
from core.db import Database
from core.log import info
from core.session import require_session


class _Refuse(Exception):
    """Carries an error answer out of a transaction so every write in it rolls back."""

    def __init__(self, out: dict):
        super().__init__(out.get("error", ""))
        self.out = out


def _contains(text: str) -> str:
    """LIKE pattern matching `text` as a literal substring (pair with `ESCAPE '\\'`).

    @param text - user text.
    @returns the escaped `%text%` pattern.
    """
    return "%" + str(text).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _tag_count(tag) -> int:
    """Row count of an asyncpg command tag such as `UPDATE 1`; 0 when unreadable."""
    try:
        return int(str(tag).split()[-1])
    except (ValueError, IndexError):
        return 0

async def list_modules(ship_name: str, session_id: int | None = None) -> dict[str, Any]:
    """List a ship's installed modules and the modules its tier can take.

    @param ship_name - literal ship name fragment.
    @param session_id - session key; the active session when None.
    @returns {"ship", "tier", "installed", "available"} or {"error": ...}.
    """
    session_id = require_session(session_id)
    ship = await Database.fetchrow(
        "SELECT id, name, tier FROM maya_rp.ships WHERE session_id=$1 AND LOWER(name) LIKE LOWER($2) ESCAPE '\\' LIMIT 1",
        session_id, _contains(ship_name))
    if not ship: return {"error": f"Ship '{ship_name}' not found"}

    installed = await Database.fetch(
        "SELECT sm.slot_index, m.name, m.category, m.effect_type FROM maya_rp.ship_modules sm "
        "JOIN maya_rp.modules m ON sm.module_id = m.id WHERE sm.ship_id=$1 ORDER BY sm.slot_index", ship["id"])
    available = await Database.fetch(
        "SELECT name, category, cost_alloys, cost_credits FROM maya_rp.modules "
        "WHERE tier_min <= $1 AND (tier_max IS NULL OR tier_max >= $1) "
        "ORDER BY category, name", ship["tier"])
    return {"ship": ship["name"], "tier": ship["tier"],
            "installed": [dict(r) for r in installed],
            "available": [dict(r) for r in available]}

async def install_module(ship_name: str, module_name: str, slot_index: int,
                          session_id: int | None = None) -> dict[str, Any]:
    """Fit a module into one slot of a ship, replacing what the slot held.

    The slot write, the event and the charge commit together, with the charge last and guarded. The old
    code charged first and then ran `ON CONFLICT (ship_id, slot_index)`, a target with no unique
    constraint behind it, so every install raised after the treasury was debited. The slot was also
    never checked against the ship's `module_slots`.

    @param ship_name - literal ship name fragment.
    @param module_name - literal module name fragment.
    @param slot_index - 1-based slot, at most the ship class's `module_slots`.
    @param session_id - session key; the active session when None.
    @returns the install summary, or {"error": ...}.
    @raises FrozenSession when the campaign is frozen reference data.
    """
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    ship = await Database.fetchrow(
        "SELECT s.id, s.name, s.tier, COALESCE(sc.module_slots, 0) AS module_slots "
        "FROM maya_rp.ships s LEFT JOIN maya_rp.ship_classes sc ON sc.class_name = s.sub_class "
        "WHERE s.session_id=$1 AND LOWER(s.name) LIKE LOWER($2) ESCAPE '\\' LIMIT 1",
        session_id, _contains(ship_name))
    if not ship: return {"error": f"Ship '{ship_name}' not found"}

    mod = await Database.fetchrow(
        "SELECT id, name, category, cost_alloys, cost_credits FROM maya_rp.modules "
        "WHERE LOWER(name) LIKE LOWER($1) ESCAPE '\\' AND tier_min <= $2 AND (tier_max IS NULL OR tier_max >= $2) "
        "ORDER BY id LIMIT 1",
        _contains(module_name), ship["tier"])
    if not mod: return {"error": f"Module '{module_name}' not found or incompatible with T{ship['tier']}"}
    slot_index = int(slot_index)
    if slot_index < 1:
        # Slot 0 and below are not slots; the row is keyed by (ship_id, slot_index).
        return {"error": f"slot_index must be at least 1, got {slot_index}"}
    if slot_index > (ship["module_slots"] or 0):
        return {"error": f"{ship['name']} has {ship['module_slots'] or 0} module slots, got slot {slot_index}"}

    res = await Database.fetchrow(
        "SELECT alloys, credits FROM maya_rp.resources WHERE session_id=$1", session_id)
    if not res:
        # `res["alloys"]` raised TypeError for a session with no resources row,
        # which is session 5 today.
        return {"error": f"No resources row for session {session_id}: refit refused"}
    if res["alloys"] < mod["cost_alloys"] or res["credits"] < mod["cost_credits"]:
        return {"error": f"Need {mod['cost_alloys']}a/{mod['cost_credits']}c, have {res['alloys']}a/{res['credits']}c"}

    try:
        async with Database.transaction() as conn:
            # Serialise installs on one ship: with no unique index, two racing inserts would both
            # miss the UPDATE and leave two rows in one slot.
            await conn.fetchval("SELECT id FROM maya_rp.ships WHERE id=$1 FOR UPDATE", ship["id"])
            replaced = await conn.execute(
                "UPDATE maya_rp.ship_modules SET module_id=$1, installed_at=now() "
                "WHERE ship_id=$2 AND slot_index=$3", mod["id"], ship["id"], slot_index)
            if _tag_count(replaced) == 0:
                await conn.execute(
                    "INSERT INTO maya_rp.ship_modules (ship_id, module_id, slot_index) VALUES ($1,$2,$3)",
                    ship["id"], mod["id"], slot_index)
            await conn.execute(
                "INSERT INTO maya_rp.events (session_id, event_type, title, description, tags) VALUES "
                "($1,'refit',$2,$3,'[\"refit\"]'::jsonb)",
                session_id, f"{ship['name']} Refit",
                f"Installed {mod['name']} [{mod['category']}] in slot {slot_index}. Cost: {mod['cost_alloys']}a/{mod['cost_credits']}c.")
            charged = await conn.execute(
                "UPDATE maya_rp.resources SET alloys=alloys-$1, credits=credits-$2 "
                "WHERE session_id=$3 AND alloys>=$1 AND credits>=$2",
                mod["cost_alloys"], mod["cost_credits"], session_id)
            if _tag_count(charged) == 0:
                raise _Refuse({"error": f"Need {mod['cost_alloys']}a/{mod['cost_credits']}c for {mod['name']}"})
    except _Refuse as refused:
        return refused.out

    info("refit", f"Installed {mod['name']} on {ship['name']} slot {slot_index}")
    return {"installed": mod["name"], "ship": ship["name"], "slot": slot_index,
            "cost_alloys": mod["cost_alloys"], "cost_credits": mod["cost_credits"]}

async def upgrade_ship(ship_name: str, session_id: int | None = None) -> dict[str, Any]:
    """Raise a ship one tier for alloys and credits; charge and tier write commit together.

    @param ship_name - literal ship name fragment.
    @param session_id - session key; the active session when None.
    @returns the before and after stats, or {"error": ...}.
    @raises FrozenSession when the campaign is frozen reference data.
    """
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    ship = await Database.fetchrow(
        "SELECT id, name, tier, hull, speed FROM maya_rp.ships WHERE session_id=$1 AND LOWER(name) LIKE LOWER($2) ESCAPE '\\' LIMIT 1",
        session_id, _contains(ship_name))
    if not ship: return {"error": f"Ship '{ship_name}' not found"}
    if ship["tier"] >= 4: return {"error": f"{ship['name']} already at max tier (T{ship['tier']})"}

    new_tier = ship["tier"] + 1
    cost_a = ship["tier"] * 2000
    cost_c = ship["tier"] * 1000
    hull_gain = round(ship["hull"] * 1.25)
    speed_gain = round(ship["speed"] * 1.15)

    res = await Database.fetchrow(
        "SELECT alloys, credits FROM maya_rp.resources WHERE session_id=$1", session_id)
    if not res:
        return {"error": f"No resources row for session {session_id}: upgrade refused"}
    if res["alloys"] < cost_a or res["credits"] < cost_c:
        return {"error": f"Need {cost_a}a/{cost_c}c for upgrade"}

    try:
        async with Database.transaction() as conn:
            # Tier guard in the WHERE: a second upgrade racing the first finds the tier moved and charges nothing.
            moved = await conn.execute(
                "UPDATE maya_rp.ships SET tier=$1, hull=$2, hull_current=$3, speed=$4 "
                "WHERE id=$5 AND session_id=$6 AND tier=$7",
                new_tier, hull_gain, hull_gain, speed_gain, ship["id"], session_id, ship["tier"])
            if _tag_count(moved) == 0:
                raise _Refuse({"error": f"{ship['name']} changed tier during the upgrade; nothing charged"})
            await conn.execute(
                "INSERT INTO maya_rp.events (session_id, event_type, title, description, tags) VALUES "
                "($1,'upgrade',$2,$3,'[\"refit\"]'::jsonb)",
                session_id, f"{ship['name']} Upgraded to T{new_tier}",
                f"{ship['name']} upgraded T{ship['tier']}->T{new_tier}. Hull: {ship['hull']}->{hull_gain}. Cost: {cost_a}a/{cost_c}c.")
            charged = await conn.execute(
                "UPDATE maya_rp.resources SET alloys=alloys-$1, credits=credits-$2 "
                "WHERE session_id=$3 AND alloys>=$1 AND credits>=$2", cost_a, cost_c, session_id)
            if _tag_count(charged) == 0:
                raise _Refuse({"error": f"Need {cost_a}a/{cost_c}c for upgrade"})
    except _Refuse as refused:
        return refused.out

    info("refit", f"Upgraded {ship['name']} to T{new_tier}")
    return {"ship": ship["name"], "old_tier": ship["tier"], "new_tier": new_tier,
            "hull_before": ship["hull"], "hull_after": hull_gain,
            "speed_before": ship["speed"], "speed_after": speed_gain}

async def run_tick(session_id: int | None = None) -> dict:
    """Report readiness; refit has no per-tick work.

    @raises FrozenSession when the campaign is frozen reference data.
    """
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    return {"status": "refit_ready"}
