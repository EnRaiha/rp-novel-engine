#!/usr/bin/env python3
"""Fill Legio I-IV to FULL STRENGTH (Day 2101).

Canon (legio_structure, Sera's Roman doctrine): 4 Legio × 10 centuries
(century 1 = elite T5, centuries 2-10 = standard T4) × 10 cohorts × 100 ships
= 1,000/century · 10,000/Legio · 40,000 full strength.

Run:  set -a; source ~/.env; set +a; python3 scripts/materialize_legio_full.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import Config
from core.db import Database
from modules.ship_generation import generate_ship

# 100-ship cohort template (structure table: ships_per_cohort = 100)
TEMPLATE = [
    ("battle_cruiser", "Battle Cruiser", 2),
    ("medium_cruiser", "Medium Cruiser", 10),
    ("frigate", "Frigate", 17),
    ("interceptor", "Corvette", 33),
    ("patrol_boat", "Corvette", 10),
    ("spy_plane", "Scout", 7),
    ("bomber", "Corvette", 5),
    ("supply_courier", "Corvette", 6),
    ("fuel_tanker", "Freighter", 3),
    ("science_small", "Science Vessel", 3),
    ("repair_tender", "Freighter", 2),
    ("ammo_ship", "Freighter", 2),
]  # total = 100

LEGIOS = [
    ("Legio I", "TKG Legio I", "Setia North — Bayu Base"),
    ("Legio II", "TKG Legio II", "Setia South — Waja Base"),
    ("Legio III", "TKG Legio III", "Setia East — Relau Base"),
    ("Legio IV", "TKG Legio IV", "Setia West — Aman Base"),
]

CENTURIES = 10
COHORTS = 10
PER_COHORT = 100
TARGET = CENTURIES * COHORTS * PER_COHORT  # 10,000 per Legio
SESSION = 3


async def main() -> None:
    await Database.init()
    sid = Config.SESSION_ID if Config.SESSION_ID else SESSION
    grand_total = 0
    for legion_name, prefix, loc in LEGIOS:
        fleet_id = await Database.fetchval(
            "SELECT id FROM maya_rp.fleets WHERE name=$1 AND session_id=$2", legion_name, sid)
        if not fleet_id:
            print(f"!! fleet {legion_name} missing — skipping")
            continue
        existing = await Database.fetchval(
            "SELECT count(*) FROM maya_rp.fleet_members WHERE fleet_id=$1", fleet_id)
        pos = existing
        created = 0
        for century in range(1, CENTURIES + 1):
            tier = 5 if century == 1 else 4  # century 1 elite T5, rest standard T4
            for _ in range(COHORTS):
                for ship_type, class_name, count in TEMPLATE:
                    for _ in range(count):
                        pos += 1
                        name = f"{prefix}-{pos:04d}"
                        ship = await generate_ship(class_name, tier, ship_type, name, sid)
                        if "error" in ship:
                            print(f"!! {name}: {ship['error']}")
                            continue
                        ship_id = await Database.fetchval(
                            "INSERT INTO maya_rp.ships (session_id, name, class_id, ship_type, mass, length_m, hull, hull_current, "
                            "speed, crew, location, tier, status) VALUES ($1,$2,$3,$4,$5,$6,$7,$7,$8,$9,$10,$11,'active') RETURNING id",
                            sid, name, ship["class_id"], ship["ship_type"], ship["mass"], ship["length_m"],
                            ship["hull"], ship["speed"], ship["crew"], loc, tier)
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
                        created += 1
        grand_total += created
        print(f"{legion_name}: +{created} ships (total {existing + created})")
    await Database.execute(
        "INSERT INTO maya_rp.events (session_id, event_type, title, description, importance) "
        "VALUES ($1,'legion_deploy','Legio I-IV FULL STRENGTH — 40,000 ships',$2,4)",
        sid,
        f"Legio field armies filled to full size per legio_structure: 4 × 10 centuries "
        f"(century 1 elite T5, 2-10 standard T4) × 10 cohorts × 100 ships = 10,000/Legio, "
        f"40,000 total. {grand_total} new hulls created.")
    await Database.close()
    print(f"GRAND TOTAL CREATED: {grand_total}")


if __name__ == "__main__":
    asyncio.run(main())
