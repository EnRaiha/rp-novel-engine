#!/usr/bin/env python3
"""Academy — Ported from Rust academy.rs. Crew training, programs, certifications."""
from __future__ import annotations
import random
from core.db import Database
from core.log import info, error
from core.session import require_session


def _writable_session(session_id: int | None) -> int:
    """Resolve the session for one call and refuse a frozen campaign.

    Sessions 3 and 5 are reference data; a writer that skipped this check mutated them.

    @param session_id - caller's session; `None` resolves through `core.session.require_session`.
    @returns the resolved session id.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    from core.ooc import _refuse_frozen

    sid = require_session(session_id)
    _refuse_frozen(sid)
    return sid


async def run_tick(session_id: int | None = None) -> dict:
    """Advance every enrolment of this campaign and graduate those that reach their target.

    Each graduation runs in one transaction and claims the enrolment first
    (`graduated=false` to `true`), so a second concurrent tick finds no row and awards no second
    certificate, XP grant or prestige point.

    @param session_id - campaign; `None` resolves through `require_session`.
    @returns `{enrolled, graduated}`, or `{error}` when a query raises.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
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
                async with Database.transaction() as conn:
                    claimed = await conn.fetchval(
                        "UPDATE maya_rp.enrolled_crew SET progress=$1, graduated=true "
                        "WHERE id=$2 AND graduated=false RETURNING id", new_progress, e["id"])
                    if claimed is None:
                        continue
                    if not prog:
                        # No program row → nothing to award; park the row instead of
                        # retrying the same graduation every tick.
                        info("academy", f"Enrolment {e['id']} has no program {e['program_id']} — closed")
                        continue
                    cert = prog.get("graduates_receive") or prog["name"]
                    await conn.execute(
                        "INSERT INTO maya_rp.certifications (session_id, crew_id, cert_name, tier, field) "
                        "VALUES ($1,$2,$3,1,$4) ON CONFLICT (crew_id, cert_name) DO NOTHING",
                        session_id, e["crew_id"], cert, prog["field"])
                    await conn.execute("UPDATE maya_rp.crew_roster SET xp=COALESCE(xp,0)+$1 WHERE id=$2 AND session_id=$3", (prog["skill_bonus"] or 0) * 10, e["crew_id"], session_id)
                    await conn.execute("UPDATE maya_rp.academy_campuses SET student_slots_used=GREATEST(student_slots_used-1,0), prestige=COALESCE(prestige,0)+1 WHERE id=$1", e["campus_id"])
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

    The slot is claimed with a guarded UPDATE (`student_slots_used < max_students`) in the same
    transaction as the enrolment insert. The old read-then-increment let two concurrent enrolments
    take the last slot and push the campus past its cap. The crew row is locked so two concurrent
    enrolments of one crew member cannot both pass the duplicate check.

    @param crew_id - roster id in this session.
    @param program_id - `training_programs.id`.
    @param campus_id - `academy_campuses.id`.
    @param session_id - campaign; `None` resolves through `require_session`.
    @returns `{crew_id, program, campus}`, or `{error}`.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
    prog = await Database.fetchrow("SELECT id, name, duration FROM maya_rp.training_programs WHERE id=$1", program_id)
    async with Database.transaction() as conn:
        crew = await conn.fetchrow(
            "SELECT id FROM maya_rp.crew_roster WHERE id=$1 AND session_id=$2 FOR UPDATE", crew_id, session_id)
        if not crew: return {"error": f"Crew {crew_id} not found in session {session_id}"}
        campus = await conn.fetchrow("SELECT id, name, student_slots_used, max_students FROM maya_rp.academy_campuses WHERE id=$1", campus_id)
        if not campus: return {"error": "Campus not found"}
        if not prog: return {"error": "Program not found"}
        # A second enrolment would hold a campus slot and grant a duplicate cert.
        already = await conn.fetchval(
            "SELECT 1 FROM maya_rp.enrolled_crew WHERE crew_id=$1 AND program_id=$2 AND graduated=false",
            crew_id, program_id)
        if already: return {"error": f"Crew {crew_id} is already enrolled in {prog['name']}"}
        slot = await conn.fetchval(
            "UPDATE maya_rp.academy_campuses SET student_slots_used=COALESCE(student_slots_used,0)+1 "
            "WHERE id=$1 AND COALESCE(student_slots_used,0) < COALESCE(max_students,10) RETURNING id",
            campus_id)
        if slot is None: return {"error": "Campus full"}
        await conn.execute("INSERT INTO maya_rp.enrolled_crew (crew_id, program_id, campus_id, progress, target_progress) VALUES ($1,$2,$3,0,$4)", crew_id, program_id, campus_id, prog["duration"] or 100)
    return {"crew_id": crew_id, "program": prog["name"], "campus": campus["name"]}
