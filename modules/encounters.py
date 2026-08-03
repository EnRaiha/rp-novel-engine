#!/usr/bin/env python3
"""Events Module — Ported from rpg-events skill (consequence-chain.js, encounter-scaler.js, encounter-tables.js, event-generator.js)"""
from __future__ import annotations
import random
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info

ENCOUNTER_CATEGORIES = {
    "space_phenomena": ["solar_flare", "nebula_storm", "gravity_anomaly", "wormhole", "void_tear"],
    "combat": ["pirate_raiders", "hostile_patrol", "ambush", "derelict_trap", "fleet_skirmish"],
    "trade": ["merchant_convoy", "smuggler_cache", "refugee_flotilla", "black_market"],
    "science": ["ancient_ruins", "alien_artifact", "signal_source", "strange_readings"],
    "diplomacy": ["faction_emissary", "distress_call", "defector", "treaty_offer"],
    "disaster": ["engine_failure", "hull_breach", "fire", "plague_outbreak", "mutiny"],
}

def get_encounter_templates() -> dict:
    templates = {}
    for cat, events in ENCOUNTER_CATEGORIES.items():
        for ev in events:
            templates[ev] = {
                "category": cat, "difficulty": random.randint(2, 8),
                "description": f"An encounter of type {ev}",
                "consequences": {
                    "success": f"Successfully navigated {ev}",
                    "failure": f"Failed to handle {ev}",
                },
            }
    return templates

async def generate_event(session_id: int, category: str | None = None, difficulty: int = 5) -> dict:
    if category is None:
        category = random.choice(list(ENCOUNTER_CATEGORIES.keys()))
    templates = ENCOUNTER_CATEGORIES.get(category, ENCOUNTER_CATEGORIES["space_phenomena"])
    event_type = random.choice(templates)
    scaled_difficulty = difficulty + random.randint(-2, 2)
    return {"category": category, "event_type": event_type, "difficulty": max(1, scaled_difficulty),
            "tier": "standard" if scaled_difficulty <= 5 else "elite" if scaled_difficulty <= 8 else "boss"}

async def log_event(session_id: int, event_type: str, title: str, description: str) -> dict:
    await Database.execute(
        "INSERT INTO maya_rp.events (session_id, event_type, title, description, tags) VALUES ($1,$2,$3,$4,'[]')",
        session_id, event_type, title, description,
    )
    return {"logged": True, "event_type": event_type, "title": title}

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    try:
        events = await Database.fetch("SELECT id, event_type, title FROM maya_rp.events WHERE session_id=$1 ORDER BY id DESC LIMIT 5", session_id)
        info("events", f"Tick: {len(events)} recent events")
        return {"recent_events": len(events)}
    except Exception as e:
        info("events", f"Error: {e}")
        return {"error": str(e)}
