#!/usr/bin/env python3
"""Generate one character folder per character: sheet.md + refs/ + emotions/.

The sheet is the prompt source for preset images and the human page for a
character: identity, type, personality, appearance, voice. Database fields are
the base; a legacy hand-written sheet in
`adventures/tkg/character-sheets/<slug>.md` is copied over verbatim when one
exists, and an existing generated sheet is kept unless `--force`.

Usage:
    python3 scripts/generate_character_sheets.py --session 3 [--limit N] [--force]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import Config  # noqa: E402
from core.db import Database  # noqa: E402
from core import portraits  # noqa: E402

LEGACY_SHEETS = Path.home() / "Bumi-Hijau" / "adventures" / "tkg" / "character-sheets"


def render_sheet(row: dict) -> str:
    """One sheet page: frontmatter the renderer reads, then the human sections."""
    traits = row.get("traits") or []
    if isinstance(traits, str):
        traits = [part.strip() for part in traits.strip("{}").split(",") if part.strip()]
    front = {
        "id": row["id"],
        "name": row["name"],
        "role": row.get("role") or "",
        "archetype": row.get("archetype") or "",
        "character_type": row.get("character_type") or "",
        "species": row.get("species") or "",
        "bond": row.get("bond"),
        "romance_stage": row.get("romance_stage") or "",
        "traits": traits,
        "voice": row.get("voice_profile") or "",
        "dialogue_style": row.get("dialogue_style") or "",
        "outfit": row.get("current_outfit") or "",
    }
    lines = ["---"]
    for key, value in front.items():
        lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {row['name']} — Character Sheet")
    lines.append("")
    lines.append("## Profile")
    lines.append("")
    lines.append(f"- **Role**: {row.get('role') or '—'}")
    lines.append(f"- **Archetype**: {row.get('archetype') or '—'}")
    lines.append(f"- **Type**: {row.get('character_type') or '—'}")
    lines.append(f"- **Species**: {row.get('species') or '—'}")
    lines.append(f"- **Bond**: {row.get('bond') if row.get('bond') is not None else '—'}"
                 + (f" · stage {row['romance_stage']}" if row.get("romance_stage") else ""))
    lines.append("")
    lines.append("## Personality")
    lines.append("")
    lines.append(f"- **Traits**: {', '.join(str(t) for t in traits) if traits else '—'}")
    lines.append(f"- **Voice**: {row.get('voice_profile') or '—'}")
    lines.append(f"- **Dialogue style**: {row.get('dialogue_style') or '—'}")
    lines.append("")
    lines.append("## Appearance")
    lines.append("")
    lines.append(row.get("appearance") or row.get("description") or "—")
    lines.append("")
    if row.get("current_outfit"):
        lines.append(f"**Current outfit**: {row['current_outfit']}")
        lines.append("")
    lines.append("## Image occasions")
    lines.append("")
    lines.append("| Occasion | Emotion | File |")
    lines.append("|---|---|---|")
    for occasion, (emotion, _triggers) in sorted(portraits.OCCASIONS.items()):
        lines.append(f"| {occasion} | {emotion} | `emotions/{emotion}.png` |")
    lines.append("")
    return "\n".join(lines) + "\n"


async def main() -> int:
    parser = argparse.ArgumentParser(description="Generate character sheets and folders")
    parser.add_argument("--session", type=int, default=Config.SESSION_ID)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    await Database.init()
    sql = (
        "SELECT id, name, role, archetype, character_type, species, bond, romance_stage,"
        " traits, voice_profile, dialogue_style, appearance, description, current_outfit"
        " FROM maya_rp.characters WHERE session_id=$1 ORDER BY importance DESC NULLS LAST, id"
    )
    params: list = [args.session]
    if args.limit:
        sql += " LIMIT $2"
        params.append(args.limit)
    rows = await Database.fetch(sql, *params)
    await Database.close()

    written = copied = skipped = 0
    for row in rows:
        row = dict(row)
        portraits.ensure_dirs(row["name"])
        target = portraits.character_dir(row["name"]) / "sheet.md"
        # A legacy sheet may be named for the short form ("Maya", "Rika Voss")
        # while the database carries the full title ("Maya al-Dabaran (Anchor)").
        words = portraits.slugify(row["name"]).split("-")
        candidates = [
            portraits.slugify(row["name"]),
            "-".join(words[:2]),
            words[0],
        ]
        legacy = next((LEGACY_SHEETS / f"{slug}.md" for slug in candidates
                       if (LEGACY_SHEETS / f"{slug}.md").is_file()), LEGACY_SHEETS / f"{candidates[0]}.md")
        if target.exists() and not args.force:
            skipped += 1
            continue
        if legacy.is_file():
            target.write_text(legacy.read_text(encoding="utf-8"), encoding="utf-8")
            copied += 1
        else:
            target.write_text(render_sheet(row), encoding="utf-8")
            written += 1
    print(f"sheets: {written} generated · {copied} copied from legacy · {skipped} kept "
          f"({len(rows)} characters, session {args.session}) -> {portraits.CHARACTERS_ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
