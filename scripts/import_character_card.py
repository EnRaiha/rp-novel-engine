#!/usr/bin/env python3
"""import_character_card — bring an outside character card into the campaign.

Accepts the community card formats the play ecosystem uses:

  * JSON (character-card-spec v2/v3) — a file with `spec`/`data` or the bare fields;
  * PNG with an embedded `chara` tEXt chunk (base64 JSON), the classic card image.

The card is mapped onto our structures, never dumped raw:

  * `maya_rp.characters` row — name, role, description, background, traits, appearance;
  * `sheet.md` — Profile / Personality / Appearance / Background plus an
    `## Imported card` block that keeps the card's own words (first message,
    example dialogue, creator notes);
  * the per-character field files (`voice.md`, `intro.md`, `lore.md`, `play-guide.md`);
  * `--queue-portrait` queues the neutral portrait for the new dossier.

Idempotent: an existing character is updated in the fields that are still empty,
and a hand-written sheet is never overwritten unless `--force`.

    python3 scripts/import_character_card.py --card card.png --dry-run
    python3 scripts/import_character_card.py --card card.json --session 3 --queue-portrait
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import Config  # noqa: E402
from core.db import Database  # noqa: E402
from core import portraits  # noqa: E402


def load_card(path: Path) -> dict:
    """A card dict out of a JSON file, a PNG tEXt chunk, or a CHARX zip."""
    raw = path.read_bytes()
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return json.loads(read_png_chara(raw))
    if raw[:2] == b"PK":  # charx (zip) — first .json member
        import io, zipfile

        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for name in archive.namelist():
                if name.endswith(".json"):
                    return json.loads(archive.read(name))
        raise ValueError("charx archive holds no json member")
    return json.loads(raw)


def read_png_chara(raw: bytes) -> str:
    """The base64 `chara` chunk of a card PNG."""
    offset = 8
    while offset + 8 <= len(raw):
        length = int.from_bytes(raw[offset:offset + 4], "big")
        kind = raw[offset + 4:offset + 8]
        body = raw[offset + 8:offset + 8 + length]
        if kind == b"tEXt":
            keyword, _, text = body.partition(b"\x00")
            if keyword == b"chara":
                return base64.b64decode(text).decode("utf-8")
        offset += 12 + length
    raise ValueError("no chara chunk in the PNG")


def contact(card: dict) -> dict:
    """The card's fields, whether they sit under `data` or at the top level."""
    data = card.get("data") if isinstance(card.get("data"), dict) else card
    return {
        "name": str(data.get("name") or "").strip(),
        "description": str(data.get("description") or "").strip(),
        "personality": str(data.get("personality") or "").strip(),
        "scenario": str(data.get("scenario") or "").strip(),
        "first_mes": str(data.get("first_mes") or "").strip(),
        "mes_example": str(data.get("mes_example") or "").strip(),
        "creator_notes": str(data.get("creator_notes") or "").strip(),
        "tags": [str(tag) for tag in (data.get("tags") or []) if str(tag).strip()],
        "alternates": [str(g) for g in (data.get("alternate_greetings") or []) if str(g).strip()],
    }


def sentences(text: str, limit: int) -> str:
    """The first `limit` sentences of a paragraph, as one line."""
    clean = " ".join((text or "").split())
    if not clean:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", clean)
    return " ".join(parts[:limit])[:600]


def appearance_from(description: str) -> str:
    """Appearance-flavoured sentences, else the head of the description."""
    clean = " ".join((description or "").split())
    hits = [s for s in re.split(r"(?<=[.!?])\s+", clean)
            if re.search(r"\b(hair|eyes?|face|skin|tall|short|build|wears?|dress|uniform|scar)\b", s, re.I)]
    return " ".join(hits[:3])[:600] or sentences(clean, 2)


def sheet_for(fields: dict, row: dict) -> str:
    """The dossier sheet a fresh import writes (hand-written text wins later)."""
    traits = ", ".join(str(t) for t in (row.get("traits") or []))
    block = [
        f"# {fields['name']} — Character Sheet",
        "",
        "## Profile",
        f"- **Role**: {row.get('role') or '—'}",
        f"- **Archetype**: imported card",
        f"- **Species**: {row.get('species') or '—'}",
        "- **Bond**: 0 · strangers",
        "",
        "## Personality",
        f"- **Traits**: {traits or '—'}",
        "- **Voice**: —",
        "- **Dialogue style**: —",
        "",
        "## Appearance",
        row.get("appearance") or "—",
        "",
        "## Background",
        row.get("background") or "—",
        "",
        "## Imported card",
        "",
        "### First message",
        fields["first_mes"] or "—",
        "",
        "### Example dialogue",
        fields["mes_example"] or "—",
    ]
    if fields["alternates"]:
        block += ["", "### Alternate greetings"] + [f"- {g}" for g in fields["alternates"]]
    if fields["creator_notes"]:
        block += ["", "### Creator notes", fields["creator_notes"]]
    block += ["", f"*Imported {fields.get('origin') or 'card'}.*", ""]
    return "\n".join(block)


async def import_card(session: int, fields: dict, *, force: bool, dry_run: bool,
                      queue_portrait: bool) -> str:
    if not fields["name"]:
        raise ValueError("card has no name")
    traits = [t.strip() for t in re.split(r"[,\n;]", fields["personality"]) if t.strip()][:8]
    row = {
        "name": fields["name"],
        "role": (fields["tags"][0] if fields["tags"] else "Imported"),
        "description": sentences(fields["description"], 2),
        "appearance": appearance_from(fields["description"]),
        "background": " ".join(fields["scenario"].split())[:4000],
        "traits": traits,
    }

    if dry_run:
        print(json.dumps({"would import": row, "first_mes": fields["first_mes"][:120]}, indent=2, ensure_ascii=False))
        return "dry-run"

    existing = await Database.fetchrow(
        "SELECT id, appearance, background, description, traits FROM maya_rp.characters"
        " WHERE session_id=$1 AND name=$2", session, fields["name"])
    if existing:
        updates = {key: row[key] for key in ("description", "appearance", "background", "traits")
                   if force or not existing[key]}
        if updates:
            assignments = ", ".join(
                f"{key}=${index + 3}::jsonb" if key == "traits" else f"{key}=${index + 3}"
                for index, key in enumerate(updates))
            await Database.execute(
                f"UPDATE maya_rp.characters SET {assignments} WHERE id=$1",  # noqa: S608 - fixed column names
                existing["id"], session,
                *[json.dumps(value) if key == "traits" else value for key, value in updates.items()])
        character_id = existing["id"]
        outcome = f"updated {len(updates)} field(s)"
    else:
        character_id = await Database.fetchval(
            "INSERT INTO maya_rp.characters"
            " (session_id, name, role, character_type, description, appearance, background, traits,"
            "  status, importance, romance_stage, bond)"
            " VALUES ($1,$2,$3,'supporting',$4,$5,$6,$7::jsonb,'alive',1,'strangers',0) RETURNING id",
            session, row["name"], row["role"], row["description"], row["appearance"],
            row["background"], json.dumps(row["traits"]))
        outcome = f"created id {character_id}"

    root = portraits.character_dir(fields["name"], character_id)
    root.mkdir(parents=True, exist_ok=True)
    sheet = root / "sheet.md"
    if force or not sheet.is_file():
        sheet.write_text(sheet_for(fields, row), encoding="utf-8")
    portraits.scaffold_fields(fields["name"], role=row["role"], lore=fields["scenario"])
    (root / "intro.md").write_text(
        f"# {fields['name']} — Intro\n\n{fields['first_mes'] or '- (entrance beat unset)'}\n", encoding="utf-8")
    if fields["mes_example"]:
        voice = root / "voice.md"
        current = voice.read_text(encoding="utf-8") if voice.is_file() else f"# {fields['name']} — Voice\n"
        voice.write_text(current.rstrip() + "\n\n## Imported examples\n\n" + fields["mes_example"] + "\n",
                         encoding="utf-8")
    if fields["creator_notes"]:
        guide = root / "play-guide.md"
        current = guide.read_text(encoding="utf-8") if guide.is_file() else "# Play guide\n"
        guide.write_text(current.rstrip() + "\n\n## Creator notes (imported)\n\n" + fields["creator_notes"] + "\n",
                         encoding="utf-8")
    if queue_portrait:
        await portraits.queue(session, fields["name"], "portrait")
        outcome += ", portrait queued"
    return f"{outcome}, folder {root.name}"


async def main() -> int:
    parser = argparse.ArgumentParser(description="Import a V2/V3 character card into the campaign")
    parser.add_argument("--card", required=True, type=Path, help="card .json, .png or .charx")
    parser.add_argument("--session", type=int, default=Config.SESSION_ID)
    parser.add_argument("--origin", default="", help="label recorded in the sheet")
    parser.add_argument("--queue-portrait", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    fields = contact(load_card(args.card))
    fields["origin"] = args.origin or args.card.name
    await Database.init()
    result = await import_card(args.session, fields, force=args.force,
                               dry_run=args.dry_run, queue_portrait=args.queue_portrait)
    await Database.close()
    print(f"{fields['name']}: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
