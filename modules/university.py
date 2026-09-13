#!/usr/bin/env python3
"""University — campus graduation mechanics (expanded 2026-08-14).

Previous version only counted projects. Now: 37 university campuses + 2
research labs generate a science-rate multiplier and graduate scientists
each cycle, boosting tech_score. Research speed bonus is materialized as
resources.tech_score growth — the research module already scales off it.
"""
from __future__ import annotations
import json
from core.db import Database
from core.config import Config
from core.log import info

async def run_tick(session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    try:
        total = await Database.fetchval("SELECT COUNT(*) FROM maya_rp.research_projects") or 0
        finished = await Database.fetchval("SELECT COUNT(*) FROM maya_rp.research_projects WHERE unlocked=true") or 0
        # Campuses link via territory_id (or colony_id → colonies); labs via colony_id.
        campuses = await Database.fetchval(
            """SELECT COUNT(*) FROM maya_rp.university_campuses uc
               WHERE uc.territory_id IN (SELECT id FROM maya_rp.territory WHERE session_id=$1)
                  OR uc.colony_id IN (SELECT id FROM maya_rp.colonies WHERE session_id=$1)""",
            session_id) or 0
        labs = await Database.fetchval(
            """SELECT COUNT(*) FROM maya_rp.research_labs rl
               JOIN maya_rp.colonies c ON c.id = rl.colony_id
               WHERE c.session_id=$1""", session_id) or 0
        rate = await Database.fetchval(
            """SELECT COALESCE(SUM(uc.research_rate),0) FROM maya_rp.university_campuses uc
               WHERE uc.territory_id IN (SELECT id FROM maya_rp.territory WHERE session_id=$1)
                  OR uc.colony_id IN (SELECT id FROM maya_rp.colonies WHERE session_id=$1)""",
            session_id) or 0
        # Graduation cycle: every 30 game days, campuses graduate scientists.
        gd = await Database.fetchval(
            "SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id) or 0
        graduated = 0
        if campuses and gd % 30 == 0:
            graduated = int(campuses * 1.5 + labs)
            await Database.execute(
                "UPDATE maya_rp.resources SET tech_score=COALESCE(tech_score,0)+$1 "
                "WHERE session_id=$2", graduated, session_id)
            await Database.execute(
                "INSERT INTO maya_rp.events (session_id, happened_at, event_type, title, description, tags, importance) "
                "VALUES ($1, NOW(), 'science', $2, $3, $4, 3)",
                session_id, "University Graduation",
                f"{graduated} scientists graduated across {campuses} campuses ({labs} labs) — tech_score +{graduated}",
                json.dumps(["science", "university"]))
        info("university", f"Tick: {campuses} campuses rate={rate:.2f} · "
             f"{total} projects ({finished} done) · graduated={graduated}")
        return {"total": total, "finished": finished, "campuses": campuses,
                "labs": labs, "research_rate": round(rate, 2), "graduated": graduated}
    except Exception as e:
        info("university", f"Error: {e}")
        return {"error": str(e)}
