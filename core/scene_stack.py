#!/usr/bin/env python3
"""Scene Stack — track interrupted scenes for later resumption."""
from __future__ import annotations
import json
from typing import Any
from core.db import Database
from core.session import require_session
from core.log import info

async def push(interrupt_type: str, context: dict, session_id: int = None):
    session_id = require_session(session_id)
    # The COALESCE used to sit inside this SELECT, where it only ever answered for a session row
    # that exists: an unknown session returns no row at all, so the game day arrived as None, the
    # insert stored a NULL, and `pop` then computed `gd - None` and raised TypeError. A scene with
    # no date is not pushed; the caller is told what is missing.
    gd = await Database.fetchval("SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id)
    if gd is None:
        raise ValueError(f"no game day for session {session_id}: no sessions row, or its game_day is NULL")
    await Database.execute("INSERT INTO maya_rp.scene_stack (session_id,interrupt_type,context_jsonb,pushed_at_game_day,status) VALUES ($1,$2,$3,$4,'suspended')", session_id, interrupt_type, json.dumps(context), gd)
    info("scene_stack", f"Pushed: {context.get('what_was_happening','?')[:60]}")

#: Urgency as a sortable rank. A numeric urgency ('2', '10') sorts by value, otherwise
#: critical > high > medium > low; anything else sorts last. Lower rank pops first.
#: Ordering the raw text put '10' before '2' ('1' < '2' lexicographically).
_URGENCY_RANK = (
    "CASE WHEN context_jsonb->>'urgency' ~ '^[0-9]{1,9}$' THEN (context_jsonb->>'urgency')::int "
    "WHEN context_jsonb->>'urgency' = 'critical' THEN -4 "
    "WHEN context_jsonb->>'urgency' = 'high' THEN -3 "
    "WHEN context_jsonb->>'urgency' = 'medium' THEN -2 "
    "WHEN context_jsonb->>'urgency' = 'low' THEN -1 "
    "ELSE 2147483647 END"
)


async def pop(session_id: int = None) -> dict | None:
    """Resume the most urgent suspended scene of a session, once.

    The claim is one statement, `UPDATE ... WHERE id=(SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1)
    AND status='suspended'`. The old SELECT then UPDATE let two concurrent pops read the same
    row and resume the same scene. A pop that finds the best row locked takes the next one, or
    returns None when none is left. Numeric urgency pops by value (lower first); named urgency
    by critical, high, medium, low. Ties go to the older pushed scene.

    @param session_id - explicit id wins; None resolves the arc now.
    @returns {"id","interrupt_type","context","games_ago","stale"}, or None when nothing is suspended.
    """
    session_id = require_session(session_id)
    r = await Database.fetchrow(
        "UPDATE maya_rp.scene_stack SET status='resumed', resolved_at_game_day="
        "(SELECT game_day FROM maya_rp.sessions WHERE id=$1) "
        "WHERE id=(SELECT id FROM maya_rp.scene_stack WHERE session_id=$1 AND status='suspended' "
        f"ORDER BY {_URGENCY_RANK} ASC, pushed_at_game_day ASC, id ASC "
        "FOR UPDATE SKIP LOCKED LIMIT 1) AND status='suspended' "
        "RETURNING id, interrupt_type, context_jsonb, pushed_at_game_day",
        session_id)
    if not r: return None
    ctx = json.loads(r["context_jsonb"])
    gd = await Database.fetchval("SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id)
    pushed = r["pushed_at_game_day"]
    # Either end can be unknown: a row written before the date was required, or a session whose
    # game_day is NULL. `gd - None` raised, and the `or 0` before it turned a missing session into
    # a negative age that read as fresh. Unknown age is reported as unknown.
    ga = None if (pushed is None or gd is None) else gd - pushed
    return {"id":r["id"],"interrupt_type":r["interrupt_type"],"context":ctx,"games_ago":ga,"stale":bool(ga is not None and ga>10)}

async def get_stack_summary(session_id: int = None) -> list:
    session_id = require_session(session_id)
    rows = await Database.fetch("SELECT id,interrupt_type,context_jsonb,pushed_at_game_day FROM maya_rp.scene_stack WHERE session_id=$1 AND status='suspended' ORDER BY id", session_id)
    return [{"id":r["id"],"interrupt_type":r["interrupt_type"],"context":json.loads(r["context_jsonb"]),"pushed_at_game_day":r["pushed_at_game_day"]} for r in rows]
