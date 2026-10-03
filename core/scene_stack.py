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
    # The COALESCE used to sit inside this SELECT, where it only ever answered for a session row
    # that exists: an unknown session returns no row at all, so the game day arrived as None, the
    # insert stored a NULL, and `pop` then computed `gd - None` and raised TypeError. A scene with
    # no date is not pushed; the caller is told what is missing.
    gd = await Database.fetchval("SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id)
    if gd is None:
        raise ValueError(f"no game day for session {session_id}: no sessions row, or its game_day is NULL")
    await Database.execute("INSERT INTO maya_rp.scene_stack (session_id,interrupt_type,context_jsonb,pushed_at_game_day,status) VALUES ($1,$2,$3,$4,'suspended')", session_id, interrupt_type, json.dumps(context), gd)
    info("scene_stack", f"Pushed: {context.get('what_was_happening','?')[:60]}")

async def pop(session_id: int = None) -> dict | None:
    if session_id is None: session_id = Config.SESSION_ID
    r = await Database.fetchrow("SELECT id,interrupt_type,context_jsonb,pushed_at_game_day FROM maya_rp.scene_stack WHERE session_id=$1 AND status='suspended' ORDER BY context_jsonb->>'urgency' ASC, pushed_at_game_day ASC LIMIT 1", session_id)
    if not r: return None
    # The row was found by session and then resumed by id alone. It carries a session, so it names
    # it: an id from another campaign's stack cannot be marked resumed by this call.
    await Database.execute("UPDATE maya_rp.scene_stack SET status='resumed' WHERE id=$1 AND session_id=$2", r["id"], session_id)
    ctx = json.loads(r["context_jsonb"])
    gd = await Database.fetchval("SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id)
    pushed = r["pushed_at_game_day"]
    # Either end can be unknown: a row written before the date was required, or a session whose
    # game_day is NULL. `gd - None` raised, and the `or 0` before it turned a missing session into
    # a negative age that read as fresh. Unknown age is reported as unknown.
    ga = None if (pushed is None or gd is None) else gd - pushed
    return {"id":r["id"],"interrupt_type":r["interrupt_type"],"context":ctx,"games_ago":ga,"stale":bool(ga is not None and ga>10)}

async def get_stack_summary(session_id: int = None) -> list:
    if session_id is None: session_id = Config.SESSION_ID
    rows = await Database.fetch("SELECT id,interrupt_type,context_jsonb,pushed_at_game_day FROM maya_rp.scene_stack WHERE session_id=$1 AND status='suspended' ORDER BY id", session_id)
    return [{"id":r["id"],"interrupt_type":r["interrupt_type"],"context":json.loads(r["context_jsonb"]),"pushed_at_game_day":r["pushed_at_game_day"]} for r in rows]
