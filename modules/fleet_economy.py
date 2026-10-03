#!/usr/bin/env python3
"""Fleet Economy Module — Ported from fleet-economy skill (resource-burn.js, caravan-events.js, production-queue.js, trade-deals.js)"""
from __future__ import annotations
import random
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info

BURN_RATES = {"per_active_ship": 10, "base_consumption": 50, "food_per_pop": 0.001}

async def calculate_daily_burn(session_id: int) -> dict:
    ships = await Database.fetchval("SELECT COUNT(*) FROM maya_rp.ships WHERE session_id=$1 AND status IN ('active','patrol','deployed')", session_id) or 0
    pop = await Database.fetchval("SELECT population FROM maya_rp.resources WHERE session_id=$1", session_id) or 0
    # crew salaries: every crewed hull draws wages (2026-08-14)
    crew = await Database.fetchval(
        "SELECT COALESCE(SUM(crew_current),0) FROM maya_rp.ships WHERE session_id=$1", session_id) or 0
    fuel_burn = (ships or 2) * BURN_RATES["per_active_ship"] + BURN_RATES["base_consumption"]
    food_burn = max(1, round(pop * BURN_RATES["food_per_pop"] * 24))
    salary_burn = int(crew * 2)  # 2C per crewman per game-day
    return {"fuel": fuel_burn, "food": food_burn, "alloy": 0,
            "credits": 100 + salary_burn, "active_ships": ships, "crew": crew}

async def apply_burn(session_id: int) -> dict:
    burn = await calculate_daily_burn(session_id)
    # One statement, decremented in the database: the old read-modify-write set
    # absolute values from a snapshot, so a concurrent tick could lose its burn.
    row = await Database.fetchrow(
        "UPDATE maya_rp.resources SET fuel=GREATEST(0, fuel-$1), alloys=GREATEST(0, alloys-$2), "
        "credits=GREATEST(0, credits-$3) WHERE session_id=$4 "
        "RETURNING fuel, alloys, credits",
        burn["fuel"], burn["alloy"], burn["credits"], session_id)
    if not row:
        return {"error": f"No resources row for session {session_id}: burn not applied"}
    return {"burn": burn, "fuel_remaining": row["fuel"], "alloy_remaining": row["alloys"],
            "credits_remaining": row["credits"]}

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
    if session_id is None: session_id = Config.SESSION_ID
    try:
        burn = await apply_burn(session_id)
        info("fleet_economy", f"Tick: burn={burn.get('burn',{}).get('fuel',0)}f {burn.get('burn',{}).get('food',0)}fd")
        return burn
    except Exception as e:
        info("fleet_economy", f"Error: {e}")
        return {"error": str(e)}
