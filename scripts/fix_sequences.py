#!/usr/bin/env python3
"""Bring every id sequence in maya_rp up to its table's max(id).

A sequence that trails its table is a latent crash: the next `nextval` hands out an id that already
exists, so any insert that lets the sequence choose the id fails on a duplicate key. Found 2026-10-03
during the module review, where `territory_id_seq` sat at 874 against a max(id) of 1348 — the seeder and
every future insert would have failed there.

A sequence that runs ahead is harmless, so this only ever raises one.

    python3 scripts/fix_sequences.py            # report
    python3 scripts/fix_sequences.py --apply    # repair
"""
from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

QUERY = """
SELECT c.relname AS table_name,
       pg_get_serial_sequence('maya_rp.' || c.relname, 'id') AS seq,
       (SELECT last_value FROM pg_sequences s
         WHERE s.schemaname = 'maya_rp'
           AND s.sequencename = split_part(pg_get_serial_sequence('maya_rp.' || c.relname, 'id'), '.', 2)
       ) AS seq_value
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = 'maya_rp' AND c.relkind = 'r'
   AND pg_get_serial_sequence('maya_rp.' || c.relname, 'id') IS NOT NULL
   -- planet_types_catalog resolves a sequence for `id` but has no such column, which made the max(id)
   -- read raise UndefinedColumnError. Only tables that really carry the column are considered.
   AND EXISTS (SELECT 1 FROM information_schema.columns col
                WHERE col.table_schema = 'maya_rp' AND col.table_name = c.relname
                  AND col.column_name = 'id')
 ORDER BY c.relname
"""


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    from core.db import Database

    await Database.init()
    rows = await Database.fetch(QUERY)
    behind = []
    for row in rows:
        biggest = await Database.fetchval(f'SELECT COALESCE(max(id), 0) FROM maya_rp."{row["table_name"]}"')
        if row["seq_value"] is not None and int(row["seq_value"]) < int(biggest):
            behind.append((row["table_name"], int(row["seq_value"]), int(biggest)))
    if not behind:
        print(f"all {len(rows)} sequences are at or ahead of their table")
        await Database.close()
        return 0
    for table, seq_value, biggest in behind:
        print(f"  {table}: sequence {seq_value}, max(id) {biggest}")
        if args.apply:
            await Database.execute(
                "SELECT setval($1::regclass, $2)",
                f"maya_rp.{table}_id_seq", biggest)
            print(f"    raised to {biggest}")
    if not args.apply:
        print("report only; pass --apply to repair")
    await Database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
