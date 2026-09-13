#!/usr/bin/env python3
"""setia_governor_model.py — Setia governor autonomy model (Day 1384, Izzat rule).

Setia's 109 governed territories run under their governors' authority (autonomous,
model-driven), EXCEPT Mastika (capital, id 170) which REQUIRES the King's prompt
before any major action.

Per governor (territory):
  - sentiment of population toward Setia Empire → approval/trust baseline
  - territory economy (tax/day) → governor competence rating
  - species composition → governance flavor (diversity index)
  - title_performance updated from live numbers
  - autonomy: FALSE at Mastika (requires_king_prompt), TRUE elsewhere
"""
from __future__ import annotations
import asyncio, sys
sys.path.insert(0, str(__file__ + "/../../"))
from core.config import Config
from core.db import Database

SID = Config.SESSION_ID


async def main() -> None:
    await Database.init()
    terr = await Database.fetch(
        """SELECT id, system_name, governor_name, tax_rate, development_level,
                  title_performance, population
           FROM maya_rp.territory
           WHERE session_id=$1 AND controlling_faction='Setia Empire'""", SID)

    updated = 0
    for t in terr:
        tid = t["id"]
        # Sentiment of population toward Setia at this territory
        sent = float(await Database.fetchval(
            """SELECT COALESCE(AVG(sentiment),0) FROM maya_rp.population_sentiment
               WHERE session_id=$1 AND territory_id=$2 AND faction_name='Setia Empire (Kingdom)'""",
            SID, tid) or 0)
        appr = float(await Database.fetchval(
            """SELECT COALESCE(AVG(approval),0) FROM maya_rp.population_sentiment
               WHERE session_id=$1 AND territory_id=$2 AND faction_name='Setia Empire (Kingdom)'""",
            SID, tid) or 55)
        # Species diversity on this territory's populated planets
        div = await Database.fetchval(
            """SELECT COUNT(DISTINCT pp.species_name) FROM maya_rp.planet_population pp
               JOIN maya_rp.planets p ON p.id = pp.planet_id
               WHERE pp.session_id=$1 AND p.territory_id=$2""", SID, tid) or 1
        # Tax income for this territory
        tax = float(await Database.fetchval(
            """SELECT COALESCE(SUM(amount_per_day),0) FROM maya_rp.resource_production
               WHERE source ILIKE $1 AND resource_type='credits'""",
            f"{t['system_name']} — Tax Revenue%") or 0)
        # Competence: base 50 + dev*2 + approval pull + tax scale
        comp = 50 + (t["development_level"] or 1) * 2 + (appr - 55) * 0.4 + min(10, tax / 500000)
        comp = max(10, min(100, round(comp, 1)))

        king_prompt = tid == 170
        await Database.execute(
            """UPDATE maya_rp.territory
               SET title_performance=$2, requires_king_prompt=$3
               WHERE id=$1""",
            tid, comp, king_prompt)
        print(f"GOV {t['system_name']:<18} {t['governor_name'] or '?':<34} "
              f"comp {comp:>5.1f} · sent {sent:>4.0f} · appr {appr:>3.0f} · "
              f"species {div} · tax {tax:>10,.0f}/d · {'👑 PROMPT KING' if king_prompt else 'autonomous'}")
        updated += 1

    print(f"SETIA GOVERNOR MODEL — {updated} governors updated (Mastika requires King prompt)")
    await Database.close()


if __name__ == "__main__":
    asyncio.run(main())