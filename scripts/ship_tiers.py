#!/usr/bin/env python3
"""Ship energy (tiers) for the TKG fleet — enforce the world's ladder.

The ladder (King, 2026-10-02): most hulls sit at **tier 1 and 2**. Large factions
reach **tier 4 at most**. **Tier 5 is the pinnacle**, a handful in the whole galaxy.
**Tier 10 and beyond are not bought, only dreamed**: relics with no yard, no parts,
no replacement.

    python3 scripts/ship_tiers.py --dry-run      # show the target distribution
    python3 scripts/ship_tiers.py                # write (takes a backup first)

Assignment is deterministic per hull: within a faction, hulls are ranked by
`security_tier` then `id`, and that rank decides the tier. Same fleet in, same tiers
out. Major factions spend one hull at tier 5, their flagship.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
from datetime import datetime

# faction scale_class "major" gets the pinnacle allowance; everyone else tops out at 4
MAJOR_NAMES = ("Iron Concord", "Vein Collective", "The Silent Choir", "Free Ports Alliance",
               "The Mechnoic", "The Cyber Collective")
MYTHIC_FLOOR = 10          # tiers 10+ stay untouched: they are the dream
RANK_BANDS = (             # share of a faction's hulls, from the top
    (0.02, 4),             # the tip: line ships of a real navy
    (0.15, 3),             # the working navy
    (0.50, 2),             # the backbone: most hulls
    (1.01, 1),             # everything else: hulls that fly because they float
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
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
    cur.execute("""SELECT f.name, count(*) FROM maya_rp.ships s
                   LEFT JOIN maya_rp.factions f ON f.id = s.faction_id
                   WHERE s.tier < %s GROUP BY 1 ORDER BY 2 DESC""", (MYTHIC_FLOOR,))
    fleets = cur.fetchall()

    plan: list[tuple[int, int]] = []
    before: dict[int, int] = {}
    for faction_name, _ in fleets:
        cur.execute("""SELECT id, tier FROM maya_rp.ships
                       WHERE tier < %s AND faction_id IS NOT DISTINCT FROM
                             (SELECT id FROM maya_rp.factions WHERE name = %%s)
                       ORDER BY security_tier DESC NULLS LAST, id""" % MYTHIC_FLOOR, (faction_name,))
        hulls = cur.fetchall()
        total = len(hulls)
        if not total:
            continue
        major = faction_name in MAJOR_NAMES
        for index, (ship_id, old_tier) in enumerate(hulls):
            before[old_tier] = before.get(old_tier, 0) + 1
            share = (index + 1) / total
            if major and index == 0:
                new_tier = 5
            else:
                new_tier = next(tier for edge, tier in RANK_BANDS if share <= edge)
            plan.append((new_tier, ship_id))

    after: dict[int, int] = {}
    for tier, _ in plan:
        after[tier] = after.get(tier, 0) + 1
    print(f"hulls in scope {len(plan)} · mythic (tier {MYTHIC_FLOOR}+) untouched")
    print("before:", "  ".join(f"t{k}:{v}" for k, v in sorted(before.items())))
    print("after: ", "  ".join(f"t{k}:{v}" for k, v in sorted(after.items())))

    if args.dry_run:
        print("dry run: nothing written")
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = pathlib.Path.home() / "backups" / f"ship-tiers-{stamp}.json"
    backup.parent.mkdir(parents=True, exist_ok=True)
    cur.execute("SELECT id, tier FROM maya_rp.ships WHERE tier < %s", (MYTHIC_FLOOR,))
    backup.write_text(json.dumps(dict(cur.fetchall())))
    print(f"backup: {backup}")

    cur.execute("CREATE TEMP TABLE tier_plan (tier int, id bigint) ON COMMIT DROP")
    cur.executemany("INSERT INTO tier_plan (tier, id) VALUES (%s, %s)", plan)
    cur.execute("""UPDATE maya_rp.ships s SET tier = p.tier FROM tier_plan p WHERE s.id = p.id""")
    print("updated:", cur.rowcount)
    conn.commit()
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
