#!/usr/bin/env python3
"""Persistent Physical State — scars, injuries, physical changes that carry history."""
from __future__ import annotations
import random
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info

SEVERITY = {"minor":{"heal":3,"scar":0.1},"moderate":{"heal":10,"scar":0.4},"severe":{"heal":30,"scar":0.8},"permanent":{"heal":999,"scar":1.0}}

async def apply(character_id: int, desc: str, severity: str = "moderate", body: str = "unspecified", cause: str = "combat", session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    if severity not in SEVERITY:
        # An unknown word used to read as "moderate" while the row stored the word
        # the caller passed, so the wound healed on a schedule nobody chose.
        return {"error": f"Unknown severity {severity!r}: use one of "
                         f"{', '.join(SEVERITY)}"}
    cfg = SEVERITY[severity]
    gd = await Database.fetchval("SELECT COALESCE(game_day,1) FROM maya_rp.sessions WHERE id=$1", session_id)
    scar = random.random()<cfg["scar"]
    iid = await Database.fetchval("INSERT INTO maya_rp.character_injuries(session_id,character_id,description,severity,body_part,cause,received_game_day,heal_by_game_day,became_scar,status) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,'active') RETURNING id", session_id,character_id,desc,severity,body,cause,gd,gd+cfg["heal"],scar)
    return {"injury_id":iid,"description":desc,"severity":severity,"heals_in":cfg["heal"],"will_scar":scar,"narrative":f"{desc} on the {body}. {'This will leave a mark.' if scar else 'Should heal cleanly.'}"}

async def get_state(character_id: int, session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    gd = await Database.fetchval("SELECT COALESCE(game_day,1) FROM maya_rp.sessions WHERE id=$1", session_id)
    injuries = await Database.fetch("SELECT description,body_part,severity,heal_by_game_day FROM maya_rp.character_injuries WHERE session_id=$1 AND character_id=$2 AND status='active' AND heal_by_game_day>$3", session_id,character_id,gd)
    scars = await Database.fetch("SELECT description,body_part FROM maya_rp.character_injuries WHERE session_id=$1 AND character_id=$2 AND became_scar=true", session_id,character_id)
    healed = await Database.fetch("SELECT id,description,body_part,became_scar FROM maya_rp.character_injuries WHERE session_id=$1 AND character_id=$2 AND status='active' AND heal_by_game_day<=$3", session_id,character_id,gd)
    for h in healed:
        ns = "scar" if h["became_scar"] else "healed"
        await Database.execute("UPDATE maya_rp.character_injuries SET status=$1 WHERE id=$2", ns,h["id"])
    parts = []
    for i in injuries:
        parts.append({"minor":"a fresh wound","moderate":"a bandaged injury","severe":"a serious injury, still painful","permanent":"an injury that will never be the same"}.get(i["severity"],f"an injured {i['body_part']}"))
    for s in scars:
        parts.append(f"a scar on the {s['body_part']}")
    return {"active_injuries":[dict(i) for i in injuries],"scars":[dict(s) for s in scars],"healed":len(healed),"visual":("They bear "+parts[0]+".") if len(parts)==1 else ("They bear "+", ".join(parts[:-1])+f", and {parts[-1]}.") if parts else None}

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    gd = await Database.fetchval("SELECT COALESCE(game_day,1) FROM maya_rp.sessions WHERE id=$1", session_id)
    # execute() returns PostgreSQL's status tag ("UPDATE 12"), which the tick used to
    # report as a count. RETURNING gives the rows themselves.
    rows = await Database.fetch(
        "UPDATE maya_rp.character_injuries SET status=CASE WHEN became_scar THEN 'scar' ELSE 'healed' END "
        "WHERE session_id=$1 AND status='active' AND heal_by_game_day<=$2 RETURNING id",
        session_id, gd)
    return {"processed": len(rows)}
