#!/usr/bin/env python3
"""Dramatic Structure — story arcs across sessions. Setup → Rising → Crisis → Climax → Falling → Resolution."""
from __future__ import annotations
import random
from typing import Any
from core.db import Database
from core.session import require_session
from core.log import info

PHASES = {"setup":{"sessions":(1,3),"tension":(1,3),"intro":["threat","key_npc","stakes"],"avoid":["climax","major_death"],"instruction":"INTRODUCE. Plant seeds. Make stakes clear.","feel":"The calm before. Something is coming."},
          "rising_action":{"sessions":(3,8),"tension":(3,6),"intro":["complications","obstacles","reversals"],"avoid":["final_confrontation","resolution"],"instruction":"ESCALATE. Make victories costly.","feel":"Momentum building. Shape of conflict becoming clear."},
          "crisis_point":{"sessions":(1,1),"tension":(8,10),"intro":["major_setback","betrayal","loss"],"avoid":["easy_solutions","new_subplots"],"instruction":"BREAK IT. Dark night of the soul.","feel":"Everything falls apart."},
          "climax":{"sessions":(1,2),"tension":(9,10),"intro":["final_confrontation","ultimate_choice"],"avoid":["new_mysteries","distractions"],"instruction":"CONFRONT. Everything built to this moment.","feel":"No going back."},
          "falling_action":{"sessions":(1,1),"tension":(4,6),"intro":["aftermath","casualty_count","processing"],"avoid":["new_conflicts","time_skips"],"instruction":"BREATHE. Let the weight land.","feel":"The quiet after the storm."},
          "resolution":{"sessions":(1,2),"tension":(1,3),"intro":["new_status_quo","changed_relationships","consequences"],"avoid":["immediate_new_threat"],"instruction":"CLOSE. Show how things changed.","feel":"A new equilibrium."}}
PHASE_ORDER = list(PHASES.keys())

async def get_current_arc(session_id: int = None) -> dict:
    if session_id is None: session_id = require_session(None)
    arc = await Database.fetchrow("SELECT id,title,theme,phase,sessions_in_phase,total_sessions,central_conflict,stakes_description FROM maya_rp.story_arcs WHERE session_id=$1 AND status='active' ORDER BY id DESC LIMIT 1", session_id)
    if not arc:
        threats = await Database.fetch("SELECT hook_type as title,status FROM maya_rp.narrative_hooks WHERE session_id=$1 AND status='active'", session_id)
        wars = await Database.fetch("SELECT opponent_faction FROM maya_rp.wars WHERE session_id=$1 AND status='active'", session_id)
        if wars: title,theme,conflict,stakes = f"The {wars[0]['opponent_faction']} War","war","Total conflict","Survival of TKG Council"
        elif threats: title,theme,conflict,stakes = threats[0]["title"],"crisis",threats[0]["title"],"Consequences will cascade"
        else:
            arcs = [("The Silent Advance","exploration","Something stirs in uncharted space.","What we find could destroy us."),("Fractured Loyalties","political","The council is splitting.","Civil war from within."),("The Price of Power","moral","War choices have consequences.","Brutality score rising."),("Ghosts of the Fall","mystery","Something from before the Fall is waking.","Ancient technology. Forgotten enemies.")]
            title,theme,conflict,stakes = random.choice(arcs)
        await Database.execute("INSERT INTO maya_rp.story_arcs(session_id,title,theme,central_conflict,stakes_description,phase,sessions_in_phase,total_sessions,status) VALUES($1,$2,$3,$4,$5,'setup',0,1,'active')", session_id,title,theme,conflict,stakes)
        info("dramatic", f"New arc: {title}")
        return await get_current_arc(session_id)
    pc = PHASES.get(arc["phase"],PHASES["setup"])
    return {"arc_id":arc["id"],"title":arc["title"],"theme":arc["theme"],"phase":arc["phase"],"phase_config":pc,"sessions_in_phase":arc["sessions_in_phase"],"total_sessions":arc["total_sessions"],"conflict":arc["central_conflict"],"stakes":arc["stakes_description"],"instruction":pc["instruction"],"feel":pc["feel"],"should_introduce":pc["intro"],"should_avoid":pc["avoid"]}

async def advance_phase(session_id: int = None) -> dict:
    if session_id is None: session_id = require_session(None)
    arc = await Database.fetchrow("SELECT id,phase,sessions_in_phase FROM maya_rp.story_arcs WHERE session_id=$1 AND status='active' ORDER BY id DESC LIMIT 1", session_id)
    if not arc: return {"error":"No active arc"}
    # `PHASE_ORDER.index` raised ValueError on a phase this table does not hold, while
    # `get_current_arc` twenty lines up resolves the same value to `setup`. One value, two answers;
    # the refusal names it now, in the shape this function already uses for a missing arc.
    if arc["phase"] not in PHASE_ORDER:
        return {"error": f"unknown arc phase {arc['phase']!r}; known phases: {PHASE_ORDER}"}
    ci = PHASE_ORDER.index(arc["phase"])
    if ci >= len(PHASE_ORDER)-1:
        await Database.execute("UPDATE maya_rp.story_arcs SET status='completed' WHERE id=$1 AND session_id=$2", arc["id"], session_id)
        return {"completed":True}
    np = PHASE_ORDER[ci+1]
    await Database.execute("UPDATE maya_rp.story_arcs SET phase=$1,sessions_in_phase=0 WHERE id=$2 AND session_id=$3", np, arc["id"], session_id)
    info("dramatic", f"Phase: {arc['phase']} → {np}")
    return {"old_phase":arc["phase"],"new_phase":np}

async def session_start(session_id: int = None) -> dict | None:
    if session_id is None: session_id = require_session(None)
    arc = await get_current_arc(session_id)
    # `PHASES[arc["phase"]]` raised KeyError for the same unknown value that `get_current_arc` had
    # already resolved to `setup` in `phase_config`, so the third reading agreed with the first.
    pc = arc["phase_config"]
    # `sessions_in_phase` and `total_sessions` are nullable, and `NULL + 1` is NULL in SQL: one such
    # row kept the counter NULL for ever, so the phase could never advance and the read below raised
    # on every later session start.
    await Database.execute("UPDATE maya_rp.story_arcs SET sessions_in_phase=COALESCE(sessions_in_phase,0)+1,total_sessions=COALESCE(total_sessions,0)+1 WHERE id=$1 AND session_id=$2", arc["arc_id"], session_id)
    new_count = (arc["sessions_in_phase"] or 0) + 1  # post-increment value
    if arc["phase"]=="crisis_point" and new_count>=1:
        return await advance_phase(session_id)
    if new_count > pc["sessions"][1]:
        return await advance_phase(session_id)
    return None

def get_prompt(arc: dict) -> str:
    lines = [f"[STORY ARC: {arc['title']}]",f"Phase: {arc['phase'].replace('_',' ').title()} ({arc['sessions_in_phase']} sessions)",f"Theme: {arc.get('theme','?')}",f"Conflict: {arc['conflict']}",f"Stakes: {arc['stakes']}","",f"GM Direction: {arc['instruction']}",f"Feel: {arc['feel']}"]
    if arc.get('should_introduce'): lines.append(f"Introduce: {', '.join(arc['should_introduce'])}")
    if arc.get('should_avoid'): lines.append(f"Avoid: {', '.join(arc['should_avoid'])}")
    return '\n'.join(lines)
