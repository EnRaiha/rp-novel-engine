#!/usr/bin/env python3
"""Ideology Engine — what kind of society is the fleet? Dictatorship? Utopia? Pirate confederacy?"""
from __future__ import annotations
import json
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info

IDEOS = {
    "military_dictatorship":{"values":["order","strength","hierarchy","duty"],"bonuses":{"combat_power":1.2},"penalties":{"research":0.8},"recruits":"soldiers, ex-military","tone":"The fleet is a sword. Sharp, rigid, unforgiving."},
    "pirate_confederacy":{"values":["freedom","profit","survival"],"bonuses":{"trade":1.3},"penalties":{"diplomacy":-20},"recruits":"outlaws, smugglers","tone":"The fleet is a pack of wolves. Free, dangerous."},
    "technocratic_utopia":{"values":["knowledge","progress","efficiency"],"bonuses":{"research":1.5},"penalties":{"morale":-10},"recruits":"scientists, engineers","tone":"The fleet is a laboratory. Cold, bright, curious."},
    "religious_fundamentalism":{"values":["faith","purity","destiny"],"bonuses":{"fanaticism":1.5},"penalties":{"science":0.6},"recruits":"believers, zealots","tone":"The fleet is a crusade. Absolute."},
    "benevolent_democracy":{"values":["freedom","equality","justice"],"bonuses":{"diplomacy":15},"penalties":{"military":0.8},"recruits":"refugees, idealists","tone":"The fleet is a city. Messy, alive."},
}

async def get(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    state = await Database.fetchrow("SELECT ideology,scores_jsonb FROM maya_rp.ideology_state WHERE session_id=$1", session_id)
    if state: return {"ideology":state["ideology"],"scores":state.get("scores_jsonb",{}),**IDEOS.get(state["ideology"],IDEOS["benevolent_democracy"])}
    return await _recalculate(session_id)

async def _recalculate(session_id: int) -> dict:
    scores = {k:0 for k in IDEOS}
    actions = await Database.fetch("SELECT action_category,SUM(count) as t FROM maya_rp.player_action_log WHERE session_id=$1 GROUP BY action_category", session_id)
    dist = {a["action_category"]:a["t"] for a in actions}
    total = sum(dist.values()) or 1
    if dist.get("combat",0)/total>0.4: scores["military_dictatorship"]+=3
    if dist.get("cruelty",0)>5: scores["military_dictatorship"]+=2
    if dist.get("intrigue",0)/total>0.3: scores["pirate_confederacy"]+=3
    if dist.get("building",0)/total>0.3: scores["technocratic_utopia"]+=3
    if dist.get("mercy",0)>5: scores["benevolent_democracy"]+=3
    if dist.get("diplomacy",0)/total>0.3: scores["benevolent_democracy"]+=2
    winner = max(scores, key=scores.get)
    await Database.execute("INSERT INTO maya_rp.ideology_state(session_id,ideology,scores_jsonb) VALUES($1,$2,$3) ON CONFLICT(session_id)DO UPDATE SET ideology=$2,scores_jsonb=$3", session_id,winner,json.dumps(scores))
    cfg = IDEOS[winner]
    return {"ideology":winner,"scores":scores,**cfg}

async def get_prompt(session_id: int = None) -> str:
    ideo = await get(session_id)
    lines=[f"[SOCIETY: {ideo['ideology'].replace('_',' ').title()}]",f"Values: {', '.join(ideo['values'])}",f"Tone: {ideo['tone']}",f"Recruits: {ideo['recruits']}"]
    return "\n".join(lines)

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    try:
        i = await get(session_id)
        return {"ideology":i["ideology"]}
    except Exception as e:
        info("ideology", f"Error: {e}")
        return {"error": str(e)}
