#!/usr/bin/env python3
"""Export V2 character cards (M14, portability to third-party frontends).

One JSON per character: identity, personality, a scenario stub, the entrance
beat as `first_mes`, the voice few-shot as `mes_example`, and the play guide in
`creator_notes`. Cards are a snapshot; the folders stay the source of truth.

Usage: python3 scripts/export_character_cards.py --session 3 [--out DIR] [--limit N]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import Config  # noqa: E402
from core.db import Database  # noqa: E402
from core import context, persona, portraits  # noqa: E402


async def build_card(row: dict) -> dict:
    slug = portraits.slugify(row["name"])
    root = portraits.character_dir(row["name"])
    traits = portraits.parse_traits(row.get("traits"))
    sheet = portraits.sheet_text(row["name"])
    fields = {field: persona.read_field(slug, field) for field in persona.FIELDS}
    if not any(fields.values()):  # character fields live beside the sheet
        for field in persona.FIELDS:
            path = root / f"{field}.md"
            fields[field] = path.read_text(encoding="utf-8").strip() if path.is_file() else ""
    description = "\n\n".join(part for part in (row.get("appearance") or row.get("description") or "", sheet) if part)
    return {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": {
            "name": row["name"],
            "description": description[:4000],
            "personality": (f"{row.get('archetype') or ''} · {', '.join(str(t) for t in traits)}").strip(" ·"),
            "scenario": "",
            "first_mes": fields.get("intro", ""),
            "mes_example": fields.get("voice", ""),
            "creator_notes": fields.get("play-guide", ""),
            "system_prompt": fields.get("voice", ""),
            "post_history_instructions": "",
            "tags": [str(t) for t in traits][:8],
            "creator": "TKG / maya",
            "character_version": "1.0",
        },
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description="Export V2 character cards")
    parser.add_argument("--session", type=int, default=Config.SESSION_ID)
    parser.add_argument("--out", default="/home/maya/Bumi-Hijau/adventures/tkg/cards")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    await Database.init()
    sql = ("SELECT id, name, role, archetype, character_type, bond, romance_stage, traits,"
           " appearance, description FROM maya_rp.characters WHERE session_id=$1"
           " AND status IS DISTINCT FROM 'dead' ORDER BY COALESCE(bond,0) DESC, id")
    if args.limit:
        sql += f" LIMIT {int(args.limit)}"
    rows = await Database.fetch(sql, args.session)
    await Database.close()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    written = 0
    for row in rows:
        card = await build_card(dict(row))
        (out / f"{portraits.slugify(row['name'])}.json").write_text(
            json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
        written += 1
    print(f"cards: {written} written -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
