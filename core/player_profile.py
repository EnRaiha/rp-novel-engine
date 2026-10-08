#!/usr/bin/env python3
"""Player Style Tracker — learns what the player tends to do and adjusts."""
from __future__ import annotations
import re
from typing import Any
from core.db import Database
from core.session import require_session
from core.log import info

ACTION_CATS = {"combat":["attack","fight","fire","shoot","strike","charge","engage","destroy","kill"],
              "diplomacy":["negotiate","talk","offer","propose","persuade","compromise","deal","treaty"],
              "exploration":["explore","investigate","scan","search","survey","examine"],
              "romance":["kiss","embrace","touch","whisper","hold","cuddle","love","desire"],
              "leadership":["order","command","assign","deploy","rally","decree"],
              "cruelty":["torture","execute","punish","break","humiliate","threaten"],
              "mercy":["spare","forgive","heal","protect","save","release"],
              "intrigue":["spy","sabotage","assassinate","manipulate","scheme","plot"],
              "building":["build","construct","research","develop","upgrade","improve"]}

STYLE_ADVICE = {
    "warlord":["Player prefers combat. Include tactical decisions.","Don't force diplomacy — let them fight.","Occasionally present unsolvable-with-force problems."],
    "diplomat":["Player prefers talking. Create negotiation scenes.","Dialogue choices should have real weight.","Occasionally force combat to maintain tension."],
    "romantic":["Player values relationships. Create intimate moments.","Develop companion stories.","Jealousy and relationship drama are effective."],
    "tyrant":["Player leans dark. Let consequences speak.","Crew fear becomes central.","Offer redemption eventually."],
    "paragon":["Player is heroic. Create moral dilemmas.","Mercy should sometimes backfire.","NPCs respond to reputation."],
    "explorer":["Player values discovery. Anomalies and ruins.","Reward curiosity with lore.","Some discoveries should be dangerous."],
    "builder":["Player likes progression. Show results.","Threaten what they've built occasionally."],
    "shadow_lord":["Player likes intrigue. Spy vs spy.","Information is currency.","Conspiracies within conspiracies."],
    "balanced":["Well-rounded. Mix elements evenly."],
}

async def record(text: str, session_id: int = None):
    if session_id is None: session_id = require_session(None)
    lower = text.lower()
    hits = []
    for cat, kws in ACTION_CATS.items():
        # `kw in lower` is a substring test, so it counted "kill" inside "skill", "deal" inside
        # "ideal", "hold" inside "household", "break" inside "breakfast", and "search" inside
        # "research" — which is also a `building` keyword, so one word scored two categories.
        # `core/guard.py` learned this one already: a substring test flagged "gun" inside "begun".
        c = sum(1 for kw in kws if re.search(rf"\b{re.escape(kw)}\b", lower))
        if c > 0: hits.append((cat, c))
    for cat, c in hits:
        await Database.execute("INSERT INTO maya_rp.player_action_log (session_id,action_category,count,raw_input) VALUES ($1,$2,$3,$4)", session_id, cat, c, text[:200])

async def get_profile(session_id: int = None) -> dict:
    if session_id is None: session_id = require_session(None)
    rows = await Database.fetch("SELECT action_category,SUM(count) as total FROM maya_rp.player_action_log WHERE session_id=$1 GROUP BY action_category ORDER BY total DESC", session_id)
    recorded = sum(r["total"] for r in rows)
    total = recorded or 1   # the divisor only: with no rows there is nothing to divide
    dist = {r["action_category"]: round(r["total"]/total*100) for r in rows}

    style = "balanced"
    for s, cond in [("warlord",dist.get("combat",0)>40),("diplomat",dist.get("diplomacy",0)>30 and dist.get("combat",0)<20),
                    ("romantic",dist.get("romance",0)>25),("tyrant",dist.get("cruelty",0)>20),
                    ("paragon",dist.get("mercy",0)>20 and dist.get("cruelty",0)<5),
                    ("shadow_lord",dist.get("intrigue",0)>25),("builder",dist.get("building",0)>30),
                    ("explorer",dist.get("exploration",0)>30)]:
        if cond: style = s; break

    # `ORDER BY ra.nights_shared DESC` puts NULLs first in Postgres, so a row with no count would
    # take the preferred-companion slot from a companion with one. Measured: 0 of the 49 live rows
    # hold NULL, so nothing is wrong today; NULLS LAST keeps it that way.
    partner = await Database.fetchrow("SELECT c.name FROM maya_rp.romance_arcs ra JOIN maya_rp.characters c ON c.id=ra.character_id WHERE ra.session_id=$1 ORDER BY ra.nights_shared DESC NULLS LAST LIMIT 1", session_id)
    return {"style":style,"distribution":dist,"total":int(recorded),"preferred_companion":partner["name"] if partner else None,"advice":STYLE_ADVICE.get(style,STYLE_ADVICE["balanced"])}
