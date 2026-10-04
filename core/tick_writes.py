#!/usr/bin/env python3
"""Tick writes — what the tick actually wrote, measured rather than reported.

`scripts/orchestrator.py` counts `modules_ok`: the number of module ticks that returned
without raising. That is not the same as the number that wrote anything. `tick()` returns
`bool(result)` and a successful tick returns `{"ok": True}`, so a module that reads two tables
and changes nothing is counted exactly like one that moved the campaign forward. Measured
2026-10-04: nine of the eighty tick modules contain no INSERT, UPDATE or DELETE at all, and
**203 of the 307 tables in `maya_rp` have never received an insert or update**.

Postgres already records this per table. `pg_stat_user_tables` carries `n_tup_ins`, `n_tup_upd`
and `n_tup_del`, cumulative since the last stats reset. Two snapshots around the tick give the
writes that happened between them, with no change to any module and no instrumentation inside
them.

    before = await snapshot()
    ... the twenty-four phases ...
    moved  = diff(before, await snapshot())
    still  = [t for t in await never_written()]

Nothing here writes. It reads a statistics view and compares two dicts.
"""
from __future__ import annotations

from typing import Any

from core.db import Database

# The view counts background autovacuum and the stats collector's own bookkeeping as well as
# application writes, so a table can move by a row or two for reasons no module caused. A
# threshold keeps the report about modules rather than about housekeeping.
NOISE_FLOOR = 0


async def snapshot() -> dict[str, dict[str, int]]:
    """Every `maya_rp` table with its cumulative insert, update and delete counts.

    Returns an empty dict when the statistics view is not readable, which is a permission
    question rather than a failure: `rp_engine` may not hold `pg_read_all_stats`. The caller
    is expected to say so rather than to report zero writes, because those look identical.
    """
    rows = await Database.fetch(
        "SELECT relname, n_tup_ins, n_tup_upd, n_tup_del"
        " FROM pg_stat_user_tables WHERE schemaname='maya_rp'")
    return {r["relname"]: {"ins": int(r["n_tup_ins"] or 0),
                           "upd": int(r["n_tup_upd"] or 0),
                           "del": int(r["n_tup_del"] or 0)} for r in rows}


def diff(before: dict, after: dict) -> dict[str, dict[str, int]]:
    """Tables that moved between two snapshots, with how far. Pure, so a test needs no database.

    Each counter is floored at zero on its own. A statistics reset between the two snapshots takes
    the counters back to zero, and summing them first would let a real rise in one counter cancel a
    reset in another: five genuine inserts beside a reset `n_tup_upd` would total negative and
    vanish. Floored per counter, a reset reads as no movement for that counter and the inserts
    still show.
    """
    moved: dict[str, dict[str, int]] = {}
    for table, now in (after or {}).items():
        was = (before or {}).get(table)
        if was is None:
            continue
        delta = {k: max(0, now.get(k, 0) - was.get(k, 0)) for k in ("ins", "upd", "del")}
        if sum(delta.values()) > NOISE_FLOOR:
            moved[table] = delta
    return moved


async def never_written() -> list[str]:
    """Tables that have received no insert and no update since the statistics were reset.

    This is the runtime answer to the question a text search answers badly. A static grep for
    `INSERT INTO` finds a writer that is never called and misses one built at runtime; this
    finds what the database has actually seen.
    """
    rows = await Database.fetch(
        "SELECT relname FROM pg_stat_user_tables"
        " WHERE schemaname='maya_rp' AND n_tup_ins=0 AND n_tup_upd=0 ORDER BY relname")
    return [r["relname"] for r in rows]


async def report(before: dict, after: dict) -> dict[str, Any]:
    """A tick's writing summarised: what moved, what never moves, and whether we could tell."""
    if not after:
        return {"readable": False, "moved": {}, "never_written": None,
                "note": "pg_stat_user_tables returned nothing; the statistics view is not readable "
                        "by this role, so 'wrote nothing' cannot be told from 'could not look'"}
    moved = diff(before, after)
    return {
        "readable": True,
        "moved": moved,
        "tables_moved": len(moved),
        "rows": sum(sum(d.values()) for d in moved.values()),
        "never_written": await never_written(),
    }
