#!/usr/bin/env python3
"""Re-queue the wives and the galaxy-crushing beauties at a new framing.

The King's scope, 2026-10-02: wives and the System's List, nothing else. 248 characters. 168 of them
hold their face on a **session-3** row, because the portrait assets were written there before the
restart and the session-5 twins never got one; the manifest reaches them through a name join. So the
queue goes on whichever row already owns the asset, and on the session-5 row for the 80 that have
none. Queueing a session-5 twin that already has a session-3 asset would create a second row and a
second file, and the manifest would then see one face twice.

    python3 scripts/requeue_framing.py --framing waist --dry-run
    python3 scripts/requeue_framing.py --framing waist --apply
"""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

POPULATION = """
    SELECT id, name FROM maya_rp.characters
     WHERE session_id = 5
       AND (beauty_catalog_id IS NOT NULL OR traits::text ILIKE '%confirmed-wife%')
"""


def main() -> int:
    import asyncio

    parser = argparse.ArgumentParser()
    parser.add_argument("--framing", default="waist", choices=("bust", "waist", "knee", "full"))
    parser.add_argument("--occasion", default="portrait")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    async def run() -> int:
        from core import portraits
        from core.db import Database

        await Database.init()
        rows = await Database.fetch(POPULATION)
        on_twin, on_self, skipped = 0, 0, 0
        for row in rows:
            # The asset's owner decides where the queue goes.
            owner = await Database.fetchrow(
                """SELECT c.session_id FROM maya_rp.character_assets a
                     JOIN maya_rp.characters c ON c.id = a.character_id
                    WHERE c.name = $1 AND a.kind = 'portrait' AND a.occasion = $2
                    ORDER BY (c.session_id = 3) DESC LIMIT 1""",
                row["name"], args.occasion)
            target = int(owner["session_id"]) if owner else 5
            if owner:
                on_twin += 1
            else:
                on_self += 1
            if not args.apply:
                continue
            try:
                await portraits.queue(target, row["name"], args.occasion, framing=args.framing)
            except ValueError as exc:
                skipped += 1
                print(f"  skip {row['name']}: {exc}")
        print(f"population {len(rows)} · queue on the asset's own row {on_twin} · on the session-5 row {on_self}"
              + (f" · skipped {skipped}" if skipped else ""))
        print("dry run: nothing written" if not args.apply else f"queued at framing={args.framing}")
        await Database.close()
        return 0

    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())
