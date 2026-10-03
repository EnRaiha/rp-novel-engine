#!/usr/bin/env python3
"""World Reactivity — when player does something, the universe responds."""
from __future__ import annotations
import random
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info, error

async def _game_day(session_id: int) -> int:
    """The session's day, or 1. The COALESCE is inside the SQL, so a session that
    does not exist returns None and `gd + delay` raised TypeError."""
    return await Database.fetchval(
        "SELECT COALESCE(game_day,1) FROM maya_rp.sessions WHERE id=$1", session_id) or 1


async def propagate(event_type: str, details: dict, session_id: int = None) -> list[dict]:
    """Queue the reactions one event provokes. Unknown event types provoke none."""
    if session_id is None: session_id = Config.SESSION_ID
    gd = await _game_day(session_id)
    reactions = []
    if event_type=="territory_conquered":
        sys_name = details.get("system_name","?")
        from_fac = details.get("from_faction","?")
        reactions.append({"rt":"outrage","desc":f"{from_fac} condemns loss of {sys_name}. Retaliation promised.","sf":from_fac,"delay":0})
        neighbors = await Database.fetch("SELECT system_name,controlling_faction FROM maya_rp.territory WHERE session_id=$1 AND controlling_faction!='Setia Empire' ORDER BY RANDOM() LIMIT 2", session_id)
        for n in neighbors:
            reactions.append({"rt":"fear","desc":f"Fall of {sys_name} has {n['controlling_faction']} in {n['system_name']} on edge.","sf":n["controlling_faction"],"delay":random.randint(1,3)})
    elif event_type=="massacre":
        cnt = details.get("count",1)
        fac = details.get("faction","?")
        loc = details.get("location","?")
        reactions.append({"rt":"horror","desc":f"News of {cnt} {fac} killed at {loc} leaks. Even allies are uncomfortable.","sf":"all","delay":random.randint(1,4)})
        if cnt>=10:
            reactions.append({"rt":"recruitment","desc":f"{fac} uses the massacre for recruitment. Moderates fall silent.","sf":fac,"delay":random.randint(3,7)})
    elif event_type=="major_treaty":
        fac = details.get("ally_faction","?")
        reactions.append({"rt":"diplomatic","desc":f"Treaty with {fac} sends ripples. Other factions reassess.","sf":"all","delay":random.randint(2,5)})
    for r in reactions:
        await Database.execute("INSERT INTO maya_rp.world_reactions(session_id,event_type,reaction_type,description,source_faction,surfaces_at_game_day,surfaced) VALUES($1,$2,$3,$4,$5,$6,false)", session_id,event_type,r["rt"],r["desc"],r["sf"],gd+r["delay"])
    return reactions

async def get_due(session_id: int = None) -> list[dict]:
    if session_id is None: session_id = Config.SESSION_ID
    gd = await _game_day(session_id)
    rows = await Database.fetch("SELECT id,reaction_type,description,source_faction FROM maya_rp.world_reactions WHERE session_id=$1 AND surfaced=false AND surfaces_at_game_day<=$2 ORDER BY surfaces_at_game_day ASC LIMIT 3", session_id,gd)
    return [dict(r) for r in rows]

async def surface(reaction_id: int, session_id: int = None) -> bool:
    """Mark one reaction surfaced. Reports whether it matched.

    It returned None either way, so a caller could not tell a surfaced reaction
    from a miss.
    """
    if session_id is None: session_id = Config.SESSION_ID
    tag = await Database.execute(
        "UPDATE maya_rp.world_reactions SET surfaced=true WHERE id=$1 AND session_id=$2",
        reaction_id, session_id)
    surfaced = not (isinstance(tag, str) and tag.split()[-1:] == ["0"])
    if not surfaced:
        info("world_react", f"reaction {reaction_id} is not in session {session_id} — nothing surfaced")
    return surfaced


async def run_tick(session_id: int = None) -> dict:
    """Count the reactions whose day has come.

    Deliberately does NOT surface them. The consumer is
    `core/master_briefing.get_due`, and a tick that marked them surfaced first
    would leave the briefing with nothing to show. That the briefing never calls
    `surface` either is reported to the lead: with no caller, the same three
    reactions are due in every briefing.
    """
    if session_id is None: session_id = Config.SESSION_ID
    due = await get_due(session_id)
    return {"due_reactions":len(due)}
