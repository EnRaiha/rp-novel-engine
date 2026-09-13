#!/usr/bin/env python3
"""SAVEGAME SYSTEM — portable .sav files (game-engine style), PG as second truth.

Design (common game engine pattern):
  - PG (maya_rp)      = PRIMARY truth while running (live queries, simulation)
  - .sav JSON file     = PORTABLE snapshot — full state dump, restorable, shareable
  - save               → full table dump → .sav (JSON, checksummed)
  - load <file.sav>    → wipe + restore PG from the .sav (crash recovery / migrate)

Layout:
  {
    "header": {"format": "tkg-sav", "version": 2, "game_day": N, "saved_at": "...",
               "session_id": 3, "checksum": "sha256-of-content"},
    "tables": { "<table>": [ {row}, ... ], ... }
  }

QA fix 2026-08-14 (BUG-1/2/3):
  - Snapshot tables are now derived DYNAMICALLY from the live schema
    (all maya_rp tables minus exclusions and vector-column tables),
    instead of a hand-maintained 50-table list that silently missed
    crew_roster (4,090 rows), prisoners (1,542), faction_ships (1,463),
    sectors (625), etc.
  - Wipe order is FK-aware (children-before-parents topological sort
    from pg_constraint) instead of alphabetical — alphabetical order
    silently failed against FK NO ACTION constraints (BUG-1).
  - TRUNCATE ... CASCADE replaced with ordered DELETE (BUG-3).
  - Errors are logged, not swallowed (BUG-6 class).

Excluded tables: migration bookkeeping, roll/telemetry logs, price ticks,
and any table containing pgvector columns (vector types cannot round-trip
through JSON; novel_chunks/wiki_articles are re-ingestible).
"""
from __future__ import annotations
import asyncio, hashlib, json, sys, time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from core.config import Config
from core.db import Database
from core.log import info, error

SAV_VERSION = 2
FORMAT = "tkg-sav"

# Tables never included in .sav snapshots (bookkeeping/telemetry/re-ingestible).
EXCLUDED_TABLES = {
    "_migrations", "migration_versions", "migration_hashes", "savepoints",
    "roll_history", "tick_summaries", "price_history", "narrator_cost_log",
}


def _json_default(o):
    if isinstance(o, (datetime,)):
        return o.isoformat()
    if hasattr(o, "isoformat"):
        return o.isoformat()
    return str(o)


# ─── Pure helpers (unit-testable, no DB) ─────────────────────────────────

def classify_tables(all_tables: set, has_session_id: set, vector_tables: set,
                    exclusions: set) -> tuple[list, list]:
    """Split tables into (session_scoped, global) lists.

    session_scoped = has a `session_id` column → filtered per session.
    global         = no session_id → catalog data dumped/restored whole.
    Tables with vector columns or in the exclusion set are omitted entirely.
    """
    included = all_tables - set(exclusions) - set(vector_tables)
    session_scoped = sorted(t for t in included if t in has_session_id)
    global_tables = sorted(t for t in included if t not in has_session_id)
    return session_scoped, global_tables


def fk_wipe_order(tables: set, fk_edges: list) -> list:
    """Topological sort: children BEFORE parents (safe delete order).

    fk_edges: [(child_table, parent_table), ...] from pg_constraint.
    A parent row cannot be deleted while child rows reference it,
    so children must be deleted first. Kahn's algorithm; cycles are
    appended at the end (best effort, no crash).
    """
    edges = [(c, p) for c, p in fk_edges if c in tables and p in tables]
    parents_of = defaultdict(list)   # child -> [parents]
    indegree = defaultdict(int)      # parent -> number of children not yet deleted
    for c, p in edges:
        parents_of[c].append(p)
        indegree[p] += 1

    queue = deque(sorted(t for t in tables if indegree[t] == 0))
    order = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for parent in parents_of[node]:
            indegree[parent] -= 1
            if indegree[parent] == 0:
                queue.append(parent)

    order.extend(sorted(set(tables) - set(order)))
    return order


# ─── Schema inventory (live DB) ─────────────────────────────────────────

async def _schema_inventory() -> tuple[set, set, set, list]:
    """(all_tables, has_session_id, vector_tables, fk_edges[(child,parent)])"""
    all_tables = {r["t"] for r in await Database.fetch(
        "SELECT tablename AS t FROM pg_tables WHERE schemaname='maya_rp'")}
    has_sid = {r["table_name"] for r in await Database.fetch(
        "SELECT table_name FROM information_schema.columns "
        "WHERE table_schema='maya_rp' AND column_name='session_id'")}
    # pgvector columns report data_type='USER-DEFINED', udt_name='vector'
    vector_tables = {r["table_name"] for r in await Database.fetch(
        "SELECT table_name FROM information_schema.columns "
        "WHERE table_schema='maya_rp' AND udt_name='vector'")}
    fks = [(r["child"], r["parent"]) for r in await Database.fetch(
        "SELECT c1.relname AS child, c2.relname AS parent "
        "FROM pg_constraint k "
        "JOIN pg_class c1 ON c1.oid = k.conrelid "
        "JOIN pg_class c2 ON c2.oid = k.confrelid "
        "JOIN pg_namespace n ON n.oid = c1.relnamespace "
        "WHERE k.contype='f' AND n.nspname='maya_rp'")]
    return all_tables, has_sid, vector_tables, fks


# ─── Export ─────────────────────────────────────────────────────────────

async def export_sav(session_id: int = 3, out_dir: str | None = None) -> str:
    """Dump full state → .sav JSON file. Returns file path."""
    await Database.init()

    all_tables, has_sid, vector_tables, fks = await _schema_inventory()
    session_scoped, global_tables = classify_tables(
        all_tables, has_sid, vector_tables, EXCLUDED_TABLES)
    # Restore order = parents before children = reverse of wipe order.
    ordered = list(reversed(fk_wipe_order(set(session_scoped) | set(global_tables), fks)))
    session_set = set(session_scoped)

    tables = {}
    for t in ordered:
        try:
            if t in session_set:
                rows = await Database.fetch(
                    f"SELECT * FROM maya_rp.{t} WHERE session_id=$1", session_id)
            else:
                rows = await Database.fetch(f"SELECT * FROM maya_rp.{t}")
            tables[t] = [dict(r) for r in rows]
        except Exception as e:
            tables[t] = {"__error__": str(e)}
            error("savegame", f"export table {t} failed: {e}")

    payload = {
        "header": {
            "format": FORMAT,
            "version": SAV_VERSION,
            "game_day": (await Database.fetchval(
                "SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id)),
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
        },
        "tables": tables,
    }
    content = json.dumps(payload, default=_json_default, indent=1)
    payload["header"]["checksum"] = hashlib.sha256(content.encode()).hexdigest()[:16]

    cfg = Config.get()
    out = Path(out_dir or cfg.BACKUP_DIR)
    out.mkdir(parents=True, exist_ok=True)
    fp = out / f"save_{session_id}_day{payload['header']['game_day']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sav"
    fp.write_text(json.dumps(payload, default=_json_default, indent=1))
    info("savegame", f"Exported {len([t for t, v in tables.items() if isinstance(v, list)])} "
                     f"tables → {fp.name}")
    await Database.close()
    return str(fp)


# ─── Import ─────────────────────────────────────────────────────────────

def _verify_checksum(data: dict) -> bool:
    saved = data.get("header", {}).get("checksum")
    if not saved:
        return False
    copy = json.loads(json.dumps(data))
    copy["header"].pop("checksum", None)
    calc = hashlib.sha256(
        json.dumps(copy, default=_json_default, indent=1).encode()).hexdigest()[:16]
    return calc == saved


async def import_sav(path: str, session_id: int | None = None, wipe: bool = True) -> dict:
    """Restore PG from a .sav file. wipe=True resets ALL current session/catalog
    tables to the snapshot (FK-safe ordered DELETE, no TRUNCATE CASCADE).

    Note: restoring a .sav produced before the 2026-08-14 fix will reset
    tables that were absent from that older partial snapshot — that is the
    correct full-reset semantic; keep a fresh export as your working save.
    """
    await Database.init()
    p = Path(path)
    if not p.exists():
        return {"ok": False, "error": f"not found: {path}"}
    data = json.loads(p.read_text())
    if data.get("header", {}).get("format") != FORMAT:
        return {"ok": False, "error": "not a tkg-sav file"}

    checksum_ok = _verify_checksum(data)
    if not checksum_ok:
        info("savegame", f"WARNING: checksum mismatch on {p.name} — proceeding anyway")

    sid = session_id or data["header"]["session_id"]
    tables = data.get("tables", {})
    restored = 0
    row_errors = 0
    skipped_tables = 0

    async with Database.transaction() as conn:
        if wipe:
            all_tables, has_sid, vector_tables, fks = await _schema_inventory()
            session_scoped, global_tables = classify_tables(
                all_tables, has_sid, vector_tables, EXCLUDED_TABLES)
            session_set = set(session_scoped)
            order = fk_wipe_order(set(session_scoped) | set(global_tables), fks)
            for t in order:
                if t == "sessions":
                    continue  # preserve the session row itself
                try:
                    if t in session_set:
                        await conn.execute(
                            f"DELETE FROM maya_rp.{t} WHERE session_id=$1", sid)
                    else:
                        await conn.execute(f"DELETE FROM maya_rp.{t}")
                except Exception as e:
                    error("savegame", f"wipe {t} failed (aborting restore): {e}")
                    raise  # no silent half-wipes — abort the transaction

        # restore in the .sav's stored (parents-first) order
        for t, rows in tables.items():
            if not isinstance(rows, list) or not rows:
                continue
            if isinstance(rows[0], dict) and "__error__" in rows[0]:
                skipped_tables += 1
                info("savegame", f"restore skip {t}: exported with error {rows[0]['__error__']}")
                continue
            cols = list(rows[0].keys())
            colsql = ", ".join(f'"{c}"' for c in cols)
            for row in rows:
                vals = []
                for c in cols:
                    v = row.get(c)
                    if isinstance(v, str):
                        vals.append(f"'{v.replace(chr(39), chr(39)+chr(39))}'")
                    elif v is None:
                        vals.append("NULL")
                    elif isinstance(v, bool):
                        vals.append("true" if v else "false")
                    elif isinstance(v, (int, float)):
                        vals.append(str(v))
                    else:
                        vals.append(
                            f"'{json.dumps(v, default=_json_default).replace(chr(39), chr(39)+chr(39))}'::jsonb")
                try:
                    await conn.execute(
                        f'INSERT INTO maya_rp.{t} ({colsql}) VALUES ({", ".join(vals)}) ON CONFLICT DO NOTHING')
                    restored += 1
                except Exception as e:
                    row_errors += 1
                    if row_errors <= 5:
                        error("savegame", f"restore row {t} failed: {e}")

    info("savegame", f"Restored {restored} rows, {row_errors} row errors, "
                     f"{skipped_tables} skipped tables (checksum_ok={checksum_ok})")
    await Database.close()
    return {"ok": True, "restored_rows": restored, "row_errors": row_errors,
            "skipped_tables": skipped_tables, "checksum_ok": checksum_ok,
            "session_id": sid, "game_day": data["header"].get("game_day")}
