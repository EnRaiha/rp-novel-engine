#!/usr/bin/env python3
"""Tech Tree — Ported from Rust tech_tree.rs. Tech view, labs, assign scientists, research tick."""
from __future__ import annotations
import json
from typing import Any
from core.db import Database
from core.config import Config
from core.log import error, info

async def view_tech(session_id: int | None = None) -> list[dict]:
    if session_id is None: session_id = Config.SESSION_ID
    rows = await Database.fetch(
        "SELECT id, name, field, tier, researched, research_progress, prerequisites, unlocks "
        "FROM maya_rp.technologies WHERE session_id=$1 ORDER BY field, tier", session_id)
    return [dict(r) for r in rows]

async def tech_info(tech_name: str, session_id: int | None = None) -> dict | None:
    if session_id is None: session_id = Config.SESSION_ID
    row = await Database.fetchrow(
        "SELECT id, name, field, tier, researched, research_progress, prerequisites, unlocks "
        "FROM maya_rp.technologies WHERE session_id=$1 AND LOWER(name) LIKE LOWER($2) LIMIT 1",
        session_id, f"%{tech_name}%")
    return dict(row) if row else None

async def build_lab(colony: str, name: str, field: str, session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    col = await Database.fetchrow("SELECT id, name FROM maya_rp.colonies WHERE session_id=$1 AND LOWER(name) LIKE LOWER($2) LIMIT 1", session_id, f"%{colony}%")
    if not col: return {"error": f"Colony '{colony}' not found"}
    res = await Database.fetchrow("SELECT credits FROM maya_rp.resources WHERE session_id=$1", session_id)
    if not res or res["credits"] < 2000: return {"error": "Need 2000 credits"}
    await Database.execute("UPDATE maya_rp.resources SET credits=credits-2000 WHERE session_id=$1", session_id)
    lab_id = await Database.fetchval(
        "INSERT INTO maya_rp.research_labs (colony_id, name, research_field) VALUES ($1,$2,$3) RETURNING id",
        col["id"], name, field)
    info("tech_tree", f"Built lab '{name}' on {col['name']}")
    return {"lab_id": lab_id, "name": name, "colony": col["name"], "field": field}

async def assign_scientist(character: str, lab_id: int, specialty: str, session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    char = await Database.fetchrow("SELECT id, name FROM maya_rp.characters WHERE session_id=$1 AND LOWER(name) LIKE LOWER($2) LIMIT 1", session_id, f"%{character}%")
    if not char: return {"error": f"Character '{character}' not found"}
    lab = await Database.fetchval(
        # `research_labs` carries no session_id: ownership runs through the colony that hosts it.
        # The bare id check let one campaign put its scientist in another campaign's lab.
        "SELECT rl.id FROM maya_rp.research_labs rl "
        "JOIN maya_rp.colonies col ON rl.colony_id = col.id AND col.session_id=$2 "
        "WHERE rl.id=$1",
        lab_id, session_id)
    if not lab: return {"error": f"Lab #{lab_id} not found in session {session_id}"}
    await Database.execute(
        "INSERT INTO maya_rp.scientist_assignments (character_id, lab_id, specialty, bonus) VALUES ($1,$2,$3,0.25) ON CONFLICT DO NOTHING",
        char["id"], lab_id, specialty)
    return {"character": char["name"], "lab_id": lab_id, "specialty": specialty, "bonus": 0.25}

async def list_labs(session_id: int | None = None) -> list[dict]:
    if session_id is None: session_id = Config.SESSION_ID
    rows = await Database.fetch(
        "SELECT rl.id, rl.name, rl.level, rl.research_field, rl.research_rate, "
        "c.name AS scientist, sa.specialty, sa.bonus "
        "FROM maya_rp.research_labs rl "
        "JOIN maya_rp.colonies col ON rl.colony_id = col.id AND col.session_id=$1 "
        "LEFT JOIN maya_rp.scientist_assignments sa ON sa.lab_id=rl.id "
        "LEFT JOIN maya_rp.characters c ON c.id=sa.character_id "
        "ORDER BY rl.id", session_id)
    return [dict(r) for r in rows]

async def run_tick(session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    try:
        active = await Database.fetch(
            "SELECT id, name, field, tier, research_progress FROM maya_rp.technologies "
            "WHERE session_id=$1 AND researched=false AND research_progress>0 AND research_progress<100 "
            "ORDER BY research_progress ASC", session_id)
        res = await Database.fetchrow("SELECT alloys, credits, tech_score FROM maya_rp.resources WHERE session_id=$1", session_id)
        if not active or not res:
            # Same keys as the full answer: a caller reading `completed` got a KeyError on exactly
            # the session with nothing in progress.
            return {"active": 0, "completed": 0, "active_projects": 0}

        total_rate = await Database.fetchval(
            "SELECT COALESCE(SUM(rl.research_rate + COALESCE(sa.bonus,0.0)),0.0) FROM maya_rp.research_labs rl "
            "JOIN maya_rp.colonies col ON rl.colony_id=col.id AND col.session_id=$1 "
            "LEFT JOIN maya_rp.scientist_assignments sa ON sa.lab_id=rl.id", session_id) or 0
        base = max(1, min(30, (res["tech_score"] or 0) / 5))
        edu_mult = 1.0  # simplified
        total = (base + total_rate) * edu_mult
        completed = 0
        for t in active:
            cost = t["tier"] * 500
            if res["alloys"] < cost or res["credits"] < cost // 2:
                continue
            await Database.execute("UPDATE maya_rp.resources SET alloys=alloys-$1, credits=credits-$2 WHERE session_id=$3", cost, cost // 2, session_id)
            new_progress = min(100, t["research_progress"] + 10 + total)
            complete = new_progress >= 100
            await Database.execute("UPDATE maya_rp.technologies SET research_progress=$1, researched=$2 WHERE id=$3",
                                   new_progress, complete, t["id"])
            if complete:
                await Database.execute("UPDATE maya_rp.resources SET tech_score=tech_score+1 WHERE session_id=$1", session_id)
                completed += 1
        info("tech_tree", f"Tick: {len(active)} active, {completed} completed")
        return {"active": len(active), "completed": completed}
    except Exception as e:
        error("tech_tree", f"tick failed for session {session_id}: {e}")
        return {"error": str(e)}
