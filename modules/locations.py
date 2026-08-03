#!/usr/bin/env python3
"""Location & Scene Management — tracks where characters are, who's present."""
from __future__ import annotations
import json
from datetime import datetime
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info

SHIP_LOCATIONS = [
    "bridge", "quarters", "observation_deck", "garden", "forge",
    "medbay", "brig", "engine_room", "armory", "cargo_bay",
    "mess_hall", "command_center", "hangar", "shuttle_bay",
]
COLONY_LOCATIONS = [
    "pelabuhan_port", "pelabuhan_square", "pelabuhan_temple",
]


async def set_player_location(session_id: int, location: str, ship: str = None):
    """Update where Izzat is."""
    val = json.dumps({"location": location, "ship": ship, "updated": datetime.now().isoformat()})
    await Database.execute(
        "INSERT INTO maya_rp.player_context (session_id, current_focus, mood, updated_at) "
        "VALUES ($1, $2, 'normal', NOW()) "
        "ON CONFLICT (session_id) DO UPDATE SET current_focus=$2, updated_at=NOW()",
        session_id, f"Location: {location} on {ship or 'unknown'}")
    info("locations", f"Player moved to: {location} on {ship or 'unknown'}")


async def get_player_location(session_id: int) -> dict:
    row = await Database.fetchrow(
        "SELECT current_focus, mood FROM maya_rp.player_context WHERE session_id=$1",
        session_id)
    if row and row["current_focus"] and "Location:" in row["current_focus"]:
        parts = row["current_focus"].replace("Location: ", "").split(" on ")
        return {"location": parts[0].strip(), "ship": parts[1].strip() if len(parts) > 1 else "Flagship"}
    return {"location": "bridge", "ship": "Flagship"}


async def set_character_presence(character_id: int, location: str, session_id: int = None):
    """Place a character at a location."""
    if session_id is None:
        session_id = Config.SESSION_ID
    await Database.execute(
        "INSERT INTO maya_rp.character_presence_log (character_table, character_id, new_presence, reason) "
        "VALUES ('characters', $1, $2, 'location_update')",
        character_id, location)


async def get_characters_at_location(session_id: int, location: str) -> list[dict]:
    """Who else is here? (Uses characters table directly — presence log has different schema)"""
    rows = await Database.fetch(
        "SELECT c.name, c.bond, c.role "
        "FROM maya_rp.characters c "
        "WHERE c.session_id=$1 AND c.status='active' "
        "ORDER BY c.bond DESC",
        session_id)
    return [dict(r) for r in rows]


async def get_scene_context(session_id: int) -> dict:
    """Full scene packet for Maya."""
    loc = await get_player_location(session_id)
    present = await get_characters_at_location(session_id, loc["location"])

    hour = datetime.now().hour
    if 6 <= hour < 12: ship_time = "morning"
    elif 12 <= hour < 18: ship_time = "afternoon"
    elif 18 <= hour < 22: ship_time = "evening"
    else: ship_time = "night cycle"

    atmosphere = await Database.fetchrow(
        "SELECT default_lighting, default_sound, default_smell, atmosphere "
        "FROM maya_rp.location_catalog WHERE name=$1",
        loc["location"])

    return {
        "location": loc["location"],
        "ship": loc.get("ship"),
        "ship_time": ship_time,
        "present": present,
        "atmosphere": dict(atmosphere) if atmosphere else {
            "default_lighting": "standard ship lighting",
            "atmosphere": "neutral",
        },
    }


async def run_tick(session_id: int = None) -> dict:
    """Location tick — currently idle, presence managed manually."""
    if session_id is None:
        session_id = Config.SESSION_ID
    return {"status": "locations_ready"}


# ─── CLI Quick Commands ──────────────────────────────────────────

async def cmd_goto(location: str, ship: str = None, session_id: int = None):
    """CLI: move player to a location."""
    if session_id is None:
        session_id = Config.SESSION_ID
    if ship is None:
        ship = "Flagship"
    await set_player_location(session_id, location, ship)
    ctx = await get_scene_context(session_id)
    print(f"\nMoved to: {location} on {ship}")
    print(f"Time: {ctx['ship_time']}")
    print(f"Present: {', '.join(p['name'] for p in ctx['present']) if ctx['present'] else 'No one'}")
    if ctx.get("atmosphere"):
        a = ctx["atmosphere"]
        print(f"Atmosphere: {a.get('default_lighting','')} ({a.get('atmosphere','')})")
    return ctx
