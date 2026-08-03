#!/usr/bin/env python3
"""Background Geopolitics — factions fight/trade with each other off-screen."""
from __future__ import annotations
import json, random
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    factions = await Database.fetch("SELECT id,name,standing,economic_strength,pirate_fleet_power,reputation FROM maya_rp.factions WHERE session_id=$1 AND name!='Setia Empire'", session_id)
    events = 0
    for i, fa in enumerate(factions):
        for j, fb in enumerate(factions):
            if i >= j: continue
            if random.random() > 0.1: continue
            rel = await Database.fetchrow("SELECT standing FROM maya_rp.faction_relations WHERE session_id=$1 AND faction_a=$2 AND faction_b=$3", session_id,fa["id"],fb["id"])
            stand = rel["standing"] if rel else "neutral"
            desc = ""
            imp = 1
            if stand == "hostile" and random.random() < 0.3:
                winner = fa if random.random() > 0.5 else fb
                losr = fb if winner["id"]==fa["id"] else fa
                desc = f"Intelligence: {winner['name']} forces engaged {losr['name']} in a border skirmish. {winner['name']} claims victory."
                imp = 2
            elif stand == "neutral" and random.random() < 0.4:
                desc = f"Trade convoy spotted between {fa['name']} and {fb['name']} territory."
            elif stand == "ally":
                desc = f"Joint fleet maneuvers detected: {fa['name']} & {fb['name']}."
            if desc:
                await Database.execute("INSERT INTO maya_rp.events(session_id,happened_at,event_type,title,description,tags,importance) VALUES($1,NOW(),'geopolitics',$2,$3,$4,$5)", session_id,desc[:80],desc,'["geopolitics","background"]',imp)
                events += 1
    return {"events_generated":events}
