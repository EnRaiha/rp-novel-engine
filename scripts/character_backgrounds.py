#!/usr/bin/env python3
"""character_backgrounds — write the campaign's own words into each dossier.

Two modes:
  --fields   fill every blank dossier field (DB columns + sheet) in one pass:
             background, appearance, description, voice_profile, dialogue_style,
             species, origin_system. Grounded in the character row, the retrieved
             canon (`maya_rag.novel_chunks`) and the events that mention them.
  (default)  write only the `## Background` section (or `## Appearance` with
             `--face`) into the sheet.

Sources: the character's own row, the retrieved canon (`maya_rag.novel_chunks`,
built by `novel_rag.py`), the recent campaign events, and the novel voice.

Idempotent and resumable: a filled field is skipped unless `--force`, and every
character is checkpointed immediately.

    python3 scripts/character_backgrounds.py --fields --scope wife
    python3 scripts/character_backgrounds.py --fields --scope beauty
    python3 scripts/character_backgrounds.py --fields            # everyone
    python3 scripts/character_backgrounds.py --character "Maya al-Dabaran (Anchor)" --face
    python3 scripts/character_backgrounds.py --limit 3
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import Config  # noqa: E402
from core.db import Database  # noqa: E402
from core import portraits  # noqa: E402

API = os.environ.get("DEEPSEEK_OPENAI_URL", "https://api.deepseek.com/v1/chat/completions")
MODEL = os.environ.get("NOVEL_MODEL", "deepseek-flash")
STATE = Path("/home/maya/backups/rp/backgrounds-state.json")

# Fields the model answered "null" for, keyed by character name: the canon is
# silent on them, so later passes must not ask again (until --force).
NULLS: dict[str, list[str]] = {}


def load_nulls() -> None:
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return
    for name, fields in (data.get("nulls") or {}).items():
        keep = [field for field in fields if field in FIELD_OPTIONAL]
        if keep:
            NULLS[name] = keep

BRIEF = (
    "TKG — a fleet state under House al-Dabaran three years into a contested expansion across the Vein "
    "Nexus corridor: pirate queens, the Marrow Fleet, the Gutterhawk Marauders, the Ashen Corsairs. "
    "The King is bound by a compliance System; warmth is audited; his people carry it in silence."
)
STYLE = (
    "Write in the novel's voice: third person past tense, concrete, sensory, no dice, no rolls, no lists, "
    "no meta commentary, no prompts. Never invent a faction or event the facts do not support."
)


def set_section(text: str, heading: str, body: str) -> str:
    """Replace one `## heading` section, or append it when absent."""
    body = body.strip() + "\n"
    pattern = re.compile(rf"(?ms)^## {re.escape(heading)}\s*\n.*?(?=^## |\Z)")
    if pattern.search(text):
        return pattern.sub(f"## {heading}\n\n{body}\n", text)
    return text.rstrip() + f"\n\n## {heading}\n\n{body}\n"


def llm(system: str, user: str, tokens: int = 700, temperature: float = 0.85) -> str | None:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        return None
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "max_tokens": tokens,
        "temperature": temperature,
        "stream": False,
    }).encode()
    request = urllib.request.Request(API, data=payload,
                                     headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    for attempt in range(5):
        try:
            data = json.loads(urllib.request.urlopen(request, timeout=180).read())
            return data["choices"][0]["message"]["content"].strip()
        except Exception as error:
            print(f"  llm error: {error}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    return None


async def facts_for(row: dict[str, Any]) -> str:
    """The grounded facts: the row, the retrieved canon, the events that name them."""
    base = row["name"].split(" (")[0]
    chunks = await Database.fetch(
        "SELECT source, ref, text_content FROM maya_rag.novel_chunks"
        " WHERE text_content ILIKE $1 AND source <> 'character' ORDER BY id LIMIT 6",
        f"%{base}%",
    )
    events = await Database.fetch(
        "SELECT happened_at, event_type, title, description FROM maya_rp.events"
        " WHERE session_id=$1 AND (title ILIKE $2 OR description ILIKE $2)"
        " ORDER BY id DESC LIMIT 5",
        row["session_id"], f"%{base}%",
    )
    lines = [
        f"name: {row['name']}",
        f"role: {row['role'] or '—'} · archetype: {row['archetype'] or '—'} · type: {row['character_type'] or '—'}",
        f"species: {row['species'] or '—'} · house: {row['house_name'] or '—'} · bond: {row['bond'] or 0} ({row['romance_stage'] or '—'})",
        f"traits: {' '.join(str(row['traits'] or '').strip('[]').replace(chr(34), '').split(','))}",
        f"appearance as recorded: {' '.join(str(row['appearance'] or row['description'] or '').split())[:400]}",
    ]
    for chunk in chunks:
        lines.append(f"[{chunk['source']}:{chunk['ref']}] {' '.join(str(chunk['text_content']).split())[:280]}")
    for event in events:
        when = str(event["happened_at"] or "")[:10]
        lines.append(f"[event:{when}:{event['event_type']}] {event['title']} — "
                     f"{' '.join(str(event['description'] or '').split())[:220]}")
    return "\n".join(lines)


async def write_sheet(row: dict[str, Any], heading: str, body: str) -> Path:
    root = portraits.character_dir(row["name"])
    root.mkdir(parents=True, exist_ok=True)
    path = root / "sheet.md"
    text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else f"# {row['name']} — Character Sheet\n"
    path.write_text(set_section(text, heading, body), encoding="utf-8")
    return path


async def run_character(row: dict[str, Any], face: bool, force: bool) -> str:
    heading = "Appearance" if face else "Background"
    root = portraits.character_dir(row["name"])
    sheet = root / "sheet.md"
    if sheet.is_file() and not force:
        text = sheet.read_text(encoding="utf-8", errors="replace")
        if re.search(rf"(?m)^## {heading}\b", text):
            return "skipped"

    facts = await facts_for(row)
    if face:
        system = ("You describe faces for a space-opera novel. " + STYLE)
        user = (
            f"### Facts\n{facts}\n\n"
            f"### Instruction\nDescribe {row['name']}'s face as the novel would when she enters a room: "
            f"bone structure, eyes (colour and habit), brows, nose, mouth, skin, hair and how she wears it, "
            f"the set of her jaw, and the expression she defaults to. She is beautiful — write that beauty "
            f"concretely, not with adjectives alone. 120-160 words, one paragraph."
        )
    else:
        system = ("You write character backgrounds for a space-opera novel. " + STYLE)
        user = (
            f"### Campaign\n{BRIEF}\n\n### Facts\n{facts}\n\n"
            f"### Instruction\nWrite {row['name']}'s background: where they came from, how they reached the "
            f"crown, what they carry now (a loyalty, a grudge, a debt, a habit). Ground every claim in the "
            f"facts; where they are silent, invent nothing that contradicts them. 120-180 words, one paragraph."
        )
    body = llm(system, user)
    if not body:
        return "failed"
    path = await write_sheet(row, heading, body)
    if face:
        await Database.execute("UPDATE maya_rp.characters SET appearance=$2 WHERE id=$1", row["id"], body[:2000])
    print(f"  {row['name']}: {len(body)} chars → {path.name}")
    return "written"


FIELD_ORDER = ["background", "appearance", "description", "voice_profile", "dialogue_style",
               "species", "origin_system"]
# Only these two may legitimately come back null: a face, a biography or a voice
# is always writable from the role, archetype and traits, so a null there is the
# model stalling, not the canon being silent, and it must not be remembered.
FIELD_OPTIONAL = {"species", "origin_system"}
FIELD_BRIEFS = {
    "background": ("where they came from, how they reached the crown, and what they carry now "
                   "(a loyalty, a grudge, a debt, a habit). Ground every claim in the facts. "
                   "120-180 words, one paragraph."),
    "appearance": ("their face and build as the novel shows it when they enter a room: bone "
                   "structure, eyes (colour and the habit of them), brows, nose, mouth, skin, hair "
                   "and how it is worn, the set of the jaw, the expression they default to. Use the "
                   "pronouns the facts imply (he, she, or they when unsure). Write beauty concretely "
                   "when they are one of the King's companions or a catalogued beauty. "
                   "110-150 words, one paragraph."),
    "description": "a two-sentence summary for lists and cards. 30-50 words.",
    "voice_profile": ("how the voice sounds and behaves: register, pace, warmth, accent, and what "
                      "it never does. 30-50 words."),
    "dialogue_style": ("a performer's note: sentence length, favourite constructions, verbal tics, "
                       "and how they address the King. 20-40 words."),
    "species": "the species, one or two words, only when the facts support it; otherwise null.",
    "origin_system": "the home system or place, a short name, only when the facts support it; otherwise null.",
}


def empty(value: Any) -> bool:
    return not str(value if value is not None else "").strip()


def extract_json(text: str) -> dict[str, Any] | None:
    """The JSON object out of a possibly fenced model reply, nulls included."""
    text = re.sub(r"^```[a-zA-Z]*\n?|```$", "", text.strip()).strip()
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def clean_fields(data: dict[str, Any]) -> dict[str, str]:
    """Drop nulls, empties and placeholder words from a parsed reply."""
    fields: dict[str, str] = {}
    for key, value in data.items():
        if not isinstance(value, str):
            continue
        cleaned = " ".join(value.split())
        if cleaned and cleaned.lower() not in {"null", "none", "unknown", "n/a", "—", "-"}:
            fields[key] = cleaned
    return fields


def parse_fields(text: str) -> dict[str, str]:
    """One JSON object out of a possibly fenced model reply."""
    data = extract_json(text)
    return clean_fields(data) if data else {}


def fields_prompt(row: dict[str, Any], facts: str, needed: list[str]) -> tuple[str, str]:
    system = ("You maintain the character dossiers of a space-opera novel. " + STYLE
              + " Answer with one JSON object and nothing else.")
    lines = [
        "### Campaign", BRIEF, "", "### Facts", facts, "",
        "### Instruction",
        f"Fill the blank dossier fields for {row['name']}. Answer with one JSON object whose keys "
        f"are exactly: {', '.join(needed)}. Values are strings. Only species and origin_system may "
        "be null, and only when the facts do not name them; never answer null for background, "
        "appearance, description, voice_profile or dialogue_style — write those from the role, "
        "archetype, traits and facts.",
        "Field briefs:",
    ]
    for key in needed:
        lines.append(f"- {key}: {FIELD_BRIEFS[key]}")
    return system, "\n".join(lines)


def patch_sheet(row: dict[str, Any], updates: dict[str, str]) -> bool:
    """Reflect filled fields into the sheet, never overwriting written prose."""
    path = portraits.character_dir(row["name"]) / "sheet.md"
    if not path.is_file():
        return False
    text = before = path.read_text(encoding="utf-8", errors="replace")

    def section_body(heading: str) -> str | None:
        match = re.search(rf"(?ms)^## {re.escape(heading)}\s*\n(.*?)(?=^## |\Z)", text)
        return match.group(1).strip() if match else None

    for key, heading in (("background", "Background"), ("appearance", "Appearance")):
        if key not in updates:
            continue
        value = updates[key]
        if section_body(heading) is None:
            text = set_section(text, heading, value)
            continue
        # A section may hold the "—" placeholder alone or above other lines
        # (the outfit note); replace only the placeholder line itself.
        placeholder = re.compile(rf"(?m)^## {re.escape(heading)}[ \t]*\n(?:\s*\n)?[ \t]*(?:—|-)[ \t]*$")
        text = placeholder.sub(lambda match: f"## {heading}\n\n{value}", text, count=1)

    line_map = {"voice_profile": "Voice", "dialogue_style": "Dialogue style", "species": "Species"}
    for key, label in line_map.items():
        if key not in updates:
            continue
        value = " ".join(updates[key].split())
        text = re.sub(rf"(?m)^(- \*\*{re.escape(label)}\*\*: )—\s*$", rf"\g<1>{value}", text)
        front = {"voice_profile": "voice", "dialogue_style": "dialogue_style", "species": "species"}[key]
        text = re.sub(rf"(?m)^{front}:\s*$", f"{front}: {value}", text)
    if text != before:
        path.write_text(text, encoding="utf-8")
        return True
    return False


async def run_fields(row: dict[str, Any], force: bool) -> str:
    # A species or origin the model answered "null" for is not a blank to chase:
    # the canon does not state it. `NULLS` remembers those answers between
    # passes. Backgrounds, faces and voices are always writable, so a null there
    # is a stall and the next pass asks again.
    remembered = set(NULLS.get(row["name"], [])) & FIELD_OPTIONAL
    known_null = set() if force else remembered
    needed = [field for field in FIELD_ORDER if (force or empty(row.get(field))) and field not in known_null]
    if not needed:
        return "skipped"
    facts = await facts_for(row)
    system, user = fields_prompt(row, facts, needed)
    # deepseek-flash is a reasoning model: the hidden reasoning tokens count
    # against max_tokens, and a truncated reply is unparseable JSON.
    raw = llm(system, user, tokens=4000)
    if not raw:
        return "failed"
    data = extract_json(raw)
    if data is None:
        # Near-JSON (an unescaped quote inside a value, a stray sentence): ask
        # for one clean pass instead of burning the character as failed.
        data = extract_json(llm(
            "You repair JSON.",
            "Rewrite this reply as one JSON object with the same keys and the same wording. "
            "Escape every double quote inside a string value. Answer with the object only.\n\n"
            + raw,
            tokens=4000, temperature=0,
        ) or "")
    if data is None:
        print(f"  {row['name']}: unparseable reply ({len(raw)} chars)", flush=True)
        return "failed"
    fields = clean_fields(data)
    filled = {key: value for key, value in fields.items() if key in needed}
    for key in needed:
        if key not in filled and key in FIELD_OPTIONAL:
            NULLS.setdefault(row["name"], [])
            if key not in NULLS[row["name"]]:
                NULLS[row["name"]].append(key)
    if not filled:
        print(f"  {row['name']}: canon is silent on {', '.join(needed)}", flush=True)
        return "skipped"
    for key, value in filled.items():
        if key in {"species", "origin_system"} and len(value) > 60:
            continue
        await Database.execute(f"UPDATE maya_rp.characters SET {key}=$2 WHERE id=$1", row["id"], value[:4000])
    patch_sheet(row, filled)
    print(f"  {row['name']}: filled {len(filled)} ({', '.join(sorted(filled))})")
    return "written"


async def main() -> int:
    parser = argparse.ArgumentParser(description="Write campaign-grounded backgrounds and dossier fields")
    parser.add_argument("--session", type=int, default=Config.SESSION_ID)
    parser.add_argument("--character", default=None)
    parser.add_argument("--fields", action="store_true", help="fill every blank dossier field (DB + sheet)")
    parser.add_argument("--sync", action="store_true",
                        help="copy filled DB fields into sheet placeholders (no model calls)")
    parser.add_argument("--face", action="store_true", help="describe the face into Appearance + DB")
    parser.add_argument("--scope", choices=("all", "wife", "beauty"), default="all",
                        help="wife = spouses; beauty = catalogued or beauty_standard")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    where = "session_id=$1 AND status IS DISTINCT FROM 'dead'"
    if args.scope == "wife":
        where += " AND (is_spouse OR romance_stage = 'married')"
    elif args.scope == "beauty":
        where += " AND (beauty_standard IS TRUE OR beauty_catalog_id IS NOT NULL)"
    order = " ORDER BY COALESCE(bond,0) DESC, importance DESC NULLS LAST, id"

    await Database.init()
    if args.character:
        rows = await Database.fetch(
            "SELECT * FROM maya_rp.characters WHERE session_id=$1 AND name ILIKE $2",
            args.session, f"%{args.character}%",
        )
    elif args.all or args.scope != "all" or args.fields or args.sync:
        # The dossier modes mean the whole scope; only the legacy sheet modes
        # keep the "no flags = a short sample" default.
        rows = await Database.fetch(f"SELECT * FROM maya_rp.characters WHERE {where}{order}", args.session)
    else:
        rows = await Database.fetch(
            f"SELECT * FROM maya_rp.characters WHERE {where}{order} LIMIT $2",
            args.session,
            args.limit or 3,
        )
    mode = "sync" if args.sync else ("fields" if args.fields else ("face" if args.face else "background"))
    load_nulls()
    done: dict[str, int] = {"written": 0, "skipped": 0, "failed": 0}
    for row in rows:
        row = dict(row)
        if args.sync:
            filled = {field: row[field] for field in FIELD_ORDER if not empty(row.get(field))}
            outcome = "written" if patch_sheet(row, filled) else "skipped"
        else:
            outcome = await run_fields(row, args.force) if args.fields else await run_character(row, args.face, args.force)
        done[outcome] += 1
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({"updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                     "mode": mode, "scope": args.scope,
                                     "last": row["name"], "counts": done,
                                     "nulls": {name: sorted(fields) for name, fields in NULLS.items()}},
                                    indent=2), encoding="utf-8")
    await Database.close()
    print(f"{mode} ({args.scope}): {done}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
