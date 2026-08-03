#!/usr/bin/env python3
"""Character Locations — current scene_location per character.

THIS is the scene-composition authority. Ship location (ship_sheet.py) is
reference only; who is PRESENT in a scene is determined here.

Usage:
  python3 scripts/char_locations.py             # all characters (spouses first)
  python3 scripts/char_locations.py <keyword>  # filter by name/location
"""
from __future__ import annotations
import asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.db import Database
from core.config import Config


async def main():
    args = sys.argv[1:]
    await Database.init()

    if args:
        kw = f"%{args[0]}%"
        rows = await Database.fetch(
            """SELECT name, COALESCE(scene_location,'?') AS loc, is_spouse, role
               FROM maya_rp.characters
               WHERE session_id=$1 AND (name ILIKE $2 OR COALESCE(scene_location,'') ILIKE $2)
               ORDER BY is_spouse DESC, name LIMIT 30""", Config.SESSION_ID, kw)
    else:
        rows = await Database.fetch(
            """SELECT name, COALESCE(scene_location,'?') AS loc, is_spouse, role
               FROM maya_rp.characters
               WHERE session_id=$1
               ORDER BY is_spouse DESC, name LIMIT 60""", Config.SESSION_ID)

    if not rows:
        print("No characters match.")
    for r in rows:
        mark = "👑" if r["is_spouse"] else "  "
        loc = r["loc"] if r["loc"] != "?" else "❓ unknown — ask/check rp-current-session"
        print(f"  {mark} {r['name']:<32} {loc}")
    await Database.close()


if __name__ == "__main__":
    asyncio.run(main())
