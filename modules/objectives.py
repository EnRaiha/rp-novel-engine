#!/usr/bin/env python3
"""Objective Tracker — aggregates all active goals into one view. Critical → Urgent → Active → Background."""
from __future__ import annotations
import json
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info

async def get_active(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    obj = {"critical":[],"urgent":[],"active":[],"background":[]}
    for r in await Database.fetch("SELECT hook_type,description,status FROM maya_rp.narrative_hooks WHERE session_id=$1 AND status='active'", session_id):
        obj["active"].append({"source":"hook","title":r["hook_type"],"detail":(r.get("description")or"")[:80],"icon":"\U0001f4cc"})

    for r in await Database.fetch("SELECT opponent_faction,phase,war_goal FROM maya_rp.wars WHERE session_id=$1 AND status='active'", session_id):
        obj["urgent"].append({"source":"war","title":f"War vs {r['opponent_faction']}","detail":f"Phase: {r['phase']}","icon":"\u2694\ufe0f"})

    for r in await Database.fetch("SELECT title,description FROM maya_rp.quests WHERE session_id=$1 AND status='active' LIMIT 5", session_id):
        obj["active"].append({"source":"quest","title":r["title"],"detail":(r["description"]or"")[:80],"icon":"\U0001f4dc"})

    for r in await Database.fetch("SELECT trigger_type,cause_description FROM maya_rp.consequence_seeds WHERE session_id=$1 AND status='planted' AND can_be_prevented=true ORDER BY id LIMIT 3", session_id):
        obj["urgent"].append({"source":"consequence","title":f"Prevent: {r['trigger_type']}","detail":(r.get("cause_description")or"")[:80],"icon":"\u23f3"})

    return obj

async def objectives_to_prompt(session_id: int = None) -> str:
    obj = await get_active(session_id)
    lines = ["## ACTIVE OBJECTIVES",""]
    for label,key in [("\U0001f534 CRITICAL","critical"),("\U0001f7e1 URGENT","urgent"),("\U0001f7e2 IN PROGRESS","active"),("\u26aa BACKGROUND","background")]:
        items = obj[key]
        if items:
            lines.append(f"### {label}")
            for o in items: lines.append(f"- {o['icon']} {o['detail']}")
            lines.append("")
    if not any(obj.values()): lines.append("_No active objectives. The galaxy is quiet..._")
    return "\n".join(lines)

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    try:
        expired = await Database.fetch("SELECT id,hook_type FROM maya_rp.narrative_hooks WHERE session_id=$1 AND status='active' AND created_at IS NOT NULL AND created_at < NOW() - INTERVAL '30 days'", session_id)
        for e in expired:
            await Database.execute("UPDATE maya_rp.narrative_hooks SET status='expired' WHERE id=$1", e["id"])
        return {"expired":len(expired)}
    except Exception as e:
        info("objectives", f"Error: {e}")
        return {"error": str(e)}
