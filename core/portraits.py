#!/usr/bin/env python3
"""Character portraits — preset images per character and occasion.

The engine owns the mapping character x occasion -> image. Rendering happens
through ComfyUI on the local GPU (`scripts/portrait_render.py`); this module
builds the prompt, looks the asset up, and queues a missing one.

Layout on disk (one folder per character):

    <TKG_CHARACTERS_ROOT>/<slug>/
        sheet.md            tipe, traits, personaliti, rupa (sumber prompt)
        refs/               reference / LoRA watak
        emotions/<key>.png  satu imej pratetap per occasion

@module core.portraits
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Sequence

from core.config import Config
from core.db import Database

CHARACTERS_ROOT = Path(
    os.environ.get("TKG_CHARACTERS_ROOT", str(Path.home() / "Bumi-Hijau" / "adventures" / "tkg" / "characters"))
)

# One prompt fragment per emotion; the renderer appends it to the character's
# own appearance so the same face reads the same across occasions.
EMOTIONS: dict[str, str] = {
    "neutral": "calm neutral expression, composed",
    "happy": "warm smile, bright eyes",
    "sad": "downcast eyes, sorrowful",
    "angry": "hard stare, jaw set",
    "surprised": "wide eyes, parted lips",
    "flustered": "faint blush, averted gaze",
    "determined": "steady resolute expression, battle-ready",
    "hurt": "bruised, exhausted",
    "tired": "heavy-lidded, weary",
    "tender": "soft protective look, gentle smile",
    "intimate": "soft-lidded gaze, close and warm",
    "mourning": "grief, restrained, dark clothes",
    "battle": "focused, weapon ready, smoke around",
}

# occasion -> (default emotion, where the game raises it)
OCCASIONS: dict[str, tuple[str, tuple[str, ...]]] = {
    "portrait": ("neutral", ("characters", "narrative")),
    "romance": ("flustered", ("romance",)),
    "intimate": ("intimate", ("romance", "pregnancy")),
    "battle": ("battle", ("battle", "siege", "duel")),
    "council": ("determined", ("council", "ministry_ai")),
    "injury": ("hurt", ("physical_state",)),
    "celebration": ("happy", ("victory",)),
    "grief": ("mourning", ("collapse", "epilogue")),
    "pregnancy": ("tender", ("pregnancy",)),
    "undercover": ("neutral", ("espionage", "stealth")),
    "wardrobe": ("neutral", ("wardrobe",)),
}

STYLE_SUFFIX = "cinematic lighting, detailed face, sci-fi, 512x512, upper body portrait"
NEGATIVE_PROMPT = "lowres, blurry, watermark, text, extra limbs, deformed, bad anatomy"


def slugify(name: str) -> str:
    """A filesystem-safe slug for one character name."""
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return slug or "unknown"


def character_dir(name: str) -> Path:
    """Folder that owns one character's sheet, refs and emotion images."""
    return CHARACTERS_ROOT / slugify(name)


def emotion_path(name: str, emotion: str) -> Path:
    """Where the preset image for one occasion lives on disk."""
    return character_dir(name) / "emotions" / f"{emotion}.png"


def sheet_text(name: str) -> str:
    """The character's sheet body, or an empty string when none exists."""
    path = character_dir(name) / "sheet.md"
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    # Keep the human-written half: everything after the frontmatter.
    parts = text.split("---", 2)
    return parts[2].strip() if len(parts) == 3 else text.strip()


def _plain(text: str) -> str:
    """Flatten sheet markdown into prompt words."""
    text = re.sub(r"[*_`#>|]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def build_prompt(character: dict[str, Any], emotion: str, *, sheet: str = "") -> str:
    """The render prompt for one character and occasion.

    The character's own words come first (sheet, then database fields), so the
    face stays the same across occasions; only the emotion fragment changes.
    """
    fragment = EMOTIONS.get(emotion, EMOTIONS["neutral"])
    identity = "; ".join(
        part
        for part in (
            character.get("name"),
            character.get("role"),
            character.get("archetype"),
            character.get("character_type"),
            (character.get("appearance") or character.get("description") or "")[:280],
            character.get("current_outfit") or "",
        )
        if part
    )
    body = _plain(sheet)[:420] if sheet else identity
    return f"{body}; {fragment}; {STYLE_SUFFIX}" if body else f"{fragment}; {STYLE_SUFFIX}"


async def find_character(session_id: int, name: str) -> dict[str, Any] | None:
    """Resolve one character by name: exact, then prefix, then contains."""
    sid = int(session_id if session_id is not None else Config.SESSION_ID)
    for pattern in (name, f"{name}%", f"%{name}%"):
        row = await Database.fetchrow(
            "SELECT id, name, role, archetype, character_type, appearance, description,"
            " current_outfit, traits FROM maya_rp.characters"
            " WHERE session_id=$1 AND name ILIKE $2 ORDER BY importance DESC NULLS LAST, id LIMIT 1",
            sid,
            pattern,
        )
        if row:
            return dict(row)
    return None


async def lookup(session_id: int, name: str, occasion: str) -> dict[str, Any] | None:
    """The preset asset for one character and occasion, when it exists on disk."""
    character = await find_character(session_id, name)
    if character is None:
        return None
    emotion = OCCASIONS.get(occasion, (occasion, ()))[0]
    row = await Database.fetchrow(
        "SELECT id, kind, occasion, image_path, status FROM maya_rp.character_assets"
        " WHERE character_id=$1 AND occasion=$2 AND kind='portrait'",
        character["id"],
        occasion,
    )
    if row is None:
        # An asset recorded under the emotion key still answers the occasion.
        row = await Database.fetchrow(
            "SELECT id, kind, occasion, image_path, status FROM maya_rp.character_assets"
            " WHERE character_id=$1 AND occasion=$2 AND kind='portrait'",
            character["id"],
            emotion,
        )
    if row is None or row["status"] != "ready" or not row["image_path"]:
        return None
    if not Path(row["image_path"]).is_file():
        return None
    return {"character": character, "emotion": emotion, "asset": dict(row)}


async def queue(session_id: int, name: str, occasion: str) -> dict[str, Any]:
    """Queue a render for one character and occasion (idempotent per pair).

    @returns the character, the emotion, the built prompt, and the row status.
    """
    character = await find_character(session_id, name)
    if character is None:
        raise ValueError(f"character not found: {name}")
    emotion = OCCASIONS.get(occasion, (occasion, ()))[0]
    prompt = build_prompt(character, emotion, sheet=sheet_text(character["name"]))
    row = await Database.fetchrow(
        "INSERT INTO maya_rp.character_assets"
        " (session_id, character_id, kind, occasion, prompt, negative_prompt, status)"
        " VALUES ($1,$2,'portrait',$3,$4,$5,'pending')"
        " ON CONFLICT (character_id, kind, occasion) DO UPDATE"
        " SET prompt=EXCLUDED.prompt, negative_prompt=EXCLUDED.negative_prompt,"
        "     status='pending', error=NULL, updated_at=now()"
        " RETURNING id, status, image_path",
        int(session_id),
        character["id"],
        occasion,
        prompt,
        NEGATIVE_PROMPT,
    )
    return {
        "character": character,
        "emotion": emotion,
        "prompt": prompt,
        "asset_id": row["id"],
        "status": row["status"],
        "image_path": row["image_path"],
    }


async def pending(session_id: int, limit: int = 10) -> list[dict[str, Any]]:
    """Queued renders, oldest first."""
    rows = await Database.fetch(
        "SELECT a.id, a.occasion, a.prompt, a.negative_prompt, c.name"
        " FROM maya_rp.character_assets a JOIN maya_rp.characters c ON c.id = a.character_id"
        " WHERE a.session_id=$1 AND a.status='pending' ORDER BY a.id LIMIT $2",
        int(session_id),
        int(limit),
    )
    return [dict(row) for row in rows]


async def mark_ready(asset_id: int, image_path: str, *, model: str, seed: int | None, width: int, height: int) -> None:
    """Record one finished render."""
    await Database.execute(
        "UPDATE maya_rp.character_assets SET image_path=$2, model=$3, seed=$4, width=$5, height=$6,"
        " status='ready', error=NULL, updated_at=now() WHERE id=$1",
        int(asset_id),
        image_path,
        model,
        None if seed is None else int(seed),
        int(width),
        int(height),
    )


async def mark_failed(asset_id: int, error: str) -> None:
    """Record one failed render without losing the queue entry's prompt."""
    await Database.execute(
        "UPDATE maya_rp.character_assets SET status='failed', error=$2, updated_at=now() WHERE id=$1",
        int(asset_id),
        error[:500],
    )


def ensure_dirs(name: str) -> dict[str, Path]:
    """Create the character folder tree (sheet, refs, emotions) when missing."""
    root = character_dir(name)
    (root / "refs").mkdir(parents=True, exist_ok=True)
    (root / "emotions").mkdir(parents=True, exist_ok=True)
    return {"root": root, "refs": root / "refs", "emotions": root / "emotions"}


def occasions_report() -> list[dict[str, Any]]:
    """The taxonomy as data, for the CLI and the harness tool."""
    return [
        {"occasion": key, "emotion": emotion, "triggers": list(triggers)}
        for key, (emotion, triggers) in sorted(OCCASIONS.items())
    ]
