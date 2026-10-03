#!/usr/bin/env python3
"""Thematic Resonance — themes echo across combat, romance, politics, exploration."""
from __future__ import annotations
import json, random
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info

VOCAB = {"trust":{"combat":["rely on ally","cover fire","trust instinct"],"romance":["vulnerability","being known","trust after betrayal"],"political":["alliance reliability","verify before trusting"],"exploration":["follow the guide","the map could be wrong"]},
         "sacrifice":{"combat":["hold the line","take the hit","protect the retreat"],"romance":["give up something loved","cost of duty"],"political":["trade territory","lose vote for integrity"],"exploration":["expedition that doesn't return","destroy something ancient"]},
         "identity":{"combat":["fight like the enemy","what does winning make you"],"romance":["who are you when alone","the mask slips"],"political":["title vs person","becoming what you overthrew"],"exploration":["civilization that lost itself","mirror worlds"]},
         "power":{"combat":["overwhelming force","temptation of more power"],"romance":["power dynamics","control as intimacy"],"political":["corrupting ease of authority","power without oversight"],"exploration":["ancient power sources","power abandoned for reason"]},
         "loss":{"combat":["empty slot in formation","victory like defeat"],"romance":["the space where someone was","remembering their laugh"],"political":["seat unfilled","what we lost to get here"],"exploration":["ruins of something beautiful","last of its kind"]},
         "freedom":{"combat":["fight to escape","break chains"],"romance":["love as liberation","choose each other freely"],"political":["freedom's cost","who defines freedom"],"exploration":["uncharted as freedom","the frontier as escape"]}}
KW = {"trust":["trust","loyalty","betray","ally","reliable"],"sacrifice":["sacrifice","lose","give up","cost","volunteer"],"identity":["identity","who am i","become","mask","true self"],"power":["power","control","authority","command","dominate"],"loss":["loss","death","gone","destroyed","empty"],"freedom":["freedom","escape","prison","chains","liberty"]}

async def detect(session_id: int = None) -> list[dict]:
    if session_id is None: session_id = Config.SESSION_ID
    recent = await Database.fetch("SELECT title,description,tags FROM maya_rp.events WHERE session_id=$1 AND happened_at>NOW()-INTERVAL'7 days'", session_id)
    scores = {}
    for event in recent:
        text = f"{event['title']} {event.get('description','')}".lower()
        tags = event["tags"]
        if isinstance(tags,str):
            try:
                tags = json.loads(tags)
            except ValueError as e:
                # A bare `except:` here swallowed malformed tag JSON in silence.
                info("themes", f"event tags are not JSON ({e}) — counting the event without them")
                tags = []
        text += " "+" ".join(str(t) for t in tags)
        for theme,kws in KW.items():
            for kw in kws:
                if kw in text: scores[theme]=scores.get(theme,0)+1
    from core.player_profile import get_profile
    prof = await get_profile(session_id)
    dist = prof.get("distribution",{})
    if dist.get("mercy",0)>15: scores["freedom"]=scores.get("freedom",0)+3
    if dist.get("cruelty",0)>15: scores["power"]=scores.get("power",0)+3
    if dist.get("diplomacy",0)>15: scores["trust"]=scores.get("trust",0)+3
    sorted_t = sorted(scores.items(),key=lambda x:x[1],reverse=True)
    return [{"theme":t,"score":s} for t,s in sorted_t[:2] if s>=2]

async def get_instruction(session_id: int = None) -> str:
    themes = await detect(session_id)
    if not themes: return ""
    lines=["[ACTIVE THEMES]"]
    for t in themes:
        lines.append(f"  \u2605 {t['theme'].upper()} (resonance: {t['score']})")
        for domain in ["combat","romance","political","exploration"]:
            beats = VOCAB.get(t["theme"],{}).get(domain,[])
            if beats: lines.append(f"    {domain}: {random.choice(beats)}")
    return "\n".join(lines)

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    themes = await detect(session_id)
    await Database.execute("INSERT INTO maya_rp.theme_state(session_id,themes_jsonb,detected_at) VALUES($1,$2,NOW()) ON CONFLICT(session_id)DO UPDATE SET themes_jsonb=$2,detected_at=NOW()", session_id,json.dumps(themes))
    return {"active":[t["theme"] for t in themes]}
