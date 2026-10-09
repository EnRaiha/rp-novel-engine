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
from core.log import error, info
from core.session import require_session

DEFAULT_THRESHOLD = 3
# clues.source_type is enum-checked in the schema; `source` is free text and
# carries the provenance label ('misdirection' marks a red herring).
ALLOWED_SOURCE_TYPES = ("discovery", "interrogation", "companion_insight",
                        "scan", "artifact", "document", "testimony")
RED_HERRING_SOURCE = "misdirection"

async def create_investigation(session_id: int, title: str, template: str = "generic", difficulty: int = 5) -> dict:
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    inv_id = await Database.fetchval(
        "INSERT INTO maya_rp.investigations (session_id, title, template_name, difficulty, status) VALUES ($1,$2,$3,$4,'active') RETURNING id",
        session_id, title, template, difficulty,
    )
    info("mystery", f"Investigation started: {title}")
    return {"investigation_id": inv_id, "title": title, "difficulty": difficulty}

async def _owned_investigation(session_id: int, investigation_id: int) -> str | None:
    """None when this session owns the case, else the reason it does not.

    `add_clue` grew this check during the previous review and `generate_red_herring` did not, so a
    red herring could still be filed against another campaign's case.
    """
    owner = await Database.fetchval(
        "SELECT session_id FROM maya_rp.investigations WHERE id=$1", investigation_id)
    if owner is None:
        return f"investigation {investigation_id} does not exist"
    if int(owner) != int(session_id):
        return f"investigation {investigation_id} belongs to session {owner}, not {session_id}"
    return None


async def add_clue(session_id: int, investigation_id: int, text: str, source: str = "discovery",
                   revealed_by: int | None = None, connects_to: int | None = None,
                   source_type: str = "discovery") -> dict:
    """Attach one clue to an investigation.

    Reviewed 2026-10-03 before wiring. The insert never checked that the investigation belonged to
    this session, so a clue could be filed against another campaign's case; that check is here now.
    An unknown `source_type` still falls back to `discovery`, which is deliberate and reported in the
    return value rather than hidden.
    """
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    if source_type not in ALLOWED_SOURCE_TYPES:
        source_type = "discovery"
    refusal = await _owned_investigation(session_id, investigation_id)
    if refusal:
        return {"error": refusal}
    if connects_to is not None:
        # The link is stored on the new clue, so the target must exist in this session and case.
        target = await Database.fetchrow(
            "SELECT id, session_id, investigation_id FROM maya_rp.clues WHERE id=$1", connects_to)
        if not target:
            return {"error": f"clue {connects_to} does not exist"}
        if int(target["session_id"]) != int(session_id):
            return {"error": f"clue {connects_to} belongs to session {target['session_id']},"
                             f" not {session_id}"}
        target_case = target["investigation_id"]
        if target_case is None:
            return {"error": f"clue {connects_to} belongs to no investigation"}
        if int(target_case) != int(investigation_id):
            return {"error": f"clue {connects_to} belongs to investigation"
                             f" {target_case}, not {investigation_id}"}
    clue_id = await Database.fetchval(
        "INSERT INTO maya_rp.clues (session_id, source, source_type, text, connects_to_clue, revealed, revealed_by_character, investigation_id) "
        "VALUES ($1,$2,$3,$4,$5,true,$6,$7) RETURNING id",
        session_id, source, source_type, text, connects_to, revealed_by, investigation_id,
    )
    await _bump_clue_count(investigation_id)
    return {"clue_id": clue_id, "investigation_id": investigation_id}

async def deduce(session_id: int, investigation_id: int, description: str = "") -> dict:
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
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
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    refusal = await _owned_investigation(session_id, investigation_id)
    if refusal:
        return {"error": refusal}
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
    """Investigation aging: an active case older than 20 wall-clock days (from `created_at`) with no
    deductions turns `cold` and logs one `trail_growing_cold` entry. The status guard makes it once."""
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
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
                async with Database.transaction() as conn:
                    claimed = await conn.fetchval(
                        "UPDATE maya_rp.investigations SET status='cold' "
                        "WHERE id=$1 AND session_id=$2 AND status='active' RETURNING id",
                        inv["id"], session_id)
                    if claimed is None:
                        continue
                    await conn.execute(
                        "INSERT INTO maya_rp.investigation_log (session_id, investigation_id, entry_type, description) "
                        "VALUES ($1,$2,'dead_end','trail_growing_cold')",
                        session_id, inv["id"])
                decayed += 1
                info("mystery", f"Decay: investigation {inv['id']} ({inv['title']}) going cold")
        info("mystery", f"Tick: {len(active)} active, {decayed} aging")
        return {"active": len(active), "decayed": decayed}
    except Exception as e:
        error("mystery", f"tick failed for session {session_id}: {e}")
        return {"error": str(e)}
