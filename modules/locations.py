#!/usr/bin/env python3
"""Location & Scene Management — tracks where characters are, who's present."""
from __future__ import annotations
from datetime import datetime
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info, warn

SHIP_LOCATIONS = [
    "bridge", "quarters", "observation_deck", "garden", "forge",
    "medbay", "brig", "engine_room", "armory", "cargo_bay",
    "mess_hall", "command_center", "hangar", "shuttle_bay",
]
COLONY_LOCATIONS = [
    "pelabuhan_port", "pelabuhan_square", "pelabuhan_temple",
]


async def set_player_location(session_id: int, location: str, ship: str = None):
    """Update where Izzat is.

    Writes `location`, the column readers use, and keeps `current_focus` as the prose
    line the CLI prints. The round trip used to be prose written here and prose read
    back out by `get_player_location`, which is why a location the parser could not
    split came back as the hardcoded `bridge`.

    The location is checked against the catalogue and only warned about, not refused:
    a name that is not in it cannot be matched by `get_characters_at_location`, so the
    scene cast would read empty for a reason nothing else would explain.
    """
    known = await Database.fetchval(
        "SELECT 1 FROM maya_rp.location_catalog WHERE name=$1", location)
    if not known:
        warn("locations", f"{location!r} is not in maya_rp.location_catalog; readers that match "
                          "scene_location against the catalogue will not find this scene")
    await Database.execute(
        "INSERT INTO maya_rp.player_context (session_id, location, current_focus, mood, updated_at) "
        "VALUES ($1, $2, $3, 'normal', NOW()) "
        "ON CONFLICT (session_id) DO UPDATE SET location=$2, current_focus=$3, updated_at=NOW()",
        session_id, location, f"Location: {location} on {ship or 'unknown'}")
    info("locations", f"Player moved to: {location} on {ship or 'unknown'}")


async def get_player_location(session_id: int) -> dict:
    """Where the player is, read from the column that owns it.

    `player_context.location` holds a `maya_rp.location_catalog.name`. Before that
    column existed this function parsed `current_focus` for the substring
    `Location:`, split on `" on "`, and returned the hardcoded `"bridge"` when the
    parse found nothing. Every session that never wrote a `current_focus` was
    therefore reported as standing on the bridge, and session 5 has no
    `player_context` row at all.

    The parse stays for a session that has not set the column, and it says so with
    a warning. Nothing is invented when both are empty: the answer is `None`, which
    the caller can pass to a filter and get no rows, rather than a place the engine
    guessed.

    @returns `location` (a catalogue name or None), `ship`, and `source`, which is
        `column`, `parsed` or `unset`.
    """
    row = await Database.fetchrow(
        "SELECT location, current_focus, mood FROM maya_rp.player_context WHERE session_id=$1",
        session_id)
    if row and row["location"]:
        return {"location": row["location"], "ship": None, "source": "column"}
    if row and row["current_focus"] and "Location:" in row["current_focus"]:
        parts = row["current_focus"].replace("Location: ", "").split(" on ")
        parsed = parts[0].strip()
        warn("locations", f"session {session_id} has no player_context.location; "
                          f"parsed {parsed!r} out of current_focus, which is prose")
        return {"location": parsed,
                "ship": parts[1].strip() if len(parts) > 1 else "Flagship",
                "source": "parsed"}
    return {"location": None, "ship": None, "source": "unset"}


async def set_character_presence(character_id: int, location: str, session_id: int = None):
    """Place a character at a location.

    The presence log is a global audit trail with no session column, so the log
    row is written unscoped by design. `characters.scene_location` is the column
    the engine actually reads back (char_query, char_locations, context), and it
    was never written here: the CLI could place a character for a year and no
    reader would see it move.
    """
    if session_id is None:
        session_id = Config.SESSION_ID
    await Database.execute(
        "INSERT INTO maya_rp.character_presence_log (character_table, character_id, new_presence, reason) "
        "VALUES ('characters', $1, $2, 'location_update')",
        character_id, location)
    tag = await Database.execute(
        "UPDATE maya_rp.characters SET scene_location=$1 WHERE id=$2 AND session_id=$3",
        location, character_id, session_id)
    if tag.rsplit(" ", 1)[-1] == "0":
        warn("locations", f"character #{character_id} is not in session {session_id}; "
                          "appearance unchanged")
    return None


async def get_characters_at_location(session_id: int, location: str | None) -> list[dict]:
    """Who is at this location, matched against the same vocabulary the player uses.

    `characters.scene_location` and `player_context.location` both name a row in
    `maya_rp.location_catalog`. Before the catalogue described the story, the
    player's side was a slug parsed from prose and the characters' side was free
    text like `MASTIKA — Royal Palace (household)`, so no filter could ever match
    and this function returned the whole active roster regardless of what it was
    asked. The parameter was accepted and dropped.

    An empty result is a real answer: nobody is recorded here. It is not the
    roster, and a caller must not substitute one for the other.

    @param location - a catalogue name, or None (an unset scene), which matches
        nothing and is reported.
    """
    if location is None:
        warn("locations", f"session {session_id} has no player location set; the scene cast is empty")
        return []
    rows = await Database.fetch(
        "SELECT c.name, c.bond, c.role "
        "FROM maya_rp.characters c "
        "WHERE c.session_id=$1 AND c.status='active' AND c.scene_location=$2 "
        "ORDER BY c.bond DESC",
        session_id, location)
    if not rows:
        warn("locations", f"no active character is recorded at {location!r} in session {session_id}; "
                          "the scene cast is empty and is not the roster")
    return [dict(r) for r in rows]


async def get_scene_context(session_id: int) -> dict:
    """Full scene packet for Maya.

    `location_source` and `present_scope` are carried so a reader can tell an unset
    scene from an empty one. Both arrive as an empty list otherwise, and they are
    not the same fact: one means nobody is here, the other means nobody has said
    where here is.
    """
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
        loc["location"]) if loc["location"] else None

    return {
        "location": loc["location"],
        "location_source": loc.get("source"),
        "ship": loc.get("ship"),
        "ship_time": ship_time,
        "present": present,
        "present_scope": "scene" if present else ("unset" if loc["location"] is None else "empty"),
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
