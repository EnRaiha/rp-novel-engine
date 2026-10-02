#!/usr/bin/env python3
"""Distribute the hulls — ownership, tier, class, and the tier 5 prototypes.

King's order (2026-10-02):

1. Every hull goes to a faction. Tier 1 to 4 is dealt at random, class and type too.
2. Tier 5 exists only as a **development programme**: large factions whose doctrine is
   science_tech or balance are building it. Small factions may hold the theory and
   cannot prove it.

Deterministic randomness: one seed, recorded, so the same deal can be reproduced or
re-rolled on purpose.

    python3 scripts/ship_fleet.py --dry-run
    python3 scripts/ship_fleet.py
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import random
from datetime import datetime

SEED = 20261002
# share of hulls, tier 1 to 4
TIER_WEIGHTS = ((1, 45), (2, 35), (3, 15), (4, 5))
# how much of the fleet each kind of faction carries
FACTION_WEIGHT = {
    "Iron Concord": 9, "Vein Collective": 8, "The Silent Choir": 7, "Free Ports Alliance": 6,
    "The Mechnoic": 6, "The Cyber Collective": 6, "TKG": 7, "The Limbah Compact": 5,
    "The Bug Swarm": 4, "Lembaga Pemeriksa": 2,
}
DEFAULT_WEIGHT = 2            # species courts, small powers, everyone unlisted
PIRATE_WEIGHT = 1             # pirates run lean
NOT_ESTABLISHED = {"Setia Empire (Kingdom)"}
# only these may build tier 5: large, and science_tech or balance
TIER5_ELIGIBLE = ("Iron Concord", "Vein Collective", "TKG", "The Cyber Collective")
TIER5_HULLS = 6               # total prototypes in the whole galaxy


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()

    import psycopg2

    env = pathlib.Path.home() / ".env"
    if env.is_file() and not os.environ.get("OC_PG_HOST"):
        for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, _, value = line.partition("=")
                key = key.removeprefix("export ").strip()
                if key.startswith(("OC_PG_", "POSTGRES_")) and key not in os.environ:
                    os.environ[key] = value.strip().strip("'\"")

    conn = psycopg2.connect(
        host=os.environ["OC_PG_HOST"], port=int(os.environ.get("OC_PG_PORT", 5432)),
        user=os.environ["OC_PG_USER"], password=os.environ.get("OC_PG_PASS"),
        dbname=os.environ.get("OC_PG_DB", "maya_memory"))
    cur = conn.cursor()
    cur.execute("SELECT id, name, is_pirate, doctrine, scale_class, economic_strength FROM maya_rp.factions")
    factions = []
    for fid, name, is_pirate, doctrine, scale_class, strength in cur.fetchall():
        if name in NOT_ESTABLISHED:
            continue
        if name in FACTION_WEIGHT:
            weight = FACTION_WEIGHT[name]
        elif is_pirate:
            weight = PIRATE_WEIGHT
        else:
            weight = DEFAULT_WEIGHT
        factions.append({"id": fid, "name": name, "weight": weight, "doctrine": doctrine})
    if not factions:
        print("no factions to distribute to"); return 1

    cur.execute("SELECT id, tier FROM maya_rp.ships ORDER BY id")
    hulls = cur.fetchall()
    cur.execute("SELECT id FROM maya_rp.ship_classes ORDER BY base_mass")
    classes = [row[0] for row in cur.fetchall()]
    if not classes:
        print("no ship classes"); return 1

    rng = random.Random(args.seed)
    ids = [f["id"] for f in factions]
    weights = [f["weight"] for f in factions]
    # class by size: the cheap hulls are common, the heavy ones are rare
    class_weights = [max(1, len(classes) - index) for index in range(len(classes))]
    tier_values = [t for t, _ in TIER_WEIGHTS]
    tier_weights = [w for _, w in TIER_WEIGHTS]
    eligible = [f["id"] for f in factions if f["name"] in TIER5_ELIGIBLE]

    plan = []
    for index, (ship_id, _) in enumerate(hulls):
        owner = rng.choices(ids, weights=weights, k=1)[0]
        if index < TIER5_HULLS and eligible:
            tier = 5
            owner = eligible[index % len(eligible)]
        else:
            tier = rng.choices(tier_values, weights=tier_weights, k=1)[0]
        plan.append((owner, tier, rng.choices(classes, weights=class_weights, k=1)[0], ship_id))

    counts: dict[int, int] = {}
    tiers: dict[int, int] = {}
    for owner, tier, _, _ in plan:
        counts[owner] = counts.get(owner, 0) + 1
        tiers[tier] = tiers.get(tier, 0) + 1
    names = {f["id"]: f["name"] for f in factions}
    print(f"hulls {len(plan)} · factions {len(factions)} · seed {args.seed}")
    print("tiers:", "  ".join(f"t{k}:{v}" for k, v in sorted(tiers.items())))
    for fid, n in sorted(counts.items(), key=lambda kv: -kv[1])[:8]:
        print(f"  {names[fid][:28]:<28} {n:>6}")

    if args.dry_run:
        print("dry run: nothing written")
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = pathlib.Path.home() / "backups" / f"ship-fleet-{stamp}.json"
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_text(json.dumps({str(sid): [old_tier] for sid, old_tier in hulls}))
    print(f"backup (id -> old tier): {backup}")

    cur.execute("CREATE TEMP TABLE fleet_plan (faction_id int, tier int, class_id int, id bigint) ON COMMIT DROP")
    cur.executemany("INSERT INTO fleet_plan (faction_id, tier, class_id, id) VALUES (%s,%s,%s,%s)", plan)
    cur.execute("""UPDATE maya_rp.ships s SET faction_id = p.faction_id, tier = p.tier, class_id = p.class_id
                   FROM fleet_plan p WHERE s.id = p.id""")
    print("updated:", cur.rowcount)
    conn.commit()
    cur.execute("""SELECT f.name, count(*), sum(CASE WHEN s.tier=5 THEN 1 ELSE 0 END)
                   FROM maya_rp.ships s JOIN maya_rp.factions f ON f.id=s.faction_id
                   GROUP BY 1 ORDER BY 2 DESC LIMIT 6""")
    print("after:", cur.fetchall())
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
