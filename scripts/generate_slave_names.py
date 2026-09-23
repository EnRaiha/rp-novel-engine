#!/usr/bin/env python3
"""generate_slave_names — fill a consignment lot's roster with names.

The OOC RP introduced a market lot (890 souls at a free dock, sold by a broker).
The engine's own `NameGenerator` supplies culturally-consistent names, and anyone
already on the roster is skipped, so re-running only fills the shortfall.

Rows land in `maya_rp.slaves` (the table the engine's slave module and the
`slave_overview` view read), tagged with the lot so the narrator can pull the
roll by name:

    SELECT name, species, gender, age, role, cost FROM maya_rp.slaves
     WHERE session_id=3 AND assigned_to = 'Marlon Bregg — lot 890'
     ORDER BY id;

    python3 scripts/generate_slave_names.py --count 890 --dry-run
    python3 scripts/generate_slave_names.py --count 890
"""
from __future__ import annotations

import argparse
import asyncio
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.db import Database  # noqa: E402
from core import name_gen  # noqa: E402

# Market stock, not household staff: low loyalty, ordinary bodies, priced by tier.
SPECIES = (("human", 68), ("alien", 32))
ROLES = ("labor", "domestic", "technical", "galley", "dock crew", "seamstress",
         "tutor", "medic's hand", "fields", "cargo")
TIERS = (("common", 4000, 13000), ("skilled", 9000, 24000), ("rare", 20000, 65000))
CULTURES = ("mixed", "malay", "chinese", "indian", "east", "western")


def weighted(pairs):
    names, weights = zip(*pairs)
    return random.choices(names, weights=weights, k=1)[0]


def stock_row(index: int) -> dict:
    tier, low, high = weighted([(t, 1) for t in TIERS])
    species = weighted(SPECIES)
    return {
        "species": species,
        "gender": random.choice(("F", "M")),
        "age": random.randint(16, 45),
        "strength": random.randint(3, 60),
        "intelligence": random.randint(5, 60),
        "loyalty": random.randint(5, 35),
        "health": random.randint(50, 95),
        "role": random.choice(ROLES),
        "cost": random.randint(low, high),
        "tier": tier,
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description="Name the individuals of a consignment lot")
    parser.add_argument("--session", type=int, default=3)
    parser.add_argument("--count", type=int, default=890, help="lot size (individuals)")
    parser.add_argument("--lot", default="890", help="lot number")
    parser.add_argument("--broker", default="Marlon Bregg")
    parser.add_argument("--dock", default="free dock 7")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    tag = f"{args.broker} — lot {args.lot}"
    await Database.init()

    taken = {row["name"].strip().lower() for row in await Database.fetch(
        "SELECT name FROM maya_rp.slaves WHERE session_id=$1 AND name IS NOT NULL", args.session)}
    taken |= {row["slave_name"].strip().lower() for row in await Database.fetch(
        "SELECT DISTINCT slave_name FROM maya_rp.slave_market WHERE session_id=$1", args.session)}
    existing = await Database.fetchval(
        "SELECT count(*) FROM maya_rp.slaves WHERE session_id=$1 AND assigned_to=$2", args.session, tag)
    shortfall = max(0, args.count - int(existing or 0))
    print(f"lot '{tag}': {existing or 0} on the roll, {len(taken)} names already in the world, "
          f"{shortfall} to generate")
    if shortfall == 0:
        print("nothing to do — every individual already has a name")
        await Database.close()
        return 0

    generator = name_gen.NameGenerator(conn=Database)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows: list[tuple] = []
    for _ in range(shortfall):
        name = ""
        for _attempt in range(12):
            candidate = await generator.unique_name(culture=random.choice(CULTURES))
            if candidate.strip().lower() not in taken:
                name = candidate
                taken.add(candidate.strip().lower())
                break
        if not name:
            continue
        stock = stock_row(len(rows))
        rows.append((args.session, name, stock["species"], stock["gender"], stock["age"],
                     stock["strength"], stock["intelligence"], stock["loyalty"], stock["health"],
                     tag, stock["role"], now, f"{args.dock} — consignment", stock["cost"],
                     "for_sale", now))

    if args.dry_run:
        for row in rows[:5]:
            print("  ", row[1], "|", row[2], row[3], row[4], "|", row[10], "|", row[13])
        print(f"DRY — would insert {len(rows)} rows into maya_rp.slaves")
        await Database.close()
        return 0

    inserted = 0
    for start in range(0, len(rows), 100):
        chunk = rows[start:start + 100]
        values = []
        params: list = []
        for offset, row in enumerate(chunk):
            base = offset * 16
            values.append("(" + ",".join(f"${base + i + 1}" for i in range(16)) + ")")
            params.extend(row)
        await Database.execute(
            "INSERT INTO maya_rp.slaves (session_id, name, species, gender, age, strength,"
            " intelligence, loyalty, health, assigned_to, role, acquired_at, acquired_from,"
            " cost, status, last_activity) VALUES " + ", ".join(values), *params)
        inserted += len(chunk)
    total = await Database.fetchval(
        "SELECT count(*) FROM maya_rp.slaves WHERE session_id=$1 AND assigned_to=$2", args.session, tag)
    print(f"inserted {inserted} named individuals; lot now {total}")
    await Database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
