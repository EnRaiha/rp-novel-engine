#!/usr/bin/env python3
"""Adventures — Ported from Rust adventure.rs."""
from __future__ import annotations
import random
from core.db import Database
from core.config import Config
from core.log import info

ENCOUNTER_TYPES = ["merchant","pirate","derelict","anomaly","distress","trade_fleet","refugee","ambush","signal","artifact"]

async def generate(session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    etype = random.choice(ENCOUNTER_TYPES)
    system = await Database.fetchval("SELECT system_name FROM maya_rp.territory WHERE session_id=$1 ORDER BY RANDOM() LIMIT 1", session_id) or "Unknown"
    gold = random.randint(100, 2000) if etype in ("merchant","trade_fleet") else 0
    combat = etype in ("pirate","ambush")
    return {"type": etype, "system": system, "gold_reward": gold, "combat": combat, "description": f"A {etype} encounter at {system}"}

async def resolve(adventure_type: str, outcome: str, session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    if outcome == "success":
        reward = random.randint(500, 5000)
        await Database.execute("UPDATE maya_rp.resources SET credits=credits+$1 WHERE session_id=$2", reward, session_id)
        return {"reward": reward, "outcome": "success"}
    return {"reward": 0, "outcome": outcome}

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    return {"status": "adventures_ready"}
