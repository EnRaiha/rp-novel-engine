#!/usr/bin/env python3
"""Disasters — Ported from Rust disasters.rs."""
from __future__ import annotations
import random
from core.db import Database
from core.log import info
from core.session import require_session


def _writable_session(session_id: int | None) -> int:
    """Resolve the session for one call and refuse a frozen campaign.

    Sessions 3 and 5 are reference data; a writer that skipped this check mutated them.

    @param session_id - caller's session; `None` resolves through `core.session.require_session`.
    @returns the resolved session id.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    from core.ooc import _refuse_frozen

    sid = require_session(session_id)
    _refuse_frozen(sid)
    return sid

async def tick_disasters(session_id: int) -> list[dict]:
    """Apply one tick of every active disaster in this campaign.

    Each disaster claims its tick first (the countdown UPDATE, guarded by `status='active'` and
    `ticks_remaining > 0`) and applies its damage in the same transaction. The damage and the
    countdown were separate statements, so an error between them repeated the damage on the next
    tick, and two concurrent ticks both damaged and both counted down.

    @param session_id - campaign; `None` resolves through `require_session`.
    @returns one event dict per disaster that ticked.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
    events = []
    active = await Database.fetch(
        "SELECT d.id, d.name, d.severity, d.ticks_remaining, t.base_damage, t.category "
        "FROM maya_rp.active_disasters d JOIN maya_rp.disaster_templates t ON d.template_id = t.id "
        "WHERE d.session_id=$1 AND d.status='active' AND d.ticks_remaining > 0", session_id)

    for d in active:
        damage = d["base_damage"] * d["severity"] * 0.3

        async with Database.transaction() as conn:
            ticked = await conn.fetchval(
                "UPDATE maya_rp.active_disasters SET ticks_remaining = ticks_remaining - 1, "
                "status = CASE WHEN ticks_remaining - 1 <= 0 THEN 'resolved' ELSE status END "
                "WHERE id=$1 AND status='active' AND ticks_remaining > 0 RETURNING id", d["id"])
            if ticked is None:
                continue
            if d["category"] == "economic":
                row = await conn.fetchrow(
                    "UPDATE maya_rp.resources SET credits=GREATEST(0, credits-$1::bigint) "
                    "WHERE session_id=$2 RETURNING credits", int(damage), session_id)
                events.append({"type": "disaster", "title": "Economic Damage",
                               "desc": f"Market drains {int(damage)} credits",
                               "applied": row is not None})
            elif d["category"] == "plague":
                # Plague hits TERRITORY population (unified model) — not colonies.
                row = await conn.fetchrow(
                    "UPDATE maya_rp.territory SET population=GREATEST(0, population-$1::bigint) "
                    "WHERE session_id=$2 AND controlling_faction='Setia Empire' AND status != 'abandoned' "
                    "RETURNING id",
                    int(damage * 100), session_id)
                events.append({"type": "disaster", "title": "Plague",
                               "desc": f"Pathogen spreads — {int(damage * 100)} population lost",
                               "applied": row is not None})
            else:
                row = await conn.fetchrow(
                    "UPDATE maya_rp.ships SET hull_current=GREATEST(0, hull_current-$1::int) "
                    "WHERE session_id=$2 AND status='active' RETURNING id",
                    int(damage), session_id)
                events.append({"type": "disaster", "title": f"{d['category'].title()} Damage",
                               "desc": f"{int(damage)} hull damage applied",
                               "applied": row is not None})
        if row is None:
            # Three UPDATEs matched nothing when the session had no resources row,
            # no Setia territory or no active ship, and the event still claimed it.
            info("disasters",
                 f"{d['name']}: no row in session {session_id} to take {d['category']} damage")

    return events

async def run_tick(session_id: int | None = None) -> dict:
    """Tick every active disaster. @raises core.ooc.FrozenSession - the campaign is frozen."""
    session_id = _writable_session(session_id)
    try:
        events = await tick_disasters(session_id)
        info("disasters", f"Tick: {len(events)} disaster events")
        return {"disaster_events": len(events)}
    except Exception as e:
        info("disasters", f"Error: {e}")
        return {"error": str(e)}
