#!/usr/bin/env python3
"""University — Simplified. Counts active/finished research projects per campus."""
from __future__ import annotations
from core.db import Database
from core.config import Config
from core.log import info

async def run_tick(session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    try:
        total = await Database.fetchval("SELECT COUNT(*) FROM maya_rp.research_projects") or 0
        finished = await Database.fetchval("SELECT COUNT(*) FROM maya_rp.research_projects WHERE unlocked=true") or 0
        info("university", f"Tick: {total} projects, {finished} completed")
        return {"total": total, "finished": finished}
    except Exception as e:
        info("university", f"Error: {e}")
        return {"error": str(e)}
