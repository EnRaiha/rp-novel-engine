#!/usr/bin/env python3
"""Chekhov's Gun Tracker — introduced elements must pay off."""
from __future__ import annotations
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info

async def introduce(elem_type: str, desc: str, importance: str = "medium", payoff_window: int = 15, session_id: int = None) -> int:
    if session_id is None: session_id = Config.SESSION_ID
    if payoff_window < 0:
        raise ValueError(f"payoff_window cannot be negative, got {payoff_window}")
    gd = await Database.fetchval("SELECT COALESCE(game_day,1) FROM maya_rp.sessions WHERE id=$1", session_id)
    return await Database.fetchval("INSERT INTO maya_rp.chekhov_elements(session_id,element_type,description,importance,introduced_game_day,payoff_deadline,status) VALUES($1,$2,$3,$4,$5,$6,'unpaid') RETURNING id", session_id,elem_type,desc,importance,gd,gd+payoff_window)

async def payoff(element_id: int, method: str, session_id: int = None) -> bool:
    """Mark one element paid off. Returns whether the element was found.

    Scoped by session: `WHERE id=$3` alone let a payoff land on another
    campaign's element, and the caller was told nothing either way.
    """
    if session_id is None: session_id = Config.SESSION_ID
    gd = await Database.fetchval("SELECT COALESCE(game_day,1) FROM maya_rp.sessions WHERE id=$1", session_id)
    tag = await Database.execute(
        "UPDATE maya_rp.chekhov_elements SET status='paid',payoff_method=$1,paid_game_day=$2 "
        "WHERE id=$3 AND session_id=$4",
        method, gd, element_id, session_id)
    paid = not (isinstance(tag, str) and tag.split()[-1:] == ["0"])
    if not paid:
        info("chekhov", f"element {element_id} is not in session {session_id} — nothing paid off")
    return paid

async def get_overdue(session_id: int = None) -> list[dict]:
    if session_id is None: session_id = Config.SESSION_ID
    gd = await Database.fetchval("SELECT COALESCE(game_day,1) FROM maya_rp.sessions WHERE id=$1", session_id)
    rows = await Database.fetch("SELECT id,element_type,description,importance,introduced_game_day,payoff_deadline FROM maya_rp.chekhov_elements WHERE session_id=$1 AND status='unpaid' AND payoff_deadline<=$2 ORDER BY importance DESC,payoff_deadline ASC", session_id,gd)
    return [dict(r) for r in rows]

async def get_prompt(session_id: int = None) -> str:
    overdue = await get_overdue(session_id)
    if not overdue: return ""
    lines=["[UNPAID NARRATIVE ELEMENTS]"]
    for e in overdue[:5]:
        urg = "\u26a0" if e["importance"] in ("high","critical") else "\u25cb"
        lines.append(f"  {urg} {e['element_type']}: {e['description'][:60]} (day {e['introduced_game_day']})")
    return "\n".join(lines)

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    overdue = await get_overdue(session_id)
    return {"overdue":len(overdue)}
