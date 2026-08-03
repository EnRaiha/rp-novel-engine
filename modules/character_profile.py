#!/usr/bin/env python3
"""
Character Profile Engine — Manages face, body, wardrobe, and inventory.
Auto-dresses characters based on the Pacing Director's narrative mode.

Usage:
    from modules.character_profile import get_character_card
    card = await get_character_card(42, session_id=3)
"""
from __future__ import annotations
import json
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info


# ─── Profile CRUD ──────────────────────────────────────────────────────

async def update_profile(character_id: int, profile_data: dict, session_id: int = None):
    """Set the static physical profile of a character (face, body, voice)."""
    if session_id is None:
        session_id = Config.SESSION_ID
    await Database.execute(
        "UPDATE maya_rp.characters SET profile_jsonb = $1 WHERE id = $2 AND session_id = $3",
        json.dumps(profile_data), character_id, session_id,
    )
    info("profile", f"Profile updated for character {character_id}")


async def add_to_wardrobe(character_id: int, outfit: dict, session_id: int = None):
    """Add a new outfit to a character's closet."""
    if session_id is None:
        session_id = Config.SESSION_ID
    current = await Database.fetchval(
        "SELECT wardrobe_jsonb FROM maya_rp.characters WHERE id = $1 AND session_id = $2",
        character_id, session_id,
    )
    wardrobe = json.loads(current) if current else []
    wardrobe.append(outfit)
    await Database.execute(
        "UPDATE maya_rp.characters SET wardrobe_jsonb = $1 WHERE id = $2 AND session_id = $3",
        json.dumps(wardrobe), character_id, session_id,
    )


async def set_outfit(character_id: int, outfit_id: str, session_id: int = None):
    """Manually force a character to wear a specific outfit from their wardrobe."""
    if session_id is None:
        session_id = Config.SESSION_ID
    wardrobe_raw = await Database.fetchval(
        "SELECT wardrobe_jsonb FROM maya_rp.characters WHERE id = $1 AND session_id = $2",
        character_id, session_id,
    )
    wardrobe = json.loads(wardrobe_raw) if wardrobe_raw else []
    outfit = next((o for o in wardrobe if o.get("id") == outfit_id), None)
    if outfit:
        await Database.execute(
            "UPDATE maya_rp.characters SET current_outfit = $1 WHERE id = $2 AND session_id = $3",
            json.dumps(outfit), character_id, session_id,
        )
        info("profile", f"{outfit.get('name', 'Unknown')} equipped", char_id=character_id)


async def add_item(character_id: int, item: dict, session_id: int = None):
    """Add an item to a character's inventory."""
    if session_id is None:
        session_id = Config.SESSION_ID
    current = await Database.fetchval(
        "SELECT inventory_jsonb FROM maya_rp.characters WHERE id = $1 AND session_id = $2",
        character_id, session_id,
    )
    inv = json.loads(current) if current else []
    inv.append(item)
    await Database.execute(
        "UPDATE maya_rp.characters SET inventory_jsonb = $1 WHERE id = $2 AND session_id = $3",
        json.dumps(inv), character_id, session_id,
    )


# ─── Auto-Dress ────────────────────────────────────────────────────────

# Maps Pacing Director modes to outfit tag priority
MODE_TAG_PRIORITY: dict[str, list[str]] = {
    "combat":      ["combat", "military", "tactical"],
    "crisis":      ["combat", "military", "tactical"],
    "social":      ["formal", "social", "casual"],
    "intimate":    ["intimate", "casual", "sleepwear"],
    "exploration": ["exploration", "tactical", "casual"],
    "political":   ["formal", "political", "military"],
    "downtime":    ["casual", "comfortable", "off-duty"],
    "horror":      ["tactical", "casual", "combat"],
}


async def auto_dress_for_mode(character_id: int, mode: str, session_id: int = None) -> bool:
    """
    Automatically change clothes based on narrative mode.
    Combat → Armour. Intimate → Casual/Sleepwear. Political → Formal.
    Returns True if outfit was changed.
    """
    if session_id is None:
        session_id = Config.SESSION_ID

    wardrobe_raw = await Database.fetchval(
        "SELECT wardrobe_jsonb FROM maya_rp.characters WHERE id = $1 AND session_id = $2",
        character_id, session_id,
    )
    wardrobe = json.loads(wardrobe_raw) if wardrobe_raw else []
    if not wardrobe:
        return False  # No wardrobe = nothing to dress in

    desired_tags = MODE_TAG_PRIORITY.get(mode, ["casual"])

    # Find best matching outfit by tag priority
    chosen = wardrobe[0]  # Fallback to first item
    for tag in desired_tags:
        match = next((o for o in wardrobe if tag in o.get("tags", [])), None)
        if match:
            chosen = match
            break

    # Skip if already wearing the same outfit
    current_raw = await Database.fetchval(
        "SELECT current_outfit FROM maya_rp.characters WHERE id = $1 AND session_id = $2",
        character_id, session_id,
    )
    current = json.loads(current_raw) if current_raw else {}

    if chosen.get("id") != current.get("id"):
        await Database.execute(
            "UPDATE maya_rp.characters SET current_outfit = $1 WHERE id = $2 AND session_id = $3",
            json.dumps(chosen), character_id, session_id,
        )
        return True
    return False


async def auto_dress_all_present(session_id: int = None) -> dict:
    """
    Auto-dress all active, present characters based on current pacing mode.
    Called on tick and on scene changes.
    """
    if session_id is None:
        session_id = Config.SESSION_ID

    from core.pacing import PacingDirector
    mode_data = await PacingDirector.get_mode(session_id)
    mode = mode_data.get("mode", "downtime")

    # Get characters in the current scene or active characters
    chars = await Database.fetch(
        """SELECT id, name FROM maya_rp.characters
           WHERE session_id=$1 AND status='active'
             AND (presence='available' OR presence IS NULL)
           ORDER BY COALESCE(bond, 0) DESC LIMIT 15""",
        session_id,
    )

    changed = 0
    for c in chars:
        if await auto_dress_for_mode(c["id"], mode, session_id):
            changed += 1

    if changed:
        info("profile", f"Auto-dressed {changed} characters for mode={mode}")

    return {"status": "ok", "auto_dressed": changed, "mode": mode}


# ─── Character Card (LLM-readable) ────────────────────────────────────

async def get_character_card(character_id: int, session_id: int = None) -> str:
    """
    Generate a compact, LLM-ready string of the character's complete physical state.
    This is what gets injected into the system prompt or used by rp-look.
    """
    if session_id is None:
        session_id = Config.SESSION_ID

    row = await Database.fetchrow(
        """SELECT name, role, profile_jsonb, current_outfit, inventory_jsonb
           FROM maya_rp.characters WHERE id = $1 AND session_id = $2""",
        character_id, session_id,
    )
    if not row:
        return "Character not found."

    profile = json.loads(row["profile_jsonb"]) if row["profile_jsonb"] else {}
    outfit = json.loads(row["current_outfit"]) if row["current_outfit"] else {}
    inventory = json.loads(row["inventory_jsonb"]) if row["inventory_jsonb"] else []

    lines = [
        f"── {row['name'].upper()} ──",
        f"  Role: {row['role'] or 'Unknown'}",
    ]

    # Face
    face = profile.get("face", {})
    if face.get("eyes"):
        lines.append(f"  Eyes: {face['eyes']}")
    if face.get("hair"):
        lines.append(f"  Hair: {face['hair']}")
    if face.get("skin"):
        lines.append(f"  Skin: {face['skin']}")
    if face.get("features"):
        lines.append(f"  Features: {face['features']}")

    # Body
    body = profile.get("body", {})
    if body.get("build"):
        lines.append(f"  Build: {body['build']}")
    if body.get("height"):
        lines.append(f"  Height: {body['height']}")
    if body.get("distinguishing"):
        lines.append(f"  Distinguishing: {body['distinguishing']}")

    # Voice
    if profile.get("voice"):
        lines.append(f"  Voice: {profile['voice']}")

    # Current Outfit
    if outfit.get("name"):
        desc = outfit.get("desc", "")
        lines.append(f"  Wearing: {outfit['name']}" + (f" ({desc})" if desc else ""))

    # Visible inventory
    visible_items = [
        i.get("name", "")
        for i in inventory
        if i.get("slot") in ("held", "holstered", "worn", "visible")
    ]
    if visible_items:
        lines.append(f"  Visible Items: {' | '.join(visible_items)}")

    return "\n".join(lines)


async def get_character_card_by_name(name: str, session_id: int = None) -> str:
    """Lookup a character by name and return card.
    Tries exact match first, then prefix/LIKE, ordered by bond descending.
    """
    if session_id is None:
        session_id = Config.SESSION_ID
    # Try exact match first (case-insensitive)
    row = await Database.fetchrow(
        """SELECT id FROM maya_rp.characters
           WHERE session_id=$1 AND LOWER(name) = LOWER($2)
           ORDER BY COALESCE(bond, 0) DESC LIMIT 1""",
        session_id, name,
    )
    # Fallback to LIKE match
    if not row:
        row = await Database.fetchrow(
            """SELECT id FROM maya_rp.characters
               WHERE session_id=$1 AND LOWER(name) LIKE LOWER($2)
               ORDER BY COALESCE(bond, 0) DESC LIMIT 1""",
            session_id, f"%{name}%",
        )
    if row:
        return await get_character_card(row["id"], session_id)
    return "Character not found."


# ─── Tick Hook ──────────────────────────────────────────────────────────

async def run_tick(session_id: int = None) -> dict:
    """Tick: auto-dress present characters based on pacing mode."""
    return await auto_dress_all_present(session_id)
