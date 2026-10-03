#!/usr/bin/env python3
"""Narrator — Ported from Rust narrator.rs. Generates narrative prose from game events."""
from __future__ import annotations
import random
from core.db import Database
from core.config import Config
from core.log import info

TEMPLATES = {
    "build": ["A new vessel joins the fleet: {title}.", "Construction complete: {title} slides into formation."],
    "battle": ["The fleet engages the enemy. {title}.", "Battle report: {title}."],
    "research": ["Laboratories report progress on {title}.", "Scientific breakthrough: {title}."],
    "academy": ["{title}. Another graduate enters service.", "Training complete: {title}."],
    "disaster": ["Crisis unfolds: {title}.", "Emergency: {title}."],
    "siege": ["{title}. The campaign continues.", "Siege progress: {title}."],
    "default": ["Fleet log: {title}.", "Narrative event: {title}."],
}

async def narrate_event(event_type: str, title: str, description: str) -> str:
    templates = TEMPLATES.get(event_type, TEMPLATES["default"])
    template = random.choice(templates)
    return template.format(title=title) + (" " + description if description else "")

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    try:
        events = await Database.fetch("SELECT event_type, title, description FROM maya_rp.events WHERE session_id=$1 ORDER BY id DESC LIMIT 3", session_id)
        narratives = [await narrate_event(e["event_type"], e["title"], e["description"] or "") for e in events]
        info("narrator", f"Narrated {len(narratives)} events")
        # The prose used to be built and thrown away: the tick returned only a count.
        return {"narrated": len(narratives), "narratives": narratives}
    except Exception as e:
        info("narrator", f"Error: {e}")
        return {"error": str(e)}
