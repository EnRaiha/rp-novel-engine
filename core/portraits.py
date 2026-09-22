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

import json
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


def parse_traits(value: Any) -> list[str]:
    """Traits as stored: a JSON list, JSON text, or a Postgres array string."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list):
        return [str(item) for item in parsed if str(item).strip()]
    return [part.strip().strip('"') for part in text.strip("{}").split(",") if part.strip()]


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


def _section(sheet: str, heading: str) -> str:
    """The prose under one `## heading`, without the outfit bookkeeping line."""
    match = re.search(rf"(?ms)^## {re.escape(heading)}\s*\n(.*?)(?=^## |\Z)", sheet or "")
    if not match:
        return ""
    body = re.split(r"\*\*Current outfit\*\*", match.group(1))[0]
    return _plain(body)


def _outfit(value: Any) -> str:
    """The outfit as words: the stored JSON carries a description."""
    if not value:
        return ""
    data = value
    if not isinstance(data, dict):
        try:
            data = json.loads(str(value))
        except json.JSONDecodeError:
            return str(value).strip()[:120]
    if isinstance(data, dict):
        return str(data.get("desc") or data.get("name") or "").strip()[:120]
    return ""


def build_prompt(character: dict[str, Any], emotion: str, *, sheet: str = "") -> str:
    """The render prompt for one character and occasion.

    The face comes first — the sheet's `## Appearance` prose, else the database
    `appearance` field — because that is what has to stay the same across
    occasions. Role, traits and outfit follow, then the emotion fragment.
    """
    fragment = EMOTIONS.get(emotion, EMOTIONS["neutral"])
    face = _section(sheet, "Appearance") or " ".join(
        str(character.get("appearance") or character.get("description") or "").split()
    )
    traits = parse_traits(character.get("traits"))[:6]
    identity = "; ".join(
        part
        for part in (
            character.get("name"),
            face[:340],
            character.get("role"),
            ", ".join(traits),
            _outfit(character.get("current_outfit")),
        )
        if part
    )
    return f"{identity}; {fragment}; {STYLE_SUFFIX}" if identity else f"{fragment}; {STYLE_SUFFIX}"


async def find_character(session_id: int, name: str) -> dict[str, Any] | None:
    """Resolve one character by name: exact, then prefix, then contains."""
    sid = int(session_id if session_id is not None else Config.SESSION_ID)
    for pattern in (name, f"{name}%", f"%{name}%"):
        row = await Database.fetchrow(
            "SELECT id, name, role, archetype, character_type, appearance, description,"
            " current_outfit, traits, bond, romance_stage, is_spouse FROM maya_rp.characters"
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


async def pending(
    session_id: int, limit: int = 10, character: str | None = None
) -> list[dict[str, Any]]:
    """Queued renders, oldest first; optionally only one character's.

    The filter runs in SQL, before the limit: filtering an already-limited page
    silently drops a character whose rows sit at the end of the queue.
    """
    sql = ("SELECT a.id, a.occasion, a.prompt, a.negative_prompt, c.name"
           " FROM maya_rp.character_assets a JOIN maya_rp.characters c ON c.id = a.character_id"
           " WHERE a.session_id=$1 AND a.status='pending'")
    params: list[Any] = [int(session_id)]
    if character:
        sql += " AND c.name=$3"
        params.append(character)
    sql += " ORDER BY a.id LIMIT $2"
    params.insert(1, int(limit))
    rows = await Database.fetch(sql, *params)
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


INSPECT_READS = {
    "neutral": "composed; the face gives nothing away",
    "flustered": "a faint blush, gaze averted a heartbeat too long",
    "happy": "the eyes brighten before the mouth does",
    "sad": "the shoulders drop; the answer is slower than the question",
    "angry": "the jaw sets; the breath goes quiet",
    "surprised": "a half-breath held, lips parted",
    "determined": "steady hands, level voice, weight forward",
    "hurt": "favouring one side; the voice thin at the edges",
    "tired": "heavy-lidded; a beat behind the conversation",
    "tender": "softened attention the words do not admit",
    "intimate": "closer than duty allows; the pause is deliberate",
    "mourning": "restrained grief; the eyes do not leave the middle distance",
    "battle": "focused, weapon ready, breathing measured",
}


async def inspect_line(session_id: int | None = None, name: str = "") -> dict[str, Any]:
    """A micro-expression hint for the narrator (M30 `/inspect`).

    Reads the character's sheet and current emotion so the model can describe
    body language instead of inventing it — a prompt aid, never a rule.

    @param session_id - session key.
    @param name - character name.
    @returns the hint, or `found: False` when the character is unknown.
    """
    sid = int(session_id if session_id is not None else Config.SESSION_ID)
    character = await find_character(sid, name)
    if character is None:
        return {"found": False, "character": None}
    hit = await lookup(sid, name, "portrait")
    emotion = hit["emotion"] if hit else "neutral"
    traits = parse_traits(character.get("traits"))
    appearance = (character.get("appearance") or character.get("description") or "")[:180]
    registers: list[str] = []
    try:
        from core import campaign

        registers = [row["id"] for row in (await campaign.character_rules(sid, character["name"]))["rules"]][:4]
    except Exception:
        registers = []
    hint = (
        f"{character['name']} — {character.get('role') or '—'}; bond {character.get('bond') or 0}"
        + (f", stage {character['romance_stage']}" if character.get("romance_stage") else "")
        + f". Read: {INSPECT_READS.get(emotion, INSPECT_READS['neutral'])}."
        + (f" Traits: {', '.join(str(t) for t in traits)}." if traits else "")
        + (f" Appearance: {appearance}" if appearance else "")
        + (f" Registers: {', '.join(registers)}." if registers else "")
    )
    return {"found": True, "character": {"id": character["id"], "name": character["name"]}, "emotion": emotion, "hint": hint}


def scaffold_fields(name: str, *, role: str = "", lore: str = "") -> dict[str, Path]:
    """Write the four per-character fields (M24) when missing.

    Same split as a persona: operational register in `voice.md`, backstory in
    `lore.md`, the entrance beat in `intro.md`, player-only notes in
    `play-guide.md`. Human-written text is never overwritten.
    """
    root = character_dir(name)
    templates = {
        "voice": (
            f"# {name} — Voice\n\n## Register rules\n\n"
            f"- (how they speak: clipped? warm? archaic? what they never say)\n\n"
            f"## Few-shot exchanges\n\n**Player:** …\n\n**{name}:** …\n\n"
            "## Boundary\n\n- player pushes past their guard => the answer deflects, never confesses\n"
        ),
        "lore": f"# {name} — Lore\n\n{lore or '- (past events, loyalties, grudges — no instructions)'}\n",
        "intro": (
            f"# {name} — Intro\n\n"
            f"- Entrance beat: where they are and what they are mid-way through when the scene opens\n"
            f"- Sensory anchor and one unresolved tension\n"
        ),
        "play-guide": (
            f"# {name} — Play guide (player only, never sent to the model)\n\n"
            "- Hooks:\n- Expectations (pace, coldness is intentional):\n- Content notes:\n"
        ),
    }
    written: dict[str, Path] = {}
    for field, text in templates.items():
        path = root / f"{field}.md"
        if not path.exists():
            path.write_text(text, encoding="utf-8")
        written[field] = path
    return written


def occasions_report() -> list[dict[str, Any]]:
    """The taxonomy as data, for the CLI and the harness tool."""
    return [
        {"occasion": key, "emotion": emotion, "triggers": list(triggers)}
        for key, (emotion, triggers) in sorted(OCCASIONS.items())
    ]
