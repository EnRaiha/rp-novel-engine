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
    # No session filter here on purpose: `weapon_blueprints` is a shared armoury with no session_id
    # column, so a blueprint name is global. Adding the filter raised UndefinedColumnError, which the
    # test caught within a minute of the mistake.
    exists = await Database.fetchval(
        "SELECT id FROM maya_rp.weapon_blueprints WHERE LOWER(name)=LOWER($1)", name)
    if exists: return {"error": f"Blueprint '{name}' already exists"}

    cost_credits = damage * 200 + range_m * 50 + tier * 500
    cost_research = damage * 100 + range_m * 25 + tier * 300

    res = await Database.fetchrow("SELECT credits FROM maya_rp.resources WHERE session_id=$1", session_id)
    if not res or (res["credits"] or 0) < cost_credits:
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
        "alloy_cost, credit_cost, research_cost FROM maya_rp.weapon_blueprints"
        " WHERE LOWER(name)=LOWER($1)",
        blueprint)
    if not bp: return {"error": f"Blueprint '{blueprint}' not found"}

    alloy_cost = (bp["alloy_cost"] or 0) * qty
    credit_cost = (bp["credit_cost"] or 0) * qty
    res = await Database.fetchrow("SELECT alloys, credits FROM maya_rp.resources WHERE session_id=$1", session_id)
    # The sibling paths already refuse this case; this one raised TypeError on a
    # session with no resources row, which is every session that has not been seeded.
    if res is None:
        return {"error": f"no resources row for session {session_id}"}
    if (res["alloys"] or 0) < alloy_cost or (res["credits"] or 0) < credit_cost:
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
    """Buy and fit one upgrade.

    Reviewed 2026-10-03 before wiring, and three things were wrong. The row carried no record that it
    had been applied, so a second call charged the treasury again for the same fitting. `effect_type`
    and `effect_value` were read and then ignored, so the upgrade cost money and changed nothing. And
    an unknown effect type fell through silently. All three are fixed here; the catalogue itself is
    empty, which is a separate and open question.
    """
    if session_id is None:
        session_id = Config.SESSION_ID
    upg = await Database.fetchrow(
        "SELECT id, upgrade_name, effect_type, effect_value, tier_required, cost, applied_at"
        " FROM maya_rp.weapon_upgrades WHERE weapon_id=$1 AND LOWER(upgrade_name)=LOWER($2)",
        weapon_id, upgrade_name)
    if not upg:
        return {"error": f"Upgrade '{upgrade_name}' not found for weapon #{weapon_id}"}
    if upg["applied_at"] is not None:
        return {"error": f"'{upgrade_name}' is already fitted to weapon #{weapon_id}"}

    effect_type = (upg["effect_type"] or "").strip().lower()
    value = upg["effect_value"]
    column = {"damage": "damage", "range": "range_m", "range_m": "range_m"}.get(effect_type)
    if column is None and effect_type not in ("special", "special_rules"):
        # Fail loudly rather than charge for an effect this engine cannot apply.
        return {"error": f"Upgrade '{upgrade_name}' has effect_type '{upg['effect_type']}',"
                         f" which this engine cannot apply"}

    cost = upg["cost"] or 0
    res = await Database.fetchrow("SELECT credits FROM maya_rp.resources WHERE session_id=$1", session_id)
    if res is None:
        return {"error": f"no resources row for session {session_id}"}
    if (res["credits"] or 0) < cost:
        return {"error": f"Need {cost} credits"}

    await Database.execute(
        "UPDATE maya_rp.resources SET credits=credits-$1 WHERE session_id=$2", cost, session_id)
    if column:
        await Database.execute(
            f"UPDATE maya_rp.weapons SET {column} = COALESCE({column},0) + $1 WHERE id=$2", value, weapon_id)
    else:
        await Database.execute(
            "UPDATE maya_rp.weapons SET special_rules="
            " COALESCE(special_rules,'{}'::jsonb) || jsonb_build_object($1::text, $2) WHERE id=$3",
            upgrade_name, str(value), weapon_id)
    await Database.execute(
        "UPDATE maya_rp.weapon_upgrades SET applied_at=now() WHERE id=$1", upg["id"])
    info("weapon_design", f"Fitted '{upgrade_name}' to weapon #{weapon_id} for {cost}")
    return {"applied": upgrade_name, "weapon_id": weapon_id, "cost": cost,
            "effect": {"type": effect_type, "value": value}}


async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    return {"status": "weapon_design_ready"}
