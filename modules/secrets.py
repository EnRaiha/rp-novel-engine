#!/usr/bin/env python3
"""Secrets System — secrets, lies & dramatic irony. What characters hide from each other."""
from __future__ import annotations
import random
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info

SECRET_TEMPLATES = {
    "personal_past": [f"was once part of {random.choice(['Den','Vigil','Federation'])}. Left under unclear circumstances.","has a family never mentioned.","was responsible for a crew death on a previous ship.","can't read. Hidden entire career.","changed name when joining."],
    "guilt": ["took something from cargo during supply crisis.","ignored a maintenance warning.","reported a crewmate for something minor — they were punished harshly."],
    "capability": ["has medical training never mentioned.","speaks Den trade language.","can pilot small craft — hid it to avoid dangerous missions."],
}

async def plant(secret_type: str, holder_id: int, content: str, hidden_from: list = None, trigger: str = "deep_bond_conversation", consequence: str = "", auto_reveal_day: int = None, session_id: int = None) -> int:
    if session_id is None: session_id = Config.SESSION_ID
    gd = await Database.fetchval("SELECT COALESCE(game_day,1) FROM maya_rp.sessions WHERE id=$1", session_id)
    sid = await Database.fetchval("INSERT INTO maya_rp.secrets(session_id,secret_type,holder_character_id,content,hidden_from_ids,discovery_trigger,consequence_description,planted_game_day,auto_reveal_game_day,status) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,'active') RETURNING id", session_id,secret_type,holder_id,content,(hidden_from or []),trigger,consequence,gd,auto_reveal_day)
    info("secrets", f"Planted: {secret_type}", holder=holder_id)
    return sid

async def check_discovery(context: str, session_id: int = None) -> list[dict]:
    if session_id is None: session_id = Config.SESSION_ID
    lower = context.lower()
    active = await Database.fetch("SELECT id,secret_type,holder_character_id,content,discovery_trigger,consequence_description FROM maya_rp.secrets WHERE session_id=$1 AND status='active'", session_id)
    discovered = []
    for s in active:
        trigger = (s.get("discovery_trigger") or "").split("_")
        matches = sum(1 for w in trigger if w in lower)
        gd = await Database.fetchval("SELECT COALESCE(game_day,1) FROM maya_rp.sessions WHERE id=$1", session_id)
        auto = s.get("auto_reveal_game_day") and gd >= s["auto_reveal_game_day"]
        if matches >= len(trigger)*0.5 or auto:
            await Database.execute("UPDATE maya_rp.secrets SET status='revealed',revealed_game_day=$1,revelation_context=$2 WHERE id=$3", gd, context[:200], s["id"])
            hn = await Database.fetchval("SELECT name FROM maya_rp.characters WHERE id=$1", s["holder_character_id"])
            discovered.append({"secret_id":s["id"],"type":s["secret_type"],"holder":hn,"content":s["content"],"consequence":s["consequence_description"]})
    return discovered

async def get_dramatic_irony(session_id: int = None) -> list[dict]:
    if session_id is None: session_id = Config.SESSION_ID
    rows = await Database.fetch("SELECT s.id,s.secret_type,s.content,c.name as holder FROM maya_rp.secrets s JOIN maya_rp.characters c ON c.id=s.holder_character_id WHERE s.session_id=$1 AND s.status='active' AND s.secret_type='player_blind' ORDER BY s.planted_game_day DESC LIMIT 5", session_id)
    return [dict(r) for r in rows]

async def seed_initial(session_id: int = None):
    if session_id is None: session_id = Config.SESSION_ID
    existing = await Database.fetchval("SELECT COUNT(*) FROM maya_rp.secrets WHERE session_id=$1", session_id)
    if existing and existing>0: return
    chars = await Database.fetch("SELECT id,name,role FROM maya_rp.characters WHERE session_id=$1 AND status='active' AND role NOT IN ('player') ORDER BY RANDOM() LIMIT 10", session_id)
    for c in chars:
        roll = random.random()
        if roll < 0.4:
            content = c['name'] + " " + random.choice(SECRET_TEMPLATES["personal_past"])
            await plant("personal_past",c["id"],content,trigger="deep_bond_conversation",consequence="Could strengthen or damage bond",session_id=session_id)
        elif roll < 0.55:
            content = c['name'] + " " + random.choice(SECRET_TEMPLATES["guilt"])
            await plant("guilt",c["id"],content,trigger="confession_under_stress",consequence="Trust could be damaged",session_id=session_id)
        elif roll < 0.65:
            content = c['name'] + " " + random.choice(SECRET_TEMPLATES["capability"])
            await plant("capability",c["id"],content,trigger="desperate_moment",consequence="Could change their role",session_id=session_id)
    player = await Database.fetchrow("SELECT id FROM maya_rp.characters WHERE session_id=$1 AND role='player'", session_id)
    if player:
        blinds = ["The Den armada has a spy among the crew.","The Vein Network artifact is still emitting a faint signal.","Three crew have been meeting in secret — it's a birthday planning committee but looks suspicious.","The water recycler has a micro-fracture. Critical in 20 days if unfound."]
        for b in blinds:
            await plant("player_blind",player["id"],b,trigger="investigation",auto_reveal_day=(await Database.fetchval("SELECT COALESCE(game_day,1) FROM maya_rp.sessions WHERE id=$1", session_id) or 0)+random.randint(15,40),session_id=session_id)

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    gd = await Database.fetchval("SELECT COALESCE(game_day,1) FROM maya_rp.sessions WHERE id=$1", session_id)
    expired = await Database.fetch("SELECT id,content FROM maya_rp.secrets WHERE session_id=$1 AND status='active' AND auto_reveal_game_day IS NOT NULL AND auto_reveal_game_day<=$2", session_id,gd)
    for e in expired:
        await Database.execute("UPDATE maya_rp.secrets SET status='revealed',revealed_game_day=$1,revelation_context='Time revealed' WHERE id=$2", gd,e["id"])
    return {"auto_revealed":len(expired)}
