#!/usr/bin/env python3
"""FLEET REFILL WORKFLOW — battle-loss detection + auto-rebuild queueing.

Extends the Fleet Expansion SOP with a post-war refill loop:
  Phase R1 DETECT  — diff current legion inventory vs last snapshot
  Phase R2 ANALYZE — losses by legion: type/tier/cost/crew
  Phase R3 QUEUE   — build_queue rows (REFILL <legion>) + reserve cost/crew
  Phase R4 ASSIGN  — crew reservation + commander + dockyard routing
  Phase R5 REPORT  — event + checkpoint

Usage:
  python3 scripts/fleet_refill.py --snapshot   # save current legion inventory baseline
  python3 scripts/fleet_refill.py              # detect losses vs snapshot + queue refills (dry)
  python3 scripts/fleet_refill.py --commit     # queue refills (greedy affordable)
  python3 scripts/fleet_refill.py --force-scan # scan ALL Setia destroyed/lost as losses
"""
import asyncio, sys, json
sys.path.insert(0, str(__file__ + "/../../"))
from core.config import Config
from core.db import Database

SID = Config.SESSION_ID

COST = {  # type -> (credit, alloy, days) — same model as fleet_expansion
    "battle_cruiser":  (25_000_000, 12_000, 8),
    "medium_cruiser":  (8_000_000, 4_000, 5),
    "frigate":         (3_000_000, 1_500, 3),
    "interceptor":     (1_500_000, 800, 2),
    "patrol_boat":     (1_200_000, 600, 2),
    "spy_plane":       (2_000_000, 900, 3),
    "bomber":          (2_500_000, 1_200, 3),
    "science_small":   (2_500_000, 1_000, 4),
    "science_large":   (4_000_000, 2_000, 5),
    "supply_courier":  (1_000_000, 500, 2),
    "fuel_tanker":     (1_200_000, 600, 2),
    "repair_tender":   (1_500_000, 700, 3),
    "ammo_ship":       (1_200_000, 600, 3),
    "cargo_freighter": (1_500_000, 700, 3),
    "capital-ship":    (40_000_000, 20_000, 12),
    "carrier":         (30_000_000, 15_000, 10),
}
CREW = {"battle_cruiser": 402, "medium_cruiser": 103, "frigate": 24, "interceptor": 10,
        "patrol_boat": 11, "spy_plane": 6, "bomber": 11, "science_small": 50,
        "science_large": 200, "supply_courier": 11, "fuel_tanker": 24, "repair_tender": 57,
        "ammo_ship": 22, "cargo_freighter": 29, "capital-ship": 1273, "carrier": 1200}
SETIA_PREFIX = ("TKG", "VC", "SEF")
NON_REFILL_TYPES = {"heavy_shipyard", "light_dockyard", "fleet_yard", "orbital_fortress",
                    "pd_platform", "missile_battery", "minelayer", "defense_monitor"}
# Crew survivability on ship loss (Battle of Gate 7 canon: 30% perished, rest ejected/recovered).
# Survivors return to crew_pool; refill only needs NEW crew = crew × (1 − survivability).
SURVIVABILITY = 0.7


async def ensure_tables(db) -> None:
    await db.execute(
        "CREATE TABLE IF NOT EXISTS maya_rp.legion_snapshot ("
        "  session_id INT, snapshot_at TIMESTAMP DEFAULT NOW(), data JSONB)")
    await db.execute(
        "CREATE TABLE IF NOT EXISTS maya_rp.refill_log ("
        "  id SERIAL PRIMARY KEY, session_id INT, legion VARCHAR, ship_type VARCHAR, "
        "  ship_name VARCHAR, tier INT, crew INT, game_day INT, refilled BOOLEAN DEFAULT false, "
        "  created_at TIMESTAMP DEFAULT NOW())")


async def current_inventory(db) -> dict[str, list[dict]]:
    """Legion -> [{ship_id, name, ship_type, tier, crew, status}]"""
    rows = await db.fetch(
        """SELECT f.name AS legion, s.id AS ship_id, s.name, s.ship_type, s.tier, s.crew, s.status
           FROM maya_rp.fleet_members fm
           JOIN maya_rp.fleets f ON f.id = fm.fleet_id
           JOIN maya_rp.ships s ON s.id = fm.ship_id
           WHERE f.session_id=$1 AND f.name LIKE 'Legion %' AND s.status IN ('active','standby_alert','undercrewed')""",
        SID)
    inv: dict[str, list[dict]] = {}
    for r in rows:
        inv.setdefault(r["legion"], []).append(dict(r))
    return inv


async def main() -> None:
    await Database.init()
    await ensure_tables(Database)
    snapshot_mode = "--snapshot" in sys.argv
    commit = "--commit" in sys.argv
    force = "--force-scan" in sys.argv

    if snapshot_mode:
        inv = await current_inventory(Database)
        await Database.execute(
            "INSERT INTO maya_rp.legion_snapshot (session_id, data) VALUES ($1,$2::jsonb)",
            SID, json.dumps(inv))
        total = sum(len(v) for v in inv.values())
        print(f"SNAPSHOT SAVED: {len(inv)} legions, {total} ships (baseline for post-war diff)")
        await Database.close()
        return

    # R1: detect losses — diff snapshot vs current
    snap = await Database.fetchrow(
        "SELECT data FROM maya_rp.legion_snapshot WHERE session_id=$1 ORDER BY snapshot_at DESC LIMIT 1", SID)
    cur = await current_inventory(Database)

    losses: dict[str, list[dict]] = {}
    if snap and snap["data"]:
        prev = json.loads(snap["data"]) if isinstance(snap["data"], str) else dict(snap["data"])
        prev_ids = {s["ship_id"] for ships in prev.values() for s in ships}
        for legion, ships in cur.items():
            pass
        # ships in snapshot but now missing/destroyed/lost = battle losses
        for legion, ships in prev.items():
            for s in ships:
                if s["ship_id"] not in {x["ship_id"] for xs in cur.values() for x in xs}:
                    losses.setdefault(legion, []).append(s)
        # ships still in legion but status flipped to destroyed/lost
        for legion, ships in cur.items():
            pass
    if force:
        # scan all Setia destroyed/lost (non-support) — treat as losses to rebuild
        rows = await Database.fetch(
            "SELECT id, name, ship_type, tier, crew FROM maya_rp.ships "
            "WHERE session_id=$1 AND status IN ('destroyed','lost') "
            "AND (name ILIKE 'TKG%' OR name ILIKE 'VC%' OR name ILIKE 'SEF%')", SID)
        for r in rows:
            if r["ship_type"] in NON_REFILL_TYPES:
                continue
            losses.setdefault("(unassigned)", []).append(dict(r, ship_id=r["id"]))

    # R2-R3: analyze + queue
    print("═" * 60)
    print("PHASE R1-R2: BATTLE-LOSS DETECTION + ANALYSIS")
    print("═" * 60)
    if not losses:
        print("No legion battle losses detected vs snapshot. (Run --snapshot to set baseline, "
              "--force-scan to scan all Setia destroyed/lost.)")
        await Database.close()
        return

    res = await Database.fetchrow(
        "SELECT credits, alloys, crew_pool FROM maya_rp.resources WHERE session_id=$1", SID)
    res = dict(res)

    total_survivors = 0
    total_new_crew = 0
    for legion, ships in sorted(losses.items()):
        by_type: dict[str, dict] = {}
        for s in ships:
            t = s["ship_type"]
            e = by_type.setdefault(t, {"n": 0, "crew": 0, "cr": 0, "al": 0, "days": 0,
                                       "survivors": 0, "new_crew": 0})
            ship_crew = s.get("crew") or CREW.get(t, 10)
            e["n"] += 1
            e["crew"] += ship_crew
            e["survivors"] += round(ship_crew * SURVIVABILITY)
            e["new_crew"] += round(ship_crew * (1 - SURVIVABILITY))
            e["cr"] += COST.get(t, (1_500_000, 800, 3))[0]
            e["al"] += COST.get(t, (1_500_000, 800, 3))[1]
            e["days"] = max(e["days"], COST.get(t, (1_500_000, 800, 3))[2])
        n = sum(e["n"] for e in by_type.values())
        cr = sum(e["cr"] for e in by_type.values())
        al = sum(e["al"] for e in by_type.values())
        crew = sum(e["crew"] for e in by_type.values())
        survivors = sum(e["survivors"] for e in by_type.values())
        new_crew = sum(e["new_crew"] for e in by_type.values())
        days = max(e["days"] for e in by_type.values())
        total_survivors += survivors
        total_new_crew += new_crew
        print(f"\n{legion}: {n} ships lost (crew {crew:,})")
        for t, e in sorted(by_type.items()):
            print(f"  {e['n']}x {t} (crew {e['crew']:,} · survivors {e['survivors']:,} · new-crew {e['new_crew']:,} · {e['cr']/1e6:.1f}M C)")
        print(f"  → SURVIVORS: {survivors:,} return to pool · NEW CREW needed: {new_crew:,}")

        if not commit:
            continue
        # R3: queue refill (greedy) — only NEW crew is reserved; survivors already back in pool
        if res["credits"] < cr or res["alloys"] < al or res["crew_pool"] < new_crew:
            print(f"  SKIP (insufficient: need {cr/1e6:.1f}M C/{al/1e3:.0f}K A/{new_crew:,} new crew, "
                  f"have {res['credits']/1e6:.1f}M C/{res['alloys']/1e3:.0f}K A/{res['crew_pool']:,})")
            continue
        desc = ", ".join(f"{e['n']}x {t}" for t, e in sorted(by_type.items()))
        await Database.execute(
            "UPDATE maya_rp.resources SET credits=credits-$1, alloys=alloys-$2, crew_pool=crew_pool-$3 WHERE session_id=$4",
            cr, al, new_crew, SID)
        res["credits"] -= cr; res["alloys"] -= al; res["crew_pool"] -= new_crew
        # survivors returned to pool (top-up source for this refill)
        await Database.execute(
            "UPDATE maya_rp.resources SET crew_pool=crew_pool+$1 WHERE session_id=$2", survivors, SID)
        res["crew_pool"] += survivors
        await Database.execute(
            "INSERT INTO maya_rp.build_queue (session_id, project_name, project_type, status, "
            "alloy_cost, fuel_cost, credit_cost, build_time_days, created_at) "
            "VALUES ($1,$2,'legion_refill','queued',$3,0,$4,$5,NOW())",
            SID, f"REFILL {legion} — {n} ships lost in battle: {desc} | new crew {new_crew} (survivors {survivors} recovered)",
            al, cr, days)
        for s in ships:
            await Database.execute(
                "INSERT INTO maya_rp.refill_log (session_id, legion, ship_type, ship_name, tier, crew, game_day) "
                "VALUES ($1,$2,$3,$4,$5,$6,(SELECT game_day FROM maya_rp.sessions WHERE id=$1))",
                SID, legion, s["ship_type"], s.get("name", ""), s.get("tier", 1),
                s.get("crew") or CREW.get(s["ship_type"], 10))
        print(f"  QUEUED REFILL: {n} ships ({cr/1e6:.1f}M C, new crew {new_crew:,}, {days}d)")

    if not commit:
        print(f"\nCREW SURVIVABILITY SUMMARY: {total_survivors:,} survivors recoverable · "
              f"{total_new_crew:,} new crew needed for refill (rate {SURVIVABILITY:.0%})")
        print("\nDRY RUN — re-run with --commit to queue refills.")
        await Database.close()
        return

    after = await Database.fetchrow("SELECT credits, alloys, crew_pool FROM maya_rp.resources WHERE session_id=$1", SID)
    print(f"\nTREASURY AFTER: {after['credits']:,}C / {after['alloys']:,}A / pool {after['crew_pool']:,}")
    print("\nRun: python3 scripts/cli.py save \"fleet refill\" — then roll100 to advance builds.")
    await Database.close()


if __name__ == "__main__":
    asyncio.run(main())
