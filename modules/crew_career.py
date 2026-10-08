#!/usr/bin/env python3
"""Crew Career — XP, level up, skills, retirement. XCOM-style progression."""
from __future__ import annotations
import random
from typing import Any
from core.db import Database
from core.log import error, info
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

SKILLS = {"combat":["gunnery","tactics","melee","boarding"],"engineering":["reactor","ftl","weapons","hull"],"science":["xenobiology","astrometrics","quantum","archaeology"],"command":["leadership","logistics","morale","strategy"],"medical":["surgery","pharma","psychology","xeno"]}
ALL_SKILLS = [s for sub in SKILLS.values() for s in sub]
RANKS = ["Crewman","Specialist","Veteran","Expert","Officer","Commander","Legend"]

async def award(crew_id: int, xp: int, source: str, session_id: int = None) -> dict:
    """Award XP to one crew member of this campaign.

    The award is scoped, and so is the log entry: an XP write for a crew member
    of another campaign matched no roster row and still wrote a log row, so the
    ledger recorded an award nobody received. The follow-up read and the level-up
    write carried no session either.

    The XP write returns the new row (`RETURNING`), which also locks it, and the XP write, the log
    row, the level-up and the skill upsert share one transaction. Two concurrent awards each read the
    pre-level XP and both levelled, and an error between the XP write and the level-up left XP banked
    past the threshold.

    @param crew_id - `crew_roster.id` in this session.
    @param xp - XP to add.
    @param source - label stored in `crew_xp_log`.
    @param session_id - campaign; `None` resolves through `require_session`.
    @returns `{leveled, ...}`; `{leveled: False, error}` when the crew is not in this session.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
    async with Database.transaction() as conn:
        cr = await conn.fetchrow(
            "UPDATE maya_rp.crew_roster SET xp=COALESCE(xp,0)+$1 WHERE id=$2 AND session_id=$3 "
            "RETURNING xp, level, role", xp, crew_id, session_id)
        if cr is None:
            info("crew_career", f"crew {crew_id} is not in session {session_id} — "
                                f"{xp} XP NOT awarded, nothing logged")
            return {"leveled": False, "error": f"Crew {crew_id} not in session {session_id}"}
        await conn.execute("INSERT INTO maya_rp.crew_xp_log(crew_id,session_id,amount,source) VALUES($1,$2,$3,$4)", crew_id,session_id,xp,source)
        needed = (cr["level"] or 1) * 100
        if (cr["xp"] or 0) >= needed:
            nl = (cr["level"] or 1) + 1
            nr = RANKS[min(nl-1, len(RANKS)-1)]
            ns = random.choice(ALL_SKILLS)
            await conn.execute(
                "UPDATE maya_rp.crew_roster SET level=$1,rank=$2,xp=COALESCE(xp,0)-$3 "
                "WHERE id=$4 AND session_id=$5",
                nl, nr, needed, crew_id, session_id)
            await conn.execute("INSERT INTO maya_rp.crew_skills(crew_id,session_id,skill_name,proficiency) VALUES($1,$2,$3,1) ON CONFLICT(crew_id,skill_name)DO UPDATE SET proficiency=crew_skills.proficiency+1", crew_id,session_id,ns)
            return {"leveled":True,"new_rank":nr,"skill":ns}
    return {"leveled":False}

async def run_tick(session_id: int | None = None) -> dict:
    """Backfill NULL level and rank. @raises core.ooc.FrozenSession - the campaign is frozen."""
    session_id = _writable_session(session_id)
    try:
        await Database.execute("UPDATE maya_rp.crew_roster SET level=COALESCE(level,1),rank=COALESCE(rank,'Crewman') WHERE session_id=$1 AND level IS NULL", session_id)
    except Exception as e:
        error("crew_career", f"rank backfill failed: {e}")
    return {"processed":True}


# ═══════════════════════════════════════════════════════════════
# NOVEL ADAPTATION — CREW PROMOTION + SPECIALIZATION (novel bab 171, 1252)
# "Oops! We are short of talent" — bottleneck bukan kapal, tapi orang.
# Artisan/planner/navigator specialization + promotion ranks.
# ═══════════════════════════════════════════════════════════════

SPECIALIZATIONS = ["artisan", "planner", "navigator", "officer", "engineer"]


async def assign_specialization(crew_id: int, specialization: str, session_id: int = None) -> dict:
    """Set one crew member's specialization. Reports whether a row matched.

    It returned success even when the id was not in this session, so the caller
    was told a specialization had been assigned that was never written.

    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
    if specialization not in SPECIALIZATIONS:
        return {"error": f"Specialization mesti salah satu: {SPECIALIZATIONS}"}
    tag = await Database.execute(
        "UPDATE maya_rp.crew_roster SET specialization=$1 WHERE id=$2 AND session_id=$3",
        specialization, crew_id, session_id)
    if isinstance(tag, str) and tag.split()[-1:] == ["0"]:
        return {"error": f"Crew {crew_id} not in session {session_id}"}
    return {"crew_id": crew_id, "specialization": specialization}


async def promote_crew(crew_id: int, session_id: int = None) -> dict:
    """Manual promotion check — naik rank bila XP cukup, buka skill specialization.

    The roster row is locked for the read-compute-write and the level, skills and event share one
    transaction; two concurrent promotions each read the pre-level XP and both levelled.

    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
    async with Database.transaction() as conn:
        cr = await conn.fetchrow(
            "SELECT id, xp, level, rank, specialization FROM maya_rp.crew_roster "
            "WHERE id=$1 AND session_id=$2 FOR UPDATE",
            crew_id, session_id)
        if not cr:
            return {"error": "Crew not found"}
        needed = (cr["level"] or 1) * 100
        if (cr["xp"] or 0) < needed:
            return {"leveled": False, "need": needed - (cr["xp"] or 0)}
        nl = (cr["level"] or 1) + 1
        nr = RANKS[min(nl - 1, len(RANKS) - 1)]
        # Specialization skill unlock: artisan → weapons/hull, planner → logistics, navigator → ftl
        spec_skills = {"artisan": ["weapons", "hull"], "planner": ["logistics", "strategy"],
                       "navigator": ["ftl"], "officer": ["leadership"], "engineer": ["reactor", "ftl"]}
        skills = spec_skills.get(cr["specialization"] or "officer", ["tactics"])
        await conn.execute(
            "UPDATE maya_rp.crew_roster SET level=$1, rank=$2, xp=COALESCE(xp,0)-$3, "
            "promotion_source='novel_promotion' WHERE id=$4 AND session_id=$5",
            nl, nr, needed, crew_id, session_id)
        for sk in skills:
            await conn.execute(
                "INSERT INTO maya_rp.crew_skills (crew_id, session_id, skill_name, proficiency) "
                "VALUES ($1, $2, $3, 1) ON CONFLICT (crew_id, skill_name) DO UPDATE SET proficiency=crew_skills.proficiency+1",
                crew_id, session_id, sk)
        await conn.execute(
            "INSERT INTO maya_rp.events (session_id, event_type, title, description, importance) "
            "VALUES ($1, 'career', $2, $3, 2)",
            session_id, f"Crew Promoted: {cr['id']}",
            f"Rank {cr['rank']} → {nr} (Level {nl}). Skills: {', '.join(skills)}. Specialization: {cr['specialization'] or 'officer'}")
    return {"leveled": True, "new_rank": nr, "level": nl, "skills": skills}


async def talent_shortage(session_id: int = None) -> dict:
    """Novel bab 171 — talent shortage arc: kalau crew < kapal aktif, bottleneck.

    Read-only, so a frozen campaign may call it.
    """
    session_id = require_session(session_id)
    crew = await Database.fetchval("SELECT COUNT(*) FROM maya_rp.crew_roster WHERE session_id=$1 AND status='active'", session_id)
    ships = await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.ships WHERE session_id=$1 AND status='active' AND ship_type NOT IN ('light_dockyard','heavy_shipyard')",
        session_id)
    shortage = (ships or 0) - (crew or 0)
    return {"crew": crew, "ships": ships, "shortage": max(0, shortage),
            "status": "SHORTAGE" if shortage > 0 else "balanced"}
