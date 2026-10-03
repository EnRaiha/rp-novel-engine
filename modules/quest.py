#!/usr/bin/env python3
"""Quest — Ported from Rust quest.rs."""
from __future__ import annotations
import random
from core.db import Database
from core.config import Config
from core.log import info

QUEST_TYPES = ["combat","exploration","diplomacy","trade","science","delivery","defense"]

async def generate(session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    qtype = random.choice(QUEST_TYPES)
    name = f"{random.choice(['Operation','Mission','Task','Contract','Expedition'])} {random.choice(['Starfall','Ironhold','Shadowmere','Dawnbreak','Voidgate'])}"
    rewards = {"alloys": random.randint(500, 5000), "credits": random.randint(1000, 10000)}
    qid = await Database.fetchval(
        "INSERT INTO maya_rp.quests (session_id, title, quest_type, description, reward_alloy, reward_credit, status) "
        "VALUES ($1,$2,$3,$4,$5,$6,'active') RETURNING id",
        session_id, name, qtype, f"A {qtype} quest", rewards["alloys"], rewards["credits"])
    return {"id": qid, "name": name, "type": qtype, "rewards": rewards}

async def complete(quest_id: int, session_id: int | None = None) -> dict:
    """Pay out one quest. A quest that is not open cannot be completed again.

    The read did not filter on status, so completing the same quest twice paid
    the reward twice. The payout also has to land: a session with no `resources`
    row (session 5 has none) used to be told it was paid.
    """
    if session_id is None: session_id = Config.SESSION_ID
    # quests spells the rewards reward_alloy / reward_credit (singular).
    q = await Database.fetchrow(
        "SELECT id, status, reward_alloy, reward_credit FROM maya_rp.quests "
        "WHERE id=$1 AND session_id=$2", quest_id, session_id)
    if not q: return {"error": "Quest not found"}
    if q["status"] != "active":
        return {"error": f"Quest {quest_id} is {q['status']}, not active — no reward paid"}
    tag = await Database.execute(
        "UPDATE maya_rp.resources SET alloys=alloys+$1, credits=credits+$2 WHERE session_id=$3",
        q["reward_alloy"], q["reward_credit"], session_id)
    if isinstance(tag, str) and tag.split()[-1:] == ["0"]:
        info("quest", f"session {session_id} has no resources row — quest {quest_id} NOT paid")
        return {"error": f"No treasury row for session {session_id} — quest left open"}
    await Database.execute(
        "UPDATE maya_rp.quests SET status='completed' WHERE id=$1 AND session_id=$2",
        quest_id, session_id)
    return {"completed": True, "alloys": q["reward_alloy"], "credits": q["reward_credit"]}

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    return {"status": "quest_ready"}
