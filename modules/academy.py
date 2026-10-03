#!/usr/bin/env python3
"""Academy — Ported from Rust academy.rs. Crew training, programs, certifications."""
from __future__ import annotations
import random
from core.db import Database
from core.config import Config
from core.log import info, error

async def run_tick(session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    try:
        enrolled = await Database.fetch(
            "SELECT ec.id, ec.crew_id, ec.program_id, ec.campus_id, ec.progress, ec.target_progress "
            "FROM maya_rp.enrolled_crew ec JOIN maya_rp.crew_roster cr ON ec.crew_id=cr.id "
            "WHERE cr.session_id=$1 AND ec.graduated=false", session_id)
        graduated = 0
        for e in enrolled:
            advance = random.randint(20, 30)
            new_progress = (e["progress"] or 0) + advance
            if new_progress >= (e["target_progress"] or 100):
                prog = await Database.fetchrow("SELECT name, field, skill_bonus, graduates_receive FROM maya_rp.training_programs WHERE id=$1", e["program_id"])
                if not prog:
                    # No program row → nothing to award; park the row instead of
                    # retrying the same graduation every tick.
                    await Database.execute(
                        "UPDATE maya_rp.enrolled_crew SET graduated=true WHERE id=$1", e["id"])
                    info("academy", f"Enrolment {e['id']} has no program {e['program_id']} — closed")
                    continue
                cert = prog.get("graduates_receive") or prog["name"]
                await Database.execute(
                    "INSERT INTO maya_rp.certifications (session_id, crew_id, cert_name, tier, field) "
                    "VALUES ($1,$2,$3,1,$4) ON CONFLICT (crew_id, cert_name) DO NOTHING",
                    session_id, e["crew_id"], cert, prog["field"])
                await Database.execute("UPDATE maya_rp.crew_roster SET xp=COALESCE(xp,0)+$1 WHERE id=$2 AND session_id=$3", (prog["skill_bonus"] or 0) * 10, e["crew_id"], session_id)
                await Database.execute("UPDATE maya_rp.academy_campuses SET student_slots_used=GREATEST(student_slots_used-1,0), prestige=COALESCE(prestige,0)+1 WHERE id=$1", e["campus_id"])
                await Database.execute("UPDATE maya_rp.enrolled_crew SET progress=$1, graduated=true WHERE id=$2", new_progress, e["id"])
                graduated += 1
            else:
                await Database.execute("UPDATE maya_rp.enrolled_crew SET progress=$1 WHERE id=$2", new_progress, e["id"])
        info("academy", f"Tick: {len(enrolled)} enrolled, {graduated} graduated")
        return {"enrolled": len(enrolled), "graduated": graduated}
    except Exception as e:
        error("academy", f"tick error: {e}")
        return {"error": str(e)}

async def enroll_crew(crew_id: int, program_id: int, campus_id: int, session_id: int | None = None) -> dict:
    """Enrol one crew member in a program at a campus.

    The crew is checked against this session: `enrolled_crew` carries no session
    of its own, so an unqualified crew id enrolled the other campaign's roster
    into this one's academy. Campuses and programs are global catalogues and are
    not session-scoped.
    """
    if session_id is None: session_id = Config.SESSION_ID
    crew = await Database.fetchrow(
        "SELECT id FROM maya_rp.crew_roster WHERE id=$1 AND session_id=$2", crew_id, session_id)
    if not crew: return {"error": f"Crew {crew_id} not found in session {session_id}"}
    campus = await Database.fetchrow("SELECT id, name, student_slots_used, max_students FROM maya_rp.academy_campuses WHERE id=$1", campus_id)
    if not campus: return {"error": "Campus not found"}
    if (campus["student_slots_used"] or 0) >= (campus["max_students"] or 10): return {"error": "Campus full"}
    prog = await Database.fetchrow("SELECT id, name, duration FROM maya_rp.training_programs WHERE id=$1", program_id)
    if not prog: return {"error": "Program not found"}
    # A second enrolment would hold a campus slot and grant a duplicate cert.
    already = await Database.fetchval(
        "SELECT 1 FROM maya_rp.enrolled_crew WHERE crew_id=$1 AND program_id=$2 AND graduated=false",
        crew_id, program_id)
    if already: return {"error": f"Crew {crew_id} is already enrolled in {prog['name']}"}
    await Database.execute("INSERT INTO maya_rp.enrolled_crew (crew_id, program_id, campus_id, progress, target_progress) VALUES ($1,$2,$3,0,$4)", crew_id, program_id, campus_id, prog["duration"] or 100)
    await Database.execute("UPDATE maya_rp.academy_campuses SET student_slots_used=COALESCE(student_slots_used,0)+1 WHERE id=$1", campus_id)
    return {"crew_id": crew_id, "program": prog["name"], "campus": campus["name"]}
