#!/usr/bin/env python3
"""Re-queue existing portraits so they re-render from the current dossier text.

The render prompt is built from the character row and the sheet, so a dossier
edit (new `appearance`, new sheet prose) makes every existing PNG stale. This
script rebuilds the prompt for the occasions a character already has, flips the
rows back to `pending`, and leaves rendering to `scripts/portrait_render.py`.

Only existing rows are touched unless `--create-portrait` fills in the neutral
portrait for someone who has none. Failed rows can be re-queued too: they hold
the prompt that never rendered.

Usage:
    python3 scripts/portrait_requeue.py --scope wife
    python3 scripts/portrait_requeue.py --scope beauty
    python3 scripts/portrait_requeue.py --character "Maya al-Dabaran"
    python3 scripts/portrait_requeue.py --scope failed
    python3 scripts/portrait_requeue.py --scope beauty --dry-run
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


async def scope_ids(session: int, scope: str, character: str | None) -> list[dict]:
    """The characters a scope selects, oldest first."""
    where = "session_id=$1 AND status IS DISTINCT FROM 'dead'"
    if scope == "wife":
        where += " AND (is_spouse OR romance_stage = 'married')"
    elif scope == "beauty":
        where += " AND (beauty_standard IS TRUE OR beauty_catalog_id IS NOT NULL)"
    params: list = [session]
    if character:
        where += " AND name ILIKE $2"
        params.append(f"%{character}%")
    rows = await Database.fetch(
        f"SELECT id, name FROM maya_rp.characters WHERE {where} ORDER BY id", *params
    )
    return [dict(row) for row in rows]


async def main() -> int:
    parser = argparse.ArgumentParser(description="Re-queue portraits for a fresh render")
    parser.add_argument("--session", type=int, default=Config.SESSION_ID)
    parser.add_argument("--scope", choices=("all", "wife", "beauty", "failed"), default="wife")
    parser.add_argument("--character", default=None, help="limit the scope to one name")
    parser.add_argument("--occasion", default=None, help="only this occasion key (e.g. portrait)")
    parser.add_argument("--occasions", default=None,
                        help="comma list of occasion keys to queue, creating rows when missing"
                             " (e.g. bun,unbun)")
    parser.add_argument("--only", action="store_true",
                        help="queue only the --occasions keys, leaving existing rows untouched")
    parser.add_argument("--create-portrait", action="store_true",
                        help="queue the neutral portrait for characters that have no rows")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    await Database.init()
    if args.scope == "failed":
        rows = await Database.fetch(
            "SELECT DISTINCT c.id, c.name FROM maya_rp.character_assets a"
            " JOIN maya_rp.characters c ON c.id = a.character_id"
            " WHERE a.status='failed' ORDER BY c.id",
        )
        characters = [dict(row) for row in rows]
    else:
        characters = await scope_ids(args.session, args.scope, args.character)

    queued = people = 0
    for character in characters:
        assets = await Database.fetch(
            "SELECT occasion FROM maya_rp.character_assets"
            " WHERE character_id=$1 AND kind='portrait' ORDER BY id",
            character["id"],
        )
        occasions = [row["occasion"] for row in assets]
        if args.occasion:
            occasions = [occasion for occasion in occasions if occasion == args.occasion]
        extra = [key.strip() for key in (args.occasions or "").split(",") if key.strip()]
        if args.only:
            occasions = extra
        else:
            occasions += [key for key in extra if key not in occasions]
        if not occasions and args.create_portrait:
            occasions = ["portrait"]
        if not occasions:
            continue
        people += 1
        for occasion in occasions:
            if args.dry_run:
                print(f"DRY  {character['name']} [{occasion}]")
            else:
                result = await portraits.queue(args.session, character["name"], occasion)
                print(f"queued {character['name']} [{occasion}] -> emotion {result['emotion']}"
                      f" ({len(result['prompt'])} chars)")
            queued += 1
    await Database.close()
    print(f"{'would queue' if args.dry_run else 'queued'} {queued} render(s) across {people} character(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
