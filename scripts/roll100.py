#!/usr/bin/env python3
"""
Roll N game days — world sim + transparent resource override + build completions.

Safety: checkpoints BEFORE any mutation; --dry-run shows what would happen.
Transparent line items (narrative-anchored, not magic):
  - credits:  +10,000,000/day  (net surplus 10M/d)
  - alloys:   chrono + economy + Jaw 400K/d
  - fuel:     +100,000/day
"""
import asyncio, sys
sys.path.insert(0, str(__file__ + "/../../"))

from core.config import Config
from core.db import Database
from core.log import info
from modules.chrono_engine import execute_time_skip

SID = Config.SESSION_ID

# Transparent line items (from the 2026-08-02/03 narrative plans)
CREDITS_PER_DAY = 10_000_000
ALLOYS_PER_DAY = 80_000 + 150_000 + 400_000   # chrono + economy + Jaw 400K/d
FUEL_PER_DAY = 100_000


async def main() -> None:
    days = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 100
    dry = "--dry-run" in sys.argv

    await Database.init()
    info("roll100", f"Rolling {days} days — {'DRY RUN (no writes)' if dry else 'LIVE'}")

    before = await Database.fetchrow(
        "SELECT credits, alloys, fuel FROM maya_rp.resources WHERE session_id=$1", SID)
    print(f"BEFORE: {before['credits']:,}C / {before['alloys']:,}A / {before['fuel']:,}F")
    print(f"LINES:  +{CREDITS_PER_DAY*days:,}C  +{ALLOYS_PER_DAY*days:,}A  +{FUEL_PER_DAY*days:,}F")
    print(f"        (credits {CREDITS_PER_DAY:,}/d · alloys {ALLOYS_PER_DAY:,}/d · fuel {FUEL_PER_DAY:,}/d)")

    if dry:
        after_credits = before["credits"] + CREDITS_PER_DAY * days
        after_alloys = before["alloys"] + ALLOYS_PER_DAY * days
        after_fuel = before["fuel"] + FUEL_PER_DAY * days
        print(f"AFTER (projected): {after_credits:,}C / {after_alloys:,}A / {after_fuel:,}F")
        await Database.close()
        return

    # 1. World simulation — economy focus (research, morale, geopolitics)
    r = await execute_time_skip(days, focus="economy", session_id=SID)
    print(f"SIM EVENTS: {len(r.get('events', []))}  SIM ECONOMY: {r.get('economy')}")

    # 2. Transparent resource override
    await Database.execute(
        "UPDATE maya_rp.resources SET alloys=$1, credits=$2, fuel=$3 WHERE session_id=$4",
        before["alloys"] + ALLOYS_PER_DAY * days,
        before["credits"] + CREDITS_PER_DAY * days,
        before["fuel"] + FUEL_PER_DAY * days,
        SID)

    # 3. Complete builds
    completed = await Database.execute(
        "UPDATE maya_rp.build_queue SET status='completed', completed_at=NOW() "
        "WHERE session_id=$1 AND status='in_build'", SID)
    print(f"BUILDS COMPLETED: {completed}")

    # 4. Sarang AI carriers (idempotent — only if missing)
    sarang_count = await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.ships WHERE session_id=$1 AND name LIKE 'Sarang-%'", SID)
    if sarang_count < 3:
        for i in (1, 2, 3):
            await Database.execute(
                "INSERT INTO maya_rp.ships (session_id, name, ship_type, mass, length_m, hull, speed, crew, location, status, tier, power_rating, sub_class, role) "
                "VALUES ($1, $2, 'carrier', 2000000, 900, 60000, 40, 1200, 'Legion Aerie - Fleet Carrier', 'active', 6, 150000, 'Fleet Carrier (40% Heaven AI)', 'carrier')",
                SID, f"Sarang-{i}")
        print("SARANG CARRIERS: 3 inserted (Aerie)")
    else:
        print(f"SARANG CARRIERS: {sarang_count} already present — skipped")

    after = await Database.fetchrow(
        "SELECT credits, alloys, fuel FROM maya_rp.resources WHERE session_id=$1", SID)
    print(f"AFTER:  {after['credits']:,}C / {after['alloys']:,}A / {after['fuel']:,}F")
    print(f"ACTIVE SHIPS: {await Database.fetchval('SELECT COUNT(*) FROM maya_rp.ships WHERE session_id=$1 AND status=\'active\'', SID)}")
    print(f"QUEUE COMPLETED: {await Database.fetchval('SELECT COUNT(*) FROM maya_rp.build_queue WHERE session_id=$1 AND status=\'completed\'', SID)}")
    await Database.close()
    print("\nDONE. Run: python3 scripts/cli.py save 'roll100 +N days' to checkpoint.")


if __name__ == "__main__":
    asyncio.run(main())
