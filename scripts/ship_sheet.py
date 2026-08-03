#!/usr/bin/env python3
"""Ship Sheet — read-only ship stats + location reference.

Usage:
  python3 scripts/ship_sheet.py <name|fleet>   # search ships by name/fleet keyword
  python3 scripts/ship_sheet.py --fleet        # list all fleets + composition
  python3 scripts/ship_sheet.py --all          # all active ships summary

NOTE: location is REFERENCE data only — NOT scene state. Scene composition
is determined by character presence (see char_locations.py).
"""
from __future__ import annotations
import asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.db import Database
from core.config import Config


async def main():
    args = sys.argv[1:]
    await Database.init()

    if "--all" in args:
        rows = await Database.fetch(
            """SELECT c.class_name, s.sub_class, s.tier, count(*) AS n,
                      sum(s.power_rating) AS power
               FROM maya_rp.ships s JOIN maya_rp.ship_classes c ON c.id=s.class_id
               WHERE s.session_id=$1 AND s.status='active'
               GROUP BY c.class_name, s.sub_class, s.tier
               ORDER BY c.class_name, s.sub_class""", Config.SESSION_ID)
        for r in rows:
            print(f"  {r['class_name']:<18} {str(r['sub_class'] or ''):<22} T{r['tier']}  {r['n']:>4}x  {r['power']:>12,} power")
        await Database.close()
        return

    if "--fleet" in args:
        rows = await Database.fetch(
            """SELECT f.name, f.formation, f.status, count(fm.id) AS ships,
                      COALESCE(sum(s.power_rating),0) AS power
               FROM maya_rp.fleets f
               LEFT JOIN maya_rp.fleet_members fm ON fm.fleet_id=f.id
               LEFT JOIN maya_rp.ships s ON s.id=fm.ship_id
               WHERE f.session_id=$1 GROUP BY f.id ORDER BY f.id""", Config.SESSION_ID)
        for r in rows:
            print(f"  {r['name']:<35} [{r['formation']:<9}] {r['ships']:>4} ships  {r['power']:>14,} power")
        await Database.close()
        return

    if not args:
        print(__doc__)
        await Database.close()
        return

    keyword = f"%{args[0]}%"
    rows = await Database.fetch(
        """SELECT s.name, c.class_name, s.sub_class, s.tier, s.hull, s.speed, s.crew,
                  s.power_rating, s.status, s.location
           FROM maya_rp.ships s LEFT JOIN maya_rp.ship_classes c ON c.id=s.class_id
           WHERE s.session_id=$1 AND (s.name ILIKE $2 OR s.location ILIKE $2 OR c.class_name ILIKE $2)
           ORDER BY s.power_rating DESC LIMIT 20""", Config.SESSION_ID, keyword)
    if not rows:
        print(f"No ships match '{args[0]}'")
    for r in rows:
        print(f"  {r['name']:<32} {r['class_name'] or '?':<16} {str(r['sub_class'] or ''):<22} "
              f"T{r['tier']} hull {r['hull']:>8,} {r['power_rating']:>10,}p [{r['status']}] {r['location']}")
    await Database.close()


if __name__ == "__main__":
    asyncio.run(main())
