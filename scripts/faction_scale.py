#!/usr/bin/env python3
"""Faction scale — cap holdings so the map matches the world's physics.

The rule (King, 2026-10-02): most factions hold **one to three planets**, at most.
Only a few large ones reach **five to ten systems**. The reason is not politics:
resources are thin, technology is not yet past torch drives, and magic does not
scale. Nothing in this galaxy can afford a hundred-system empire.

The generated map disagrees: 892 systems across 37 holders, one faction with 109.
This script enforces the rule and releases the excess back to `Unclaimed`.

    python3 scripts/faction_scale.py --dry-run
    python3 scripts/faction_scale.py            # writes, after backing up

The backup is `~/backups/faction-scale-<stamp>.json`, the full old holder for every
row this script touches.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from datetime import datetime

# Factions allowed past the minor cap, with the systems they keep.
MAJOR = {
    "Iron Concord": 10,
    "Vein Collective": 9,
    "The Silent Choir": 8,
    "Free Ports Alliance": 7,
    "The Mechnoic": 7,
    "The Cyber Collective": 6,
}
# the territory rows spell it without the parenthetical: "Setia Empire"
NOT_ESTABLISHED = {"Setia Empire (Kingdom)": 0, "Setia Empire": 0}
MINOR_CAP = 3
UNCLAIMED = "Unclaimed"


def minor_allowance(held: int) -> int:
    """One to three planets, decided by how much the faction already holds."""
    return MINOR_CAP if held >= 20 else (2 if held >= 10 else 1)


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
    cur.execute("SELECT id, controlling_faction FROM maya_rp.territory"
                " WHERE COALESCE(controlling_faction, '') NOT IN ('', %s) ORDER BY id", (UNCLAIMED,))
    rows = cur.fetchall()

    held: dict[str, list[int]] = {}
    for tid, holder in rows:
        held.setdefault(holder, []).append(tid)

    plan: list[tuple[int, str]] = []
    summary: dict[str, tuple[str, int, int]] = {}
    for holder, ids in held.items():
        if holder in NOT_ESTABLISHED:
            keep, klass = 0, "not_established"
        elif holder in MAJOR:
            keep, klass = MAJOR[holder], "major"
        else:
            keep, klass = minor_allowance(len(ids)), "minor"
        for tid in ids[keep:]:
            plan.append((tid, holder))
        summary[holder] = (klass, len(ids), keep)

    print(f"holders {len(held)} · rows {len(rows)} · releasing {len(plan)}")
    for holder, (klass, before, keep) in sorted(summary.items(), key=lambda kv: -kv[1][1])[:8]:
        print(f"  {holder[:28]:<28} {klass:<16} {before:>4} -> {keep}")

    if args.dry_run:
        print("dry run: nothing written")
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = pathlib.Path.home() / "backups" / f"faction-scale-{stamp}.json"
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_text(json.dumps({str(tid): holder for tid, holder in plan}, indent=0))
    print(f"backup: {backup}")

    for tid, _ in plan:
        # status keeps its own vocabulary; releasing a system does not invent a new one
        cur.execute("""UPDATE maya_rp.territory SET controlling_faction=%s, contested_by=NULL,
                       updated_at=now() WHERE id=%s""", (UNCLAIMED, tid))
    cur.execute("ALTER TABLE maya_rp.factions ADD COLUMN IF NOT EXISTS systems_held integer DEFAULT 0")
    cur.execute("ALTER TABLE maya_rp.factions ADD COLUMN IF NOT EXISTS scale_class text DEFAULT 'minor'")
    for holder, (klass, _, keep) in summary.items():
        cur.execute("UPDATE maya_rp.factions SET systems_held=%s, scale_class=%s WHERE name=%s",
                    (keep, klass, holder))
    conn.commit()
    cur.execute("SELECT controlling_faction, count(*) FROM maya_rp.territory GROUP BY 1 ORDER BY 2 DESC LIMIT 5")
    print("after:", cur.fetchall())
    cur.execute("SELECT scale_class, count(*) FROM maya_rp.factions GROUP BY 1 ORDER BY 2 DESC")
    print("classes:", cur.fetchall())
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
