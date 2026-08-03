#!/usr/bin/env python3
"""Faction AI — Simplified. Update faction state with real column names."""
from __future__ import annotations
import random
from core.db import Database
from core.config import Config
from core.log import info

async def run_tick(session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    try:
        factions = await Database.fetch(
            "SELECT id, name, reputation, pirate_fleet_power, treasury, economic_strength "
            "FROM maya_rp.factions WHERE session_id=$1", session_id)
        for f in factions:
            # Fleet power drift
            fp = f["pirate_fleet_power"] or 0
            if random.random() < 0.3:
                fp += random.randint(0, 5)
                await Database.execute("UPDATE maya_rp.factions SET pirate_fleet_power=$1 WHERE id=$2", fp, f["id"])
            # Treasury drift
            tres = f["treasury"] or 0
            if random.random() < 0.2:
                tres += random.randint(-10000, 10000)
                await Database.execute("UPDATE maya_rp.factions SET treasury=$1 WHERE id=$2", tres, f["id"])
            # Rep decay toward 0
            rep = f["reputation"] or 0
            if rep > 0:
                rep = max(0, rep - 1)
                await Database.execute("UPDATE maya_rp.factions SET reputation=GREATEST(-100,LEAST(100,$1)) WHERE id=$2", rep, f["id"])
        info("faction_ai", f"Tick: {len(factions)} factions")
        return {"factions": len(factions)}
    except Exception as e:
        info("faction_ai", f"Error: {e}")
        return {"error": str(e)}
