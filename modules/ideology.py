#!/usr/bin/env python3
"""Ideology Engine — what kind of society is the fleet? Dictatorship? Utopia? Pirate confederacy?"""
from __future__ import annotations
import json
from typing import Any
from core.db import Database
from core.log import info, error
from core.session import require_session

IDEOS = {
    "military_dictatorship":{"values":["order","strength","hierarchy","duty"],"bonuses":{"combat_power":1.2},"penalties":{"research":0.8},"recruits":"soldiers, ex-military","tone":"The fleet is a sword. Sharp, rigid, unforgiving."},
    "pirate_confederacy":{"values":["freedom","profit","survival"],"bonuses":{"trade":1.3},"penalties":{"diplomacy":-20},"recruits":"outlaws, smugglers","tone":"The fleet is a pack of wolves. Free, dangerous."},
    "technocratic_utopia":{"values":["knowledge","progress","efficiency"],"bonuses":{"research":1.5},"penalties":{"morale":-10},"recruits":"scientists, engineers","tone":"The fleet is a laboratory. Cold, bright, curious."},
    "religious_fundamentalism":{"values":["faith","purity","destiny"],"bonuses":{"fanaticism":1.5},"penalties":{"science":0.6},"recruits":"believers, zealots","tone":"The fleet is a crusade. Absolute."},
    "benevolent_democracy":{"values":["freedom","equality","justice"],"bonuses":{"diplomacy":15},"penalties":{"military":0.8},"recruits":"refugees, idealists","tone":"The fleet is a city. Messy, alive."},
}

# A campaign with no evidence is not a dictatorship. `max(scores, key=scores.get)`
# broke a five-way tie at zero by dictionary order, so the first key won and the
# guess was persisted: BOTH live sessions carry `military_dictatorship` with
# every score 0 and an empty `player_action_log`. No evidence now means
# undetermined, and nothing is written.
UNDETERMINED_IDEOLOGY = "undetermined"
UNDETERMINED_PROFILE = {
    "values": ["undecided"], "bonuses": {}, "penalties": {},
    "recruits": "none yet",
    "tone": "The fleet has not decided what it is yet.",
}

DEFAULT_TAX_TOLERANCE = 0.20


async def get(session_id: int = None) -> dict:
    """The society this campaign has become. Derives and PERSISTS one when no
    row exists yet, which is why this read can write. A frozen campaign is derived
    and returned without the write."""
    session_id = require_session(session_id)
    from core.ooc import _writes_allowed
    state = await Database.fetchrow("SELECT ideology,scores_jsonb FROM maya_rp.ideology_state WHERE session_id=$1", session_id)
    if state:
        profile = IDEOS.get(state["ideology"])
        if profile is None:
            info("ideology", f"session {session_id} stores unknown ideology "
                             f"{state['ideology']!r} — neutral profile shown, not a guess")
            profile = UNDETERMINED_PROFILE
        return {"ideology":state["ideology"],"scores":_scores(state.get("scores_jsonb")),**profile}
    return await _recalculate(session_id, persist=_writes_allowed(session_id))


def _scores(value) -> dict:
    """`scores_jsonb` is jsonb, so asyncpg hands it back as text. The derived
    path returns a dict, so the two paths used to differ in type."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError as e:
            info("ideology", f"scores_jsonb is not JSON ({e}) — reporting none")
            return {}
    return value or {}


async def _persist(session_id: int, winner: str, scores: dict) -> None:
    await Database.execute(
        "INSERT INTO maya_rp.ideology_state(session_id,ideology,scores_jsonb) VALUES($1,$2,$3) "
        "ON CONFLICT(session_id)DO UPDATE SET ideology=$2,scores_jsonb=$3,set_at=NOW()",
        session_id, winner, json.dumps(scores))


async def _recalculate(session_id: int, persist: bool = True) -> dict:
    """Derive the society from `player_action_log`. `persist` False derives without writing."""
    scores = {k:0 for k in IDEOS}
    actions = await Database.fetch("SELECT action_category,COALESCE(SUM(count),0) as t FROM maya_rp.player_action_log WHERE session_id=$1 GROUP BY action_category", session_id)
    dist = {a["action_category"]:a["t"] for a in actions}
    total = sum(dist.values()) or 1
    if dist.get("combat",0)/total>0.4: scores["military_dictatorship"]+=3
    if dist.get("cruelty",0)>5: scores["military_dictatorship"]+=2
    if dist.get("intrigue",0)/total>0.3: scores["pirate_confederacy"]+=3
    if dist.get("building",0)/total>0.3: scores["technocratic_utopia"]+=3
    if dist.get("mercy",0)>5: scores["benevolent_democracy"]+=3
    if dist.get("diplomacy",0)/total>0.3: scores["benevolent_democracy"]+=2
    if not any(scores.values()):
        info("ideology", f"session {session_id} has no action history — ideology left "
                         f"undetermined rather than derived from a tie at zero")
        return {"ideology":UNDETERMINED_IDEOLOGY,"scores":scores,**UNDETERMINED_PROFILE}
    winner = max(scores, key=scores.get)
    if persist: await _persist(session_id, winner, scores)
    cfg = IDEOS[winner]
    return {"ideology":winner,"scores":scores,**cfg}

TAX_TOLERANCE = {"military_dictatorship": 0.25, "pirate_confederacy": 0.20,
                 "technocratic_utopia": 0.15, "religious_fundamentalism": 0.30,
                 "benevolent_democracy": 0.12}

def tax_tolerance(ideology: str) -> float:
    """Max tax rate before population attrition kicks in.

    An unknown name takes the declared neutral default rather than a per-ideology
    rate it does not have.
    """
    return TAX_TOLERANCE.get(ideology, DEFAULT_TAX_TOLERANCE)

async def get_prompt(session_id: int = None) -> str:
    ideo = await get(session_id)
    lines=[f"[SOCIETY: {ideo['ideology'].replace('_',' ').title()}]",f"Values: {', '.join(ideo['values']) or 'undecided'}",f"Tone: {ideo['tone']}",f"Recruits: {ideo['recruits']}"]
    return "\n".join(lines)

async def run_tick(session_id: int = None) -> dict:
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    try:
        i = await get(session_id)
        # Re-derive once per tick. No evidence keeps the stored society.
        fresh = await _recalculate(session_id, persist=False)
        if fresh["ideology"] != UNDETERMINED_IDEOLOGY and (fresh["ideology"], fresh["scores"]) != (i["ideology"], i["scores"]):
            await _persist(session_id, fresh["ideology"], fresh["scores"])
            info("ideology", f"session {session_id}: {i['ideology']} -> {fresh['ideology']}")
            i = fresh
        return {"ideology":i["ideology"]}
    except Exception as e:
        error("ideology", f"tick error: {e}")
        return {"error": str(e)}
