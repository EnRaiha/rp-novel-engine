#!/usr/bin/env python3
"""Ship data repair — fix class_id mapping, regen hull/speed/crew from class
base, assign sub-class variants, compute power_rating consistent with
faction_ships (power = hull * tier * class_factor).

Run: python3 fix_ship_data.py [--dry-run]
"""
from __future__ import annotations
import asyncio, os, sys, random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.db import Database
from core.config import Config

# ship_type (role) -> proper class_name
ROLE_CLASS = {
    "interceptor": "Corvette",
    "spy_plane": "Scout",
    "patrol_boat": "Corvette",
    "frigate": "Frigate",
    "medium_cruiser": "Medium Cruiser",
    "heavy_cruiser": "Heavy Cruiser",
    "battle_cruiser": "Battle Cruiser",
    "battleship": "Battleship",
    "capital-ship": "Dreadnought",
    "DRM": "Dreadnought",
    "SPC": "Medium Cruiser",   # overridden per-ship for GS names below
    "arkship": "Carrier",
    "heavy_shipyard": "Freighter",
    "fleet_yard": "Freighter",
    "light_dockyard": "Freighter",
    "ammo_ship": "Freighter",
    "cargo_freighter": "Freighter",
    "fuel_tanker": "Freighter",
    "supply_courier": "Corvette",
    "repair_tender": "Freighter",
    "hospital_ship": "Freighter",
    "harvester": "Freighter",
    "refinery": "Freighter",
    "science_vessel": "Science Vessel",
    "science_small": "Science Vessel",
    "science_medium": "Science Vessel",
    "science_large": "Science Vessel",
    "ew_ship": "Corvette",
    "bomber": "Corvette",
    "escort_capital": "Frigate",
    "orbital_fortress": "Battleship",
    "missile_battery": "Frigate",
    "pd_platform": "Frigate",
    "minelayer": "Frigate",
    "defense_monitor": "Frigate",
    "unknown_colossal": "Fleet Carrier",
}

# Per-name class overrides (GS integrated + key ships)
NAME_CLASS = {
    "Ghost-1": "Frigate", "Ghost-2": "Frigate",
    "Wraith-1": "Heavy Cruiser", "Wraith-2": "Heavy Cruiser",
    "Phantom-1": "Dreadnought",
    "TKG Silent Maw": "Dreadnought",
    "TKG Nusantara": "Battle Cruiser",
    "TKG Silent Wing": "Scout",
}

# Per-name sub-class overrides (GS ships have canonical variant names)
NAME_SUBCLASS = {
    "Ghost-1": "Ghost Frigate", "Ghost-2": "Ghost Frigate",
    "Wraith-1": "Wraith Cruiser", "Wraith-2": "Wraith Cruiser",
    "Phantom-1": "Phantom Dreadnought",
}

# GS integrated ships keep their authored faction stats (faction_ships)
GS_NAMES = {"Ghost-1", "Ghost-2", "Wraith-1", "Wraith-2", "Phantom-1"}

# power_rating = hull * tier * factor  (calibrated vs faction_ships)
CLASS_POWER_FACTOR = {
    "Frigate": 0.60, "Destroyer": 0.50, "Light Cruiser": 0.46,
    "Medium Cruiser": 0.42, "Heavy Cruiser": 0.38, "Battle Cruiser": 0.36,
    "Battleship": 0.32, "Dreadnought": 0.30, "Carrier": 0.30,
    "Fleet Carrier": 0.30, "Scout": 0.70, "Corvette": 0.70,
    "Science Vessel": 0.45, "Freighter": 0.25, "Colony Ship": 0.25,
}

DRY_RUN = "--dry-run" in sys.argv


def roll_stat(base: int, tier: int, scale: float = 1.15, variance: float = 0.08) -> int:
    mult = scale ** max(tier - 1, 0)
    return round(base * mult * (1 + random.uniform(-variance, variance)))


async def main():
    await Database.init()
    classes = {r["class_name"]: r for r in await Database.fetch(
        "SELECT id, class_name, base_hull, base_speed, base_crew FROM maya_rp.ship_classes")}
    subclasses = await Database.fetch(
        "SELECT ship_type, sub_class, hull_mult, speed_mult, crew_mult, power_mult FROM maya_rp.ship_sub_classes")

    # sub-class pool per ship_type for round-robin variety
    pool_by_type: dict[str, list[dict]] = {}
    for sc in subclasses:
        pool_by_type.setdefault(sc["ship_type"], []).append(sc)
    counters: dict[str, int] = {}

    ships = await Database.fetch(
        "SELECT id, name, ship_type, tier, status FROM maya_rp.ships WHERE session_id=$1",
        Config.SESSION_ID)

    fixed_class = regen = sub_assigned = power_set = 0
    for s in ships:
        st = s["ship_type"]
        # 1. class_id
        class_name = NAME_CLASS.get(s["name"]) or ROLE_CLASS.get(st)
        if not class_name or class_name not in classes:
            print(f"  SKIP {s['name']} ({st}): no class mapping")
            continue
        c = classes[class_name]
        new_class_id = c["id"]
        # 2. sub-class assignment (round-robin per type, name override wins)
        pool = pool_by_type.get(st) or []
        sub = None
        sub_name = NAME_SUBCLASS.get(s["name"])
        if not sub_name:
            if pool:
                i = counters.get(st, 0)
                counters[st] = i + 1
                sub = pool[i % len(pool)]
                sub_name = sub["sub_class"]
            if sub_name is None and s["name"] in GS_NAMES:
                sub_name = st  # DRM/SPC fallback
        hm = float(sub["hull_mult"]) if sub else 1.0
        sm = float(sub["speed_mult"]) if sub else 1.0
        cm = float(sub["crew_mult"]) if sub else 1.0
        pm = float(sub["power_mult"]) if sub else 1.0

        # 3. stats: GS ships keep authored faction stats; others regen from
        #    class base (active + under_construction regen; lost/hostile keep
        #    hull but still get class + power fixed)
        regen_this = s["status"] in ("active", "under_construction")
        if s["name"] in GS_NAMES:
            fs = await Database.fetchrow(
                "SELECT hull, speed, crew, power_rating FROM maya_rp.faction_ships "
                "WHERE session_id=$1 AND ship_name=$2 AND faction_name ILIKE '%ghost%' LIMIT 1",
                Config.SESSION_ID, s["name"])
            if fs:
                hull, speed, crew, power = fs["hull"], fs["speed"], fs["crew"], fs["power_rating"]
                hm = sm = cm = pm = 1.0
                regen_this = False
            else:
                regen_this = True
        elif regen_this:
            hull = roll_stat(c["base_hull"], s["tier"]) * hm
            speed = max(1, round(c["base_speed"] / (1.15 ** (max(s["tier"] - 1, 0)) * 0.5) * sm))
            crew = roll_stat(c["base_crew"], s["tier"], 1.12) * cm
        else:
            row = await Database.fetchrow(
                "SELECT hull, speed, crew FROM maya_rp.ships WHERE id=$1", s["id"])
            hull, speed, crew = row["hull"], row["speed"], row["crew"]

        hull = int(hull)
        if not (s["name"] in GS_NAMES and fs):
            power = int(round(hull * s["tier"] * CLASS_POWER_FACTOR.get(class_name, 0.4) * pm))

        if not DRY_RUN:
            await Database.execute(
                """UPDATE maya_rp.ships SET class_id=$1, sub_class=$2, hull=$3, hull_current=$4,
                   speed=$5, crew=$6, power_rating=$7 WHERE id=$8""",
                new_class_id, sub_name, hull, hull, speed, crew, power, s["id"])
        if new_class_id != s.get("class_id"):
            fixed_class += 1
        if regen_this:
            regen += 1
        if sub_name:
            sub_assigned += 1
        power_set += 1

    print(f"DRY_RUN={DRY_RUN}")
    print(f"  class fixed: {fixed_class} | stats regen: {regen} | sub-class: {sub_assigned} | power: {power_set}")
    await Database.close()


if __name__ == "__main__":
    asyncio.run(main())
