#!/usr/bin/env python3
"""relive_session — start a session over with the same world and cast.

The campaign may be re-lived: the same stations, the same queens, the same
dossiers — but nobody knows him, no empire exists, and every relationship starts
from nothing. This clones the cast of one session into another with the *state*
columns reset and the *dossier* columns carried over, so portraits, sheets,
voices and backgrounds keep working while the story starts clean.

World tables (fleets, economy, decrees, events, relationships…) are deliberately
**not** copied: a relived arc starts with an empty ledger, and the engine creates
defaults per session as they are needed.

The target session belongs to one novel, and `--novel` names it. The clone puts one story's
cast inside another campaign, so a target that already plays another novel is refused. A
target that does not exist yet is created with that novel.

    python3 scripts/relive_session.py --from 3 --to 5 --novel tkg-the-sunrise --dry-run
    python3 scripts/relive_session.py --from 3 --to 5 --novel tkg-the-sunrise
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.db import Database  # noqa: E402

# What a fresh start resets on every cloned character.
RESET: dict[str, Any] = {
    "bond": 0,
    "bond_level": 0,
    "romance_flag": False,
    "romance_stage": "strangers",
    "last_romance_scene": None,
    "is_spouse": False,
    "relationship_to_player": 0,
    "presence": "hidden",
    "scene_location": None,
    "last_seen_day": None,
    "clearance_level": 0,
    "screened": False,
    "crew_id": None,
    "ship_id": None,
    "inventory_jsonb": "{}",  # jsonb binds as text through asyncpg
}


async def main() -> int:
    parser = argparse.ArgumentParser(description="Clone a session's cast for a relived arc")
    parser.add_argument("--from", dest="source", type=int, required=True)
    parser.add_argument("--to", dest="target", type=int, required=True)
    parser.add_argument("--novel", required=True, help="novel_id of the session being relived")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    await Database.init()
    novel = await Database.fetchval(
        "SELECT novel_id FROM maya_rp.novels WHERE novel_id=$1", args.novel)
    if novel is None:
        print(f"refused: maya_rp.novels holds no novel {args.novel!r}", file=sys.stderr)
        await Database.close()
        return 2
    target_novel = await Database.fetchval(
        "SELECT novel_id FROM maya_rp.sessions WHERE id=$1", args.target)
    if target_novel is None:
        await Database.execute(
            "INSERT INTO maya_rp.sessions (id, name, status, game_day, novel_id)"
            " VALUES ($1, $2, 'active', 1, $3)",
            args.target, f"Relived from session {args.source}", args.novel)
    elif target_novel != args.novel:
        print(f"refused: session {args.target} plays novel {target_novel!r},"
              f" not {args.novel!r}; pass --novel {target_novel}", file=sys.stderr)
        await Database.close()
        return 2

    columns = [
        row["column_name"] for row in await Database.fetch(
            "SELECT column_name FROM information_schema.columns"
            " WHERE table_schema='maya_rp' AND table_name='characters' ORDER BY ordinal_position")
    ]
    copy_columns = [c for c in columns if c not in {"id", "session_id"}]

    roster = await Database.fetch(
        "SELECT * FROM maya_rp.characters WHERE session_id=$1 ORDER BY id", args.source)
    already = await Database.fetchval(
        "SELECT count(*) FROM maya_rp.characters WHERE session_id=$1", args.target)
    print(f"source session {args.source}: {len(roster)} characters"
          f" | target session {args.target} (novel {args.novel}): {already} already")

    if args.dry_run:
        sample = dict(roster[0]) if roster else {}
        print("would copy columns:", ", ".join(copy_columns[:10]), "…")
        print("would reset:", ", ".join(f"{k}={v!r}" for k, v in list(RESET.items())[:6]), "…")
        print("sample keeps:", {k: sample.get(k) for k in ("name", "role", "appearance")[:1]})
        await Database.close()
        return 0

    inserted = 0
    for row in roster:
        record = dict(row)
        values = [RESET.get(c, record.get(c)) for c in copy_columns]
        placeholders = ", ".join(f"${i + 2}" for i in range(len(copy_columns)))
        columns_sql = ", ".join(f'"{c}"' for c in copy_columns)
        await Database.execute(
            f'INSERT INTO maya_rp.characters ("session_id", {columns_sql})'
            f" VALUES ($1, {placeholders})",
            args.target, *values,
        )
        inserted += 1
    total = await Database.fetchval(
        "SELECT count(*) FROM maya_rp.characters WHERE session_id=$1", args.target)
    spouses = await Database.fetchval(
        "SELECT count(*) FROM maya_rp.characters WHERE session_id=$1 AND (is_spouse OR bond > 0)",
        args.target)
    print(f"cloned {inserted} characters into session {args.target}"
          f" (total {total}); relationships reset, {spouses} start with a bond")
    await Database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
