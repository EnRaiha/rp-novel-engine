#!/usr/bin/env python3
"""Foreshadowing & Payoff System — plant narrative seeds, hint at them, payoff later."""
from __future__ import annotations
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info


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
    """Mark a seed as foreshadowed (hinted at)."""
    if session_id is None:
        session_id = Config.SESSION_ID
    row = await Database.fetchrow(
        "SELECT id, foreshadow_count, max_foreshadows FROM maya_rp.narrative_seeds WHERE id=$1",
        seed_id)
    if row:
        fc = row["foreshadow_count"] + 1
        ns = "paid_off" if fc >= (row["max_foreshadows"] or 3) else "foreshadowed"
        await Database.execute(
            "UPDATE maya_rp.narrative_seeds SET foreshadow_count=$1, status=$2 WHERE id=$3",
            fc, ns, seed_id)


async def pay_off(seed_id: int, session_id: int = None) -> dict:
    """Trigger a seed's payoff event."""
    if session_id is None:
        session_id = Config.SESSION_ID
    seed = await Database.fetchrow(
        "SELECT id, content, payoff_event_template, seed_type FROM maya_rp.narrative_seeds WHERE id=$1",
        seed_id)
    if not seed:
        return {"error": "Seed not found"}

    await Database.execute(
        "UPDATE maya_rp.narrative_seeds SET status='paid_off' WHERE id=$1", seed_id)
    await Database.execute(
        "INSERT INTO maya_rp.events (session_id, happened_at, event_type, title, description, tags, importance) "
        "VALUES ($1, NOW(), 'payoff', $2, $3, $4, 4)",
        session_id,
        f"PAYOFF: {seed.get('payoff_event_template', seed['seed_type'])}",
        seed["content"],
        '["narrative", "payoff", "' + seed["seed_type"] + '"]')
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
            "FROM maya_rp.narrative_seeds WHERE session_id=$1 AND status='planted' "
            "AND payoff_game_day IS NOT NULL AND payoff_game_day <= $2",
            session_id, game_day)
        paid = 0
        for d in due:
            await pay_off(d["id"], session_id)
            paid += 1
        info("narrative_seeds", f"Tick: {paid} auto-payoffs")
        return {"auto_payoffs": paid}
    except Exception as e:
        info("narrative_seeds", f"Error: {e}")
        return {"error": str(e)}
