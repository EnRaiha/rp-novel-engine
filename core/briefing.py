#!/usr/bin/env python3
"""Briefing Engine — LLM-optimized session summary. <2000 tokens per briefing."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info

async def generate_briefing(session_id: int = None) -> dict[str, Any]:
    """Generate a compact, LLM-optimized briefing packet."""
    if session_id is None:
        session_id = Config.SESSION_ID

    await Database.init()
    briefing = {}

    # 1. Session state
    s = await Database.fetchrow(
        "SELECT name, status, game_day FROM maya_rp.sessions WHERE id=$1", session_id)
    if s is None:
        raise ValueError(f"no session {session_id}: maya_rp.sessions has no such row")
    # A NULL game_day is an unset clock; a game_day of 0 is day zero, not day one.
    game_day = s["game_day"] if s["game_day"] is not None else 1
    briefing["session"] = f"Day {game_day}, {s['status']} — {s['name']}"

    # 2. Active crises (max 5)
    briefing["crises"] = [
        {"title": r["hook_type"], "description": r.get("description",""), "status": r["status"]}
        for r in await Database.fetch(
            "SELECT hook_type, description, status FROM maya_rp.narrative_hooks "
            "WHERE session_id=$1 AND status='active' ORDER BY id LIMIT 5",
            session_id)]

    # 3. Where the scene is, from the column that owns it.
    #
    # This was a second copy of the same parse `modules.locations.get_player_location` did — look for
    # the substring `Location:` in `current_focus`, split on `" on "` — with the same hardcoded
    # `bridge` when it found nothing. Two readers of one field, both guessing, and `player_context`
    # held no rows for any session, so the guess was the only path either of them ever took.
    loc = await Database.fetchrow(
        "SELECT location, current_focus FROM maya_rp.player_context WHERE session_id=$1",
        session_id)
    if loc and loc["location"]:
        current_location = loc["location"]
    elif loc and loc["current_focus"] and "Location:" in loc["current_focus"]:
        current_location = loc["current_focus"].replace("Location: ", "").split(" on ")[0].strip()
    else:
        current_location = None
    briefing["location"] = current_location
    briefing["present"] = [
        {"name": r["name"], "bond": r["bond"], "role": r["role"]}
        for r in await Database.fetch(
            "SELECT c.name, c.bond, c.role FROM maya_rp.characters c "
            "WHERE c.session_id=$1 AND c.status='active' "
            "ORDER BY c.bond DESC LIMIT 10",
            session_id)]

    # 4. Companion emotional states (bond >= 5 with pending reactions)
    briefing["companion_states"] = [
        dict(r) for r in await Database.fetch(
            "SELECT c.name, ra.arc_stage, ra.saturation_pct, ra.pursuit_stage "
            "FROM maya_rp.romance_arcs ra JOIN maya_rp.characters c ON c.id=ra.character_id "
            "WHERE ra.session_id=$1 AND c.session_id=$1 AND c.bond >= 5 ORDER BY c.bond DESC LIMIT 8",
            session_id)]

    # 5. Resource pressure
    r = await Database.fetchrow(
        "SELECT credits, alloys, fuel FROM maya_rp.resources WHERE session_id=$1", session_id)
    briefing["resource_pressure"] = []
    if r:
        # A NULL figure is a figure the ledger does not hold, so the briefing does
        # not claim the treasury is low on it.
        for column, threshold, alert in (
            ("fuel", 500_000, "FUEL LOW"),
            ("credits", 200_000, "CREDITS LOW"),
            ("alloys", 100_000, "ALLOYS LOW"),
        ):
            value = r[column]
            if value is not None and value < threshold:
                briefing["resource_pressure"].append(alert)

    # 6. Last 3 narrative beats
    briefing["recent_beats"] = [
        dict(r) for r in await Database.fetch(
            "SELECT title, description FROM maya_rp.events WHERE session_id=$1 "
            "ORDER BY id DESC LIMIT 3", session_id)]

    # 7. Pending player choices
    briefing["pending_choices"] = [
        {"id": r["id"], "title": r.get("situation", "Choice"), "description": ""}
        for r in await Database.fetch(
            "SELECT id, situation, options FROM maya_rp.choices WHERE session_id=$1 AND picked IS NULL",
            session_id)]

    # 8. Unexpired character memories (overdue callbacks)
    briefing["overdue_memories"] = [
        dict(r) for r in await Database.fetch(
            "SELECT cm.character_id, c.name, cm.memory_type, cm.content "
            "FROM maya_rp.character_memories cm JOIN maya_rp.characters c ON c.id=cm.character_id "
            "WHERE cm.session_id=$1 AND c.session_id=$1 AND cm.recalled_count=0 AND cm.emotional_weight >= 7 "
            "ORDER BY cm.emotional_weight DESC LIMIT 3",
            session_id)]

    # 9. Active wars
    briefing["wars"] = [
        dict(r) for r in await Database.fetch(
            "SELECT opponent_faction, phase, status, casus_belli FROM maya_rp.wars "
            "WHERE session_id=$1 AND status='active'", session_id)]

    # 10. Flag state
    rp_flag = Path("/home/maya/Bumi-Hijau/main/rp-leave-flag.txt")
    briefing["leave_mode"] = rp_flag.read_text().strip() if rp_flag.exists() else "NONE"
    briefing["rp_tone"] = Config.RP_TONE

    return briefing


def briefing_to_prompt(briefing: dict) -> str:
    """Convert briefing dict to compact prompt block."""
    lines = ["## SITUATION BRIEFING", ""]
    lines.append(briefing["session"])

    if briefing.get("crises"):
        lines.append("\n### ACTIVE CRISES")
        for c in briefing["crises"][:5]:
            lines.append(f"- {c.get('title') or '?'}: {(c.get('description') or '?')[:80]}")

    lines.append(f"\n### LOCATION: {briefing.get('location','bridge')}")

    if briefing.get("present"):
        lines.append("\n### PRESENT")
        for p in briefing["present"]:
            bond = p.get("bond") or 0
            icon = "\u2665" if bond >= 7 else "\u25cb" if bond >= 3 else "\u00b7"
            lines.append(f"- {icon} {p['name']} ({p.get('role') or '?'})")

    if briefing.get("companion_states"):
        lines.append("\n### COMPANION STATES")
        for cs in briefing["companion_states"]:
            lines.append(f"- {cs.get('name') or '?'}: {cs.get('arc_stage') or '?'}, sat {cs.get('saturation_pct') or 0}%")

    if briefing.get("resource_pressure"):
        lines.append(f"\n### \u26a0 RESOURCE ALERTS: {', '.join(briefing['resource_pressure'])}")

    if briefing.get("pending_choices"):
        lines.append("\n### PENDING DECISIONS")
        for ch in briefing["pending_choices"]:
            lines.append(f"- [ ] {ch.get('title') or '?'}")

    if briefing.get("overdue_memories"):
        lines.append("\n### UNRESOLVED MEMORIES")
        for m in briefing["overdue_memories"]:
            lines.append(f"- {m['name']} still remembers: {m['content'][:60]}...")

    if briefing.get("wars"):
        lines.append("\n### ACTIVE WARS")
        for w in briefing["wars"]:
            lines.append(f"- {w['opponent_faction'] or '?'} ({w['phase'] or '?'})")

    lines.append(f"\n### FLAGS: leave_mode={briefing.get('leave_mode','NONE')}, tone={briefing.get('rp_tone','English')}")
    return "\n".join(lines)


async def cmd_briefing(session_id: int = None):
    """CLI command: generate and print briefing."""
    if session_id is None:
        session_id = Config.SESSION_ID
    await Database.init()
    briefing = await generate_briefing(session_id)
    print(briefing_to_prompt(briefing))
    await Database.close()
    return briefing
