#!/usr/bin/env python3
"""Crew Career — XP, level up, skills, retirement. XCOM-style progression."""
from __future__ import annotations
import random
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info

SKILLS = {"combat":["gunnery","tactics","melee","boarding"],"engineering":["reactor","ftl","weapons","hull"],"science":["xenobiology","astrometrics","quantum","archaeology"],"command":["leadership","logistics","morale","strategy"],"medical":["surgery","pharma","psychology","xeno"]}
ALL_SKILLS = [s for sub in SKILLS.values() for s in sub]
RANKS = ["Crewman","Specialist","Veteran","Expert","Officer","Commander","Legend"]

async def award(crew_id: int, xp: int, source: str, session_id: int = None):
    if session_id is None: session_id = Config.SESSION_ID
    await Database.execute("UPDATE maya_rp.crew_roster SET xp=COALESCE(xp,0)+$1 WHERE id=$2 AND session_id=$3", xp,crew_id,session_id)
    await Database.execute("INSERT INTO maya_rp.crew_xp_log(crew_id,session_id,amount,source) VALUES($1,$2,$3,$4)", crew_id,session_id,xp,source)
    cr = await Database.fetchrow("SELECT xp,level,role FROM maya_rp.crew_roster WHERE id=$1", crew_id)
    if not cr: return
    needed = (cr["level"] or 1) * 100
    if (cr["xp"] or 0) >= needed:
        nl = (cr["level"] or 1) + 1
        nr = RANKS[min(nl-1, len(RANKS)-1)]
        ns = random.choice(ALL_SKILLS)
        await Database.execute("UPDATE maya_rp.crew_roster SET level=$1,rank=$2,xp=COALESCE(xp,0)-$3 WHERE id=$4", nl,nr,needed,crew_id)
        await Database.execute("INSERT INTO maya_rp.crew_skills(crew_id,session_id,skill_name,proficiency) VALUES($1,$2,$3,1) ON CONFLICT(crew_id,skill_name)DO UPDATE SET proficiency=crew_skills.proficiency+1", crew_id,session_id,ns)
        return {"leveled":True,"new_rank":nr,"skill":ns}
    return {"leveled":False}

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    gd = await Database.fetchval("SELECT COALESCE(game_day,1) FROM maya_rp.sessions WHERE id=$1", session_id)
    try:
        await Database.execute("UPDATE maya_rp.crew_roster SET level=COALESCE(level,1),rank=COALESCE(rank,'Crewman') WHERE session_id=$1 AND level IS NULL", session_id)
    except Exception:
        pass
    return {"processed":True}
