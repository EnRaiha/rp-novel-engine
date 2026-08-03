#!/usr/bin/env python3
"""Stealth/Spy — Ported from Rust stealth.rs."""
from __future__ import annotations
import random
from core.db import Database
from core.config import Config
from core.log import info

async def build_spy(unit_type: str, name: str, session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    ut = await Database.fetchrow("SELECT id, name, base_cost_alloys, cloak_level, max_lanes FROM maya_rp.stealth_unit_types WHERE LOWER(name) LIKE LOWER($1) LIMIT 1", f"%{unit_type}%")
    if not ut: return {"error": f"Unknown unit type: {unit_type}"}
    res = await Database.fetchrow("SELECT alloys FROM maya_rp.resources WHERE session_id=$1", session_id)
    if not res or res["alloys"] < ut["base_cost_alloys"]:
        return {"error": f"Need {ut['base_cost_alloys']} alloys"}
    await Database.execute("UPDATE maya_rp.resources SET alloys=alloys-$1 WHERE session_id=$2", ut["base_cost_alloys"], session_id)
    await Database.execute("INSERT INTO maya_rp.stealth_units (session_id, unit_type_id, name) VALUES ($1,$2,$3)", session_id, ut["id"], name)
    info("stealth", f"Built spy: {name}")
    return {"name": name, "type": ut["name"], "cloak": ut["cloak_level"], "lanes": ut["max_lanes"]}

async def deploy_spy(name: str, lane: str, session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    su = await Database.fetchrow("SELECT id FROM maya_rp.stealth_units WHERE session_id=$1 AND LOWER(name) LIKE LOWER($2) AND status='active' LIMIT 1", session_id, f"%{name}%")
    if not su: return {"error": f"Spy '{name}' not found"}
    await Database.execute("UPDATE maya_rp.stealth_units SET assigned_lane=$1 WHERE id=$2", lane, su["id"])
    return {"deployed": name, "lane": lane}

async def hack(name: str, operation: str, target: str, session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    su = await Database.fetchrow("SELECT su.id, su.name FROM maya_rp.stealth_units su WHERE su.session_id=$1 AND LOWER(su.name) LIKE LOWER($2) LIMIT 1", session_id, f"%{name}%")
    if not su: return {"error": f"Spy '{name}' not found"}
    chance = 40 + random.randint(-10, 20)
    roll = random.randint(1, 100)
    outcome = "success" if roll <= chance else "detected" if roll <= chance + 20 else "failure"
    intel = random.randint(20, 80) if outcome == "success" else random.randint(0, 10)
    if intel > 0:
        await Database.execute("UPDATE maya_rp.space_lanes SET intel_level=LEAST(COALESCE(intel_level,0)+$1,100) WHERE session_id=$2 AND (origin=$3 OR destination=$3)", intel, session_id, target)
    return {"spy": su["name"], "operation": operation, "target": target, "outcome": outcome, "intel_gained": intel}

async def build_anticloak(system: str, level: int = 1, session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    lev = max(1, min(5, level))
    cost = [0, 10000, 25000, 60000, 150000, 500000][lev]
    detect = [0, 15, 30, 50, 75, 95][lev]
    rng = [0, 3, 6, 10, 15, 25][lev]
    upk = [0, 200, 500, 1500, 4000, 15000][lev]
    res = await Database.fetchrow("SELECT alloys FROM maya_rp.resources WHERE session_id=$1", session_id)
    if not res or res["alloys"] < cost: return {"error": f"Need {cost} alloys"}
    await Database.execute("UPDATE maya_rp.resources SET alloys=alloys-$1 WHERE session_id=$2", cost, session_id)
    await Database.execute("INSERT INTO maya_rp.anti_cloak_grids (session_id, system_name, level, detection_pct, range_ly, upkeep_credits) VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT DO NOTHING", session_id, system, lev, detect, rng, upk)
    return {"system": system, "level": lev, "detection": detect, "range": rng, "cost": cost}

async def list_anticloak(session_id: int | None = None) -> list[dict]:
    if session_id is None: session_id = Config.SESSION_ID
    rows = await Database.fetch("SELECT system_name, level, detection_pct, range_ly, upkeep_credits FROM maya_rp.anti_cloak_grids WHERE session_id=$1 AND status='active' ORDER BY level DESC", session_id)
    return [dict(r) for r in rows]

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    return {"status": "stealth_ready"}
