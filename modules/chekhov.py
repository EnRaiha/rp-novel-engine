#!/usr/bin/env python3
"""Chekhov's Gun Tracker — introduced elements must pay off."""
from __future__ import annotations
from typing import Any
from core.db import Database
from core.session import require_session
from core.log import info

def _writable_session(session_id: int | None) -> int:
    """Resolve the session for one call and refuse a frozen campaign.

    @param session_id - caller's session; `None` resolves through `core.session.require_session`.
    @returns the resolved session id.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    from core.ooc import _refuse_frozen

    sid = session_id if session_id is not None else require_session(None)
    _refuse_frozen(sid)
    return sid


#: `importance` is varchar. A plain `ORDER BY importance DESC` sorted text: 'medium' before 'high',
#: and '9.7' before '10'. Named levels map to a 0-10 scale and numeric strings keep their value.
_IMPORTANCE_RANK = (
    "CASE WHEN importance ~ '^[0-9]+(\\.[0-9]+)?$' THEN importance::numeric "
    "WHEN importance='critical' THEN 10 WHEN importance='high' THEN 8 "
    "WHEN importance='medium' THEN 5 WHEN importance='low' THEN 2 ELSE 0 END"
)


async def introduce(elem_type: str, desc: str, importance: str = "medium", payoff_window: int = 15, session_id: int = None) -> int:
    """Introduce one element that must pay off within `payoff_window` days.

    @param session_id - session to write; `None` resolves through `require_session`.
    @returns the new element id.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
    if payoff_window < 0:
        raise ValueError(f"payoff_window cannot be negative, got {payoff_window}")
    gd = await Database.fetchval("SELECT COALESCE(game_day,1) FROM maya_rp.sessions WHERE id=$1", session_id)
    return await Database.fetchval("INSERT INTO maya_rp.chekhov_elements(session_id,element_type,description,importance,introduced_game_day,payoff_deadline,status) VALUES($1,$2,$3,$4,$5,$6,'unpaid') RETURNING id", session_id,elem_type,desc,importance,gd,gd+payoff_window)

async def payoff(element_id: int, method: str, session_id: int = None) -> bool:
    """Mark one element paid off. Returns whether the element was found.

    Scoped by session: `WHERE id=$3` alone let a payoff land on another
    campaign's element, and the caller was told nothing either way.

    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
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
    """Unpaid elements at or past their deadline, most important first."""
    if session_id is None: session_id = require_session(None)
    gd = await Database.fetchval("SELECT COALESCE(game_day,1) FROM maya_rp.sessions WHERE id=$1", session_id)
    rows = await Database.fetch("SELECT id,element_type,description,importance,introduced_game_day,payoff_deadline FROM maya_rp.chekhov_elements WHERE session_id=$1 AND status='unpaid' AND payoff_deadline<=$2 ORDER BY " + _IMPORTANCE_RANK + " DESC,payoff_deadline ASC", session_id,gd)
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
    """Count overdue elements. Guards the session like the writers.

    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
    overdue = await get_overdue(session_id)
    return {"overdue":len(overdue)}
