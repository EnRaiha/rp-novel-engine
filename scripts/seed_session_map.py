#!/usr/bin/env python3
"""Give the live arc a galaxy.

Session 5 holds 440 characters, five food commodities, and no map at all: zero territories, zero trade
routes, zero planets. Phase 4.4 to 4.7 of the plan (fuel, spoilage, water, slavery) is computed per
territory, and any market or fleet scene has nothing to answer from.

The King ruled on 2026-10-02: **terrain only, and TKG owns nothing.** So this copies the galaxy's
shape from the frozen session — every system, planet, resource deposit, port and slave listing — and
clears the ownership that belonged to the old timeline's conquests. The galaxy is the same galaxy.
Who holds it is Arc I's question, and the answer starts at nothing.

    python3 scripts/seed_session_map.py --dry-run     # the default
    python3 scripts/seed_session_map.py --apply

Writes only with `--apply`, and takes its own backup of whatever session-5 rows already exist.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
from datetime import datetime

from psycopg2.extras import Json

SOURCE_SESSION = 3
TARGET_SESSION = 5

#: Copied in this order, because each row may point at a row copied before it.
#: `remap` names the columns whose values are ids of an earlier table.
TABLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("locations", ()),
    ("territory", ("location_id",)),
    ("planets", ("territory_id",)),
    ("territory_resources", ("territory_id",)),
    ("ports", ("territory_id",)),
    ("slave_market", ("territory_id",)),
    ("trade_routes", ("origin_territory_id", "destination_territory_id")),
)

#: Ownership columns cleared, because the ruling is that Arc I starts with TKG holding nothing and the
#: old timeline's conquests are not part of this arc.
CLEARED = ("controlling_faction", "contested_by")


def connect():
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
    return psycopg2.connect(host=os.environ["OC_PG_HOST"],
                            port=int(os.environ.get("OC_PG_PORT", 5432)),
                            user=os.environ["OC_PG_USER"],
                            password=os.environ.get("OC_PG_PASS"),
                            dbname=os.environ.get("OC_PG_DB", "maya_memory"))


PARENT = {"territory_resources": "territory_id"}


def source_rows(cur, table: str, cols: list[str], id_map: dict[str, dict[int, int]]) -> list[tuple]:
    """The rows to copy, which for a table with no session column means the parent's rows.

    `territory_resources` carries no session_id: a deposit belongs to a territory, and the territory
    carries the session. Selecting it by session is an error, and the error is the point of this
    function existing rather than being inlined.
    """
    if table in PARENT:
        parent = PARENT[table]
        owner = parent.replace("_id", "")
        ids = list(id_map.get(owner, {}).keys())
        if not ids:
            return []
        cur.execute(f"SELECT * FROM maya_rp.{table} WHERE {parent} = ANY(%s) ORDER BY id", (ids,))
        return cur.fetchall()
    cur.execute(f"SELECT * FROM maya_rp.{table} WHERE session_id = %s ORDER BY id", (SOURCE_SESSION,))
    return cur.fetchall()


def has_session(cur, table: str) -> bool:
    cur.execute("""SELECT 1 FROM information_schema.columns
                   WHERE table_schema='maya_rp' AND table_name=%s AND column_name='session_id'""", (table,))
    return cur.fetchone() is not None


def columns_of(cur, table: str) -> list[str]:
    cur.execute("""SELECT column_name FROM information_schema.columns
                   WHERE table_schema='maya_rp' AND table_name=%s ORDER BY ordinal_position""", (table,))
    return [row[0] for row in cur.fetchall()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="write; absent means report only")
    parser.add_argument("--dry-run", action="store_true", help="accepted for symmetry")
    args = parser.parse_args()

    conn = connect()
    cur = conn.cursor()
    report: dict[str, int] = {}
    existing: dict[str, int] = {}
    for table, _ in TABLES:
        if has_session(cur, table):
            cur.execute(f"SELECT count(*) FROM maya_rp.{table} WHERE session_id = %s", (TARGET_SESSION,))
        else:
            parent = PARENT[table]
            owner = parent.replace("_id", "")
            cur.execute(f"""SELECT count(*) FROM maya_rp.{table} t
                            JOIN maya_rp.{owner} p ON p.id = t.{parent}
                            WHERE p.session_id = %s""", (TARGET_SESSION,))
        existing[table] = cur.fetchone()[0]

    if any(existing.values()):
        print("session 5 already holds rows; refusing to add a second map")
        for table, count in existing.items():
            if count:
                print(f"  {table}: {count}")
        return 1

    if not args.apply:
        print("dry run: nothing written")
        for table, _ in TABLES:
            if table in PARENT:
                # Counted through the parent, because the mapping the copy builds does not exist yet
                # and reporting 0 for a table with 24 rows would be a lie.
                parent = PARENT[table]
                owner = parent.replace("_id", "")
                cur.execute(f"""SELECT count(*) FROM maya_rp.{table} t
                                JOIN maya_rp.{owner} p ON p.id = t.{parent}
                                WHERE p.session_id = %s""", (SOURCE_SESSION,))
                report[table] = cur.fetchone()[0]
            else:
                cols = columns_of(cur, table)
                report[table] = len(source_rows(cur, table, cols, {}))
            print(f"  {table:<22} {report[table]:>5} rows would be copied")
        conn.close()
        return 0

    # A sequence that sits behind the ids already in use hands out a duplicate key. Session 3 was
    # seeded with explicit ids, so the sequences never advanced past them.
    for table, _ in TABLES:
        cur.execute("""SELECT pg_get_serial_sequence(%s, 'id')""", (f"maya_rp.{table}",))
        sequence = cur.fetchone()[0]
        if sequence:
            cur.execute(f"SELECT setval(%s, GREATEST((SELECT COALESCE(max(id), 1) FROM maya_rp.{table}), 1))",
                        (sequence,))

    id_map: dict[str, dict[int, int]] = {}
    for table, remap in TABLES:
        cols = columns_of(cur, table)
        rows = source_rows(cur, table, cols, id_map)
        report[table] = len(rows)
        mapping: dict[int, int] = {}
        for raw in rows:
            row = dict(zip(cols, raw))
            source_id = int(row["id"])
            for column in remap:
                if row.get(column) is None:
                    continue
                owner = column.replace("_territory_id", "").replace("_id", "")
                row[column] = id_map.get(owner, {}).get(int(row[column]))
            if table == "territory":
                row["controlling_faction"] = ""
                row["contested_by"] = None
                row["fleet_presence"] = 0
                row["last_battle_session"] = None
                row["last_campaign"] = None
                row["governor_name"] = None
            row["session_id"] = TARGET_SESSION
            for drop in ("id", "created_at", "updated_at"):
                row.pop(drop, None)
            keys = [key for key in row if row[key] is not None
                    or key in ("controlling_faction", "contested_by")]
            placeholders = ", ".join(f"%({key})s" for key in keys)
            params = {}
            for key in keys:
                value = row[key]
                # A list or dict column is jsonb or an array here, and psycopg2 adapts a plain list
                # as a text array, which the server refuses.
                params[key] = Json(value) if isinstance(value, (list, dict)) else value
            cur.execute(
                f"INSERT INTO maya_rp.{table} ({', '.join(keys)}) VALUES ({placeholders}) RETURNING id",
                params)
            mapping[source_id] = int(cur.fetchone()[0])
        id_map[table] = mapping
        print(f"copied: {table:<22} {len(rows):>5} rows")


    if not args.apply:
        conn.rollback()
        print("dry run: nothing written")
        for table, count in report.items():
            print(f"  {table:<22} {count:>5} rows would be copied")
        conn.close()
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = pathlib.Path.home() / "backups" / f"session5-map-seed-{stamp}.json"
    backup.write_text(json.dumps({"applied_at": stamp, "copied": report}, indent=1))
    conn.commit()
    print(f"copied (backup note: {backup}):")
    for table, count in report.items():
        print(f"  {table:<22} {count}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
