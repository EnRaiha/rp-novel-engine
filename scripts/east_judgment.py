#!/usr/bin/env python3
"""east_judgment.py — Register East pirate captures + King's judgment (Day 1480, Izzat).

1,142 prisoners from the eastern cleanup. Judgment:
  - BLOOD ON HANDS (combat/command ranks) → EXECUTED
  - The rest (crew, cooks, conscripts) → debt-bound Pool (labor rehabilitation)
Archives (Echo Nest Wraiths' relic records) → Celestial Archive.

A session that already holds `eastern_cleanup` prisoners is refused.

  python3 scripts/east_judgment.py --session N            # report only
  python3 scripts/east_judgment.py --session N --apply    # insert in one transaction
"""
from __future__ import annotations
import os
import asyncio, random, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.db import Database
from scripts._oneshot import parse, guard

PACKS = {
    "Raiding Den Reavers": 31, "Smuggler Cove Corsairs": 22, "Wreck Haven Scavengers": 19,
    "Black Market Syndicate": 42, "Cutthroat Anchorage Cuts": 28, "Renegade Post Outlaws": 17,
    "Rust Belt Camp Marauders": 15, "Lane Cutter Raiders": 0, "Salvage Den Scrappers": 0,
    "Echo Nest Wraiths": 36,
}
# Add the unlisted captures (156 ships total; 42+31+28+22+19+17+15+36 = 210 ships)
# Recompute: total ships 156. Ship-count per pack above sums to 210 — rescale to crew counts instead.
# Actual: 1,142 prisoners total. Blood ratio by faction ruthlessness:
BLOOD_RATIO = {
    "Raiding Den Reavers": 0.55, "Smuggler Cove Corsairs": 0.35, "Wreck Haven Scavengers": 0.30,
    "Black Market Syndicate": 0.45, "Cutthroat Anchorage Cuts": 0.60, "Renegade Post Outlaws": 0.40,
    "Rust Belt Camp Marauders": 0.55, "Lane Cutter Raiders": 0.50, "Salvage Den Scrappers": 0.35,
    "Echo Nest Wraiths": 0.20,   # relic-hunters — fewer killers, more scholars
}

RANKS = ["Captain", "Commodore", "Boarding Officer", "Enforcer", "Raider", "Gunner",
         "Navigator", "Engineer", "Cook", "Crew", "Deckhand", "Conscript"]


async def main(argv=None) -> int:
    args = parse(__doc__, argv)
    guard(args)
    sid = args.session
    await Database.init()
    already = await Database.fetchval(
        "SELECT count(*) FROM maya_rp.prisoners WHERE session_id=$1 AND captured_from_ship='eastern_cleanup'", sid)
    if already:
        print(f"REFUSED: session {sid} already holds {already} eastern_cleanup prisoners")
        await Database.close()
        return 1
    # Distribute 1,142 prisoners across packs (weighted by fleet size seen)
    weights = {"Raiding Den Reavers": 31, "Smuggler Cove Corsairs": 22, "Wreck Haven Scavengers": 19,
               "Black Market Syndicate": 28, "Cutthroat Anchorage Cuts": 28, "Renegade Post Outlaws": 17,
               "Rust Belt Camp Marauders": 15, "Lane Cutter Raiders": 14, "Salvage Den Scrappers": 13,
               "Echo Nest Wraiths": 36}
    total_w = sum(weights.values())
    rng = random.Random(1480)
    executed = 0
    pooled = 0
    rows: list[tuple] = []

    for pack, w in weights.items():
        count = max(1, round(1142 * w / total_w))
        blood_ratio = BLOOD_RATIO[pack]
        for i in range(count):
            name = f"{pack.split()[0]}-{i+1:03d}"
            # Blood on hands: combat ranks + leadership
            roll = rng.random()
            blood = roll < blood_ratio
            if blood:
                rank = rng.choice(["Captain", "Commodore", "Boarding Officer", "Enforcer", "Raider", "Gunner"])
            else:
                rank = rng.choice(["Navigator", "Engineer", "Cook", "Crew", "Deckhand", "Conscript"])
            rows.append((sid, name, pack, rank, '["—"]', rng.randint(1, 20), rng.randint(20, 95),
                         "executed" if blood else "transferred",
                         "execution" if blood else "labor_rehabilitation",
                         0 if blood else rng.randint(5, 30)))
            if blood:
                executed += 1
            else:
                pooled += 1

    print(f"EAST JUDGMENT — {executed} executed (blood on hands) · {pooled} to debt-bound Pool")
    if not args.apply:
        print(f"DRY RUN — would insert {len(rows)} prisoners. Re-run with --apply to write.")
        await Database.close()
        return 0

    async with Database.transaction() as conn:
        for row in rows:
            await conn.execute(
                """INSERT INTO maya_rp.prisoners
                   (session_id, name, faction, rank, personality_traits, intel_value, resistance,
                    status, cell_security, interrogations_count, secrets_jsonb, captured_at,
                    captured_from_ship, conversion_path, conversion_progress, held_sessions)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'standard',0,'{}',NOW(),'eastern_cleanup',$9,$10,0)""",
                *row)
    print(f"APPLIED — inserted {len(rows)} prisoners")
    await Database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))