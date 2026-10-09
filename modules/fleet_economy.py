#!/usr/bin/env python3
"""Fleet Economy Module — Ported from fleet-economy skill (resource-burn.js, caravan-events.js, production-queue.js, trade-deals.js)"""
from __future__ import annotations
import json
import random
from typing import Any
from core.db import Database
from core.log import info, warn
from core.session import require_session
from modules._economy import InsufficientResources, _deduct_resources

BURN_RATES = {"per_active_ship": 10, "base_consumption": 50, "food_per_pop": 0.001}

#: Ships that draw fuel and wages. Hostile, destroyed, lost and in_build hulls are not the fleet.
BILLED_STATUSES = ("active", "patrol", "deployed", "damaged", "undercrewed")


async def calculate_daily_burn(session_id: int, conn=None) -> dict:
    """One game day of burn for the billed fleet. A session with no billed ship burns nothing."""
    db = conn or Database
    ships = await db.fetchval(
        "SELECT COUNT(*) FROM maya_rp.ships WHERE session_id=$1 AND status = ANY($2::text[])",
        session_id, list(BILLED_STATUSES)) or 0
    if ships == 0:
        return {"fuel": 0, "food": 0, "alloy": 0, "credits": 0, "active_ships": 0, "crew": 0}
    pop = await db.fetchval("SELECT population FROM maya_rp.resources WHERE session_id=$1", session_id) or 0
    # crew salaries: every crewed billed hull draws wages (2026-08-14)
    crew = await db.fetchval(
        "SELECT COALESCE(SUM(crew_current),0) FROM maya_rp.ships "
        "WHERE session_id=$1 AND status = ANY($2::text[])",
        session_id, list(BILLED_STATUSES)) or 0
    fuel_burn = ships * BURN_RATES["per_active_ship"] + BURN_RATES["base_consumption"]
    food_burn = max(1, round(pop * BURN_RATES["food_per_pop"] * 24))
    salary_burn = int(crew * 2)  # 2C per crewman per game-day
    return {"fuel": fuel_burn, "food": food_burn, "alloy": 0,
            "credits": 100 + salary_burn, "active_ships": ships, "crew": crew}


async def apply_burn(session_id: int) -> dict:
    """Charge one game day of burn, once per (session, game day).

    A `fleet_burn` event tagged `day:<game_day>` is the claim. It is written in the same transaction
    as the charge, under a per-session advisory lock, so an overlapping or repeated tick finds it and
    bills nothing. Each resource is charged through the guarded `_deduct_resources`. A resource the
    treasury cannot cover is left uncharged and recorded as a `fleet_shortfall` event and in the
    `shortfall` key. The day stays claimed, so the unpaid burn is not retried.
    """
    async with Database.transaction() as conn:
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext('fleet_economy'), $1)", session_id)
        day = await conn.fetchval("SELECT COALESCE(game_day, 1) FROM maya_rp.sessions WHERE id=$1", session_id)
        if day is None:
            return {"error": f"No session row for session {session_id}: burn not applied"}
        held = await conn.fetchrow(
            "SELECT fuel, alloys, credits FROM maya_rp.resources WHERE session_id=$1 FOR UPDATE", session_id)
        if not held:
            return {"error": f"No resources row for session {session_id}: burn not applied"}
        day_tag = json.dumps([f"day:{day}"])
        if await conn.fetchval(
                "SELECT 1 FROM maya_rp.events WHERE session_id=$1 AND event_type='fleet_burn' "
                "AND tags @> $2::jsonb LIMIT 1", session_id, day_tag):
            return {"skipped": f"game day {day} already billed", "game_day": day}
        burn = await calculate_daily_burn(session_id, conn)
        if burn["active_ships"] == 0:
            return {"burn": burn, "game_day": day, "skipped": "no billed ships"}
        charged: dict[str, int] = {}
        shortfall: dict[str, dict[str, int]] = {}
        for column, due in (("fuel", burn["fuel"]), ("alloys", burn["alloy"]), ("credits", burn["credits"])):
            if due <= 0:
                continue
            try:
                await _deduct_resources(session_id, {column: due}, conn=conn)
                charged[column] = due
            except InsufficientResources:
                shortfall[column] = {"due": due, "held": int(held[column] or 0)}
        paid = ", ".join(f"{col} {qty}" for col, qty in charged.items()) or "nothing"
        await _record(conn, session_id, "fleet_burn", f"Fleet burn, day {day}", day, 1,
                      f"{burn['active_ships']} ships, {burn['crew']} crew. Charged {paid}.")
        if shortfall:
            unpaid = ", ".join(f"{col} {v['due']} (held {v['held']})" for col, v in shortfall.items())
            await _record(conn, session_id, "fleet_shortfall", f"Fleet burn unpaid, day {day}", day, 3,
                          f"The treasury cannot cover the burn. Unpaid: {unpaid}.")
            warn("fleet_economy", f"session {session_id} day {day}: burn unpaid, {unpaid}")
        left = await conn.fetchrow(
            "SELECT fuel, alloys, credits FROM maya_rp.resources WHERE session_id=$1", session_id)
    out = {"burn": burn, "game_day": day, "charged": charged, "fuel_remaining": left["fuel"],
           "alloy_remaining": left["alloys"], "credits_remaining": left["credits"]}
    if shortfall:
        out["shortfall"] = shortfall
    return out


async def _record(conn, session_id: int, event_type: str, title: str, day: int,
                  importance: int, description: str) -> None:
    await conn.execute(
        "INSERT INTO maya_rp.events (session_id, happened_at, event_type, title, description, tags, importance) "
        "VALUES ($1, NOW(), $2, $3, $4, $5, $6)",
        session_id, event_type, title, description, json.dumps([event_type, f"day:{day}"]), importance)


async def get_burn_summary(session_id: int) -> dict:
    burn = await calculate_daily_burn(session_id)
    res = await Database.fetchrow("SELECT fuel, alloys, credits FROM maya_rp.resources WHERE session_id=$1", session_id)
    if not res: return {"error": "No resources"}
    days = (res["fuel"] // burn["fuel"]) if burn["fuel"] > 0 else 999
    return {"resources": {"fuel": res["fuel"], "alloys": res["alloys"], "credits": res["credits"]},
            "daily_burn": burn, "days_of_fuel": days, "critical": days < 3}

async def generate_caravan(session_id: int) -> dict:
    cargo = random.choice(["fuel","alloys","food","credits"])
    qty = random.randint(100, 5000)
    return {"cargo": cargo, "quantity": qty, "origin": "friendly_territory", "transit_days": random.randint(1, 5)}

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = require_session(None)
    try:
        burn = await apply_burn(session_id)
        info("fleet_economy", f"Tick: burn={burn.get('burn',{}).get('fuel',0)}f {burn.get('burn',{}).get('food',0)}fd")
        return burn
    except Exception as e:
        info("fleet_economy", f"Error: {e}")
        return {"error": str(e)}
