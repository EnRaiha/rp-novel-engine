#!/usr/bin/env python3
"""Disasters — Ported from Rust disasters.rs."""
from __future__ import annotations
import random
from core.db import Database
from core.config import Config
from core.log import info

async def tick_disasters(session_id: int) -> list[dict]:
    events = []
    active = await Database.fetch(
        "SELECT d.id, d.name, d.severity, d.ticks_remaining, t.base_damage, t.category "
        "FROM maya_rp.active_disasters d JOIN maya_rp.disaster_templates t ON d.template_id = t.id "
        "WHERE d.session_id=$1 AND d.status='active' AND d.ticks_remaining > 0", session_id)

    for d in active:
        new_ticks = d["ticks_remaining"] - 1
        damage = d["base_damage"] * d["severity"] * 0.3

        if d["category"] == "economic":
            await Database.execute("UPDATE maya_rp.resources SET credits=GREATEST(0, credits-$1::bigint) WHERE session_id=$2", int(damage), session_id)
            events.append({"type": "disaster", "title": "Economic Damage", "desc": f"Market drains {int(damage)} credits"})
        elif d["category"] == "plague":
            # Plague hits TERRITORY population (unified model) — not colonies.
            await Database.execute(
                "UPDATE maya_rp.territory SET population=GREATEST(0, population-$1::bigint) "
                "WHERE session_id=$2 AND controlling_faction='Setia Empire' AND status != 'abandoned'",
                int(damage * 100), session_id)
            events.append({"type": "disaster", "title": "Plague",
                           "desc": f"Pathogen spreads — {int(damage * 100)} population lost"})
        else:
            await Database.execute("UPDATE maya_rp.ships SET hull_current=GREATEST(0, hull_current-$1::int) WHERE session_id=$2 AND status='active'", int(damage), session_id)
            events.append({"type": "disaster", "title": f"{d['category'].title()} Damage", "desc": f"{int(damage)} hull damage applied"})

        if new_ticks <= 0:
            await Database.execute("UPDATE maya_rp.active_disasters SET status='resolved', ticks_remaining=0 WHERE id=$1", d["id"])
        else:
            await Database.execute("UPDATE maya_rp.active_disasters SET ticks_remaining=$1 WHERE id=$2", new_ticks, d["id"])

    return events

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    try:
        events = await tick_disasters(session_id)
        info("disasters", f"Tick: {len(events)} disaster events")
        return {"disaster_events": len(events)}
    except Exception as e:
        info("disasters", f"Error: {e}")
        return {"error": str(e)}
