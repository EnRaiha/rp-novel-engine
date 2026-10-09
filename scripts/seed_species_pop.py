#!/usr/bin/env python3
"""
seed_species_pop.py — Seed per-planet species composition (Stellaris-style pops, Day 1384).

Model (Izzat): population is resource-driven and faction-independent. Species composition
shows WHO lives on each planet:
  - Controlled-by-Setia planets: human-dominant (65-90%) + minority species mix
  - Neutral/faction-governed planets: faction-aligned species dominant + human minority
  - Frontier/abandoned: mixed opportunistic populations
Species weights respect market_available (only t species seed in volume; f = rare/unique).

  python3 scripts/seed_species_pop.py --session N            # report only
  python3 scripts/seed_species_pop.py --session N --apply    # replace the session's rows in one transaction
"""
from __future__ import annotations
import os
import asyncio, hashlib, random, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.db import Database
from scripts._oneshot import parse, guard

# Faction → dominant species (canon-flavored)
FACTION_SPECIES = {
    "Setia Empire (Kingdom)": "human",
    "Vein Collective": "human",
    "Iron Concord": "human",
    "The Silent Choir": "ghost",
    "The Demon Legions": "demon",
    "The Succubi Court": "succubus",
    "The Fairy Courts": "fairy",
    "The Spirit Weave": "spirit",
    "The Clone Legions": "clone",
    "The Cyber Collective": "cyborg",
    "The Swarm": "zerg",
    "The Dwarf Holdings": "dwarf",
    "The Seeder Gardens": "seeder",
    "The Ghost Chorus": "ghost",
    "The Half-Beast Clans": "half_beast",
    "The Hybrid Flotilla": "hybrid",
    "The Mechnoic": "mechanical",
    "The Cyber Collective": "cyborg",
}

# species_id lookup
SPECIES_ID = {}


async def main(argv=None) -> int:
    args = parse(__doc__, argv)
    guard(args)
    sid = args.session
    await Database.init()

    # species catalog
    for s in await Database.fetch("SELECT id, name, market_available FROM maya_rp.species_catalog"):
        SPECIES_ID[s["name"]] = {"id": s["id"], "avail": s["market_available"]}

    # planets with population > 0
    planets = await Database.fetch(
        """SELECT p.id, p.name, p.planet_type, p.population, p.territory_id,
                  t.controlling_faction, t.status, t.development_level
           FROM maya_rp.planets p
           JOIN maya_rp.territory t ON t.id = p.territory_id
           WHERE p.session_id=$1 AND p.population > 0""",
        sid)

    inserts: list[tuple] = []

    for pl in planets:
        pop = pl["population"]
        if pop <= 0:
            continue
        fac = pl["controlling_faction"] or ""
        rng = random.Random(int(hashlib.md5(f"sp-{pl['id']}".encode()).hexdigest(), 16) % (2**32))

        # dominant species
        dom_name = FACTION_SPECIES.get(fac, "human")
        if fac == "" or pl["status"] == "neutral":
            # frontier mixed: random available species dominant
            avail = [n for n, s in SPECIES_ID.items() if s["avail"]]
            dom_name = rng.choice(avail)

        # composition split
        dom_share = rng.uniform(0.55, 0.85) if pl["development_level"] >= 3 else rng.uniform(0.45, 0.70)
        minority_pool = [n for n, s in SPECIES_ID.items() if s["avail"] and n != dom_name]
        n_minor = rng.randint(1, 4)
        rng.shuffle(minority_pool)
        minority = minority_pool[:n_minor]

        # weights
        comp = {dom_name: dom_share}
        rest = 1.0 - dom_share
        for i, m in enumerate(minority):
            comp[m] = rest * (0.6 ** i) / sum(0.6 ** j for j in range(len(minority)))

        for name, share in comp.items():
            cnt = int(round(pop * share))
            if cnt <= 0:
                continue
            inserts.append((sid, pl["id"], SPECIES_ID[name]["id"], name, cnt, round(share * 100, 2),
                            name == dom_name))

    existing = await Database.fetchval(
        "SELECT count(*) FROM maya_rp.planet_population WHERE session_id=$1", sid)
    print(f"SPECIES POP SEED — {len(inserts)} species-pop rows across {len(planets)} populated planets "
          f"(session {sid} holds {existing} rows now)")
    if not args.apply:
        print("DRY RUN — re-run with --apply to replace them.")
        await Database.close()
        return 0

    async with Database.transaction() as conn:
        await conn.execute("DELETE FROM maya_rp.planet_population WHERE session_id=$1", sid)
        for row in inserts:
            await conn.execute(
                """INSERT INTO maya_rp.planet_population
                   (session_id, planet_id, species_id, species_name, count, pct, dominant, updated_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,NOW())
                   ON CONFLICT (session_id, planet_id, species_id) DO UPDATE
                   SET count=$5, pct=$6, dominant=$7, updated_at=NOW()""",
                *row)
    print(f"APPLIED — replaced {existing} rows with {len(inserts)}")
    await Database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))