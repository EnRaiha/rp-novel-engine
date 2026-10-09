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
and a hand-written sheet is never overwritten unless `--force`. A non-empty `intro.md`
is never overwritten unless `--force-intro`.

`--session` resolves through `core.session.require_session`: the flag, then `RP_SESSION`,
then the active arc. Nothing resolved is an error.

    python3 scripts/import_character_card.py --card card.png --dry-run
    python3 scripts/import_character_card.py --card card.json --session 7 --queue-portrait
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

from core.db import Database  # noqa: E402
from core import portraits  # noqa: E402
from core.session import require_session  # noqa: E402


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


# Stock names shipped by card generators. This is a floor, not a classifier: it
# catches the handful that appear in every pack, and it will never catch a name
# that is generic in a way this list does not know. A hit is a question to ask,
# never a refusal.
GENERIC_NAMES = frozenset({
    "aiden", "alex", "aria", "asher", "aurora", "elara", "elena", "ezra", "kael",
    "kai", "lena", "luna", "maya", "nova", "raven", "rowan", "sage", "seraphina",
    "silas", "sky", "talia", "thorn", "valeria", "willow", "zara", "zephyr",
})

# Below this many letters, one normalised name being contained in another means
# nothing. The roster's designations normalise to one or two characters, and a
# single `a` is contained in most names ever written.
_CONTAINMENT_FLOOR = 4


def _normalise_name(name: str) -> str:
    """Letters only, lowercased. What a name is when its spelling is not the point."""
    return re.sub(r"[^a-z]", "", name.lower())


def _name_distance(a: str, b: str) -> int:
    """Levenshtein distance, two rows of memory. Names are short."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, 1):
        current = [i]
        for j, char_b in enumerate(b, 1):
            current.append(min(previous[j] + 1,
                               current[j - 1] + 1,
                               previous[j - 1] + (char_a != char_b)))
        previous = current
    return previous[-1]


async def name_report(session: int, name: str, *, near_limit: int = 2) -> dict:
    """What the campaign already holds under this name, and what this name resembles.

    The import path matches on the whole name exactly. A name one letter away from
    an existing one therefore inserts a second character, and nothing says so. This
    reports the neighbour instead of guessing at it.

    @param session - session whose roster to compare against.
    @param name - the name about to be imported.
    @param near_limit - edit distance at or below which a neighbour is reported.
    @returns exact matches, near neighbours ordered by distance, and a generic flag.
    """
    rows = await Database.fetch(
        "SELECT id, name FROM maya_rp.characters WHERE session_id=$1", session)
    wanted = _normalise_name(name)
    exact: list[dict] = []
    near: list[dict] = []
    for row in rows:
        other = _normalise_name(row["name"])
        if other == wanted:
            exact.append({"id": int(row["id"]), "name": row["name"]})
            continue
        if not wanted or not other:
            continue
        if wanted in other or other in wanted:
            # One name contains the other: a variant or a title, not a typo.
            #
            # Only when both sides carry enough letters to mean something. The
            # roster holds designations like `A-011`, which normalise to a single
            # `a`, and a lone `a` is contained in most names ever written. Without
            # this floor every designation is reported as a neighbour of every
            # person in the campaign, and the five slots are spent on them.
            if min(len(wanted), len(other)) < _CONTAINMENT_FLOOR:
                continue
            near.append({"id": int(row["id"]), "name": row["name"],
                         "distance": abs(len(other) - len(wanted))})
            continue
        if abs(len(other) - len(wanted)) <= near_limit:
            distance = _name_distance(wanted, other)
            if distance <= near_limit:
                near.append({"id": int(row["id"]), "name": row["name"], "distance": distance})
    near.sort(key=lambda item: (item["distance"], item["name"]))
    return {"exact": exact, "near": near[:5], "generic": wanted in GENERIC_NAMES,
            "checked": len(rows)}


async def import_card(session: int, fields: dict, *, force: bool, dry_run: bool,
                      queue_portrait: bool, force_intro: bool = False) -> str:
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

    report = await name_report(session, row["name"])
    if report["generic"]:
        print(f"  note: {row['name']!r} is a stock name from the common card packs; "
              f"the campaign roots its names in its own places ({report['checked']} checked)")
    for neighbour in report["near"]:
        print(f"  note: {row['name']!r} sits {neighbour['distance']} edit(s) from "
              f"#{neighbour['id']} {neighbour['name']!r} — confirm they are not one person")

    existing = await Database.fetchrow(
        "SELECT id, appearance, background, description, traits FROM maya_rp.characters"
        " WHERE session_id=$1 AND name=$2", session, fields["name"])
    if existing:
        updates = {key: row[key] for key in ("description", "appearance", "background", "traits")
                   if force or not existing[key]}
        if updates:
            # $1 is the id, $2.. are the values in `updates` order. A placeholder with no
            # reference makes asyncpg raise, so the numbers must be gapless.
            assignments = ", ".join(
                f"{key}=${index + 2}::jsonb" if key == "traits" else f"{key}=${index + 2}"
                for index, key in enumerate(updates))
            await Database.execute(
                f"UPDATE maya_rp.characters SET {assignments} WHERE id=$1",  # noqa: S608 - fixed column names
                existing["id"],
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
    intro = root / "intro.md"
    # Read before `scaffold_fields`: it writes a non-empty template when the file is missing.
    intro_kept = intro.is_file() and bool(intro.read_text(encoding="utf-8").strip())
    portraits.scaffold_fields(fields["name"], role=row["role"], lore=fields["scenario"])
    if force_intro or not intro_kept:
        intro.write_text(
            f"# {fields['name']} — Intro\n\n{fields['first_mes'] or '- (entrance beat unset)'}\n",
            encoding="utf-8")
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
    parser.add_argument("--session", type=int, default=None,
                        help="campaign id. The default resolves through RP_SESSION or the active arc")
    parser.add_argument("--origin", default="", help="label recorded in the sheet")
    parser.add_argument("--queue-portrait", action="store_true")
    parser.add_argument("--force", action="store_true",
                        help="overwrite sheet.md and fields that are already filled")
    parser.add_argument("--force-intro", action="store_true",
                        help="overwrite a non-empty intro.md with the card's first message")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    session = require_session(args.session)
    fields = contact(load_card(args.card))
    fields["origin"] = args.origin or args.card.name
    await Database.init()
    result = await import_card(session, fields, force=args.force, dry_run=args.dry_run,
                               queue_portrait=args.queue_portrait, force_intro=args.force_intro)
    await Database.close()
    print(f"{fields['name']}: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
