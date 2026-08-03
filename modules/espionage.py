#!/usr/bin/env python3
"""Espionage — Ported from Rust espionage.rs."""
from __future__ import annotations
import random
from core.db import Database
from core.config import Config
from core.log import info

async def run_espionage(faction: str, mission_type: str, agent: str, session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    fac = await Database.fetchrow("SELECT id, name, reputation FROM maya_rp.factions WHERE session_id=$1 AND LOWER(name) LIKE LOWER($2) LIMIT 1", session_id, f"%{faction}%")
    if not fac: return {"error": f"Faction '{faction}' not found"}

    base = {"steal_tech": 40, "sabotage": 35, "steal_resources": 55, "assassinate": 20, "plant_rumor": 60, "scout_fleet": 70}
    chance = base.get(mission_type)
    if not chance: return {"error": f"Unknown mission: {mission_type}"}

    rep_mod = max(-10, fac["reputation"] // 10)
    success = max(5, min(95, chance + rep_mod + random.randint(-15, 15)))
    roll = random.randint(1, 100)
    outcome = "critical_failure" if roll <= success // 5 else "success" if roll <= success else "detected" if roll <= success + 20 else "failure"

    loot_a, loot_c, rep_delta, narrative = 0, 0, 0, ""
    if outcome == "success":
        loot_a, loot_c = random.randint(500, 2000), random.randint(200, 1000)
        narrative = f"{agent} successfully completed {mission_type} against {fac['name']}."
    elif outcome == "critical_failure":
        rep_delta = -15
        narrative = f"{agent} was CAPTURED during {mission_type} against {fac['name']}!"
    elif outcome == "detected":
        rep_delta = -5
        narrative = f"{agent} was detected during {mission_type}. {fac['name']} is not amused."
    else:
        rep_delta = -3
        narrative = f"{agent} failed the {mission_type} mission against {fac['name']}."

    if loot_a or loot_c:
        await Database.execute("UPDATE maya_rp.resources SET alloys=alloys+$1, credits=credits+$2 WHERE session_id=$3", loot_a, loot_c, session_id)
    await Database.execute("UPDATE maya_rp.factions SET reputation=GREATEST(reputation+$1, -100) WHERE id=$2", rep_delta, fac["id"])
    info("espionage", f"{agent} → {fac['name']} ({mission_type}): {outcome}")
    return {"outcome": outcome, "agent": agent, "mission": mission_type, "faction": fac["name"], "loot_alloys": loot_a, "loot_credits": loot_c, "rep_delta": rep_delta, "narrative": narrative}

async def list_espionage_log(session_id: int | None = None) -> list[dict]:
    if session_id is None: session_id = Config.SESSION_ID
    rows = await Database.fetch("SELECT em.mission_type, em.agent_name, em.outcome, em.narrative FROM maya_rp.espionage_missions em WHERE em.session_id=$1 ORDER BY em.created_at DESC LIMIT 15", session_id)
    return [dict(r) for r in rows]

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    return {"status": "espionage_ready"}
