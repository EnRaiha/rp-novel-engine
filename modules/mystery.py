#!/usr/bin/env python3
"""Mystery Module — Ported from rpg-mystery skill."""
from __future__ import annotations
import random
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info

async def create_investigation(session_id: int, title: str, template: str = "generic", difficulty: int = 5) -> dict:
    inv_id = await Database.fetchval(
        "INSERT INTO maya_rp.investigations (session_id, title, template_name, difficulty, status) VALUES ($1,$2,$3,$4,'active') RETURNING id",
        session_id, title, template, difficulty,
    )
    info("mystery", f"Investigation started: {title}")
    return {"investigation_id": inv_id, "title": title, "difficulty": difficulty}

async def add_clue(session_id: int, investigation_id: int, text: str, source: str = "discovery",
                   revealed_by: int | None = None, connects_to: int | None = None) -> dict:
    clue_id = await Database.fetchval(
        "INSERT INTO maya_rp.clues (session_id, source, source_type, text, connects_to_clue, revealed, revealed_by_character) "
        "VALUES ($1,$2,'manual',$3,$4,true,$5) RETURNING id",
        session_id, source, text, connects_to, revealed_by,
    )
    if connects_to:
        await Database.execute(
            "UPDATE maya_rp.clues SET connects_to_clue=$1 WHERE id=$2",
            min(clue_id, connects_to), max(clue_id, connects_to),
        )
    return {"clue_id": clue_id}

async def deduce(session_id: int, investigation_id: int, description: str) -> dict:
    rows = await Database.fetch("SELECT id FROM maya_rp.clues WHERE investigation_id=$1 AND revealed=true", investigation_id)
    # Also check clues linked via key
    linked = await Database.fetch("SELECT id FROM maya_rp.clues WHERE connects_to_clue IS NOT NULL AND id IN (SELECT id FROM maya_rp.clues WHERE investigation_id=$1)", investigation_id)
    score = min(len(rows) + len(linked), 5)
    success = score >= 3
    if success:
        await Database.execute("UPDATE maya_rp.investigations SET status='solved' WHERE id=$1", investigation_id)
    await Database.execute(
        "INSERT INTO maya_rp.investigation_log (session_id, investigation_id, action, result) VALUES ($1,$2,'deduce',$3)",
        session_id, investigation_id, "solved" if success else "insufficient_clues",
    )
    return {"success": success, "clues_found": score, "threshold": 3}

async def generate_red_herring(session_id: int, investigation_id: int) -> dict:
    texts = ["False witness places suspect elsewhere", "Forged log entry misdirects investigation",
             "Signal turns out to be natural phenomenon", "Debris field leads nowhere"]
    text = random.choice(texts)
    clue_id = await Database.fetchval(
        "INSERT INTO maya_rp.clues (session_id, source, source_type, text, revealed) VALUES ($1,'misdirection','red_herring',$2,true) RETURNING id",
        session_id, text,
    )
    return {"clue_id": clue_id, "text": text}

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    try:
        active = await Database.fetch("SELECT id, title FROM maya_rp.investigations WHERE session_id=$1 AND status='active'", session_id)
        info("mystery", f"Tick: {len(active)} active")
        return {"active": len(active)}
    except Exception as e:
        info("mystery", f"Error: {e}")
        return {"error": str(e)}
