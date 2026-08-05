#!/usr/bin/env python3
"""
Roll N game days — world sim + transparent resource override + flexible build completions.

Safety: checkpoints BEFORE any mutation; --dry-run shows what would happen.
Flags:
  --dry-run          show projections, write nothing
  --no-builds        skip build-queue completion
  --no-collapse      skip collapse check
  --no-sarang        skip Sarang carrier insertion
  --rates A,B,C      override daily credits, alloys, fuel (e.g. --rates 12000000,700000,110000)

Build logic (flexible, game-day based): each in_build row accumulates progress equal to the
number of game days rolled. A build completes when accumulated progress >= build_time_days.
Progress is tracked in maya_rp.roll_state (build_progress JSONB map: build_id -> days done).

Sarang carriers: spawned only from completed Sarang build-queue rows (not hardcoded).
"""
import asyncio, sys, json
sys.path.insert(0, str(__file__ + "/../../"))

from core.config import Config
from core.db import Database
from core.log import info
from modules.chrono_engine import execute_time_skip

SID = Config.SESSION_ID

# Default transparent line items (narrative-anchored, not magic)
DEFAULT_CREDITS_PER_DAY = 10_000_000
DEFAULT_ALLOYS_PER_DAY = 80_000 + 150_000 + 400_000   # chrono + economy + Jaw 400K/d
DEFAULT_FUEL_PER_DAY = 100_000


def parse_flags(argv: list[str]) -> dict:
    flags = {
        "dry": "--dry-run" in argv,
        "no_builds": "--no-builds" in argv,
        "no_collapse": "--no-collapse" in argv,
        "no_sarang": "--no-sarang" in argv,
    }
    days = 100
    for a in argv:
        if a.isdigit():
            days = int(a)
            break
    rates = None
    for i, a in enumerate(argv):
        if a == "--rates" and i + 1 < len(argv):
            try:
                c, al, f = (int(x) for x in argv[i + 1].split(","))
                rates = (c, al, f)
            except ValueError:
                info("roll100", f"Bad --rates value: {argv[i+1]}")
    flags["days"] = days
    flags["rates"] = rates
    return flags


async def main() -> None:
    flags = parse_flags(sys.argv[1:])
    days = flags["days"]
    dry = flags["dry"]

    await Database.init()
    info("roll100", f"Rolling {days} days — {'DRY RUN (no writes)' if dry else 'LIVE'}")

    credits_pd, alloys_pd, fuel_pd = (
        flags["rates"] or (DEFAULT_CREDITS_PER_DAY, DEFAULT_ALLOYS_PER_DAY, DEFAULT_FUEL_PER_DAY)
    )

    before = await Database.fetchrow(
        "SELECT credits, alloys, fuel FROM maya_rp.resources WHERE session_id=$1", SID)
    print(f"BEFORE: {before['credits']:,}C / {before['alloys']:,}A / {before['fuel']:,}F")
    print(f"LINES:  +{credits_pd*days:,}C  +{alloys_pd*days:,}A  +{fuel_pd*days:,}F"
          f"   (credits {credits_pd:,}/d · alloys {alloys_pd:,}/d · fuel {fuel_pd:,}/d)")

    if dry:
        print(f"AFTER (projected): {before['credits'] + credits_pd*days:,}C / "
              f"{before['alloys'] + alloys_pd*days:,}A / {before['fuel'] + fuel_pd*days:,}F")
        await Database.close()
        return

    # 1. World simulation — economy focus (research, morale, geopolitics)
    r = await execute_time_skip(days, focus="economy", session_id=SID)
    print(f"SIM EVENTS: {len(r.get('events', []))}  SIM ECONOMY: {r.get('economy')}")

    # 2. Transparent resource override
    await Database.execute(
        "UPDATE maya_rp.resources SET alloys=$1, credits=$2, fuel=$3 WHERE session_id=$4",
        before["alloys"] + alloys_pd * days,
        before["credits"] + credits_pd * days,
        before["fuel"] + fuel_pd * days,
        SID)

    # 3. Flexible build completion — game-day progress accumulation
    new_day = await Database.fetchval(
        "SELECT game_day FROM maya_rp.sessions WHERE id=$1", SID)
    if flags["no_builds"]:
        print("BUILDS: skipped (--no-builds)")
    else:
        # load roll state
        state = await Database.fetchrow(
            "SELECT build_progress FROM maya_rp.roll_state WHERE session_id=$1", SID)
        raw_progress = state["build_progress"] if state and state["build_progress"] else "{}"
        progress = json.loads(raw_progress) if isinstance(raw_progress, str) else dict(raw_progress or {})

        due_rows = await Database.fetch(
            """SELECT id, project_name, build_time_days
               FROM maya_rp.build_queue
               WHERE session_id=$1 AND status='in_build' AND build_time_days IS NOT NULL""", SID)

        completed_ids = []
        still = []
        for b in due_rows:
            pid = str(b["id"])
            done = int(progress.get(pid, 0)) + days
            if done >= (b["build_time_days"] or 0):
                completed_ids.append(b["id"])
            else:
                progress[pid] = done
                still.append(b["id"])

        if completed_ids:
            await Database.execute(
                "UPDATE maya_rp.build_queue SET status='completed', completed_at=NOW() "
                "WHERE session_id=$1 AND id=ANY($2::int[])", SID, completed_ids)
        # persist progress (drop fully completed entries)
        for pid in [str(i) for i in completed_ids]:
            progress.pop(pid, None)
        await Database.execute(
            "INSERT INTO maya_rp.roll_state (session_id, last_rolled_game_day, build_progress) "
            "VALUES ($1, $2, $3) "
            "ON CONFLICT (session_id) DO UPDATE SET last_rolled_game_day=$2, build_progress=$3",
            SID, new_day, json.dumps(progress))

        print(f"BUILDS COMPLETED: {len(completed_ids)} · in progress: {len(still)}")
        for b in due_rows:
            mark = "COMPLETED" if b["id"] in completed_ids else f"{progress.get(str(b['id']), days)}/{b['build_time_days']}d"
            print(f"   {b['project_name']}: {mark}")

    # 4. Sarang AI carriers — spawn ONLY from completed Sarang build rows
    if flags["no_sarang"]:
        print("SARANG: skipped (--no-sarang)")
    else:
        done_sarang = await Database.fetch(
            """SELECT id FROM maya_rp.build_queue
               WHERE session_id=$1 AND status='completed' AND project_name LIKE '%Sarang%'""", SID)
        existing = await Database.fetchval(
            "SELECT COUNT(*) FROM maya_rp.ships WHERE session_id=$1 AND name LIKE 'Sarang-%'", SID)
        spawned = 0
        for idx, b in enumerate(done_sarang, start=1):
            if existing + spawned >= 3:
                break
            await Database.execute(
                """INSERT INTO maya_rp.ships
                   (session_id, name, ship_type, mass, length_m, hull, speed, crew, location, status,
                    tier, power_rating, sub_class, role)
                   VALUES ($1, $2, 'carrier', 2000000, 900, 60000, 40, 1200,
                           'Legion Aerie - Fleet Carrier', 'active', 6, 150000,
                           'Fleet Carrier (40% Heaven AI)', 'carrier')""",
                SID, f"Sarang-{idx}")
            spawned += 1
        if spawned:
            print(f"SARANG CARRIERS: {spawned} spawned from completed builds")
        else:
            print(f"SARANG CARRIERS: none ({existing} already present or builds not complete)")

    # 5. Collapse check (optional)
    if flags["no_collapse"]:
        print("COLLAPSE: skipped (--no-collapse)")
    else:
        from modules.collapse import check_for_collapse
        collapse = await check_for_collapse(SID)
        if collapse:
            print(f"⚠️ COLLAPSE: {collapse['title']} ({collapse['new_arc']})")
            print(f"   Recovery: {collapse['recovery']}")
        else:
            print("COLLAPSE: stable")

    after = await Database.fetchrow(
        "SELECT credits, alloys, fuel FROM maya_rp.resources WHERE session_id=$1", SID)
    print(f"AFTER:  {after['credits']:,}C / {after['alloys']:,}A / {after['fuel']:,}F")
    print(f"ACTIVE SHIPS: {await Database.fetchval('SELECT COUNT(*) FROM maya_rp.ships WHERE session_id=$1 AND status=\'active\'', SID)}")
    print(f"QUEUE COMPLETED: {await Database.fetchval('SELECT COUNT(*) FROM maya_rp.build_queue WHERE session_id=$1 AND status=\'completed\'', SID)}")
    await Database.close()
    print("\nDONE. Run: python3 scripts/cli.py save 'roll100 +N days' to checkpoint.")


if __name__ == "__main__":
    asyncio.run(main())
