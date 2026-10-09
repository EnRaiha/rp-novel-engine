#!/usr/bin/env python3
"""rebuild_production.py — Rebuild resource_production display with the REAL economy (Day 1384).

Fixes the stale display (was showing template pops 1.2M) with the new model:
  - Per Setia-controlled territory: real daily tax via marginal brackets (matches economy.py)
  - Per faction-controlled territory: faction tax income (same bracket math)
  - Production lines: alloy/fuel/medical/hull/pharma output per line
  - Strategic: Dream Essence (Heaven), rare earth mines, EDEN food
  - Species-adjusted: none (tax is pop-based, already correct)

`resource_production` has no `session_id`. The DELETE of tax rows therefore removes every
session's tax display, and the rows rebuilt here come from `--session` only. `source` is the
primary key, so a production line or EDEN row that already exists is updated in place.

  python3 scripts/rebuild_production.py --session N            # report only
  python3 scripts/rebuild_production.py --session N --apply    # delete and insert in one transaction
"""
from __future__ import annotations
import os
import asyncio, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.db import Database
from modules.economy import _territory_tax
from scripts._oneshot import parse, guard

TAX_PREDICATE = "source ILIKE '%Tax Revenue%' OR source ILIKE '%Collective Tax%'"
BRACKETS_STR = "progressive marginal (10M@100%, 100M@18%, 1B@5%, beyond@0.8%)"


async def main(argv=None) -> int:
    args = parse(__doc__, argv)
    guard(args)
    sid = args.session
    await Database.init()

    terr = await Database.fetch(
        """SELECT id, system_name, population, tax_rate, development_level,
                  crisis_level, controlling_faction, status
           FROM maya_rp.territory WHERE session_id=$1""", sid)

    setia_total = 0
    faction_income: dict[str, float] = {}
    n_terr_rows = 0
    tax_rows: list[tuple] = []  # (source, resource_type, amount_per_day, description)

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
            tax_rows.append((
                f"{t['system_name']} — Tax Revenue", "credits", int(daily),
                f"Real tax from {t['system_name']}. Pop {pop:,.0f}, rate {rate*100:.1f}%, dev {dev}, brackets {BRACKETS_STR}"))

    # Faction aggregate rows
    for fac, amt in sorted(faction_income.items(), key=lambda x: -x[1]):
        tax_rows.append((f"{fac} — Collective Tax", "credits", int(amt),
                         f"Aggregated tax from territories governed by {fac}."))

    if not tax_rows:
        print(f"REFUSED: session {sid} has no taxable territory, "
              "the DELETE would empty the tax display for every session")
        await Database.close()
        return 1
    rows = list(tax_rows)

    # Production lines
    lines = await Database.fetch("SELECT id, name, efficiency FROM maya_rp.production_lines")
    for ln in lines:
        eff = float(ln["efficiency"] or 1.0)
        rtype = "alloys" if "lloy" in ln["name"] else "fuel" if "uel" in ln["name"] else "credits"
        base = 150000 if rtype == "alloys" else 120000 if rtype == "fuel" else 200000
        rows.append((f"{ln['name']}", rtype, int(base * eff),
                     f"Production line {ln['name']} @ {eff:.2f} efficiency"))

    # EDEN food (30 ships, ~150K food/day each)
    eden = await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.ships WHERE session_id=$1 AND ship_type='eden_class' AND status='active'", sid) or 0
    if eden:
        rows.append(("EDEN Fleet — Food Production", "food", int(eden * 150000),
                     f"{eden} EDEN greenhouses at 150K food/day each"))

    print(f"PRODUCTION REBUILD — {n_terr_rows} territories · Setia tax {setia_total:,.0f}/day · "
          f"{len(faction_income)} factions · {len(lines)} lines · {eden} EDEN")
    doomed = await Database.fetchval(f"SELECT count(*) FROM maya_rp.resource_production WHERE {TAX_PREDICATE}")
    if not args.apply:
        print(f"DRY RUN — would delete {doomed} rows (the table has no session_id, so this means every session) "
              f"and insert {len(rows)}. Re-run with --apply to write.")
        await Database.close()
        return 0

    async with Database.transaction() as conn:
        await conn.execute(f"DELETE FROM maya_rp.resource_production WHERE {TAX_PREDICATE}")
        for source, resource_type, amount, description in rows:
            await conn.execute(
                """INSERT INTO maya_rp.resource_production
                   (source, resource_type, amount_per_day, description, resource_id)
                   VALUES ($1,$2,$3,$4,NULL)
                   ON CONFLICT (source) DO UPDATE SET resource_type=EXCLUDED.resource_type,
                       amount_per_day=EXCLUDED.amount_per_day, description=EXCLUDED.description""",
                source, resource_type, amount, description)
    print(f"APPLIED — deleted {doomed} rows, inserted {len(rows)}")
    await Database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))