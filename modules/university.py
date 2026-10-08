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
from core.log import error, info

async def run_tick(session_id: int | None = None) -> dict:
    """Count campuses and labs, and graduate scientists on every 30th game day.

    The session and freeze check resolve before the `try`: a frozen campaign raises instead of
    being reported as a tick error. A read or write error inside is logged at error level and
    returned as `{"error"}`; it was logged at info, below the level anyone watches.

    @param session_id - campaign; `None` resolves through `require_session`.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    from core.ooc import _refuse_frozen
    from core.session import require_session

    session_id = require_session(session_id)
    _refuse_frozen(session_id)
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
        # Day 0 (or a session with no day) is not a cycle: `0 % 30 == 0` graduated scientists
        # the moment a campaign started.
        if campuses and gd > 0 and gd % 30 == 0:
            # The cycle is per game day, and a manual tick plus the orchestrator tick
            # on day 30 used to graduate twice. The day is recorded in the event tags
            # (the events table carries no game_day column) and checked first. The check, the
            # tech_score credit and the event commit together under a lock on the resources row,
            # so two ticks cannot both pass the check.
            marker = json.dumps([f"day:{gd}"])
            async with Database.transaction() as conn:
                await conn.fetchrow(
                    "SELECT session_id FROM maya_rp.resources WHERE session_id=$1 FOR UPDATE", session_id)
                already = await conn.fetchval(
                    "SELECT COUNT(*) FROM maya_rp.events WHERE session_id=$1 "
                    "AND title='University Graduation' AND tags @> $2::jsonb",
                    session_id, marker) or 0
                if already:
                    info("university", f"Graduation for day {gd} is already recorded; nothing added")
                else:
                    graduated = int(campuses * 1.5 + labs)
                    row = await conn.fetchrow(
                        "UPDATE maya_rp.resources SET tech_score=COALESCE(tech_score,0)+$1 "
                        "WHERE session_id=$2 RETURNING tech_score", graduated, session_id)
                    if row is None:
                        # A session without a resources row graduated on paper only.
                        info("university",
                             f"No resources row for session {session_id}: tech_score +{graduated} not applied")
                    await conn.execute(
                        "INSERT INTO maya_rp.events (session_id, happened_at, event_type, title, description, tags, importance) "
                        "VALUES ($1, NOW(), 'science', $2, $3, $4::jsonb, 3)",
                        session_id, "University Graduation",
                        f"{graduated} scientists graduated across {campuses} campuses ({labs} labs) — tech_score +{graduated}",
                        json.dumps(["science", "university", f"day:{gd}"]))
        info("university", f"Tick: {campuses} campuses rate={rate:.2f} · "
             f"{total} projects ({finished} done) · graduated={graduated}")
        return {"total": total, "finished": finished, "campuses": campuses,
                "labs": labs, "research_rate": round(rate, 2), "graduated": graduated}
    except Exception as e:
        error("university", f"tick error: {e}")
        return {"error": str(e)}
