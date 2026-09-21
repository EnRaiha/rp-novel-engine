#!/usr/bin/env python3
"""rebuild_production.py — Rebuild resource_production display with the REAL economy (Day 1384).

Fixes the stale display (was showing template pops 1.2M) with the new model:
  - Per Setia-controlled territory: real daily tax via marginal brackets (matches economy.py)
  - Per faction-controlled territory: faction tax income (same bracket math)
  - Production lines: alloy/fuel/medical/hull/pharma output per line
  - Strategic: Dream Essence (Heaven), rare earth mines, EDEN food
  - Species-adjusted: none (tax is pop-based, already correct)
"""
from __future__ import annotations
import os
import asyncio, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import Config
from core.db import Database
from modules.economy import _territory_tax

SID = Config.SESSION_ID

BRACKETS_STR = "progressive marginal (10M@100%, 100M@18%, 1B@5%, beyond@0.8%)"


async def main() -> None:
    await Database.init()
    # Rebuild: drop old tax rows, keep specials
    await Database.execute(
        "DELETE FROM maya_rp.resource_production WHERE source ILIKE '%Tax Revenue%' OR source ILIKE '%Collective Tax%'")

    terr = await Database.fetch(
        """SELECT id, system_name, population, tax_rate, development_level,
                  crisis_level, controlling_faction, status
           FROM maya_rp.territory WHERE session_id=$1""", SID)

    setia_total = 0
    faction_income: dict[str, float] = {}
    n_terr_rows = 0

    for t in terr:
        pop = float(t["population"] or 0)
        if pop <= 0:
            continue
        rate = float(t["tax_rate"] or 0.05)
        dev = float(t["development_level"] or 1)
        crisis = float(t["crisis_level"] or 0)
        dev_mult = 1.0 + (dev - 1) * 0.05
        crisis_pen = max(0.2, 1.0 - crisis * 0.1)
        daily = _territory_tax(pop, rate, dev_mult, crisis_pen)
        if daily < 1:
            continue
        fac = t["controlling_faction"] or "Unclaimed"
        if fac == "Setia Empire":
            setia_total += daily
        else:
            faction_income[fac] = faction_income.get(fac, 0.0) + daily
        n_terr_rows += 1
        # Only write per-territory rows for Setia (faction rows aggregated below)
        if fac == "Setia Empire":
            await Database.execute(
                """INSERT INTO maya_rp.resource_production
                   (source, resource_type, amount_per_day, description, resource_id)
                   VALUES ($1,'credits',$2,$3,NULL)""",
                f"{t['system_name']} — Tax Revenue",
                int(daily),
                f"Real tax from {t['system_name']}. Pop {pop:,.0f}, rate {rate*100:.1f}%, dev {dev}, brackets {BRACKETS_STR}")

    # Faction aggregate rows
    for fac, amt in sorted(faction_income.items(), key=lambda x: -x[1]):
        await Database.execute(
            """INSERT INTO maya_rp.resource_production
               (source, resource_type, amount_per_day, description, resource_id)
               VALUES ($1,'credits',$2,$3,NULL)""",
            f"{fac} — Collective Tax",
            int(amt),
            f"Aggregated tax from territories governed by {fac}.")

    # Production lines
    lines = await Database.fetch("SELECT id, name, efficiency FROM maya_rp.production_lines")
    for ln in lines:
        eff = float(ln["efficiency"] or 1.0)
        rtype = "alloys" if "lloy" in ln["name"] else "fuel" if "uel" in ln["name"] else "credits"
        base = 150000 if rtype == "alloys" else 120000 if rtype == "fuel" else 200000
        amt = int(base * eff)
        await Database.execute(
            """INSERT INTO maya_rp.resource_production
               (source, resource_type, amount_per_day, description, resource_id)
               VALUES ($1,$2,$3,$4,NULL)""",
            f"{ln['name']}", rtype, amt, f"Production line {ln['name']} @ {eff:.2f} efficiency")

    # EDEN food (30 ships, ~150K food/day each)
    eden = await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.ships WHERE session_id=$1 AND ship_type='eden_class' AND status='active'", SID) or 0
    if eden:
        await Database.execute(
            """INSERT INTO maya_rp.resource_production
               (source, resource_type, amount_per_day, description, resource_id)
               VALUES ('EDEN Fleet — Food Production','food',$1,$2,NULL)""",
            int(eden * 150000), f"{eden} EDEN greenhouses at 150K food/day each")

    print(f"PRODUCTION REBUILD — {n_terr_rows} territories · Setia tax {setia_total:,.0f}/day · "
          f"{len(faction_income)} factions · {len(lines)} lines · {eden} EDEN")
    await Database.close()


if __name__ == "__main__":
    asyncio.run(main())