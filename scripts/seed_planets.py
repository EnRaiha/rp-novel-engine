#!/usr/bin/env python3
"""
seed_planets.py — Reseed planets across all systems (Day 1383, Izzat spec).

1. FULL PLANET TYPE CATALOG — every known type seeded somewhere.
2. MASTIKA SYSTEM (territory 170) — crafted exactly by Izzat:
   1 big sun · 5 big habitable · 2 gas giants · 2 ice worlds · 4 large asteroid fields
   · 1 gaia planet · 2 significant planets (random) · 1 molten planet
3. RESEED — every other system (territory) gets 1-8 planets, deterministic by coord hash.

Only Mastika is hand-crafted; the rest are generated.
"""
from __future__ import annotations
import os
import asyncio, hashlib, random, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import Config
from core.db import Database

SID = Config.SESSION_ID

# ---------------------------------------------------------------- type catalog
# (type, diameter_range_km, gravity_range_g, atmosphere, water%, habitability, biosphere)
PLANET_TYPES = {
    "Terran":       (9000, 15000, 0.9, 1.3, "nitrogen-oxygen", 60, 75,
                     "terrestrial — forests, seas, diverse biosphere"),
    "Gaia":         (11000, 16000, 0.95, 1.1, "perfect nitrogen-oxygen", 75, 100,
                     "superhabitable — lush biomes, thriving megafauna, gentle weather"),
    "Continental":  (8000, 14000, 0.85, 1.2, "nitrogen-oxygen", 50, 70,
                     "terrestrial — large landmasses, temperate zones, river systems"),
    "Ocean":        (9000, 16000, 0.9, 1.25, "nitrogen-oxygen humid", 80, 95,
                     "water world — vast seas, island chains, deep trenches"),
    "Desert":       (7000, 13000, 0.7, 1.1, "thin nitrogen", 5, 25,
                     "arid world — dunes, rock mesas, hidden oases"),
    "Arid":         (7500, 12500, 0.75, 1.05, "thin nitrogen-oxygen", 15, 40,
                     "semi-arid — scrublands, dry canyons, seasonal rivers"),
    "Tundra":       (6500, 12000, 0.7, 1.0, "cold nitrogen-oxygen", 10, 35,
                     "cold world — permafrost plains, sparse hardy flora"),
    "Ice World":    (4000, 9000, 0.5, 0.9, "frozen atmosphere", 5, 10,
                     "ice world — global cryosphere, subsurface oceans possible"),
    "Frozen":       (3000, 8000, 0.4, 0.8, "trace frozen gases", 0, 5,
                     "frozen rock — ancient ice crust, no active biosphere"),
    "Barren":       (2000, 6000, 0.3, 0.7, "none", 0, 0,
                     "barren rock — lifeless surface, mineral deposits"),
    "Rocky":        (1500, 5000, 0.25, 0.6, "none", 0, 0,
                     "rocky body — cratered, heavy metals, no atmosphere"),
    "Molten":       (5000, 11000, 1.0, 1.8, "sulfurous", 0, 0,
                     "molten world — lava seas, tectonic fury, young crust"),
    "Volcanic":     (4000, 10000, 0.8, 1.5, "volcanic gases", 0, 0,
                     "volcanic — active eruptions, mineral-rich ash plains"),
    "Toxic":        (8000, 13000, 0.9, 1.4, "dense CO2 sulfuric", 0, 0,
                     "toxic (venusian) — crushing atmosphere, acid clouds, metal rain"),
    "Gas Giant":    (60000, 160000, 2.0, 4.0, "hydrogen-helium", 0, 0,
                     "gas giant — storm cells, harvestable atmosphere, many moons"),
    "Ringed Gas Giant": (80000, 200000, 2.2, 4.5, "hydrogen-helium", 0, 0,
                     "ringed gas giant — spectacular bands, shepherd moons, 60+ moons"),
    "Ice Giant":    (40000, 65000, 1.2, 2.0, "methane-hydrogen", 0, 0,
                     "ice giant — methane haze, deep oceans of supercritical water"),
    "Dwarf Planet": (800, 2500, 0.05, 0.2, "none", 0, 0,
                     "dwarf planet — small, icy/rocky, trans-system body"),
    "Asteroid Field": (100, 500, 0.001, 0.05, "none", 0, 0,
                     "asteroid field — dense belt, mining-rich, navigational hazard"),
    "Carbon World": (6000, 12000, 0.8, 1.3, "hydrocarbon haze", 0, 0,
                     "carbon world — diamond crust, graphite plains, hydrocarbon seas"),
    "Crystal World":(5000, 10000, 0.6, 1.1, "thin crystalline", 0, 0,
                     "crystal world — silicate spires, reflective surfaces, exotic minerals"),
    "Habitat Station": (50, 200, 0.0, 1.0, "sealed oxygen", 5, 60,
                     "orbital habitat — artificial world, hydroponics, docking rings"),
    "Star":         (1000000, 3000000, 0, 0, "stellar plasma", 0, 0,
                     "star — system primary, fusion heart"),
}


def make_name(sysname: str, idx: int, label: str) -> str:
    """Deterministic planet name: 'SYSTEM-α', 'SYSTEM-β'... or label-based."""
    greek = "αβγδεζηθικλμνξοπρστυφχψω"
    if idx <= len(greek):
        return f"{sysname} {greek[idx-1]}"
    return f"{sysname} {label}-{idx}"


def make_planet(cursor_id: int, territory_id: int, sysname: str, idx: int,
                ptype: str, rng: random.Random) -> dict:
    t = PLANET_TYPES[ptype]
    d_min, d_max, g_min, g_max, atmo, w_min, w_max, bio = t
    diam = rng.randint(d_min, d_max)
    grav = round(rng.uniform(g_min, g_max), 2)
    water = rng.randint(w_min, w_max)
    if ptype in ("Terran", "Gaia", "Continental", "Ocean", "Tundra", "Arid"):
        hab_lo = max(0, int(w_max * 0.6))
        hab = rng.randint(min(hab_lo, w_max), w_max)
        if ptype == "Gaia":
            hab = 100
    elif ptype in ("Barren", "Rocky", "Molten", "Volcanic", "Toxic", "Gas Giant",
                   "Ringed Gas Giant", "Ice Giant", "Dwarf Planet", "Asteroid Field",
                   "Carbon World", "Crystal World", "Star", "Frozen", "Ice World"):
        hab = 0
    else:
        hab = 0
    name = make_name(sysname, idx, ptype.split()[0])
    return {
        "id": cursor_id, "session_id": SID, "name": name, "system_name": sysname,
        "diameter_km": diam, "gravity_g": grav, "atmosphere": atmo, "water_pct": water,
        "habitability_score": hab, "biosphere": bio, "status": "unexplored",
        "habitability": hab, "terraformable": ptype in ("Barren","Rocky","Arid","Tundra"),
        "planet_type": ptype, "features": "[]", "surveyed": False,
        "resource_modifiers": "{}", "territory_id": territory_id, "population": 0,
    }


# ---------------------------------------------------------------- mastika spec
MASTIKA = [  # (planet_type, label) — order = orbit position
    ("Star", "Sol Mastika"),
    ("Terran", "Mastika Prime"),      # 5 big habitable
    ("Continental", "Mastika Secunda"),
    ("Ocean", "Mastika Tertia"),
    ("Terran", "Mastika Quarta"),
    ("Continental", "Mastika Quinta"),
    ("Gas Giant", "Mastika Colossus I"),
    ("Ringed Gas Giant", "Mastika Colossus II"),
    ("Ice World", "Mastika Glacialis I"),
    ("Ice World", "Mastika Glacialis II"),
    ("Asteroid Field", "Mastika Belt Alpha"),
    ("Asteroid Field", "Mastika Belt Beta"),
    ("Asteroid Field", "Mastika Belt Gamma"),
    ("Asteroid Field", "Mastika Belt Delta"),
    ("Gaia", "Mastika Paradiso"),     # gaia — crown jewel
    ("Volcanic", "Mastika Ignis"),    # molten
    ("Barren", "Mastika Exsul"),      # significant random 1
    ("Crystal World", "Mastika Prism"),  # significant random 2
]


async def main() -> None:
    await Database.init()

    # Existing planet ids per territory (don't clobber crafted/surveyed)
    existing = await Database.fetch(
        "SELECT id, territory_id, name FROM maya_rp.planets WHERE session_id=$1 AND territory_id IS NOT NULL",
        SID)
    terr_has = {}
    for e in existing:
        terr_has.setdefault(e["territory_id"], []).append(e)

    # All territories
    terrs = await Database.fetch(
        "SELECT id, system_name FROM maya_rp.territory WHERE session_id=$1 ORDER BY id", SID)

    next_id = (await Database.fetchval("SELECT COALESCE(MAX(id),0) FROM maya_rp.planets WHERE session_id=$1", SID)) + 1

    rows = []
    mastika_terr = 170
    created = {"mastika": 0, "other": 0}

    for t in terrs:
        tid, sysname = t["id"], t["system_name"]
        rng = random.Random(int(hashlib.md5(str(tid).encode()).hexdigest(), 16) % (2**32))
        have = terr_has.get(tid, [])

        if tid == mastika_terr:
            # Mastika: keep existing (Mastika Prime etc.), add spec objects missing
            have_names = {h["name"] for h in have}
            for idx, (ptype, label) in enumerate(MASTIKA, start=1):
                if label in have_names:
                    continue
                rows.append(make_planet(next_id, tid, sysname, idx, ptype, rng))
                rows[-1]["name"] = label
                next_id += 1
                created["mastika"] += 1
        else:
            # Other systems: 1-8 planets, deterministic weighted by dev level
            dev = t.get("development_level") or 1
            n_planets = max(1, min(8, 1 + dev // 2 + rng.randint(0, 3)))
            if have:
                n_planets = max(0, n_planets - len(have))  # top-up only
            pool = [k for k in PLANET_TYPES if k != "Star"]
            weights = {
                "Terran": 3, "Continental": 2, "Ocean": 2, "Desert": 3, "Arid": 3,
                "Tundra": 2, "Ice World": 2, "Barren": 4, "Rocky": 4, "Gas Giant": 3,
                "Ringed Gas Giant": 1, "Ice Giant": 1, "Volcanic": 2, "Molten": 1,
                "Toxic": 1, "Dwarf Planet": 2, "Asteroid Field": 3, "Carbon World": 1,
                "Crystal World": 1, "Gaia": 0,
            }
            # at least 1 habitable-ish in developed systems
            if dev >= 3 and not have and n_planets >= 2:
                rows.append(make_planet(next_id, tid, sysname, 1, "Terran", rng))
                next_id += 1
                created["other"] += 1
                n_planets -= 1
            for i in range(n_planets):
                ptype = rng.choices(pool, weights=[weights.get(p, 1) for p in pool])[0]
                rows.append(make_planet(next_id, tid, sysname, len(have) + i + 2, ptype, rng))
                next_id += 1
                created["other"] += 1

    # Bulk insert
    for r in rows:
        await Database.execute(
            """INSERT INTO maya_rp.planets
               (id, session_id, name, system_name, diameter_km, gravity_g, atmosphere,
                water_pct, habitability_score, biosphere, status, habitability,
                terraformable, planet_type, features, surveyed, resource_modifiers,
                territory_id, population)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19)
               ON CONFLICT (id) DO NOTHING""",
            r["id"], r["session_id"], r["name"], r["system_name"], r["diameter_km"],
            r["gravity_g"], r["atmosphere"], r["water_pct"], r["habitability_score"],
            r["biosphere"], r["status"], r["habitability"], r["terraformable"],
            r["planet_type"], r["features"], r["surveyed"], r["resource_modifiers"],
            r["territory_id"], r["population"])

    print(f"SEED COMPLETE — Mastika +{created['mastika']} · other systems +{created['other']} · total rows {len(rows)}")
    await Database.close()


if __name__ == "__main__":
    asyncio.run(main())