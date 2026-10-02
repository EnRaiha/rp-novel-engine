#!/usr/bin/env python3
"""Record the migrations that were applied by hand, before the bookkeeping table existed.

`maya_rp._migrations` starts at 118, so 56 SQL files on disk are absent from it. `scripts/migrate.py`
treats an absent file as pending and **executes** it, and it continues past failures — so running it
today would replay 56 migrations, 13 of which carry UPDATE or DROP TABLE. One of them drops a table.

This records the ones that can be proved applied: a file is recorded when every object it creates can
be found in the schema. A file whose objects cannot be verified is **listed, never recorded**, because
recording a migration that never ran is the same mistake in the other direction.

    python3 scripts/record_legacy_migrations.py --dry-run     # the default
    python3 scripts/record_legacy_migrations.py --apply
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations"

TABLE = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:maya_rp\.)?([a-z_][a-z0-9_]*)", re.I)
COLUMN = re.compile(r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?(?:maya_rp\.)?([a-z_][a-z0-9_]*)[^;]*?ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-z_][a-z0-9_]*)", re.I | re.S)
INDEX = re.compile(r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-z_][a-z0-9_]*)", re.I)


def objects(text: str) -> dict[str, list[tuple[str, str]]]:
    """The objects a migration creates, by kind.

    @returns {"table": [(name, "")], "column": [(table, column)], "index": [(name, "")]}
    """
    return {
        "table": [(name.lower(), "") for name in TABLE.findall(text)],
        "column": [(table.lower(), column.lower()) for table, column in COLUMN.findall(text)],
        "index": [(name.lower(), "") for name in INDEX.findall(text)],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
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
    if not os.environ.get("OC_PG_HOST"):
        raise SystemExit("no OC_PG_* settings")

    conn = psycopg2.connect(host=os.environ["OC_PG_HOST"], port=int(os.environ.get("OC_PG_PORT", 5432)),
                            user=os.environ["OC_PG_USER"], password=os.environ.get("OC_PG_PASS"),
                            dbname=os.environ.get("OC_PG_DB", "maya_memory"))
    cur = conn.cursor()
    cur.execute("SELECT name FROM maya_rp._migrations")
    recorded = {row[0] for row in cur.fetchall()}

    provable: list[str] = []
    uncertain: list[tuple[str, str]] = []
    for path in sorted(MIGRATIONS.glob("*.sql")):
        if path.name in recorded:
            continue
        found = objects(path.read_text(encoding="utf-8", errors="replace"))
        checks = []
        for name, _ in found["table"]:
            cur.execute("""SELECT 1 FROM information_schema.tables
                           WHERE table_schema='maya_rp' AND table_name=%s""", (name,))
            checks.append(bool(cur.fetchone()))
        for table, column in found["column"]:
            cur.execute("""SELECT 1 FROM information_schema.columns
                           WHERE table_schema='maya_rp' AND table_name=%s AND column_name=%s""",
                        (table, column))
            checks.append(bool(cur.fetchone()))
        for name, _ in found["index"]:
            cur.execute("""SELECT 1 FROM pg_indexes
                           WHERE schemaname='maya_rp' AND indexname=%s""", (name,))
            checks.append(bool(cur.fetchone()))
        if checks and all(checks):
            provable.append(path.name)
        elif not checks:
            uncertain.append((path.name, "nothing to verify: no table, column or index named"))
        else:
            uncertain.append((path.name, f"{checks.count(False)} of {len(checks)} objects missing"))

    print(f"already recorded: {len(recorded)}")
    print(f"provable as applied: {len(provable)}")
    print(f"needs a human: {len(uncertain)}")
    for name, why in uncertain[:12]:
        print(f"   {name:<36} {why}")

    if not args.apply:
        print("dry run: nothing written")
        conn.close()
        return 0

    for name in provable:
        cur.execute("INSERT INTO maya_rp._migrations (name) VALUES (%s) ON CONFLICT (name) DO NOTHING", (name,))
    conn.commit()
    cur.execute("SELECT count(*) FROM maya_rp._migrations")
    print(f"recorded {len(provable)}; _migrations now holds {cur.fetchone()[0]}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
