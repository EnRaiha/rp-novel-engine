#!/usr/bin/env python3
"""Events Module — Ported from rpg-events skill (consequence-chain.js, encounter-scaler.js, encounter-tables.js, event-generator.js)"""
from __future__ import annotations
import random
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info, error

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
    """Roll one encounter. `session_id` is accepted for the tick's uniform call shape and read by
    nothing: this function touches no session state, it rolls a template.
    """
    if category is None:
        category = random.choice(list(ENCOUNTER_CATEGORIES.keys()))
    # An unknown category is still answered with a space phenomenon, which the CLI and the existing
    # wiring tests depend on, but the answer now says so instead of reporting the caller's own word
    # back as the category it used.
    fallback = category not in ENCOUNTER_CATEGORIES
    requested = category
    if fallback:
        category = "space_phenomena"
    templates = ENCOUNTER_CATEGORIES[category]
    event_type = random.choice(templates)
    scaled_difficulty = difficulty + random.randint(-2, 2)
    result = {"category": category, "event_type": event_type,
              "difficulty": max(1, scaled_difficulty),
              "tier": "standard" if scaled_difficulty <= 5 else "elite" if scaled_difficulty <= 8 else "boss"}
    if fallback:
        result["requested_category"] = requested
        result["available"] = sorted(ENCOUNTER_CATEGORIES)
    return result

async def log_event(session_id: int, event_type: str, title: str, description: str) -> dict:
    await Database.execute(
        "INSERT INTO maya_rp.events (session_id, event_type, title, description, tags) VALUES ($1,$2,$3,$4,'[]')",
        session_id, event_type, title, description,
    )
    return {"logged": True, "event_type": event_type, "title": title}

async def run_tick(session_id: int = None) -> dict:
    """Recent-events scan + catalog wiring + consequence planting (2026-08-14).

    - 3% per tick: a random event_catalog template fires as an encounter event.
    - 5% per recent high-importance event: plant a consequence_seed so
      consequences.py has something to resolve (seeds table was empty)."""
    import json as _j
    if session_id is None: session_id = Config.SESSION_ID
    try:
        events = await Database.fetch(
            "SELECT id, event_type, title, importance FROM maya_rp.events "
            "WHERE session_id=$1 ORDER BY id DESC LIMIT 5", session_id)
        fired = planted = 0
        if events and _r.random() < 0.03:
            from modules.event_catalog import get_random_encounter
            enc = get_random_encounter()
            await Database.execute(
                "INSERT INTO maya_rp.events (session_id, happened_at, event_type, title, description, tags, importance) "
                "VALUES ($1, NOW(), 'encounter', $2, $3, $4, 2)",
                session_id, f"Encounter: {enc['name'].replace('_',' ').title()}",
                enc["desc"], _j.dumps(["encounter", str(enc["diff"])]))
            fired = 1
        for ev in events:
            if (ev["importance"] or 0) >= 5 and _r.random() < 0.05:
                await Database.execute(
                    "INSERT INTO maya_rp.consequence_seeds (session_id, trigger_type, cause_description, effects_jsonb, planted_at_tick, can_be_prevented, status) "
                    "VALUES ($1,$2,$3,$4::jsonb,$5,true,'planted')",
                    session_id, ev["event_type"] or "event",
                    f"Ripple from: {ev['title']}",
                    _j.dumps([{"type": "stat", "target": "morale", "delta": -1}]),
                    await Database.fetchval("SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id) or 0)
                try:
                    from modules.chekhov import introduce
                    await introduce("consequence", ev["title"], importance="medium", payoff_window=15, session_id=session_id)
                except Exception as e:  # noqa: BLE001 - reported below
                    error("encounters", f"run_tick: {e}")
                planted += 1
                break
        info("events", f"Tick: {len(events)} recent, fired={fired}, planted={planted}")
        return {"recent_events": len(events), "encounters_fired": fired, "consequences_planted": planted}
    except Exception as e:
        error("events", f"tick failed for session {session_id}: {e}")
        return {"error": str(e)}

import random as _r
