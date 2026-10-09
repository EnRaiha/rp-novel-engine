#!/usr/bin/env python3
"""Materialize Legio I-IV ships (Day 2101 fix).

Builds 31-34 (LEGIO I-IV DEPLOYED, completed 2026-08-10, 1.355M alloys / 2.73B C each)
were paid but never spawned hulls — ship_building.py has no legion_build handler,
so completed legion_build queue items are no-ops in the tick.

Fix: create 120 ships per Legio (100 warships + 20 support, T5 standard from
fleet_expansion.py: WAR_TARGET=100 +20% / SUP_TARGET=20) and assign to the
Legio fleets. Duplicate queued builds 82-85 are cancelled in the named session.
A Legio that already has ships is skipped.

Run:  set -a; source ~/.env; set +a
      python3 scripts/materialize_legio.py --session N            # report only
      python3 scripts/materialize_legio.py --session N --apply    # write
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.db import Database
from modules.ship_generation import generate_ship
from scripts._oneshot import parse, guard

# (ship_type, class_name, count) — the 120-ship legion standard template
TEMPLATE = [
    ("battle_cruiser", "Battle Cruiser", 2),
    ("medium_cruiser", "Medium Cruiser", 12),
    ("frigate", "Frigate", 20),
    ("interceptor", "Corvette", 40),
    ("patrol_boat", "Corvette", 12),
    ("spy_plane", "Scout", 8),
    ("bomber", "Corvette", 6),
    ("supply_courier", "Corvette", 8),
    ("fuel_tanker", "Freighter", 4),
    ("science_small", "Science Vessel", 4),
    ("repair_tender", "Freighter", 2),
    ("ammo_ship", "Freighter", 2),
]

# Deploy canon (builds 31-34): I NORTH, II SOUTH, III WEST, IV EAST
LEGIOS = [
    ("Legio I", "TKG Legio I", "Setia North — Bayu Base"),
    ("Legio II", "TKG Legio II", "Setia South — Waja Base"),
    ("Legio III", "TKG Legio III", "Setia West — Relau Base"),
    ("Legio IV", "TKG Legio IV", "Setia East — Aman Base"),
]

TIER = 5


async def main(argv=None) -> int:
    args = parse(__doc__, argv)
    guard(args)
    sid = args.session
    await Database.init()
    total = 0
    for legion_name, prefix, loc in LEGIOS:
        fleet_id = await Database.fetchval(
            "SELECT id FROM maya_rp.fleets WHERE name=$1 AND session_id=$2",
            legion_name, sid)
        if not fleet_id:
            print(f"!! fleet {legion_name} missing — skipping")
            continue
        members = await Database.fetchval(
            "SELECT count(*) FROM maya_rp.fleet_members WHERE fleet_id=$1", fleet_id)
        if members:
            print(f"{legion_name} already has {members} ships, skipping")
            continue
        if not args.apply:
            print(f"{legion_name}: would create {sum(c for *_, c in TEMPLATE)} ships")
            continue
        pos = 0
        for ship_type, class_name, count in TEMPLATE:
            for _ in range(count):
                pos += 1
                name = f"{prefix}-{pos:02d}"
                ship = await generate_ship(class_name, TIER, ship_type, name, sid)
                if "error" in ship:
                    print(f"!! {name}: {ship['error']}")
                    continue
                ship_id = await Database.fetchval(
                    "INSERT INTO maya_rp.ships (session_id, name, class_id, ship_type, mass, length_m, hull, hull_current, "
                    "speed, crew, location, tier, status) VALUES ($1,$2,$3,$4,$5,$6,$7,$7,$8,$9,$10,$11,'active') RETURNING id",
                    sid, name, ship["class_id"], ship["ship_type"], ship["mass"], ship["length_m"],
                    ship["hull"], ship["speed"], ship["crew"], loc, TIER)
                for arm in ship["armaments"]:
                    await Database.execute(
                        "INSERT INTO maya_rp.ship_armaments (ship_id, weapon_id, slot_index, slot_size) VALUES ($1,$2,$3,$4)",
                        ship_id, arm["weapon_id"], arm["slot_index"], arm["slot_size"])
                for i, m in enumerate(ship["modules"]):
                    await Database.execute(
                        "INSERT INTO maya_rp.ship_modules (ship_id, module_id, slot_index) VALUES ($1,$2,$3)",
                        ship_id, m["module_id"], i)
                speed_rating = ("very_fast" if ship["speed"] > 80 else "fast" if ship["speed"] > 60
                                else "medium" if ship["speed"] > 40 else "slow" if ship["speed"] > 20 else "very_slow")
                evasion = min(80, max(10, round(ship["speed"] * 0.5)))
                combat_rating = round(ship["hull"] * 0.3 + ship["speed"] * 0.5 + ship["crew"] * 0.2)
                await Database.execute(
                    "INSERT INTO maya_rp.combat_stats (ship_id, hull_points, max_hull_points, shield_points, "
                    "max_shield_points, speed, evasion, combat_rating) VALUES ($1,$2,$3,$4,$5,$6,$7,$8) "
                    "ON CONFLICT (ship_id) DO NOTHING",
                    ship_id, ship["hull"], ship["hull"], round(ship["hull"] * 0.6), round(ship["hull"] * 0.6),
                    speed_rating, evasion, combat_rating)
                await Database.execute(
                    "INSERT INTO maya_rp.fleet_members (fleet_id, ship_id, position) VALUES ($1,$2,$3)",
                    fleet_id, ship_id, ((pos - 1) % 10) + 1)
                total += 1
        print(f"{legion_name}: {pos} ships materialized")
    if not args.apply:
        print("DRY RUN — re-run with --apply to write.")
        await Database.close()
        return 0
    await Database.execute(
        "UPDATE maya_rp.build_queue SET status='cancelled' "
        "WHERE id BETWEEN 82 AND 85 AND session_id=$1 AND status='queued'", sid)
    if total > 0:
        await Database.execute(
            "INSERT INTO maya_rp.events (session_id, event_type, title, description, importance) "
            "VALUES ($1,'legion_deploy','Legio I-IV ships materialized',$2,4)",
            sid,
            f"Completed builds 31-34 (2026-08-10) never spawned ships — engine bug "
            f"(ship_building.py has no legion_build handler). {total} hulls created now: "
            f"120 per Legio (100 warships + 20 support, T5). Duplicate queued builds 82-85 cancelled.")
    await Database.close()
    print(f"TOTAL: {total} ships")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
