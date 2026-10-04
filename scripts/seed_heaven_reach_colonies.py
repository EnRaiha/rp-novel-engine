#!/usr/bin/env python3
"""seed_heaven_reach_colonies — give the live arc the settlements it has been standing on.

`maya_rp.colonies` holds four rows, all for session 3. Session 5 holds none, and six modules
read the table. Two of them answer with a hard error when a colony is missing:

    modules/defense.py:16    if not col: return {"error": f"Colony '{colony}' not found"}
    modules/tech_tree.py:28  the same

so `defense.build(colony="Garden")` on the live arc returns a not-found error, and nothing in
the engine could ever have fixed that: there is no `create_colony`, no `found_colony`, and no
migration that inserts one.

THE SOURCE IS TURN 73 of the tkg-play record, `LAPORAN POPULASI — HEAVEN REACH`, compiled by
Zulaikha Nadira and confirmed by Hasnah Rahim on day 64. It gives three surface settlements with
their populations and their roles, and the orbit separately.

WHAT THIS WRITES, AND WHAT IT REFUSES TO:

  name, population, status     sourced, so they are set.
  planet_type                  the report says "di permukaan", not what the surface is. NULL.
  development                  not in the report at any scale the column could hold. NULL.
  alloy_output · fuel_output   Bukit Kaca smelts nine tonnes of iron a day. The column is
  credit_output                `alloy_output`, integer, and a tonne of iron is neither an
                               alloy nor an integer of that unit. Writing 9 would be a number
                               this file invented, so these stay NULL rather than 0. The column
                               defaults to 0 and NULL is not the same claim: 0 says the colony
                               produces nothing, NULL says nobody has said.

Dry run by default. `--apply` writes. A settlement that already exists is left alone and
reported, because this seeds a state that the story owns and a re-run must not overwrite what
the campaign has since changed.

    python3 scripts/seed_heaven_reach_colonies.py --session 5
    python3 scripts/seed_heaven_reach_colonies.py --session 5 --apply
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.db import Database  # noqa: E402
from core.log import info, warn  # noqa: E402

SOURCE = "Turn 73, LAPORAN POPULASI — HEAVEN REACH (day 64), compiled by Zulaikha Nadira"

# name, population, status, the sentence the population came from
SETTLEMENTS: tuple[tuple[str, int, str, str], ...] = (
    ("Garden", 8400, "active",
     "GARDEN — bandar pusat: administration, main clinic, school, river dock, archive, a 60 m "
     "town hall with the captain's office at one end, 240 finished houses and 5,520 still in the "
     "11 km cave."),
    ("Bukit Kaca", 3300, "active",
     "BUKIT KACA — pusat besi: two furnaces at nine tonnes of iron a day, a 300 kg drop hammer, "
     "an 8 mm plate roller, 62 stone houses. Furnace fog covers the plateau in the morning."),
    ("Pesisir Panjang", 3100, "active",
     "PESISIR PANJANG — pertanian dan laut: 640 hectares opened and 210 planted, 400 head of "
     "livestock, 14 boats at 2.1 tonnes a day, three salt pans at 400 kg a week, long twin "
     "houses on stilts."),
)


async def seed(session: int, *, write: bool) -> dict:
    ensured = {"created": [], "kept": [], "refused": []}
    for name, population, status, source in SETTLEMENTS:
        existing = await Database.fetchrow(
            "SELECT id, population, status FROM maya_rp.colonies WHERE session_id=$1 AND name=$2",
            session, name)
        if existing:
            ensured["kept"].append(name)
            info("colonies", f"{name}: already present as #{existing['id']} "
                             f"(population {existing['population']}, {existing['status']}); left alone")
            continue
        if not write:
            ensured["created"].append(name)
            info("colonies", f"{name}: would create, population {population:,}   [{source[:70]}...]")
            continue
        new_id = await Database.fetchval(
            "INSERT INTO maya_rp.colonies"
            " (session_id, name, planet_type, population, development,"
            "  alloy_output, fuel_output, credit_output, status)"
            " VALUES ($1, $2, NULL, $3, NULL, NULL, NULL, NULL, $4) RETURNING id",
            session, name, population, status)
        read_back = await Database.fetchrow(
            "SELECT name, population, status FROM maya_rp.colonies WHERE id=$1", new_id)
        if not read_back or read_back["population"] != population:
            ensured["refused"].append(name)
            warn("colonies", f"{name}: write did not take; read back {dict(read_back) if read_back else None}")
            continue
        ensured["created"].append(name)
        info("colonies", f"{name}: created #{new_id}, population {population:,} ({SOURCE[:46]}...)")
    return ensured


async def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Heaven Reach's settlements into maya_rp.colonies.")
    parser.add_argument("--session", type=int, default=5)
    parser.add_argument("--apply", action="store_true", help="write; the default is a dry run")
    args = parser.parse_args()

    await Database.init()
    try:
        result = await seed(args.session, write=args.apply)
    finally:
        await Database.close()

    verb = "created" if args.apply else "would create"
    print(f"{verb} {len(result['created'])} of {len(SETTLEMENTS)} settlement(s) in session {args.session}")
    if result["kept"]:
        print(f"left alone (already present): {', '.join(result['kept'])}")
    if result["refused"]:
        print(f"REFUSED (write did not take): {', '.join(result['refused'])}")
    if not args.apply:
        print("dry run: nothing written")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
