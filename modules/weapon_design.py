#!/usr/bin/env python3
"""Weapon Design — Ported from Rust weapon_design.rs. Blueprints, produce, upgrades."""
from __future__ import annotations
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info

async def list_weapons() -> list[dict]:
    rows = await Database.fetch(
        "SELECT id, name, kind, slot_size, damage, range_m, tier_min, tier_max, special_rules "
        "FROM maya_rp.weapons ORDER BY kind, slot_size, name")
    return [dict(r) for r in rows]

async def list_blueprints() -> list[dict]:
    rows = await Database.fetch(
        "SELECT id, name, category, base_damage, base_range, slot_size, tier_required, tech_prereq, "
        "alloy_cost, credit_cost, research_cost, special_rules "
        "FROM maya_rp.weapon_blueprints ORDER BY category, tier_required, name")
    return [dict(r) for r in rows]

async def design_blueprint(name: str, category: str, damage: int, range_m: int, slot: str, tier: int,
                            session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    exists = await Database.fetchval("SELECT id FROM maya_rp.weapon_blueprints WHERE LOWER(name)=LOWER($1)", name)
    if exists: return {"error": f"Blueprint '{name}' already exists"}

    cost_credits = damage * 200 + range_m * 50 + tier * 500
    cost_research = damage * 100 + range_m * 25 + tier * 300

    res = await Database.fetchrow("SELECT credits FROM maya_rp.resources WHERE session_id=$1", session_id)
    if not res or res["credits"] < cost_credits:
        return {"error": f"Need {cost_credits} credits"}

    await Database.execute("UPDATE maya_rp.resources SET credits=credits-$1 WHERE session_id=$2",
                           cost_credits, session_id)
    await Database.execute(
        "INSERT INTO maya_rp.weapon_blueprints (name, category, base_damage, base_range, slot_size, tier_required, credit_cost, research_cost) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
        name, category, damage, range_m, slot, tier, cost_credits, cost_research)

    info("weapon_design", f"Designed blueprint: {name} (T{tier}, {slot})")
    return {"name": name, "category": category, "tier": tier, "slot": slot, "cost_credits": cost_credits}

async def produce_weapons(blueprint: str, qty: int = 1, session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    bp = await Database.fetchrow(
        "SELECT id, name, category, base_damage, base_range, slot_size, tier_required, "
        "alloy_cost, credit_cost, research_cost FROM maya_rp.weapon_blueprints WHERE LOWER(name)=LOWER($1)",
        blueprint)
    if not bp: return {"error": f"Blueprint '{blueprint}' not found"}

    alloy_cost = (bp["alloy_cost"] or 0) * qty
    credit_cost = (bp["credit_cost"] or 0) * qty
    res = await Database.fetchrow("SELECT alloys, credits FROM maya_rp.resources WHERE session_id=$1", session_id)
    if res["alloys"] < alloy_cost or res["credits"] < credit_cost:
        return {"error": f"Need {alloy_cost}a/{credit_cost}c"}

    await Database.execute("UPDATE maya_rp.resources SET alloys=alloys-$1, credits=credits-$2 WHERE session_id=$3",
                           alloy_cost, credit_cost, session_id)
    for _ in range(qty):
        await Database.execute(
            "INSERT INTO maya_rp.weapons (name, kind, slot_size, damage, range_m, tier_min, tier_max) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7)",
            bp["name"], bp["category"], bp["slot_size"] or "L",
            bp["base_damage"] or 0, bp["base_range"] or 0, bp["tier_required"], bp["tier_required"] + 2)

    info("weapon_design", f"Produced {qty}x {bp['name']}")
    return {"produced": qty, "weapon": bp["name"], "cost_alloys": alloy_cost, "cost_credits": credit_cost}

async def list_upgrades(weapon_id: int) -> list[dict]:
    rows = await Database.fetch(
        "SELECT id, upgrade_name, effect_type, effect_value, tier_required, cost "
        "FROM maya_rp.weapon_upgrades WHERE weapon_id=$1 ORDER BY tier_required, upgrade_name", weapon_id)
    return [dict(r) for r in rows]

async def apply_upgrade(weapon_id: int, upgrade_name: str, ship_id: int | None = None,
                         session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    upg = await Database.fetchrow(
        "SELECT id, upgrade_name, effect_type, effect_value, tier_required, cost "
        "FROM maya_rp.weapon_upgrades WHERE weapon_id=$1 AND LOWER(upgrade_name)=LOWER($2)",
        weapon_id, upgrade_name)
    if not upg: return {"error": f"Upgrade '{upgrade_name}' not found for weapon #{weapon_id}"}

    cost = upg["cost"] or 0
    res = await Database.fetchrow("SELECT credits FROM maya_rp.resources WHERE session_id=$1", session_id)
    if res["credits"] < cost: return {"error": f"Need {cost} credits"}

    await Database.execute("UPDATE maya_rp.resources SET credits=credits-$1 WHERE session_id=$2", cost, session_id)
    info("weapon_design", f"Applied '{upgrade_name}' to weapon #{weapon_id}")
    return {"applied": upgrade_name, "weapon_id": weapon_id, "cost": cost}

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    return {"status": "weapon_design_ready"}
