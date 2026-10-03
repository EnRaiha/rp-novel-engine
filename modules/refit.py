#!/usr/bin/env python3
"""Refit/Upgrade — Ported from Rust refit.rs. Module install, tier upgrade, list config."""
from __future__ import annotations
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info

async def list_modules(ship_name: str, session_id: int | None = None) -> dict[str, Any]:
    if session_id is None: session_id = Config.SESSION_ID
    ship = await Database.fetchrow(
        "SELECT id, name, tier FROM maya_rp.ships WHERE session_id=$1 AND LOWER(name) LIKE LOWER($2) LIMIT 1",
        session_id, f"%{ship_name}%")
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
    if session_id is None: session_id = Config.SESSION_ID
    ship = await Database.fetchrow(
        "SELECT id, name, tier FROM maya_rp.ships WHERE session_id=$1 AND LOWER(name) LIKE LOWER($2) LIMIT 1",
        session_id, f"%{ship_name}%")
    if not ship: return {"error": f"Ship '{ship_name}' not found"}

    mod = await Database.fetchrow(
        "SELECT id, name, category, cost_alloys, cost_credits FROM maya_rp.modules "
        "WHERE LOWER(name) LIKE LOWER($1) AND tier_min <= $2 AND (tier_max IS NULL OR tier_max >= $2) "
        "ORDER BY id LIMIT 1",
        f"%{module_name}%", ship["tier"])
    if not mod: return {"error": f"Module '{module_name}' not found or incompatible with T{ship['tier']}"}
    if int(slot_index) < 1:
        # Slot 0 and below are not slots; the row is keyed by (ship_id, slot_index).
        return {"error": f"slot_index must be at least 1, got {slot_index}"}

    res = await Database.fetchrow(
        "SELECT alloys, credits FROM maya_rp.resources WHERE session_id=$1", session_id)
    if not res:
        # `res["alloys"]` raised TypeError for a session with no resources row,
        # which is session 5 today.
        return {"error": f"No resources row for session {session_id}: refit refused"}
    if res["alloys"] < mod["cost_alloys"] or res["credits"] < mod["cost_credits"]:
        return {"error": f"Need {mod['cost_alloys']}a/{mod['cost_credits']}c, have {res['alloys']}a/{res['credits']}c"}

    await Database.execute("UPDATE maya_rp.resources SET alloys=alloys-$1, credits=credits-$2 WHERE session_id=$3",
                           mod["cost_alloys"], mod["cost_credits"], session_id)
    await Database.execute(
        "INSERT INTO maya_rp.ship_modules (ship_id, module_id, slot_index) VALUES ($1,$2,$3) "
        "ON CONFLICT (ship_id, slot_index) DO UPDATE SET module_id=$2",
        ship["id"], mod["id"], slot_index)
    await Database.execute(
        "INSERT INTO maya_rp.events (session_id, event_type, title, description, tags) VALUES "
        "($1,'refit',$2,$3,'[\"refit\"]'::jsonb)",
        session_id, f"{ship['name']} Refit",
        f"Installed {mod['name']} [{mod['category']}] in slot {slot_index}. Cost: {mod['cost_alloys']}a/{mod['cost_credits']}c.")

    info("refit", f"Installed {mod['name']} on {ship['name']} slot {slot_index}")
    return {"installed": mod["name"], "ship": ship["name"], "slot": slot_index,
            "cost_alloys": mod["cost_alloys"], "cost_credits": mod["cost_credits"]}

async def upgrade_ship(ship_name: str, session_id: int | None = None) -> dict[str, Any]:
    if session_id is None: session_id = Config.SESSION_ID
    ship = await Database.fetchrow(
        "SELECT id, name, tier, hull, speed FROM maya_rp.ships WHERE session_id=$1 AND LOWER(name) LIKE LOWER($2) LIMIT 1",
        session_id, f"%{ship_name}%")
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

    await Database.execute("UPDATE maya_rp.resources SET alloys=alloys-$1, credits=credits-$2 WHERE session_id=$3",
                           cost_a, cost_c, session_id)
    await Database.execute(
        "UPDATE maya_rp.ships SET tier=$1, hull=$2, hull_current=$3, speed=$4 "
        "WHERE id=$5 AND session_id=$6",
        new_tier, hull_gain, hull_gain, speed_gain, ship["id"], session_id)
    await Database.execute(
        "INSERT INTO maya_rp.events (session_id, event_type, title, description, tags) VALUES "
        "($1,'upgrade',$2,$3,'[\"refit\"]'::jsonb)",
        session_id, f"{ship['name']} Upgraded to T{new_tier}",
        f"{ship['name']} upgraded T{ship['tier']}->T{new_tier}. Hull: {ship['hull']}->{hull_gain}. Cost: {cost_a}a/{cost_c}c.")

    info("refit", f"Upgraded {ship['name']} to T{new_tier}")
    return {"ship": ship["name"], "old_tier": ship["tier"], "new_tier": new_tier,
            "hull_before": ship["hull"], "hull_after": hull_gain,
            "speed_before": ship["speed"], "speed_after": speed_gain}

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    return {"status": "refit_ready"}
