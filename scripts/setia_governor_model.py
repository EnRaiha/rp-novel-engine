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

Every read is scoped to `--session`, and the write names the session too. The script reports by
default and writes only with `--apply`.

  python3 scripts/setia_governor_model.py --session N            # report only
  python3 scripts/setia_governor_model.py --session N --apply    # write the governor rows
"""
from __future__ import annotations
import os
import asyncio, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.db import Database
from scripts._oneshot import parse, guard


async def main(argv=None) -> int:
    args = parse(__doc__, argv)
    guard(args)
    sid = args.session
    await Database.init()
    terr = await Database.fetch(
        """SELECT id, system_name, governor_name, tax_rate, development_level,
                  title_performance, population
           FROM maya_rp.territory
           WHERE session_id=$1 AND controlling_faction='Setia Empire'""", sid)

    updated = 0
    for t in terr:
        tid = t["id"]
        # Sentiment of population toward Setia at this territory
        sent = float(await Database.fetchval(
            """SELECT COALESCE(AVG(sentiment),0) FROM maya_rp.population_sentiment
               WHERE session_id=$1 AND territory_id=$2 AND faction_name='Setia Empire (Kingdom)'""",
            sid, tid) or 0)
        appr = float(await Database.fetchval(
            """SELECT COALESCE(AVG(approval),0) FROM maya_rp.population_sentiment
               WHERE session_id=$1 AND territory_id=$2 AND faction_name='Setia Empire (Kingdom)'""",
            sid, tid) or 55)
        # Species diversity on this territory's populated planets
        div = await Database.fetchval(
            """SELECT COUNT(DISTINCT pp.species_name) FROM maya_rp.planet_population pp
               JOIN maya_rp.planets p ON p.id = pp.planet_id
               WHERE pp.session_id=$1 AND p.session_id=$1 AND p.territory_id=$2""", sid, tid) or 1
        # Tax income for this territory. `resource_production` carries `session_id`: another
        # campaign's row can hold the same source text.
        tax = float(await Database.fetchval(
            """SELECT COALESCE(SUM(amount_per_day),0) FROM maya_rp.resource_production
               WHERE session_id=$1 AND source ILIKE $2 AND resource_type='credits'""",
            sid, f"{t['system_name']} — Tax Revenue%") or 0)
        # Competence: base 50 + dev*2 + approval pull + tax scale
        comp = 50 + (t["development_level"] or 1) * 2 + (appr - 55) * 0.4 + min(10, tax / 500000)
        comp = max(10, min(100, round(comp, 1)))

        king_prompt = tid == 170
        gov = (f"GOV {t['system_name']:<18} {t['governor_name'] or '?':<34} "
               f"comp {comp:>5.1f} · sent {sent:>4.0f} · appr {appr:>3.0f} · "
               f"species {div} · tax {tax:>10,.0f}/d · "
               f"{'👑 PROMPT KING' if king_prompt else 'autonomous'}")
        if not args.apply:
            print(f"{gov} · dry run")
            continue
        await Database.execute(
            """UPDATE maya_rp.territory
               SET title_performance=$3, requires_king_prompt=$4
               WHERE id=$1 AND session_id=$2""",
            tid, sid, comp, king_prompt)
        print(gov)
        updated += 1

    if args.apply:
        print(f"SETIA GOVERNOR MODEL — {updated} governors updated (Mastika requires King prompt)")
    else:
        print(f"DRY RUN: session {sid} holds {len(terr)} Setia governors; nothing written. "
              "Re-run with --apply to write.")
    await Database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
