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
    fuel_burn = (ships or 2) * BURN_RATES["per_active_ship"] + BURN_RATES["base_consumption"]
    food_burn = max(1, round(pop * BURN_RATES["food_per_pop"] * 24))
    return {"fuel": fuel_burn, "food": food_burn, "alloy": 0, "credits": 100, "active_ships": ships}

async def apply_burn(session_id: int) -> dict:
    burn = await calculate_daily_burn(session_id)
    res = await Database.fetchrow("SELECT fuel, alloys, credits FROM maya_rp.resources WHERE session_id=$1", session_id)
    if not res: return {"error": "No resources"}
    new_fuel = max(0, res["fuel"] - burn["fuel"])
    new_alloy = max(0, res["alloys"] - burn["alloy"])
    new_credits = max(0, res["credits"] - burn["credits"])
    await Database.execute("UPDATE maya_rp.resources SET fuel=$1, alloys=$2, credits=$3 WHERE session_id=$4",
                           new_fuel, new_alloy, new_credits, session_id)
    return {"burn": burn, "fuel_remaining": new_fuel, "alloy_remaining": new_alloy, "credits_remaining": new_credits}

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
