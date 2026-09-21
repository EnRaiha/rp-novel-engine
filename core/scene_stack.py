#!/usr/bin/env python3
"""Scene Stack — track interrupted scenes for later resumption."""
from __future__ import annotations
import json
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info

async def push(interrupt_type: str, context: dict, session_id: int = None):
    if session_id is None: session_id = Config.SESSION_ID
    gd = await Database.fetchval("SELECT COALESCE(game_day,1) FROM maya_rp.sessions WHERE id=$1", session_id)
    await Database.execute("INSERT INTO maya_rp.scene_stack (session_id,interrupt_type,context_jsonb,pushed_at_game_day,status) VALUES ($1,$2,$3,$4,'suspended')", session_id, interrupt_type, json.dumps(context), gd)
    info("scene_stack", f"Pushed: {context.get('what_was_happening','?')[:60]}")

async def pop(session_id: int = None) -> dict | None:
    if session_id is None: session_id = Config.SESSION_ID
    r = await Database.fetchrow("SELECT id,interrupt_type,context_jsonb,pushed_at_game_day FROM maya_rp.scene_stack WHERE session_id=$1 AND status='suspended' ORDER BY context_jsonb->>'urgency' ASC, pushed_at_game_day ASC LIMIT 1", session_id)
    if not r: return None
    await Database.execute("UPDATE maya_rp.scene_stack SET status='resumed' WHERE id=$1", r["id"])
    ctx = json.loads(r["context_jsonb"])
    gd = await Database.fetchval("SELECT COALESCE(game_day,1) FROM maya_rp.sessions WHERE id=$1", session_id) or 0
    ga = gd - r["pushed_at_game_day"]
    return {"id":r["id"],"interrupt_type":r["interrupt_type"],"context":ctx,"games_ago":ga,"stale":ga>10}

async def get_stack_summary(session_id: int = None) -> list:
    if session_id is None: session_id = Config.SESSION_ID
    rows = await Database.fetch("SELECT id,interrupt_type,context_jsonb,pushed_at_game_day FROM maya_rp.scene_stack WHERE session_id=$1 AND status='suspended' ORDER BY id", session_id)
    return [{"id":r["id"],"interrupt_type":r["interrupt_type"],"context":json.loads(r["context_jsonb"]),"pushed_at_game_day":r["pushed_at_game_day"]} for r in rows]
