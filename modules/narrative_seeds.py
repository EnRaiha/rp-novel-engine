#!/usr/bin/env python3
"""Foreshadowing & Payoff System — plant narrative seeds, hint at them, payoff later."""
from __future__ import annotations
import json
from typing import Any
from core.db import Database
from core.config import Config
from core.log import error, info


async def plant_seed(seed_type: str, content: str, payoff_condition: str = "",
                     payoff_template: str = "", payoff_by_day: int = None,
                     session_id: int = None):
    """Plant a narrative seed for later payoff."""
    if session_id is None:
        session_id = Config.SESSION_ID
    game_day = await Database.fetchval(
        "SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id) or 1

    await Database.execute(
        "INSERT INTO maya_rp.narrative_seeds (session_id, seed_type, content, planted_at_game_day, "
        "payoff_condition, payoff_event_template, payoff_game_day) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7)",
        session_id, seed_type, content, game_day, payoff_condition, payoff_template, payoff_by_day)
    info("narrative_seeds", f"Planted: [{seed_type}] {content[:60]}...")


async def get_foreshadow_ops(session_id: int = None) -> list[dict]:
    """Get seeds that should be hinted at in current narrative."""
    if session_id is None:
        session_id = Config.SESSION_ID
    game_day = await Database.fetchval(
        "SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id) or 1

    rows = await Database.fetch(
        "SELECT id, seed_type, content, foreshadow_count, max_foreshadows, payoff_game_day "
        "FROM maya_rp.narrative_seeds WHERE session_id=$1 AND status IN ('planted','foreshadowed') "
        "AND foreshadow_count < max_foreshadows "
        "AND (payoff_game_day IS NULL OR payoff_game_day > $2) "
        "ORDER BY RANDOM() LIMIT 2",
        session_id, game_day)
    return [dict(r) for r in rows]


async def mark_foreshadowed(seed_id: int, session_id: int = None):
    """Count one hint on an open seed. The third hint closes it as `paid_off` and emits no event.

    @returns {"seed_id", "marked", "status"}. `marked` is False for a seed that is missing,
    belongs to another session, or is already closed.
    """
    if session_id is None:
        session_id = Config.SESSION_ID
    returned = await Database.fetchval(
        "UPDATE maya_rp.narrative_seeds "
        "SET foreshadow_count = COALESCE(foreshadow_count, 0) + 1, "
        "    status = CASE WHEN COALESCE(foreshadow_count, 0) + 1 >= COALESCE(max_foreshadows, 3) "
        "                  THEN 'paid_off' ELSE 'foreshadowed' END "
        "WHERE id=$1 AND session_id=$2 AND status IN ('planted','foreshadowed') RETURNING status",
        seed_id, session_id)
    return {"seed_id": seed_id, "marked": returned is not None, "status": returned}


async def pay_off(seed_id: int, session_id: int = None) -> dict:
    """Pay off one open seed. The claim and the PAYOFF event share one transaction.

    @returns the paid seed, or a dict with `error` when the seed is missing or already closed.
    """
    if session_id is None:
        session_id = Config.SESSION_ID
    async with Database.transaction() as conn:
        seed = await conn.fetchrow(
            "UPDATE maya_rp.narrative_seeds SET status='paid_off' "
            "WHERE id=$1 AND session_id=$2 AND status IN ('planted','foreshadowed') "
            "RETURNING id, content, payoff_event_template, seed_type",
            seed_id, session_id)
        if not seed:
            status = await conn.fetchval(
                "SELECT status FROM maya_rp.narrative_seeds WHERE id=$1 AND session_id=$2",
                seed_id, session_id)
            if status is None:
                return {"error": f"seed {seed_id} not found in session {session_id}"}
            return {"seed_id": seed_id, "paid_off": False,
                    "error": f"seed {seed_id} is {status}, not open for payoff"}
        await conn.execute(
            "INSERT INTO maya_rp.events (session_id, happened_at, event_type, title, description, tags, importance) "
            "VALUES ($1, NOW(), 'payoff', $2, $3, $4, 4)",
            session_id,
            f"PAYOFF: {seed['payoff_event_template'] or seed['seed_type'] or 'seed'}",
            seed["content"],
            json.dumps(["narrative", "payoff", seed["seed_type"] or "unknown"]))
    return {"seed_id": seed_id, "paid_off": True, "content": seed["content"]}


async def run_tick(session_id: int = None) -> dict:
    """Check for auto-payoff seeds that have reached their payoff day."""
    if session_id is None:
        session_id = Config.SESSION_ID
    try:
        game_day = await Database.fetchval(
            "SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id) or 1
        due = await Database.fetch(
            "SELECT id, content, payoff_event_template, seed_type "
            "FROM maya_rp.narrative_seeds WHERE session_id=$1 "
            "AND status IN ('planted','foreshadowed') "
            "AND payoff_game_day IS NOT NULL AND payoff_game_day <= $2",
            session_id, game_day)
        paid = failed = 0
        for d in due:
            try:
                result = await pay_off(d["id"], session_id)
            except Exception as e:
                error("narrative_seeds", f"payoff of seed {d['id']} failed: {e}")
                failed += 1
                continue
            if result.get("paid_off"):
                paid += 1
        info("narrative_seeds", f"Tick: {paid} auto-payoffs, {failed} failed")
        return {"auto_payoffs": paid, "failed": failed} if failed else {"auto_payoffs": paid}
    except Exception as e:
        error("narrative_seeds", f"tick failed for session {session_id}: {e}")
        return {"error": str(e)}
