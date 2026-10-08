#!/usr/bin/env python3
"""Events Module — Ported from rpg-events skill (consequence-chain.js, encounter-scaler.js, encounter-tables.js, event-generator.js)"""
from __future__ import annotations
import random
from typing import Any
from core.db import Database
from core.log import info, error
from core.session import require_session

#: Tag `run_tick` writes on an event once it has planted that event's consequence seed.
#: `consequence_seeds` carries no event reference, so without a marker the 5-event scan
#: planted a fresh seed for the same high-importance event on every tick it stayed in the window.
SEEDED_TAG = "consequence_seeded"


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
    """Write one event row.

    @param session_id - campaign; `None` resolves through `require_session`.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
    await Database.execute(
        "INSERT INTO maya_rp.events (session_id, event_type, title, description, tags) VALUES ($1,$2,$3,$4,'[]')",
        session_id, event_type, title, description,
    )
    return {"logged": True, "event_type": event_type, "title": title}

async def run_tick(session_id: int | None = None) -> dict:
    """Recent-events scan + catalog wiring + consequence planting (2026-08-14).

    - 3% per tick: a random event_catalog template fires as an encounter event.
    - 5% per recent high-importance event: plant a consequence_seed so
      consequences.py has something to resolve (seeds table was empty).

    An event that already planted a seed carries `SEEDED_TAG` and is skipped. The seed insert and the
    tag write share one transaction.

    @param session_id - campaign; `None` resolves through `require_session`.
    @returns `{recent_events, encounters_fired, consequences_planted}`, or `{error}` when a query raises.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    import json as _j
    session_id = _writable_session(session_id)
    try:
        events = await Database.fetch(
            "SELECT id, event_type, title, importance, "
            "COALESCE(tags, '[]'::jsonb) ? $2 AS seeded FROM maya_rp.events "
            "WHERE session_id=$1 ORDER BY id DESC LIMIT 5", session_id, SEEDED_TAG)
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
            if ev["seeded"]:
                continue
            if (ev["importance"] or 0) >= 5 and _r.random() < 0.05:
                async with Database.transaction() as conn:
                    # The tag write is the claim: a concurrent tick that read the same untagged event
                    # matches no row here and plants nothing.
                    claimed = await conn.fetchval(
                        "UPDATE maya_rp.events SET tags = COALESCE(tags, '[]'::jsonb) || $2::jsonb "
                        "WHERE id=$1 AND session_id=$3 AND NOT (COALESCE(tags, '[]'::jsonb) ? $4) "
                        "RETURNING id", ev["id"], _j.dumps([SEEDED_TAG]), session_id, SEEDED_TAG)
                    if claimed is None:
                        continue
                    tick = await conn.fetchval("SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id) or 0
                    await conn.execute(
                        "INSERT INTO maya_rp.consequence_seeds (session_id, trigger_type, cause_description, effects_jsonb, planted_at_tick, can_be_prevented, status) "
                        "VALUES ($1,$2,$3,$4::jsonb,$5,true,'planted')",
                        session_id, ev["event_type"] or "event",
                        f"Ripple from: {ev['title']}",
                        _j.dumps([{"type": "stat", "target": "morale", "delta": -1}]),
                        tick)
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
