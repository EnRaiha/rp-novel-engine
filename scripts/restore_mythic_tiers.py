#!/usr/bin/env python3
"""Put the three mythic hulls back on their canonical tiers.

The fleet distribution of 2026-10-02 dealt a random tier 1 to 4 to every hull, because that is what
the King asked for. It also flattened the three relics whose tiers were 10 and 11, and one of them,
`Celestia — Starforged-03`, carries 2,000,000,000 of the fleet's 2,009,510,958 combat power. That is
99.53% of every battle, sitting on the cheapest tier label in the world.

The hulls are found from the distribution's own backup, not from a name list: `~/backups/ship-fleet-*.json`
records the tier each hull held before the deal, so the restore is evidence, not memory.

    python3 scripts/restore_mythic_tiers.py --dry-run
    python3 scripts/restore_mythic_tiers.py --apply

Dry by default. This writes to production, so the run also records its own backup.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import datetime

MYTHIC_FLOOR = 10


def previous_tiers() -> tuple[pathlib.Path, dict[int, int]]:
    """The pre-distribution tier of every hull, from the newest distribution backup.

    @returns (backup path, {ship id: tier}) for the hulls whose tier was at or above the floor.
    """
    candidates = sorted(pathlib.Path.home().glob("backups/ship-fleet-*.json"))
    if not candidates:
        raise SystemExit("no ship-fleet backup found; the restore has nothing to trust")
    newest = candidates[-1]
    payload = json.loads(newest.read_text())
    mythic: dict[int, int] = {}
    for ship_id, value in payload.items():
        old = value[0] if isinstance(value, list) and value else value
        if old is None:
            continue
        if int(old) >= MYTHIC_FLOOR:
            mythic[int(ship_id)] = int(old)
    return newest, mythic


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="write; absent means the run only reports")
    parser.add_argument("--dry-run", action="store_true", help="accepted for symmetry with the other scripts")
    args = parser.parse_args()

    import os
    import psycopg2

    env = pathlib.Path.home() / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, _, value = line.partition("=")
                key = key.removeprefix("export ").strip()
                if key.startswith(("OC_PG_", "POSTGRES_")) and key not in os.environ:
                    os.environ[key] = value.strip().strip("'\"")

    source, mythic = previous_tiers()
    print(f"evidence: {source.name} · hulls at tier {MYTHIC_FLOOR}+ before the deal: {len(mythic)}")
    if not mythic:
        print("nothing to restore")
        return 0

    conn = psycopg2.connect(host=os.environ["OC_PG_HOST"], port=int(os.environ.get("OC_PG_PORT", 5432)),
                            user=os.environ["OC_PG_USER"], password=os.environ.get("OC_PG_PASS"),
                            dbname=os.environ.get("OC_PG_DB", "maya_memory"))
    cur = conn.cursor()
    for ship_id, old_tier in sorted(mythic.items()):
        cur.execute("SELECT name, tier, power_rating FROM maya_rp.ships WHERE id=%s", (ship_id,))
        row = cur.fetchone()
        if row is None:
            print(f"  id {ship_id}: no such hull")
            continue
        name, tier, power = row
        flag = "" if tier == old_tier else "  <- restore"
        print(f"  id {ship_id:<6} {str(name)[:30]:<30} tier {tier} -> {old_tier}  power {power:,}{flag}")

    if not args.apply:
        print("dry run: nothing written (pass --apply to write)")
        conn.close()
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = pathlib.Path.home() / "backups" / f"mythic-tier-restore-{stamp}.json"
    cur.execute("SELECT id, tier FROM maya_rp.ships WHERE id = ANY(%s)", (list(mythic),))
    backup.write_text(json.dumps({str(r[0]): r[1] for r in cur.fetchall()}, indent=1))
    print(f"backup: {backup}")
    restored = 0
    for ship_id, old_tier in sorted(mythic.items()):
        cur.execute("UPDATE maya_rp.ships SET tier=%s WHERE id=%s AND tier IS DISTINCT FROM %s",
                    (old_tier, ship_id, old_tier))
        restored += cur.rowcount
    conn.commit()
    print(f"restored {restored} hull(s)")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
