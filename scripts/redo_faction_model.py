#!/usr/bin/env python3
"""redo_faction_model.py — Rebuild ALL non-Setia faction models from live parameters (Day 1384).

Every faction NOT controlled by the user (Setia Empire, id 1) gets its model recomputed
from the new layers:
  - Governed territories → daily tax income → treasury
  - Species population (faction→species mapping) → economic strength
  - Population sentiment → reputation + personality tone
  - Pirates: fleet power from territories + fear generated
  - Neutrals: diplomatic power from territory count + sentiment

Deterministic, rerun-safe. Setia Empire (user) untouched.

The script reads one campaign and writes one campaign: every statement names `--session`, including
the two faction UPDATEs. It reports by default and writes only with `--apply`.

  python3 scripts/redo_faction_model.py --session N            # report only
  python3 scripts/redo_faction_model.py --session N --apply    # write the faction rows
"""
from __future__ import annotations
import os
import asyncio, json, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.db import Database
from scripts._oneshot import parse, guard

# Faction → dominant species (from canon mapping)
FACTION_SPECIES = {
    "Vein Collective": ["human"], "Iron Concord": ["human"], "The Silent Choir": ["ghost"],
    "Ghost Signal": ["ghost"], "Exodus Fleet": ["human"], "Lost Colonies": ["alien"],
    "The Rim Council": ["human"], "The Mechnoic": ["mechanical"], "The Succubi Court": ["succubus"],
    "The Demon Legions": ["demon"], "The Fairy Courts": ["fairy"], "The Spirit Weave": ["spirit"],
    "The Clone Legions": ["clone"], "The Cyber Collective": ["cyborg"], "The Swarm": ["zerg"],
    "The Dwarf Holdings": ["dwarf"], "The Seeder Gardens": ["seeder"], "The Ghost Chorus": ["ghost"],
    "The Half-Beast Clans": ["half_beast"], "The Hybrid Flotilla": ["hybrid"],
}

# Personality tone by standing
STANDING_TONE = {
    "hostile": "aggressive, opportunistic, expansionist",
    "suspicious": "wary, guarded, probing",
    "neutral": "pragmatic, trade-minded, self-interested",
    "friendly": "cooperative, allied, trade-partner",
    "unknown": "inscrutable, patient, observant",
    "allied": "loyal, allied, integrated",
    "kingdom": "—",
}


async def main(argv=None) -> int:
    args = parse(__doc__, argv)
    guard(args)
    sid = args.session
    await Database.init()
    factions = await Database.fetch(
        """SELECT id, name, is_pirate, standing, treasury, reputation, diplomatic_power,
                  economic_strength, trade_aggressiveness, pirate_fleet_power, pirate_aggressiveness, status
           FROM maya_rp.factions WHERE session_id=$1 AND id != 1 ORDER BY id""", sid)
    updated = 0

    for f in factions:
        name = f["name"]
        if f["status"] == "defeated":
            continue  # leave defeated factions alone

        # ── 1. Territory income → treasury ───────────────────────────
        # `resource_production` carries `session_id`: another campaign's row can hold the same
        # source text, so the sum names the campaign.
        tax = float(await Database.fetchval(
            """SELECT COALESCE(SUM(amount_per_day),0) FROM maya_rp.resource_production
               WHERE session_id=$1 AND source ILIKE $2 AND resource_type='credits'""",
            sid, f"{name} — Collective Tax%") or 0)
        terr_count = await Database.fetchval(
            """SELECT COUNT(*) FROM maya_rp.territory
               WHERE session_id=$1 AND controlling_faction=$2""", sid, name) or 0

        # ── 2. Species population → economic strength ────────────────
        species_list = FACTION_SPECIES.get(name, [])
        sp = 0.0
        if species_list:
            sp = float(await Database.fetchval(
                """SELECT COALESCE(SUM(count),0) FROM maya_rp.planet_population
                   WHERE session_id=$1 AND species_name = ANY($2::text[])""", sid, species_list) or 0)
        econ = max(0.5, round(sp / 2e9, 2)) if sp else max(0.5, round(terr_count * 0.05, 2))

        # ── 3. Sentiment → reputation ────────────────────────────────
        sent = float(await Database.fetchval(
            """SELECT COALESCE(AVG(sentiment),0) FROM maya_rp.population_sentiment
               WHERE session_id=$1 AND faction_name=$2""", sid, name) or 0)
        fear = float(await Database.fetchval(
            """SELECT COALESCE(AVG(fear),0) FROM maya_rp.population_sentiment
               WHERE session_id=$1 AND faction_name=$2""", sid, name) or 5)
        rep = max(-100, min(100, int(sent)))

        # ── 4. Treasury from tax (income × 30-day reserve) ───────────
        treasury = int(tax * 30) if tax > 0 else max(100000, f["treasury"] or 100000)

        # ── 5. Pirates: fleet + aggressiveness from territory/fear ───
        if f["is_pirate"]:
            fleet = f["pirate_fleet_power"] or 0
            if terr_count > 0:  # sponsored wolves
                fleet = max(fleet, 1200 + terr_count * 40)
                agg = min(1.0, 0.55 + terr_count * 0.02)
                funding = "anonymous benefactor — source unknown"
            else:  # free pirates
                fleet = max(fleet, 150 + int(fear * 8))
                agg = min(1.0, 0.7 + fear * 0.002)
                funding = "self-funded"
            goals = {"pirate": ["raid", "expand", "build", "appoint_queen"] if terr_count > 0
                     else ["raid", "expand", "loot"], "funding": funding,
                     "economy": f"{tax:,.0f} C/day tax" if tax > 0 else "no territory income"}
            personality = {"personality": STANDING_TONE.get(f["standing"], "opportunistic"),
                           "tier": 5 if terr_count > 0 else 3,
                           "governed_territories": terr_count, "fear_generated": round(fear, 1)}
            if args.apply:
                await Database.execute(
                    """UPDATE maya_rp.factions SET pirate_fleet_power=$2, pirate_aggressiveness=$3,
                       treasury=$4, reputation=$5, ai_personality=$6::jsonb, ai_goals=$7::jsonb
                       WHERE id=$1 AND session_id=$8""",
                    f["id"], fleet, agg, treasury, rep, json.dumps(personality), json.dumps(goals), sid)
            print(f"PIR {name}: terr {terr_count} · tax {tax:,.0f}/d · fleet {fleet} · agg {agg:.2f} · sent {sent:.0f}")

        # ── 6. Neutrals/AI: econ + diplomacy + personality ───────────
        else:
            dip = max(10, int(20 + terr_count * 1.5 + sent * 0.3))
            trade_agg = min(1.0, max(0.3, 0.4 + econ * 0.05)) if f["standing"] != "hostile" else 0.2
            goals = {
                "species": species_list, "species_pop": sp,
                "territories": terr_count, "economy": f"{tax:,.0f} C/day tax",
                "sentiment": round(sent, 1),
                "expansion": "absorb_unclaimed" if f["standing"] == "hostile" else "trade_and_grow",
            }
            personality = {"personality": STANDING_TONE.get(f["standing"], "pragmatic"),
                           "tier": 3, "species_backing": species_list,
                           "governed_territories": terr_count}
            if args.apply:
                await Database.execute(
                    """UPDATE maya_rp.factions SET economic_strength=$2, treasury=$3, reputation=$4,
                       diplomatic_power=$5, trade_aggressiveness=$6, ai_personality=$7::jsonb,
                       ai_goals=$8::jsonb WHERE id=$1 AND session_id=$9""",
                    f["id"], econ, treasury, rep, dip, trade_agg, json.dumps(personality),
                    json.dumps(goals), sid)
            print(f"NEU {name}: terr {terr_count} · tax {tax:,.0f}/d · species {sp:,.0f} · econ {econ} · sent {sent:.0f} · dip {dip}")

        updated += 1

    if args.apply:
        print(f"FACTION MODEL REDO — {updated} non-Setia factions rebuilt from live parameters")
    else:
        print(f"DRY RUN: session {sid} holds {updated} rebuildable non-Setia factions; nothing written. "
              "Re-run with --apply to write.")
    await Database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
