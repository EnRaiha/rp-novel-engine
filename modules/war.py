#!/usr/bin/env python3
"""War System — strategic entity with phases, objectives, resolution."""
from __future__ import annotations
import json, random
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info

WAR_PHASES = ["escalation","mobilization","clash","attrition","turning_point","resolution"]

async def declare(target_faction: str, casus_belli: str, war_goal: str,
                  session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    game_day = await Database.fetchval("SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id)
    wid = await Database.fetchval(
        "INSERT INTO maya_rp.wars (session_id, opponent_faction, casus_belli, war_goal, "
        "phase, started_at_game_day, status) "
        "VALUES ($1,$2,$3,$4,'escalation',$5,'active') RETURNING id",
        session_id, target_faction, casus_belli, war_goal, game_day)
    await Database.execute(
        "UPDATE maya_rp.factions SET standing='hostile' WHERE session_id=$1 AND LOWER(name) LIKE LOWER($2)",
        session_id, f"%{target_faction}%")
    info("war", f"WAR: {target_faction} — {casus_belli}")
    return {"war_id": wid, "phase": "escalation", "opponent": target_faction}

async def advance(war_id: int, session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    war = await Database.fetchrow("SELECT * FROM maya_rp.wars WHERE id=$1 AND session_id=$2", war_id, session_id)
    if not war: return {"error": "War not found"}

    player_power = await Database.fetchval(
        "SELECT COALESCE(SUM(s.power_rating), 0) FROM maya_rp.ships s "
        "WHERE s.session_id=$1 AND s.status='active'", session_id) or 1
    enemy_power = await Database.fetchval(
        "SELECT COALESCE(SUM(fs.power_rating), 0) FROM maya_rp.faction_ships fs "
        "WHERE fs.session_id=$1 AND fs.faction_name=$2 AND fs.status='active'",
        session_id, war["opponent_faction"]) or 1

    ratio = player_power / max(1, enemy_power)
    current_idx = WAR_PHASES.index(war["phase"]) if war["phase"] in WAR_PHASES else 0
    advance_phase = False
    if current_idx < 4:
        if ratio > 1.5: advance_phase = True
        elif ratio < 0.4: advance_phase = True
        else: advance_phase = random.random() < 0.3

    cas_a = random.randint(0, 50)
    cas_d = random.randint(0, 30)
    await Database.execute(
        "UPDATE maya_rp.wars SET attacker_casualties=attacker_casualties+$1, "
        "defender_casualties=defender_casualties+$2, updated_at=NOW() WHERE id=$3",
        cas_a, cas_d, war_id)

    result = {"war_id": war_id, "phase": war["phase"], "power_ratio": round(ratio, 2),
              "attacker_cas": cas_a, "defender_cas": cas_d}

    if advance_phase and current_idx < 5:
        new_phase = WAR_PHASES[current_idx + 1]
        await Database.execute("UPDATE maya_rp.wars SET phase=$1 WHERE id=$2", new_phase, war_id)
        result["new_phase"] = new_phase
        await Database.execute(
            "INSERT INTO maya_rp.events (session_id, happened_at, event_type, title, description, tags, importance) "
            "VALUES ($1, NOW(), 'war_phase', $2, $3, $4, 5)",
            session_id, f"War Phase: {new_phase.upper()}",
            f"The war with {war['opponent_faction']} enters {new_phase} phase. Power ratio: {ratio:.1f}",
            json.dumps(["war", war["opponent_faction"], new_phase]))

    if current_idx >= 4:
        winner = war["opponent_faction"] if ratio < 0.8 else "Player"
        await Database.execute("UPDATE maya_rp.wars SET status='ended', phase='resolution' WHERE id=$1", war_id)
        await Database.execute(
            "INSERT INTO maya_rp.events (session_id, happened_at, event_type, title, description, tags, importance) "
            "VALUES ($1, NOW(), 'war_end', $2, $3, $4, 10)",
            session_id, f"War Ended: {war['opponent_faction']}",
            f"The war with {war['opponent_faction']} has ended. {winner} emerges victorious.",
            json.dumps(["war", "ended"]))
        result["ended"] = True
        result["winner"] = winner

    return result

async def list_wars(session_id: int = None) -> list[dict]:
    if session_id is None: session_id = Config.SESSION_ID
    rows = await Database.fetch(
        "SELECT id, opponent_faction, phase, status, casus_belli, attacker_casualties, defender_casualties "
        "FROM maya_rp.wars WHERE session_id=$1 ORDER BY id", session_id)
    return [dict(r) for r in rows]

async def tick_wars(session_id: int = None) -> list[dict]:
    if session_id is None: session_id = Config.SESSION_ID
    wars = await list_wars(session_id)
    results = []
    for w in wars:
        r = await advance(w["id"], session_id)
        results.append(r)
    return results

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    try:
        results = await tick_wars(session_id)
        info("war", f"Tick: {len(results)} wars advanced")
        return {"wars_advanced": len(results)}
    except Exception as e:
        info("war", f"Error: {e}")
        return {"error": str(e)}
