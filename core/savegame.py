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


# ─── Row encoding (type-aware) ──────────────────────────────────────────

async def _column_udts(tables: list[str]) -> dict[str, dict[str, str]]:
    """{table: {column: udt_name}} for the tables in a .sav (one query)."""
    rows = await Database.fetch(
        "SELECT table_name, column_name, udt_name FROM information_schema.columns "
        "WHERE table_schema='maya_rp' AND table_name = ANY($1::text[])", tables)
    out: dict[str, dict[str, str]] = {}
    for r in rows:
        out.setdefault(r["table_name"], {})[r["column_name"]] = r["udt_name"]
    return out


def _pg_array_literal(v: list, udt: str) -> str:
    """Encode a Python list as a PostgreSQL ARRAY literal.

    The old blanket `::jsonb` cast raised DatatypeMismatchError for every
    ARRAY column (8 of them, e.g. cabinet_decrees.event_ids INT[],
    planet_types_catalog.special_events TEXT[]), which is why those tables
    could never be restored.
    """
    elem_type = udt[1:] + "[]" if udt.startswith("_") else "text[]"
    parts = []
    for x in v:
        if x is None:
            parts.append("NULL")
        elif isinstance(x, bool):
            parts.append("true" if x else "false")
        elif isinstance(x, (int, float)):
            parts.append(str(x))
        else:
            s = str(x).replace("\\", "\\\\").replace('"', '\\"')
            parts.append(f'"{s}"')
    return f"'{{{','.join(parts)}}}'::{elem_type}"


def _encode_value(v, udt: str) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, list):
        if udt in ("json", "jsonb"):
            return "'" + json.dumps(v, default=_json_default).replace("'", "''") + "'::jsonb"
        return _pg_array_literal(v, udt)
    if isinstance(v, str):
        if udt in ("json", "jsonb"):
            return "'" + v.replace("'", "''") + "'::jsonb"
        return "'" + v.replace("'", "''") + "'"
    # dict / anything else → jsonb
    return "'" + json.dumps(v, default=_json_default).replace("'", "''") + "'::jsonb"


async def _generated_columns(tables: list[str]) -> dict[str, set]:
    """{table: {generated column}} — GENERATED ALWAYS columns cannot be
    inserted explicitly (e.g. yard_capacity.total_capacity)."""
    rows = await Database.fetch(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema='maya_rp' AND is_generated = 'ALWAYS' "
        "AND table_name = ANY($1::text[])", tables)
    out: dict[str, set] = {}
    for r in rows:
        out.setdefault(r["table_name"], set()).add(r["column_name"])
    return out


def _insert_sql(table: str, cols: list, row: dict, types: dict, conflict: str) -> str:
    colsql = ", ".join(f'"{c}"' for c in cols)
    vals = ", ".join(_encode_value(row.get(c), types.get(c, "")) for c in cols)
    return f"INSERT INTO maya_rp.{table} ({colsql}) VALUES ({vals}) {conflict}"


def _conflict_clause(table: str, cols: list) -> str:
    """UPSERT on the primary key so the .sav is authoritative.

    ON CONFLICT DO NOTHING silently skipped any snapshot row whose id was still
    present in the live table (rows outside the wiped session scope), so those
    tables came back short. DO UPDATE replaces them instead.
    """
    if table == "sessions" or "id" in cols:
        upd = ", ".join(f'"{c}"=EXCLUDED."{c}"' for c in cols if c != "id")
        if not upd:
            return "ON CONFLICT DO NOTHING"
        target = "(id)" if "id" in cols else ""
        return f"ON CONFLICT {target} DO UPDATE SET {upd}"
    return "ON CONFLICT DO NOTHING"


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


def fk_cycle_members(tables: set, fk_edges: list) -> set:
    """Tables Kahn cannot order because they sit in an FK cycle.

    fk_wipe_order() appends these at the end (alphabetical), which is NOT a
    valid delete order — the first DELETE then hits a parent FK. Callers must
    break each cycle-internal edge (NULL the child column) before wiping.
    """
    edges = [(c, p) for c, p in fk_edges if c in tables and p in tables]
    parents_of = defaultdict(list)
    indegree = defaultdict(int)
    for c, p in edges:
        parents_of[c].append(p)
        indegree[p] += 1

    queue = deque(sorted(t for t in tables if indegree[t] == 0))
    done = set()
    while queue:
        node = queue.popleft()
        done.add(node)
        for parent in parents_of[node]:
            indegree[parent] -= 1
            if indegree[parent] == 0:
                queue.append(parent)
    return set(tables) - done


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


async def _fk_child_columns() -> list[tuple[str, str, str]]:
    """[(child_table, parent_table, child_column)] for every maya_rp FK."""
    return [(r["child"], r["parent"], r["col"]) for r in await Database.fetch(
        "SELECT c1.relname AS child, c2.relname AS parent, a.attname AS col "
        "FROM pg_constraint k "
        "JOIN pg_class c1 ON c1.oid = k.conrelid "
        "JOIN pg_class c2 ON c2.oid = k.confrelid "
        "JOIN pg_namespace n ON n.oid = c1.relnamespace "
        "JOIN unnest(k.conkey) AS ck(attnum) ON true "
        "JOIN pg_attribute a ON a.attrelid = c1.oid AND a.attnum = ck.attnum "
        "WHERE k.contype='f' AND n.nspname='maya_rp'")]


# ─── Export ─────────────────────────────────────────────────────────────

#: Above this many parent ids the child is exported whole rather than filtered: an `= ANY($1)` with
#: hundreds of thousands of values costs more than the rows it saves.
MAX_IN_FILTER_IDS = 250_000


class SaveIncomplete(RuntimeError):
    """A save could not read every table, so no file was written.

    The old behaviour stored `{"__error__": ...}` in place of the table and wrote the file anyway. The
    restore path wipes every table before loading, so a save that is missing one table silently
    restores that table as empty, and nobody finds out until the data is needed. A checkpoint that
    cannot be trusted is worse than no checkpoint.
    """

    def __init__(self, failed: dict[str, str]):
        self.failed = dict(failed)
        tables = ", ".join(sorted(failed)[:8])
        more = "" if len(failed) <= 8 else f" (+{len(failed) - 8} more)"
        super().__init__(f"{len(failed)} table(s) could not be read, so nothing was written: "
                         f"{tables}{more}")


async def export_sav(session_id: int = 3, out_dir: str | None = None) -> str:
    """Dump full state → .sav JSON file. Returns file path.

    @raises SaveIncomplete - when any table fails to read. Nothing is written in that case.
    """
    await Database.init()

    all_tables, has_sid, vector_tables, fks = await _schema_inventory()
    session_scoped, global_tables = classify_tables(
        all_tables, has_sid, vector_tables, EXCLUDED_TABLES)
    # Restore order = parents before children = reverse of wipe order.
    ordered = list(reversed(fk_wipe_order(set(session_scoped) | set(global_tables), fks)))
    session_set = set(session_scoped)

    # A table with no session_id takes its session from a parent. Without this map the export dumps
    # every row of every such table: the session-5 checkpoint of 2026-10-02 carried 109,149
    # ship_armaments and 41,594 fleet_members rows that all belonged to frozen session 3, and the
    # restore wipes before it loads, so those numbers were a rewrite waiting to happen.
    # A child may carry more than one foreign key into the session's tables (fleet_members points at
    # both a fleet and a ship), so all of them are kept and a row belongs to the session when any of
    # them does.
    # Which session-scoped tables can be filtered against at all. Asked once, because a table with no
    # rows still means "this session owns none", and reading that as "no filter" let session 3's 24
    # territory_resources rows ride along in a session-5 save.
    has_id = {r["table_name"] for r in await Database.fetch(
        "SELECT table_name FROM information_schema.columns "
        "WHERE table_schema='maya_rp' AND column_name='id'")}
    child_of: dict[str, list[tuple[str, str]]] = {}
    for child, parent, column in await _fk_child_columns():
        if parent in session_set and child not in session_set:
            child_of.setdefault(child, []).append((parent, column))

    tables: dict[str, object] = {}
    failed: dict[str, str] = {}
    exported_ids: dict[str, list[int]] = {}
    partial: list[str] = []      # session-less tables carried only in part, or not at all
    unfiltered: list[str] = []   # session-less tables with no session-scoped parent: honestly global
    for t in ordered:
        try:
            if t in session_set:
                rows = await Database.fetch(
                    f"SELECT * FROM maya_rp.{t} WHERE session_id=$1", session_id)
            elif t in child_of and any(parent in exported_ids for parent, _ in child_of[t]):
                clauses, params = [], []
                too_wide = False
                for parent, column in child_of[t]:
                    ids = exported_ids.get(parent)
                    if ids is None:
                        continue
                    if not ids:
                        continue
                    if len(ids) > MAX_IN_FILTER_IDS:
                        too_wide = True
                        break
                    params.append(ids)
                    clauses.append(f"{column} = ANY(${len(params)})")
                if too_wide:
                    rows = await Database.fetch(f"SELECT * FROM maya_rp.{t}")
                    unfiltered.append(t)
                elif not clauses:
                    rows = []
                else:
                    rows = await Database.fetch(
                        f"SELECT * FROM maya_rp.{t} WHERE " + " OR ".join(clauses), *params)
                partial.append(t)
            else:
                rows = await Database.fetch(f"SELECT * FROM maya_rp.{t}")
                unfiltered.append(t)
            tables[t] = [dict(r) for r in rows]
            if t in session_set and t in has_id:
                # Recorded even when empty: `ooc_suspicion` and its neighbours key on
                # (session_id, observer_id) and carry no id, so they are skipped.
                exported_ids[t] = [int(r["id"]) for r in rows]
        except Exception as e:
            failed[t] = str(e)
            error("savegame", f"export table {t} failed: {e}")

    if failed:
        # Refuse rather than write a snapshot with a hole in it.
        await Database.close()
        raise SaveIncomplete(failed)

    payload = {
        "header": {
            "format": FORMAT,
            "version": SAV_VERSION,
            "game_day": (await Database.fetchval(
                "SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id)),
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            # A restore must not touch a table this file carries only in part, or the wipe deletes
            # rows the file cannot put back.
            "partial_tables": partial,
            "unfiltered_tables": unfiltered,
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
    # A file written before the export learned to refuse carries `{"__error__": ...}` where a table
    # should be. Restoring it would wipe that table and leave it empty, so the restore refuses too.
    broken = {name: value.get("__error__") for name, value in tables.items()
              if isinstance(value, dict) and "__error__" in value}
    if broken:
        raise SaveIncomplete({name: str(err) for name, err in broken.items()})
    restored = 0
    row_errors = 0
    skipped_tables = 0
    deferred: list[tuple[str, str]] = []   # (insert SQL, table) awaiting parents

    async with Database.transaction() as conn:
        if wipe:
            all_tables, has_sid, vector_tables, fks = await _schema_inventory()
            session_scoped, global_tables = classify_tables(
                all_tables, has_sid, vector_tables, EXCLUDED_TABLES)
            session_set = set(session_scoped)
            # A table the file carries only in part must not be wiped: the wipe would delete rows the
            # file cannot put back. Session 3's 109,149 ship_armaments would have gone that way.
            partial = set(data.get("header", {}).get("partial_tables") or [])
            if partial:
                info("savegame", f"restore leaves {len(partial)} partially carried table(s) untouched: "
                                 + ", ".join(sorted(partial)[:6]))
            wipe_set = ((set(session_scoped) | set(global_tables)) - {"sessions"}) - partial
            order = fk_wipe_order(wipe_set, fks)
            fk_cols = await _fk_child_columns()
            # Tables left OUT of the wipe (excluded logs, vector/RAG tables) can
            # still hold FKs into tables we are about to wipe — PostgreSQL then
            # aborts the parent DELETE and the whole restore rolls back
            # (e.g. sessions.primary_partner_id -> characters,
            #  roll_history.difficulty_id -> difficulty_tiers). Detach first:
            # NULL the referencing column, and only delete rows if it is NOT NULL.
            for child, parent, col in fk_cols:
                if parent not in wipe_set or child in wipe_set:
                    continue
                try:
                    async with conn.transaction():  # savepoint
                        await conn.execute(f'UPDATE maya_rp.{child} SET "{col}"=NULL')
                except Exception:
                    try:
                        async with conn.transaction():  # savepoint
                            if child in has_sid:
                                await conn.execute(
                                    f"DELETE FROM maya_rp.{child} WHERE session_id=$1", sid)
                            else:
                                await conn.execute(f"DELETE FROM maya_rp.{child}")
                    except Exception as e:
                        # the parent wipe below will surface any real blocker
                        error("savegame",
                              f"detach {child}.{col} skipped ({e})")
            # FK cycles (10 tables in maya_rp: characters -> territory ->
            # locations, clues -> characters, self-referencing heirs/prerequisites)
            # cannot be topologically ordered; Kahn parks them at the end and the
            # first DELETE then violates a parent FK. Break each cycle-internal
            # edge by NULLing the child column first.
            cycles = fk_cycle_members(wipe_set, fks)
            if cycles:
                info("savegame",
                     f"FK cycles: {len(cycles)} tables — breaking with NULLs")
            for child, parent, col in fk_cols:
                if child not in cycles or parent not in cycles:
                    continue
                try:
                    async with conn.transaction():  # savepoint
                        if child in has_sid:
                            await conn.execute(
                                f'UPDATE maya_rp.{child} SET "{col}"=NULL '
                                f"WHERE session_id=$1", sid)
                        else:
                            await conn.execute(
                                f'UPDATE maya_rp.{child} SET "{col}"=NULL')
                except Exception as e:
                    error("savegame", f"cycle break {child}.{col} skipped ({e})")
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
        udts = await _column_udts(list(tables))
        gens = await _generated_columns(list(tables))
        for t, rows in tables.items():
            if t in partial:
                # Same reason as the wipe: a table carried in part cannot be restored without
                # deleting what the file never had.
                skipped_tables += 1
                continue
            if not isinstance(rows, list) or not rows:
                continue
            if isinstance(rows[0], dict) and "__error__" in rows[0]:
                skipped_tables += 1
                info("savegame", f"restore skip {t}: exported with error {rows[0]['__error__']}")
                continue
            cols = [c for c in rows[0].keys() if c not in gens.get(t, set())]
            # Type-aware encoding: ARRAY columns need an ARRAY literal, jsonb
            # columns need ::jsonb, everything else stays a scalar. The old
            # blanket `::jsonb` broke all 8 ARRAY columns.
            types = udts.get(t, {})
            conflict = _conflict_clause(t, cols)

            def _sql(row: dict, _t=t, _cols=cols, _types=types,
                     _conflict=conflict) -> str:
                return _insert_sql(_t, _cols, row, _types, _conflict)

            # One savepoint per table: a single bad row must NOT abort the outer
            # transaction (that used to abort every remaining INSERT, silently
            # reporting ok:True with a partial restore). On failure the table is
            # retried row-by-row under its own savepoint so the good rows land.
            try:
                async with conn.transaction():
                    for row in rows:
                        await conn.execute(_sql(row))
                        restored += 1
            except Exception as e:
                error("savegame",
                      f"restore {t}: batch failed ({e}) — retrying row-by-row")
                for row in rows:
                    try:
                        async with conn.transaction():
                            await conn.execute(_sql(row))
                        restored += 1
                    except Exception as e2:
                        row_errors += 1
                        deferred.append((_sql(row), t))
                        if row_errors <= 10:
                            error("savegame", f"restore row {t} failed: {e2}")

        # Deferred pass: the .sav's stored order is parents-first, but FK cycles
        # (characters ⇄ territory ⇄ locations ⇄ clues) can't be ordered at all and
        # a child row may legitimately fail before its parent lands. Retry the
        # leftovers until a round makes no progress.
        for _round in range(4):
            if not deferred:
                break
            still: list[tuple[str, str]] = []
            for sql, tbl in deferred:
                try:
                    async with conn.transaction():  # savepoint
                        await conn.execute(sql)
                    restored += 1
                    row_errors -= 1
                except Exception:
                    still.append((sql, tbl))
            if len(still) == len(deferred):
                break  # no progress — remaining rows are genuinely unresolvable
            info("savegame",
                 f"deferred pass {_round + 1}: {len(deferred) - len(still)} rows landed, "
                 f"{len(still)} still pending")
            deferred = still
        if deferred:
            error("savegame",
                  f"{len(deferred)} rows could not be restored (FK-unresolvable): "
                  f"{sorted({t for _, t in deferred})[:8]}")

    info("savegame", f"Restored {restored} rows, {row_errors} row errors, "
                     f"{skipped_tables} skipped tables (checksum_ok={checksum_ok})")
    await Database.close()
    return {"ok": True, "restored_rows": restored, "row_errors": row_errors,
            "skipped_tables": skipped_tables, "checksum_ok": checksum_ok,
            "session_id": sid, "game_day": data["header"].get("game_day")}
