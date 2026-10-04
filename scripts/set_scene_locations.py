#!/usr/bin/env python3
"""set_scene_locations — put the named cast where the prose puts them.

Every assignment carries the sentence it came from. A row whose character is not in
the session, or whose location is not in `maya_rp.location_catalog`, is reported and
skipped rather than written, because a slug that is not in the catalogue cannot be
matched by `get_characters_at_location` and would make the scene filter look empty
for a reason nobody could see.

Dry run by default. `--apply` writes.

    python3 scripts/set_scene_locations.py --session 5
    python3 scripts/set_scene_locations.py --session 5 --apply
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.db import Database  # noqa: E402
from core.log import info, warn  # noqa: E402

# Session 5, at the point after the three letters and before the seventh day.
#
# The player's character is `Izzat Aldebaran`, `controlled_by` = `gm`. There is no character named
# `player`: the three session-5 rows matching that word are `Izzat Aldebaran` (gm), and two AI rows,
# `King Izzat al-Setia` and `The Immortal Like Izzat (sealed)`.
ASSIGNMENTS: tuple[tuple[str, str, str], ...] = (
    ("Izzat Aldebaran", "rumah_agung",
     "Turn 74 `### 3. Rumah agung`: the 140-metre house north of the lake, built in month thirteen. "
     "The prose names no room of his, so the house is the narrowest place it supports."),
    ("Ersya Ardani", "rumah_agung_sayap_timur",
     "Turn 74, same section: 'Ersya Ardani tinggal di sayap timur, bilik lapan, dan dia tinggal di "
     "situ kerana dia memilihnya'. Turn 75 reads her letter 'di dalam biliknya di sayap timur'."),
    ("Sumayyah Harun", "garden_city_klinik",
     "Turn 75 `### 3. Sumayyah Harun`: she reads it 'di dalam klinik, di antara dua pesakit'. The "
     "day-64 report puts the main clinic in GARDEN, the central city."),
    ("Zulaikha Nadira", "amanah_arkib",
     "Turn 75 `### 4. Zulaikha Nadira`: she reads it 'di dalam bilik arkib, di dalam AMANAH di "
     "orbit', three days into reorganising the population records."),
    ("Wulan", "rumah_agung",
     "Turn 74: one of the twelve families living in the great house."),
    ("Lek", "rumah_agung", "Turn 74: one of the twelve families living in the great house."),
    ("Ruslan Bakar", "rumah_agung", "Turn 74: one of the twelve families living in the great house."),
    ("A-023", "rumah_agung", "Turn 74: named among the twelve families in the great house."),
    ("A-017", "rumah_agung", "Turn 74: named among the twelve families in the great house."),
    ("Bowo Sim", "rumah_agung", "Turn 74: named among the twelve families in the great house."),
    ("Boyet", "rumah_agung",
     "Turn 74: named among the twelve families. Fourteen now, and working at the river boat yard."),
)


async def apply_assignments(session: int, *, write: bool) -> int:
    catalogue = {r["name"] for r in await Database.fetch("SELECT name FROM maya_rp.location_catalog")}
    roster = {r["name"]: r["id"] for r in await Database.fetch(
        "SELECT id, name FROM maya_rp.characters WHERE session_id=$1", session)}

    changed = 0
    for name, location, source in ASSIGNMENTS:
        if location not in catalogue:
            warn("scene-locations", f"{name}: {location!r} is not in location_catalog; skipped")
            continue
        if name not in roster:
            warn("scene-locations", f"{name}: not in session {session}; skipped")
            continue
        before = await Database.fetchval(
            "SELECT scene_location FROM maya_rp.characters WHERE id=$1", roster[name])
        if before == location:
            info("scene-locations", f"{name}: already at {location}")
            continue
        if write:
            await Database.execute(
                "UPDATE maya_rp.characters SET scene_location=$1 WHERE id=$2",
                location, roster[name])
            after = await Database.fetchval(
                "SELECT scene_location FROM maya_rp.characters WHERE id=$1", roster[name])
            if after != location:
                warn("scene-locations", f"{name}: write did not take; still {after!r}")
                continue
        changed += 1
        info("scene-locations", f"{name}: {before!r} -> {location}   [{source[:60]}...]")

    if write:
        await Database.execute(
            "INSERT INTO maya_rp.player_context (session_id, location) VALUES ($1, $2)"
            " ON CONFLICT (session_id) DO UPDATE SET location=EXCLUDED.location",
            session, "rumah_agung")
        read_back = await Database.fetchrow(
            "SELECT location FROM maya_rp.player_context WHERE session_id=$1", session)
        info("scene-locations", f"player_context.location = {read_back['location'] if read_back else None}")
    return changed


async def main() -> int:
    parser = argparse.ArgumentParser(description="Place the named cast where the prose puts them.")
    parser.add_argument("--session", type=int, default=5)
    parser.add_argument("--apply", action="store_true", help="write; the default is a dry run")
    args = parser.parse_args()

    await Database.init()
    try:
        changed = await apply_assignments(args.session, write=args.apply)
    finally:
        await Database.close()

    verb = "set" if args.apply else "would set"
    print(f"{verb} {changed} of {len(ASSIGNMENTS)} assignment(s) in session {args.session}")
    if not args.apply:
        print("dry run: nothing written")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
