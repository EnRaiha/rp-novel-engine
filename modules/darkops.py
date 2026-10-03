#!/usr/bin/env python3
"""Dark Ops — Ported from Rust darkops.rs."""
from __future__ import annotations
import random
from core.db import Database
from core.config import Config
from core.log import info

VALID_OPS = ["assassinate","sabotage","terror","planet_crack","enslave","purge","interrogate_hard"]
OP_COSTS = {"assassinate":(2000,5000,-40,10),"sabotage":(1000,2000,-20,5),"terror":(2000,1000,-30,15),
            "planet_crack":(10000,5000,-100,30),"enslave":(1000,500,-80,20),"purge":(5000,5000,-60,25),
            "interrogate_hard":(100,200,-10,5)}
MORALITY_COST = {"assassinate":-10,"sabotage":-5,"terror":-20,"planet_crack":-40,"enslave":-50,"purge":-60,"interrogate_hard":-10}

async def run_op(operation: str, target: str, session_id: int | None = None) -> dict:
    """Run one dark operation against a faction of this campaign.

    The target is resolved BEFORE anything is charged: a misspelled name used to
    match no faction, take the alloys and credits anyway, and report success.
    The operation is recorded now too — `list_darkops` reads `maya_rp.dark_ops`
    and nothing in the repo wrote to it, so the log door opened on an empty room.
    """
    if session_id is None: session_id = Config.SESSION_ID
    if operation not in VALID_OPS: return {"error": f"Unknown: {operation}. Valid: {VALID_OPS}"}
    faction = await Database.fetchrow(
        "SELECT id, name FROM maya_rp.factions WHERE session_id=$1 "
        "AND LOWER(name) LIKE LOWER($2) ORDER BY id LIMIT 1",
        session_id, f"%{target}%")
    if not faction:
        return {"error": f"No faction matching '{target}' in session {session_id}"}
    cost_a, cost_c, rep_delta, fear = OP_COSTS[operation]
    res = await Database.fetchrow("SELECT alloys, credits FROM maya_rp.resources WHERE session_id=$1", session_id)
    if not res or res["alloys"] < cost_a or res["credits"] < cost_c:
        return {"error": f"Need {cost_a}a/{cost_c}c"}

    await Database.execute("UPDATE maya_rp.resources SET alloys=alloys-$1, credits=credits-$2 WHERE session_id=$3", cost_a, cost_c, session_id)
    chance = 30 + random.randint(-10, 20)
    roll = random.randint(1, 100)
    outcome = "exposed" if roll <= chance // 5 else "success" if roll <= chance else "failure"
    collat = random.randint(5, 50) if outcome == "success" else random.randint(20, 100) if outcome == "failure" else random.randint(50, 200)
    eff_rep = rep_delta if outcome == "success" else rep_delta // 2 if outcome == "failure" else rep_delta * 2
    morality = MORALITY_COST.get(operation, -5)

    await Database.execute(
        "UPDATE maya_rp.factions SET reputation=GREATEST(reputation+$1,-100), "
        "fear_of_player=COALESCE(fear_of_player,0)+$2 WHERE id=$3 AND session_id=$4",
        eff_rep, fear, faction["id"], session_id)
    await Database.execute("UPDATE maya_rp.resources SET fear=COALESCE(fear,0)+$1 WHERE session_id=$2", fear, session_id)
    await Database.execute(
        "INSERT INTO maya_rp.dark_ops (session_id, target_type, target_name, operation, "
        "success_chance, collateral, reputation_delta, outcome, narrative, launched_at) "
        "VALUES ($1,'faction',$2,$3,$4,$5,$6,$7,$8,NOW())",
        session_id, faction["name"], operation, chance, collat, eff_rep, outcome,
        f"{operation} against {faction['name']}: {outcome}, collateral {collat}")
    info("darkops", f"{operation} → {target}: {outcome} (collat: {collat})")
    return {"operation": operation, "target": target, "outcome": outcome, "cost_alloys": cost_a, "cost_credits": cost_c, "rep_delta": eff_rep, "collateral": collat, "morality": morality}

async def list_darkops(session_id: int | None = None) -> list[dict]:
    if session_id is None: session_id = Config.SESSION_ID
    rows = await Database.fetch("SELECT operation, target_name, outcome, collateral, narrative FROM maya_rp.dark_ops WHERE session_id=$1 ORDER BY launched_at DESC LIMIT 15", session_id)
    return [dict(r) for r in rows]

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    return {"status": "darkops_ready"}
