#!/usr/bin/env python3
"""Name every character folder `<id>-<slug>`.

The folder carries the database id, so a folder listing maps straight onto
`maya_rp.characters` without a name lookup. Renames are `git mv`-friendly (a
plain rename inside the tracked tree), and the recorded `image_path` values in
`maya_rp.character_assets` are repointed at the new folder in the same pass.

Idempotent: a folder already carrying its id is skipped.

Usage:
    python3 scripts/rename_character_folders.py --dry-run
    python3 scripts/rename_character_folders.py
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


async def main() -> int:
    parser = argparse.ArgumentParser(description="Rename character folders to <id>-<slug>")
    parser.add_argument("--session", type=int, default=Config.SESSION_ID)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    await Database.init()
    rows = await Database.fetch(
        "SELECT id, name FROM maya_rp.characters WHERE session_id=$1 ORDER BY id", args.session
    )
    renamed = already = missing = 0
    for row in rows:
        cid, name = row["id"], row["name"]
        slug = portraits.slugify(name)
        target = portraits.CHARACTERS_ROOT / f"{cid}-{slug}"
        current = portraits.CHARACTERS_ROOT / slug
        if target.is_dir():
            already += 1
            continue
        if not current.is_dir():
            missing += 1
            print(f"  no folder for {name} ({slug})")
            continue
        if args.dry_run:
            print(f"DRY  {slug} -> {target.name}")
        else:
            current.rename(target)
            await Database.execute(
                "UPDATE maya_rp.character_assets"
                " SET image_path = replace(image_path, $2, $3)"
                " WHERE character_id = $1 AND image_path IS NOT NULL",
                cid, str(current), str(target),
            )
        renamed += 1
    await Database.close()
    verb = "would rename" if args.dry_run else "renamed"
    print(f"{verb} {renamed}, already named {already}, missing {missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
