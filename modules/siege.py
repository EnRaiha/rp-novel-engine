#!/usr/bin/env python3
"""Siege — Ported from Rust siege.rs."""
from __future__ import annotations
import random
import json
from core.db import Database
from core.config import Config
from core.log import info

async def start_siege(system: str, session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    t = await Database.fetchrow("SELECT id, controlling_faction, status FROM maya_rp.territory WHERE session_id=$1 AND LOWER(system_name) LIKE LOWER($2) LIMIT 1", session_id, f"%{system}%")
    if not t: return {"error": f"System '{system}' not found"}
    atk = await Database.fetchval("SELECT COALESCE(SUM(tier)*1000 + SUM(hull_current/10), 0) FROM maya_rp.ships WHERE session_id=$1 AND status='active'", session_id) or 0
    # factions has no fleet_strength column: the registered scalar for a
    # faction's fleet is pirate_fleet_power (maintained by pirates.py /
    # faction_ai.py). The * 800 scale below was calibrated for that magnitude,
    # so keep the module's own default when the faction has no rating yet.
    def_power = await Database.fetchval(
        "SELECT NULLIF(pirate_fleet_power, 0) FROM maya_rp.factions WHERE name=$1 AND session_id=$2",
        t["controlling_faction"], session_id) or 30
    defender = def_power * 800 + random.randint(200, 2000)
    sid = await Database.fetchval("INSERT INTO maya_rp.sieges (session_id, territory_id, target_system, target_faction, attacker_power, defender_power) VALUES ($1,$2,$3,$4,$5,$6) RETURNING id", session_id, t["id"], system, t["controlling_faction"], atk, defender)
    info("siege", f"Siege started: {system} vs {t['controlling_faction']}")
    return {"siege_id": sid, "system": system, "faction": t["controlling_faction"], "attacker_power": atk, "defender_power": defender}

async def advance_siege(siege_id: int, session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    s = await Database.fetchrow("SELECT id, target_system, target_faction, attacker_power, defender_power, phase, max_phases, damage_dealt, casualties_taken FROM maya_rp.sieges WHERE id=$1 AND status='active'", siege_id)
    if not s: return {"error": f"Siege {siege_id} not found or resolved"}
    atk_roll = s["attacker_power"] + random.randint(0, s["attacker_power"] // 4) - s["defender_power"] // 4
    def_roll = s["defender_power"] + random.randint(0, s["defender_power"] // 3) - s["attacker_power"] // 5
    dmg, cas = s["damage_dealt"] or 0, s["casualties_taken"] or 0

    if atk_roll > def_roll * 2: dmg += s["defender_power"] // 2; cas += random.randint(10, 100); desc = "Major Victory"
    elif atk_roll > def_roll: dmg += s["defender_power"] // 3; cas += random.randint(20, 200); desc = "Advantage"
    elif atk_roll > def_roll // 2: cas += random.randint(50, 300); desc = "Stalemate"
    else: cas += random.randint(100, 500); desc = "Defender Advantage"

    new_phase = s["phase"] + 1
    status = "victory" if dmg >= s["defender_power"] * 2 else "stalemate" if new_phase > s["max_phases"] else "routed" if cas > 3000 else "active"
    await Database.execute("UPDATE maya_rp.sieges SET phase=$1, damage_dealt=$2, casualties_taken=$3, status=$4 WHERE id=$5", new_phase, dmg, cas, status, siege_id)

    result = {"siege_id": siege_id, "system": s["target_system"], "phase": new_phase, "max_phases": s["max_phases"], "status": status, "description": desc, "damage_dealt": dmg, "casualties": cas}

    if status == "victory":
        await Database.execute("UPDATE maya_rp.territory SET controlling_faction='Setia Empire', status='controlled' WHERE system_name=$1", s["target_system"])
        loot = random.randint(1000, 5000)
        await Database.execute("UPDATE maya_rp.resources SET alloys=alloys+$1 WHERE session_id=$2", loot, session_id)
        await Database.execute("UPDATE maya_rp.ships SET experience=COALESCE(experience,0)+100 WHERE session_id=$1", session_id)
        result["loot"] = loot
        info("siege", f"VICTORY: {s['target_system']} captured!")

    return result

async def list_sieges(session_id: int | None = None) -> list[dict]:
    if session_id is None: session_id = Config.SESSION_ID
    rows = await Database.fetch("SELECT id, target_system, target_faction, status, phase, max_phases, casualties_taken FROM maya_rp.sieges WHERE session_id=$1 ORDER BY status, created_at DESC", session_id)
    return [dict(r) for r in rows]

async def run_tick(session_id: int = None) -> dict:
    """Auto-advance all active sieges (attrition loop, added 2026-08-14)."""
    if session_id is None: session_id = Config.SESSION_ID
    rows = await Database.fetch(
        "SELECT id FROM maya_rp.sieges WHERE session_id=$1 AND status='active'", session_id)
    advanced = 0
    for r in rows:
        try:
            res = await advance_siege(r["id"], session_id)
            if res.get("status") != "active":
                await Database.execute(
                    "INSERT INTO maya_rp.events (session_id, happened_at, event_type, title, description, tags, importance) "
                    "VALUES ($1, NOW(), 'siege', $2, $3, $4, 6)",
                    session_id, f"Siege {res.get('status')}: {res.get('system')}",
                    f"Siege of {res.get('system')} {res.get('status')}: {res.get('description')}",
                    json.dumps(["siege", res.get("system", ""), res.get("status", "")]))
            advanced += 1
        except Exception as e:
            info("siege", f"advance error: {e}")
    info("siege", f"Tick: {advanced} sieges advanced")
    return {"sieges_advanced": advanced}
