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
               "session_id": 3, "novel_id": "tkg-setia-kingdom",
               "checksum": "sha256-of-content"},
    "tables": { "<table>": [ {row}, ... ], ... }
  }

The header names the novel its session plays, so a file says which story it belongs to. The novel
lives on `sessions` alone and every scoped row inherits it through `session_id`.

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
import asyncio, hashlib, json, re, sys, time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, NamedTuple
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


#: Every maya_rp table and column name matches this shape (checked against information_schema).
_IDENT_RE = re.compile(r"[a-z_][a-z0-9_]*")


def _ident(name: str, known: set | None = None) -> str:
    """Validate one SQL identifier and return it double-quoted.

    Table names in an import come from the .sav file, and column names come from its row keys. Both
    are interpolated into SQL, so a crafted file with `x"; DROP ...` in a key ran as written.

    @param name - table or column name.
    @param known - when given, the name must be in this set (the live maya_rp table list).
    @returns the name wrapped in double quotes.
    @raises ValueError - the name has a quote or a non-identifier character, or is not in `known`.
    """
    if not isinstance(name, str) or not _IDENT_RE.fullmatch(name):
        raise ValueError(f"unsafe SQL identifier {name!r}: only [a-z0-9_] names are accepted")
    if known is not None and name not in known:
        raise ValueError(f"unknown maya_rp table {name!r}")
    return f'"{name}"'


class FkRef(NamedTuple):
    """One maya_rp foreign key. `on_delete` is pg_constraint.confdeltype:
    a = no action, r = restrict, c = cascade, n = set null, d = set default."""
    child: str
    parent: str
    columns: tuple
    ref_columns: tuple
    on_delete: str


class DetachStep(NamedTuple):
    """Detach statements for one FK. `update_sql` runs first; `delete_sql` runs only when the
    update fails (NOT NULL column). Both are scoped to rows that reference the wiped parent rows."""
    child: str
    columns: tuple
    update_sql: str
    delete_sql: str
    params: tuple


#: Delete actions the database applies itself when the parent rows go, scoped to those rows.
_DB_HANDLED_DELETE = {"c", "n", "d"}


class DetachRefused(RuntimeError):
    """A wipe would delete rows of a non-session table that a kept table still references.

    The wipe deletes a non-session-scoped parent whole, so detaching its children cannot be scoped to
    one session: it nulls or deletes the child rows of every session, frozen session 3 included.
    """

    def __init__(self, refs: list):
        self.refs = list(refs)
        edges = ", ".join(f"{r.child}.{'/'.join(r.columns)} -> {r.parent}" for r in self.refs[:8])
        more = "" if len(self.refs) <= 8 else f" (+{len(self.refs) - 8} more)"
        super().__init__(
            f"wipe refused before any write: {len(self.refs)} kept table FK(s) point at non-session "
            f"tables the wipe deletes whole, and detaching them would touch every session: "
            f"{edges}{more}. Restore with wipe=False (CLI: --keep-session).")


def _detach_plan(fk_rows: Iterable[FkRef], wipe_set: set, session_scoped_tables: set,
                 session_id: int) -> list[DetachStep]:
    """Plan the detach of kept tables from the rows a wipe deletes. Pure: no DB access.

    Incident: the detach loop ran `UPDATE child SET col=NULL` with no WHERE, and on a NOT NULL column
    fell back to `DELETE FROM child` with no WHERE. Restoring a session-5 file deleted every
    ship_armaments and fleet_members row, frozen session 3's ~109k included; both tables are partial,
    so the restore skipped them and the transaction committed the loss.

    @param fk_rows - every maya_rp FK, as FkRef.
    @param wipe_set - tables the wipe deletes from.
    @param session_scoped_tables - tables with a session_id column; the wipe deletes only `session_id`'s rows there.
    @param session_id - session being wiped; bound as $1 in every step.
    @returns one DetachStep per FK that needs a detach. CASCADE / SET NULL / SET DEFAULT children of a
        session-scoped parent get none: the database applies them to the deleted parent rows only.
    @raises DetachRefused - a kept table references a wiped parent that is not session-scoped.
    @raises ValueError - an identifier fails `_ident`.
    """
    steps: list[DetachStep] = []
    refused: list[FkRef] = []
    for fk in fk_rows:
        if fk.parent not in wipe_set or fk.child in wipe_set:
            continue
        if fk.parent not in session_scoped_tables:
            # Covers CASCADE too: the parent DELETE has no WHERE, so the cascade reaches every session.
            refused.append(fk)
            continue
        if fk.on_delete in _DB_HANDLED_DELETE:
            continue
        child, parent = _ident(fk.child), _ident(fk.parent)
        cols = [_ident(c) for c in fk.columns]
        refs = [_ident(c) for c in fk.ref_columns]
        lhs = cols[0] if len(cols) == 1 else "(" + ", ".join(cols) + ")"
        scope = (f"{lhs} IN (SELECT {', '.join(refs)} FROM maya_rp.{parent} "
                 f"WHERE session_id=$1)")
        sets = ", ".join(f"{c}=NULL" for c in cols)
        steps.append(DetachStep(
            child=fk.child, columns=tuple(fk.columns),
            update_sql=f"UPDATE maya_rp.{child} SET {sets} WHERE {scope}",
            delete_sql=f"DELETE FROM maya_rp.{child} WHERE {scope}",
            params=(session_id,)))
    if refused:
        raise DetachRefused(refused)
    return steps


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


async def _fk_refs() -> list[FkRef]:
    """Every maya_rp FK with its column lists (in key order) and delete action.

    @returns FkRef per constraint whose child and parent are both in maya_rp.
    """
    rows = await Database.fetch(
        "SELECT c1.relname AS child, c2.relname AS parent, k.confdeltype::text AS on_delete, "
        "(SELECT array_agg(a.attname ORDER BY u.ord) FROM unnest(k.conkey) WITH ORDINALITY "
        " AS u(attnum, ord) JOIN pg_attribute a ON a.attrelid = k.conrelid AND a.attnum = u.attnum) "
        " AS cols, "
        "(SELECT array_agg(a.attname ORDER BY u.ord) FROM unnest(k.confkey) WITH ORDINALITY "
        " AS u(attnum, ord) JOIN pg_attribute a ON a.attrelid = k.confrelid AND a.attnum = u.attnum) "
        " AS ref_cols "
        "FROM pg_constraint k "
        "JOIN pg_class c1 ON c1.oid = k.conrelid "
        "JOIN pg_class c2 ON c2.oid = k.confrelid "
        "JOIN pg_namespace n ON n.oid = c1.relnamespace "
        "JOIN pg_namespace n2 ON n2.oid = c2.relnamespace "
        "WHERE k.contype='f' AND n.nspname='maya_rp' AND n2.nspname='maya_rp'")
    return [FkRef(r["child"], r["parent"], tuple(r["cols"] or ()), tuple(r["ref_cols"] or ()),
                  str(r["on_delete"])) for r in rows]


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

    @param session_id - session to dump.
    @param out_dir - target directory; defaults to Config BACKUP_DIR.
    @returns path of the written .sav.
    @raises SaveIncomplete - when any table fails to read. Nothing is written in that case.
    @raises ValueError - the session does not exist.
    """
    # Close only a pool this call opened: the orchestrator exports in-process after every tick, and
    # the unconditional close shut its shared pool. Early raises skipped the close and leaked it.
    created = Database.pool is None
    await Database.init()
    try:
        return await _export(session_id, out_dir)
    finally:
        if created:
            await Database.close()


async def _export(session_id: int, out_dir: str | None) -> str:
    session_row = await Database.fetchrow(
        "SELECT id, game_day, novel_id FROM maya_rp.sessions WHERE id=$1", session_id)
    if session_row is None:
        # Every session-scoped table would come back empty, the file would still look like a
        # checkpoint, and the restore path trusts it. Refuse by name, the way an audit of a session
        # that does not exist is refused, rather than write a file that restores an empty campaign.
        raise ValueError(
            f"no session {session_id}: refusing to write a checkpoint of a campaign that does not exist")

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
        raise SaveIncomplete(failed)

    payload = {
        "header": {
            "format": FORMAT,
            "version": SAV_VERSION,
            "game_day": session_row["game_day"],
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            # The novel this campaign is canon for, read from the session row. A restore into another
            # novel is refused by default: the wipe merges two stories the engine keeps apart.
            "novel_id": session_row.get("novel_id"),
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


class SessionMismatch(RuntimeError):
    """A save file belongs to a different session than the one asked to restore it.

    The restore wipes the target session before it loads, and the rows it inserts keep their own
    `session_id`. So restoring session 3's file into session 5 deletes session 5 and then either
    conflicts on every primary key or writes session 3's rows back as themselves. Either way the
    caller asked for something other than what happens, and the difference is silent.
    """

    def __init__(self, file_session: int, requested: int):
        self.file_session = file_session
        self.requested = requested
        super().__init__(
            f"this save belongs to session {file_session}, but the restore targets session "
            f"{requested}. Pass allow_session_mismatch=True (CLI: --allow-session-mismatch) if that "
            f"is really what you want.")


class NovelMismatch(SessionMismatch):
    """A save belongs to a novel the target session does not play.

    `sessions.novel_id` is the one place a campaign names its novel, so a restore into another novel
    merges two stories the engine keeps apart. The guard also catches a file whose stored novel no
    longer matches the session it names, which is what a binding moved after the write leaves behind.

    A `SessionMismatch` subclass on purpose: a caller that refuses a foreign session refuses a foreign
    novel the same way, and `scripts/cli.py load` reports both through the one handler.
    """

    def __init__(self, file_novel: str, requested: int, target_novel: str):
        self.file_novel = file_novel
        self.requested = requested
        self.target_novel = target_novel
        RuntimeError.__init__(
            self,
            f"this save belongs to novel {file_novel!r}, but session {requested} plays "
            f"{target_novel!r}. Pass allow_novel_mismatch=True (CLI: --allow-novel-mismatch) if that "
            f"is really what you want.")


class RestoreIncomplete(RuntimeError):
    """Rows of a .sav could not be restored, so the whole import rolled back.

    The import used to log the leftovers and commit: the wipe stood, the rows it could not put back
    stayed gone, and the result still said ok True.
    """

    def __init__(self, failures: list[tuple[str, str]]):
        self.failures = list(failures)
        tables = sorted({t for t, _ in self.failures})
        causes = "; ".join(f"{t}: {c}" for t, c in self.failures[:3])
        super().__init__(
            f"{len(self.failures)} row(s) could not be restored, so nothing was committed "
            f"(tables: {', '.join(tables[:8])}). First causes: {causes}. "
            f"Pass allow_partial=True to commit the partial restore.")


async def _session_novel(session_id: int | None) -> str | None:
    """The novel one session plays, or None when the session has no row.

    @param session_id - a session id, or None.
    @returns the `novel_id` slug; None when the row is absent.
    """
    if session_id is None:
        return None
    row = await Database.fetchrow(
        "SELECT novel_id FROM maya_rp.sessions WHERE id=$1", int(session_id))
    return None if row is None else row.get("novel_id")


async def _refuse_novel_mismatch(header: dict, file_session, sid: int, allow: bool) -> None:
    """Refuse a file whose novel differs from the novel of the session it restores into.

    The file's novel is the header's when it carries one. A file written before the header carried a
    novel names none, so it resolves through its own `session_id`: that row is where the export came
    from, and refusing every checkpoint older than this change strands the backups it protects.
    A file and a target that name one session need no read while the file names no novel, because
    one row answers for both.

    @param header - the file's header.
    @param file_session - the session the file names; None when it names none.
    @param sid - the session the restore targets.
    @param allow - the caller accepted a cross-novel restore.
    @raises NovelMismatch - both novels are known and differ.
    """
    if allow:
        return
    file_novel = header.get("novel_id")
    if not file_novel:
        if file_session is not None and int(file_session) == int(sid):
            return
        file_novel = await _session_novel(file_session)
    target_novel = await _session_novel(sid)
    if file_novel and target_novel and str(file_novel) != str(target_novel):
        raise NovelMismatch(str(file_novel), int(sid), str(target_novel))


async def import_sav(path: str, session_id: int | None = None, wipe: bool = True,
                     allow_session_mismatch: bool = False, force: bool = False,
                     allow_partial: bool = False, allow_novel_mismatch: bool = False) -> dict:
    """Restore PG from a .sav file. wipe=True resets ALL current session/catalog
    tables to the snapshot (FK-safe ordered DELETE, no TRUNCATE CASCADE).

    Note: restoring a .sav produced before the 2026-08-14 fix will reset
    tables that were absent from that older partial snapshot — that is the
    correct full-reset semantic; keep a fresh export as your working save.

    @param path - .sav file.
    @param session_id - target session; defaults to the file's.
    @param wipe - delete the session's rows and the catalog tables before loading.
    @param allow_session_mismatch - restore another session's file on purpose.
    @param force - restore a file whose checksum does not match.
    @param allow_partial - commit even when rows could not be restored.
    @param allow_novel_mismatch - restore another novel's file on purpose.
    @returns {"ok": True, "restored_rows", ...}, or {"ok": False, "error"} for a file refused before any DB access.
    @raises SessionMismatch - the file names another session; NovelMismatch extends it for a foreign
    novel. Both refuse before any write.
    @raises DetachRefused - the wipe would reach other sessions' rows; nothing written.
    @raises RestoreIncomplete - rows could not be restored and allow_partial is False; rolled back.
    @raises ValueError - a table or column name in the file is not a safe known identifier; rolled back.
    """
    p = Path(path)
    if not p.exists():
        return {"ok": False, "error": f"not found: {path}"}
    data = json.loads(p.read_text())
    if data.get("header", {}).get("format") != FORMAT:
        return {"ok": False, "error": "not a tkg-sav file"}

    checksum_ok = _verify_checksum(data)

    file_session = data["header"].get("session_id")
    if session_id is not None and file_session is not None and int(session_id) != int(file_session):
        if not allow_session_mismatch:
            raise SessionMismatch(int(file_session), int(session_id))
        info("savegame", f"restoring session {file_session}'s file into session {session_id} on purpose")
    sid = session_id or data["header"]["session_id"]
    tables = data.get("tables", {})
    # A file written before the export learned to refuse carries `{"__error__": ...}` where a table
    # should be. Restoring it would wipe that table and leave it empty, so the restore refuses too.
    broken = {name: value.get("__error__") for name, value in tables.items()
              if isinstance(value, dict) and "__error__" in value}
    if broken:
        raise SaveIncomplete({name: str(err) for name, err in broken.items()})

    if not checksum_ok:
        # A mismatch used to log "proceeding anyway" and then wipe. A file that writes nothing
        # (no wipe, no rows) is harmless and still passes. A file with no checksum at all (written
        # before exports carried one, or by hand) cannot be shown altered: it warns and proceeds.
        writes = wipe or any(isinstance(v, list) and v for v in tables.values())
        if not data.get("header", {}).get("checksum"):
            info("savegame", f"WARNING: {p.name} carries no checksum, restoring it unverified")
        elif writes and not force:
            return {"ok": False, "error": f"checksum mismatch on {p.name}: refusing to restore a "
                                          f"file that changed after it was written. "
                                          f"Pass force=True to restore it anyway."}
        elif writes:
            info("savegame", f"WARNING: checksum mismatch on {p.name}, restoring under force=True")

    # Close only a pool this call opened: an in-process caller keeps its shared pool, and an
    # early raise no longer leaks one.
    created = Database.pool is None
    await Database.init()
    try:
        # Outside the transaction: a cross-novel file is refused with no row written, and the pool
        # this call opened still closes on the way out. The guard reads two session rows, the file's
        # and the target's; neither read is a write.
        await _refuse_novel_mismatch(data.get("header", {}), file_session, sid,
                                     allow_novel_mismatch)
        return await _restore(data, tables, sid, wipe, allow_partial, checksum_ok)
    finally:
        if created:
            await Database.close()


async def _restore(data: dict, tables: dict, sid: int, wipe: bool, allow_partial: bool,
                   checksum_ok: bool) -> dict:
    restored = 0
    row_errors = 0
    skipped_tables = 0
    sequences_reset = 0
    deferred: list[tuple[str, str, str]] = []   # (insert SQL, table, last error) awaiting parents
    # A table the file carries only in part must not be wiped and must not be restored: the wipe
    # would delete rows the file cannot put back, and the insert would leave the table holding only
    # what the file happens to carry. Session 3's 109,149 ship_armaments would have gone that way.
    # Read here, not inside the `wipe` branch: the restore skips these tables whether or not a wipe
    # runs, which is why `--keep-session` used to die with an UnboundLocalError on any real file.
    partial = set(data.get("header", {}).get("partial_tables") or [])
    if partial:
        info("savegame", f"restore leaves {len(partial)} partially carried table(s) untouched: "
                         + ", ".join(sorted(partial)[:6]))

    async with Database.transaction() as conn:
        all_tables, has_sid, vector_tables, fks = await _schema_inventory()
        # Table names and row keys come from the file and are interpolated into SQL: validate them
        # all before the first write.
        # A well-formed name the live schema lacks (a table from a newer or older build) is skipped and
        # counted, as before; a malformed name is refused.
        unknown_tables: set[str] = set()
        for t, rows in tables.items():
            if t in partial or not isinstance(rows, list) or not rows:
                continue
            if _ident(t) and t not in all_tables:
                unknown_tables.add(t)
                info("savegame", f"restore skip {t}: no such table in maya_rp")
                continue
            if isinstance(rows[0], dict):
                for c in rows[0].keys():
                    _ident(c)

        if wipe:
            session_scoped, global_tables = classify_tables(
                all_tables, has_sid, vector_tables, EXCLUDED_TABLES)
            session_set = set(session_scoped)
            wipe_set = ((set(session_scoped) | set(global_tables)) - {"sessions"}) - partial
            order = fk_wipe_order(wipe_set, fks)
            refs = await _fk_refs()
            # Tables left OUT of the wipe (excluded logs, vector/RAG tables, partial tables) can
            # still hold FKs into tables we are about to wipe — PostgreSQL then aborts the parent
            # DELETE (e.g. sessions.primary_partner_id -> characters). Planned before any write:
            # DetachRefused aborts with nothing touched.
            plan = _detach_plan(refs, wipe_set, session_set, sid)
            for step in plan:
                try:
                    async with conn.transaction():  # savepoint
                        await conn.execute(step.update_sql, *step.params)
                except Exception:
                    try:
                        async with conn.transaction():  # savepoint
                            await conn.execute(step.delete_sql, *step.params)
                    except Exception as e:
                        # the parent wipe below will surface any real blocker
                        error("savegame",
                              f"detach {step.child}.{'/'.join(step.columns)} skipped ({e})")
            # FK cycles (10 tables in maya_rp: characters -> territory ->
            # locations, clues -> characters, self-referencing heirs/prerequisites)
            # cannot be topologically ordered; Kahn parks them at the end and the
            # first DELETE then violates a parent FK. Break each cycle-internal
            # edge by NULLing the child column first. Both ends are in wipe_set, so an
            # unscoped UPDATE here only touches a table the wipe deletes whole.
            cycles = fk_cycle_members(wipe_set, fks)
            if cycles:
                info("savegame",
                     f"FK cycles: {len(cycles)} tables — breaking with NULLs")
            for fk in refs:
                if fk.child not in cycles or fk.parent not in cycles:
                    continue
                child = _ident(fk.child, all_tables)
                for col in fk.columns:
                    try:
                        async with conn.transaction():  # savepoint
                            if fk.child in has_sid:
                                await conn.execute(
                                    f"UPDATE maya_rp.{child} SET {_ident(col)}=NULL "
                                    f"WHERE session_id=$1", sid)
                            else:
                                await conn.execute(
                                    f"UPDATE maya_rp.{child} SET {_ident(col)}=NULL")
                    except Exception as e:
                        error("savegame", f"cycle break {fk.child}.{col} skipped ({e})")
            for t in order:
                if t == "sessions":
                    continue  # preserve the session row itself
                qt = _ident(t, all_tables)
                try:
                    if t in session_set:
                        await conn.execute(
                            f"DELETE FROM maya_rp.{qt} WHERE session_id=$1", sid)
                    else:
                        await conn.execute(f"DELETE FROM maya_rp.{qt}")
                except Exception as e:
                    error("savegame", f"wipe {t} failed (aborting restore): {e}")
                    raise  # no silent half-wipes — abort the transaction

        # restore in the .sav's stored (parents-first) order
        udts = await _column_udts(list(tables))
        gens = await _generated_columns(list(tables))
        with_id: list[str] = []   # restored tables whose `id` sequence may now trail max(id)
        for t, rows in tables.items():
            if t in partial or t in unknown_tables:
                # Same reason as the wipe: a table carried in part cannot be restored without
                # deleting what the file never had. A table the schema lacks has nowhere to land.
                skipped_tables += 1
                continue
            if not isinstance(rows, list) or not rows:
                continue
            if isinstance(rows[0], dict) and "__error__" in rows[0]:
                skipped_tables += 1
                info("savegame", f"restore skip {t}: exported with error {rows[0]['__error__']}")
                continue
            qt = _ident(t, all_tables)
            cols = [c for c in rows[0].keys() if c not in gens.get(t, set())]
            if "id" in cols:
                with_id.append(t)
            # Type-aware encoding: ARRAY columns need an ARRAY literal, jsonb
            # columns need ::jsonb, everything else stays a scalar. The old
            # blanket `::jsonb` broke all 8 ARRAY columns.
            types = udts.get(t, {})
            conflict = _conflict_clause(t, cols)

            def _sql(row: dict, _t=qt, _cols=cols, _types=types,
                     _conflict=conflict) -> str:
                return _insert_sql(_t, _cols, row, _types, _conflict)

            # One savepoint per table: a single bad row must NOT abort the outer
            # transaction. On failure the table is retried row-by-row under its own
            # savepoint so the good rows land; leftovers decide commit vs rollback below.
            try:
                async with conn.transaction():
                    for row in rows:
                        await conn.execute(_sql(row))
                # Counted after the savepoint commits. The counter used to rise inside the loop, so a
                # batch that failed on its last row kept every row before it in the total although the
                # savepoint rolled them back, and the row-by-row retry below then counted them again.
                restored += len(rows)
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
                        deferred.append((_sql(row), t, str(e2)))
                        if row_errors <= 10:
                            error("savegame", f"restore row {t} failed: {e2}")

        # Deferred pass: the .sav's stored order is parents-first, but FK cycles
        # (characters ⇄ territory ⇄ locations ⇄ clues) can't be ordered at all and
        # a child row may legitimately fail before its parent lands. Retry the
        # leftovers until a round makes no progress.
        for _round in range(4):
            if not deferred:
                break
            still: list[tuple[str, str, str]] = []
            for sql, tbl, _err in deferred:
                try:
                    async with conn.transaction():  # savepoint
                        await conn.execute(sql)
                    restored += 1
                    row_errors -= 1
                except Exception as e:
                    still.append((sql, tbl, str(e)))
            if len(still) == len(deferred):
                deferred = still
                break  # no progress — remaining rows are genuinely unresolvable
            info("savegame",
                 f"deferred pass {_round + 1}: {len(deferred) - len(still)} rows landed, "
                 f"{len(still)} still pending")
            deferred = still
        if deferred:
            error("savegame",
                  f"{len(deferred)} rows could not be restored (FK-unresolvable): "
                  f"{sorted({t for _, t, _ in deferred})[:8]}")
            if not allow_partial:
                # Raised inside the transaction: the wipe rolls back with the inserts. Committing
                # here kept the wipe and lost every row listed above, behind ok True.
                raise RestoreIncomplete([(t, err) for _, t, err in deferred])

        # Explicit ids leave each serial sequence where it was; the next INSERT then collides with
        # a restored row. Skip tables whose `id` has no sequence (ooc_rules.id is text).
        for t in with_id:
            qt = _ident(t, all_tables)
            seq = await conn.fetchval("SELECT pg_get_serial_sequence($1, 'id')", f"maya_rp.{qt}")
            if seq:
                await conn.execute(
                    f"SELECT setval(CAST($1::text AS regclass), m) "
                    f"FROM (SELECT MAX(id) AS m FROM maya_rp.{qt}) x WHERE m IS NOT NULL", seq)
                sequences_reset += 1

    info("savegame", f"Restored {restored} rows, {row_errors} row errors, "
                     f"{skipped_tables} skipped tables, {sequences_reset} sequences reset "
                     f"(checksum_ok={checksum_ok})")
    return {"ok": True, "restored_rows": restored, "row_errors": row_errors,
            "skipped_tables": skipped_tables, "sequences_reset": sequences_reset,
            "checksum_ok": checksum_ok,
            "session_id": sid, "game_day": data["header"].get("game_day")}
