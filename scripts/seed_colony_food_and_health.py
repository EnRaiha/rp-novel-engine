#!/usr/bin/env python3
"""seed_colony_food_and_health — give the settlements what their sources support.

`food_priority` IS LEFT EMPTY ON PURPOSE, and it is the field landmark 5 needs. Two sources were
read for an order and neither has one.

  `wiki/rp-dev/FOOD-LADDER-2026-10-02.md` says who eats each tier: tier 1 is "semua orang, setiap
  hari, ini baseline", tier 2 is "kapal, koloni, pelombong", tier 3 is "pegawai, upacara, hadiah".
  That is a class, not a settlement. It does not say Garden eats before Bukit Kaca.

  Turn 73 gives populations and roles for the three settlements and no rationing order.

  `The Hungry Months` is "the dock learns which mouth it feeds last", so the order is the landmark's
  subject. Writing one now would be the engine deciding a story question before the story does.

FOOD IS SET, because the ladder does answer that. Tier 1 is the baseline for everyone, so all three
settlements eat Nutrient Pack. It is stored as a `maya_rp.commodities.name` rather than a tier number,
so the settlement's food is the commodity's own supply and demand and cannot drift from them.

HEALTH IS SET FOR ONE SETTLEMENT, from turn 73: "Kabus relau menutupi penara pada waktu pagi; dua kes
penyakit paru-paru dilaporkan (dalam siasatan Sumayyah)" and "Sumayyah meminta penapis atau relau
dipindahkan". Two active cases, under investigation, with a request attached. That is `watch` rather
than `outbreak`: reported and being worked, not spreading.

Dry run by default. `--apply` writes.

    python3 scripts/seed_colony_food_and_health.py --session 5
    python3 scripts/seed_colony_food_and_health.py --session 5 --apply
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.db import Database  # noqa: E402
from core.log import info, warn  # noqa: E402

LADDER = "FOOD-LADDER-2026-10-02.md, tier 1: 'semua orang, setiap hari. Ini baseline, bukan makanan'"
TURN73_HEALTH = ("Turn 73, LAPORAN POPULASI — HEAVEN REACH: 'Kabus relau menutupi penara pada waktu "
                 "pagi; dua kes penyakit paru-paru dilaporkan (dalam siasatan Sumayyah)'")

# colony, food_commodity, health_status, health_notes, source
PLAN: tuple[tuple[str, str | None, str | None, str | None, str], ...] = (
    ("Garden", "Nutrient Pack", None, None, LADDER),
    ("Bukit Kaca", "Nutrient Pack", "watch",
     "Furnace fog over the plateau each morning. Two lung cases reported, under Sumayyah's "
     "investigation. She has asked for filters, or for the furnace to be moved.",
     f"{LADDER}. Health: {TURN73_HEALTH}"),
    ("Pesisir Panjang", "Nutrient Pack", None, None, LADDER),
)


async def seed(session: int, *, write: bool) -> dict:
    result = {"set": [], "kept": [], "no_colony": [], "no_commodity": []}
    for name, food, health, notes, source in PLAN:
        row = await Database.fetchrow(
            "SELECT id, food_commodity, health_status FROM maya_rp.colonies"
            " WHERE session_id=$1 AND name=$2", session, name)
        if not row:
            result["no_colony"].append(name)
            warn("colonies", f"{name}: not in session {session}; skipped")
            continue
        if food:
            known = await Database.fetchval(
                "SELECT 1 FROM maya_rp.commodities WHERE session_id=$1 AND name=$2", session, food)
            if not known:
                result["no_commodity"].append(f"{name}/{food}")
                warn("colonies", f"{name}: {food!r} is not a commodity in session {session}; "
                                 "food left as it was")
                food = None
        if row["food_commodity"] == food and row["health_status"] == health:
            result["kept"].append(name)
            info("colonies", f"{name}: already set ({food}, health {health}); left alone")
            continue
        if not write:
            result["set"].append(name)
            info("colonies", f"{name}: would set food={food}, health={health}   [{source[:66]}...]")
            continue
        await Database.execute(
            "UPDATE maya_rp.colonies SET food_commodity=COALESCE($2, food_commodity),"
            " health_status=$3, health_notes=COALESCE($4, health_notes)"
            " WHERE id=$1",
            row["id"], food, health, notes)
        back = await Database.fetchrow(
            "SELECT food_commodity, health_status, health_notes FROM maya_rp.colonies WHERE id=$1",
            row["id"])
        if back["food_commodity"] != food or back["health_status"] != health:
            warn("colonies", f"{name}: write did not take; read back {dict(back)}")
            continue
        result["set"].append(name)
        info("colonies", f"{name}: food={back['food_commodity']}, health={back['health_status']}")
    return result


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Set colony food tier and health from the sources that support them.")
    parser.add_argument("--session", type=int, default=5)
    parser.add_argument("--apply", action="store_true", help="write; the default is a dry run")
    args = parser.parse_args()

    await Database.init()
    try:
        result = await seed(args.session, write=args.apply)
    finally:
        await Database.close()

    verb = "set" if args.apply else "would set"
    print(f"{verb} {len(result['set'])} of {len(PLAN)} settlement(s) in session {args.session}")
    if result["kept"]:
        print(f"left alone (already set): {', '.join(result['kept'])}")
    if result["no_colony"]:
        print(f"SKIPPED (not in this session): {', '.join(result['no_colony'])}")
    if result["no_commodity"]:
        print(f"SKIPPED (no such commodity): {', '.join(result['no_commodity'])}")
    print("food_priority is left NULL: no source orders the settlements, and that order is what "
          "landmark 5 is about")
    if not args.apply:
        print("dry run: nothing written")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
