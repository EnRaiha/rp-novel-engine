#!/usr/bin/env python3
"""Mystery Module — Ported from rpg-mystery skill.

Schema contract (migration 105): `investigations.template_name` keeps the
mystery_templates row that seeded the case, and `clues.investigation_id` links a
clue to its case. The log table keys on (entry_type, description).
"""
from __future__ import annotations
import random
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info

DEFAULT_THRESHOLD = 3
# clues.source_type is enum-checked in the schema; `source` is free text and
# carries the provenance label ('misdirection' marks a red herring).
ALLOWED_SOURCE_TYPES = ("discovery", "interrogation", "companion_insight",
                        "scan", "artifact", "document", "testimony")
RED_HERRING_SOURCE = "misdirection"

async def create_investigation(session_id: int, title: str, template: str = "generic", difficulty: int = 5) -> dict:
    inv_id = await Database.fetchval(
        "INSERT INTO maya_rp.investigations (session_id, title, template_name, difficulty, status) VALUES ($1,$2,$3,$4,'active') RETURNING id",
        session_id, title, template, difficulty,
    )
    info("mystery", f"Investigation started: {title}")
    return {"investigation_id": inv_id, "title": title, "difficulty": difficulty}

async def add_clue(session_id: int, investigation_id: int, text: str, source: str = "discovery",
                   revealed_by: int | None = None, connects_to: int | None = None,
                   source_type: str = "discovery") -> dict:
    if source_type not in ALLOWED_SOURCE_TYPES:
        source_type = "discovery"
    clue_id = await Database.fetchval(
        "INSERT INTO maya_rp.clues (session_id, source, source_type, text, connects_to_clue, revealed, revealed_by_character, investigation_id) "
        "VALUES ($1,$2,$3,$4,$5,true,$6,$7) RETURNING id",
        session_id, source, source_type, text, connects_to, revealed_by, investigation_id,
    )
    if connects_to:
        await Database.execute(
            "UPDATE maya_rp.clues SET connects_to_clue=$1 WHERE id=$2",
            min(clue_id, connects_to), max(clue_id, connects_to),
        )
    await _bump_clue_count(investigation_id)
    return {"clue_id": clue_id, "investigation_id": investigation_id}

async def deduce(session_id: int, investigation_id: int, description: str = "") -> dict:
    inv = await Database.fetchrow(
        "SELECT id, template_name, status FROM maya_rp.investigations WHERE id=$1 AND session_id=$2",
        investigation_id, session_id,
    )
    if not inv:
        return {"error": f"Investigation {investigation_id} not found in session {session_id}"}
    rows = await Database.fetch(
        "SELECT id FROM maya_rp.clues WHERE investigation_id=$1 AND revealed=true "
        "AND source IS DISTINCT FROM $2", investigation_id, RED_HERRING_SOURCE)
    chained = await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.clues WHERE investigation_id=$1 AND connects_to_clue IS NOT NULL",
        investigation_id) or 0
    # Threshold comes from the template that seeded the case (registered),
    # not from a hardcoded constant.
    threshold = await Database.fetchval(
        "SELECT min_clues_for_deduction FROM maya_rp.mystery_templates WHERE name=$1",
        inv["template_name"]) or DEFAULT_THRESHOLD
    score = len(rows)   # not capped: template thresholds run up to 6
    success = score >= threshold
    await Database.execute(
        "UPDATE maya_rp.investigations SET clues_found=$1, deductions_made=COALESCE(deductions_made,0)+1, "
        "status=CASE WHEN $2 THEN 'solved' ELSE status END, "
        "solved_at=CASE WHEN $2 THEN NOW() ELSE solved_at END, "
        "summary=COALESCE(NULLIF($3,''), summary) "
        "WHERE id=$4",
        score, success, description, investigation_id,
    )
    await Database.execute(
        "INSERT INTO maya_rp.investigation_log (session_id, investigation_id, entry_type, description) "
        "VALUES ($1,$2,'deduction',$3)",
        session_id, investigation_id, "solved" if success else "insufficient_clues",
    )
    return {"success": success, "clues_found": score, "chained": chained,
            "threshold": threshold, "investigation_id": investigation_id}

async def generate_red_herring(session_id: int, investigation_id: int) -> dict:
    texts = ["False witness places suspect elsewhere", "Forged log entry misdirects investigation",
             "Signal turns out to be natural phenomenon", "Debris field leads nowhere"]
    text = random.choice(texts)
    # source_type must stay inside the schema enum; the red-herring marker is the
    # free-text `source` label, which deduce() excludes from the clue count.
    clue_id = await Database.fetchval(
        "INSERT INTO maya_rp.clues (session_id, source, source_type, text, revealed, investigation_id) "
        "VALUES ($1,$2,'document',$3,true,$4) RETURNING id",
        session_id, RED_HERRING_SOURCE, text, investigation_id,
    )
    await _bump_clue_count(investigation_id)
    return {"clue_id": clue_id, "text": text, "investigation_id": investigation_id}

async def _bump_clue_count(investigation_id: int):
    """Keep investigations.clues_found in step with its revealed clues (red
    herrings excluded — they are not progress)."""
    if not investigation_id:
        return
    await Database.execute(
        "UPDATE maya_rp.investigations SET clues_found = ("
        "  SELECT COUNT(*) FROM maya_rp.clues c "
        "  WHERE c.investigation_id = $1 AND c.revealed = true "
        "  AND c.source IS DISTINCT FROM $2) "
        "WHERE id = $1",
        investigation_id, RED_HERRING_SOURCE,
    )

async def run_tick(session_id: int = None) -> dict:
    """Investigation aging (added 2026-08-14): active investigations older
    than 20 game-days with no deductions log a 'trail aging' entry — the GM
    sees cold cases instead of them silently persisting."""
    if session_id is None: session_id = Config.SESSION_ID
    try:
        active = await Database.fetch(
            "SELECT id, title, deductions_made, created_at FROM maya_rp.investigations "
            "WHERE session_id=$1 AND status='active'", session_id)
        decayed = 0
        for inv in active:
            if not inv.get("created_at"):
                continue
            age = (await Database.fetchval(
                "SELECT EXTRACT(EPOCH FROM NOW()-$1::timestamptz)/86400", inv["created_at"]))
            if age >= 20 and (inv.get("deductions_made") or 0) == 0:
                await Database.execute(
                    "INSERT INTO maya_rp.investigation_log (session_id, investigation_id, entry_type, description) "
                    "VALUES ($1,$2,'dead_end','trail_growing_cold')",
                    session_id, inv["id"])
                decayed += 1
                info("mystery", f"Decay: investigation {inv['id']} ({inv['title']}) going cold")
        info("mystery", f"Tick: {len(active)} active, {decayed} aging")
        return {"active": len(active), "decayed": decayed}
    except Exception as e:
        info("mystery", f"Error: {e}")
        return {"error": str(e)}
