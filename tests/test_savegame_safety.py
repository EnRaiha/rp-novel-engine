"""A restore must not reach rows it cannot put back.

Incident: `import_sav` detached kept tables from the wipe with `UPDATE child SET col=NULL` (no WHERE)
and, on a NOT NULL column, `DELETE FROM child` (no WHERE). A session-5 restore deleted every
ship_armaments and fleet_members row, frozen session 3's ~109k included, and committed.

No test here touches a database. The planner is pure; every import/export test replaces
`core.savegame.Database` with `FakeDatabase`, whose connection records SQL and executes nothing.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys
from contextlib import asynccontextmanager

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import savegame  # noqa: E402

#: An UPDATE or DELETE with no WHERE: the statement shape that wiped session 3.
UNSCOPED = re.compile(
    r"^\s*(?:UPDATE\s+\S+\s+SET\s+(?:(?!\bWHERE\b).)*|DELETE\s+FROM\s+\S+\s*)$", re.S | re.I)


def _fk(child, parent, col, on_delete="a", ref="id"):
    return savegame.FkRef(child, parent, (col,), (ref,), on_delete)


# ─── Stub database ──────────────────────────────────────────────────────

class _Savepoint:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeConn:
    """Records every statement. Executes nothing."""

    def __init__(self, fail_inserts: bool = False):
        self.executed: list[str] = []
        self.fail_inserts = fail_inserts

    def transaction(self):
        return _Savepoint()

    async def execute(self, sql, *args):
        self.executed.append(sql)
        if self.fail_inserts and sql.lstrip().upper().startswith("INSERT"):
            raise RuntimeError("violates foreign key constraint")
        return "OK"

    async def fetchval(self, sql, *args):
        if "pg_get_serial_sequence" in sql:
            return "maya_rp.ships_id_seq"
        return None


class FakeDatabase:
    """Stands in for core.db.Database: pool bookkeeping, canned schema reads, recorded transaction."""

    def __init__(self, *, conn: FakeConn | None = None, pool=None, tables=("ships", "weapons"),
                 session_tables=("ships",), fk_refs=(), fetch_error: Exception | None = None,
                 session_row=None):
        self.pool = pool
        self.conn = conn or FakeConn()
        self.tables = tables
        self.session_tables = session_tables
        self.fk_refs = fk_refs
        self.fetch_error = fetch_error
        self.session_row = session_row
        self.inits = 0
        self.closes = 0
        self.transactions = 0
        self.transaction_error: BaseException | None = None

    async def init(self):
        self.inits += 1
        if self.pool is None:
            self.pool = object()
        return self.pool

    async def close(self):
        self.closes += 1
        self.pool = None

    async def fetchrow(self, sql, *args):
        return self.session_row

    async def fetch(self, sql, *args):
        if self.fetch_error is not None:
            raise self.fetch_error
        if "pg_tables" in sql:
            return [{"t": t} for t in self.tables]
        if "column_name='session_id'" in sql:
            return [{"table_name": t} for t in self.session_tables]
        if "confdeltype" in sql:
            return [{"child": r.child, "parent": r.parent, "on_delete": r.on_delete,
                     "cols": list(r.columns), "ref_cols": list(r.ref_columns)} for r in self.fk_refs]
        if "contype='f'" in sql:
            return [{"child": r.child, "parent": r.parent} for r in self.fk_refs]
        return []

    @asynccontextmanager
    async def transaction(self):
        self.transactions += 1
        try:
            yield self.conn
        except BaseException as exc:
            self.transaction_error = exc
            raise


def _write_sav(tmp_path, tables: dict, *, session_id: int = 5, checksum: str | None = None,
               partial=()) -> str:
    """Write a .sav the way export_sav does, checksum included unless overridden."""
    payload = {"header": {"format": savegame.FORMAT, "version": savegame.SAV_VERSION,
                          "game_day": 1, "session_id": session_id,
                          "partial_tables": list(partial)},
               "tables": tables}
    content = json.dumps(payload, default=savegame._json_default, indent=1)
    payload["header"]["checksum"] = checksum or hashlib.sha256(content.encode()).hexdigest()[:16]
    path = tmp_path / "save.sav"
    path.write_text(json.dumps(payload, default=savegame._json_default, indent=1))
    return str(path)


# ─── S1: detach plan ────────────────────────────────────────────────────

class TestDetachPlan:
    """The planner decides every detach statement before the first write, with no DB access."""

    def test_a_cascade_child_of_a_session_parent_gets_no_statement(self):
        """ship_armaments.ship_id is ON DELETE CASCADE in the live schema. The old loop still ran
        `UPDATE ship_armaments SET ship_id=NULL`, failed on NOT NULL, and fell back to an unscoped
        DELETE. The database already removes exactly the wiped ships' armaments."""
        plan = savegame._detach_plan([_fk("ship_armaments", "ships", "ship_id", "c")],
                                     wipe_set={"ships"}, session_scoped_tables={"ships"},
                                     session_id=5)
        assert plan == [], f"a CASCADE child must be left to the database, got {plan}"

    def test_set_null_and_set_default_children_get_no_statement(self):
        """The database applies SET NULL / SET DEFAULT to the deleted parent rows only."""
        plan = savegame._detach_plan(
            [_fk("colonization_projects", "planets", "planet_id", "n"),
             _fk("yard_capacity", "territory", "territory_id", "d")],
            wipe_set={"planets", "territory"}, session_scoped_tables={"planets", "territory"},
            session_id=5)
        assert plan == [], f"SET NULL / SET DEFAULT children need no detach, got {plan}"

    def test_a_no_action_child_is_scoped_to_the_wiped_parent_rows(self):
        """A NOT NULL, NO ACTION child of a session-scoped parent: the old fallback was
        `DELETE FROM maya_rp.combat_stats` with no WHERE, every session's rows gone."""
        plan = savegame._detach_plan([_fk("combat_stats", "ships", "ship_id", "a")],
                                     wipe_set={"ships"}, session_scoped_tables={"ships"},
                                     session_id=5)
        assert len(plan) == 1, f"one FK, one step expected, got {plan}"
        step = plan[0]
        assert step.params == (5,), f"session id must be bound as $1, got {step.params}"
        for sql in (step.update_sql, step.delete_sql):
            assert not UNSCOPED.match(sql), f"unscoped statement planned: {sql}"
            assert " WHERE " in sql, f"statement has no WHERE: {sql}"
            assert 'IN (SELECT "id" FROM maya_rp."ships" WHERE session_id=$1)' in sql, \
                f"statement not scoped to the wiped ships rows: {sql}"
        assert step.update_sql.startswith('UPDATE maya_rp."combat_stats" SET "ship_id"=NULL'), \
            step.update_sql
        assert step.delete_sql.startswith('DELETE FROM maya_rp."combat_stats"'), step.delete_sql

    def test_the_referenced_column_is_used_not_assumed_to_be_id(self):
        """ooc_rules.session_id references ooc_system_state(session_id), not id."""
        plan = savegame._detach_plan(
            [_fk("ooc_rules", "ooc_system_state", "session_id", "a", ref="session_id")],
            wipe_set={"ooc_system_state"}, session_scoped_tables={"ooc_system_state"},
            session_id=5)
        assert 'SELECT "session_id" FROM maya_rp."ooc_system_state"' in plan[0].delete_sql, \
            plan[0].delete_sql

    def test_children_inside_the_wipe_and_parents_outside_it_are_ignored(self):
        """Only kept children of wiped parents need a detach."""
        plan = savegame._detach_plan(
            [_fk("crew_roster", "ships", "ship_id"), _fk("combat_stats", "sectors", "sector_id")],
            wipe_set={"ships", "crew_roster"}, session_scoped_tables={"ships", "crew_roster"},
            session_id=5)
        assert plan == [], f"no kept child of a wiped parent here, got {plan}"

    def test_a_non_session_parent_refuses_the_wipe(self):
        """weapons has no session_id, so the wipe deletes it whole. Detaching
        ship_armaments.weapon_id cannot be scoped: the old loop nulled or deleted every session's
        armaments. The planner refuses instead."""
        with pytest.raises(savegame.DetachRefused) as caught:
            savegame._detach_plan([_fk("ship_armaments", "weapons", "weapon_id", "a")],
                                  wipe_set={"weapons", "ships"}, session_scoped_tables={"ships"},
                                  session_id=5)
        assert "ship_armaments.weapon_id -> weapons" in str(caught.value), str(caught.value)

    def test_a_cascade_from_a_non_session_parent_refuses_too(self):
        """territory_resources.resource_id cascades from strategic_resources. A whole-table delete
        of the parent cascades into every session's territory_resources."""
        with pytest.raises(savegame.DetachRefused):
            savegame._detach_plan(
                [_fk("territory_resources", "strategic_resources", "resource_id", "c")],
                wipe_set={"strategic_resources"}, session_scoped_tables=set(), session_id=5)


class TestIdentifiers:
    """Table names and row keys from a .sav are interpolated into SQL."""

    def test_a_name_with_a_quote_is_rejected(self):
        with pytest.raises(ValueError):
            savegame._ident('ships"; DROP TABLE maya_rp.sessions; --')

    def test_a_name_outside_the_known_tables_is_rejected(self):
        with pytest.raises(ValueError):
            savegame._ident("not_a_table", {"ships"})

    def test_a_valid_name_comes_back_quoted(self):
        assert savegame._ident("ship_armaments", {"ship_armaments"}) == '"ship_armaments"'

    def test_the_planner_rejects_a_quoted_child(self):
        with pytest.raises(ValueError):
            savegame._detach_plan([_fk('x"y', "ships", "ship_id")], wipe_set={"ships"},
                                  session_scoped_tables={"ships"}, session_id=5)


# ─── S1 end to end on the stub ──────────────────────────────────────────

class TestWipeRefusal:
    async def test_a_wipe_that_would_reach_other_sessions_writes_nothing(self, tmp_path,
                                                                         monkeypatch):
        """Before: the kept child's unscoped UPDATE/DELETE ran, then the restore committed.
        After: DetachRefused before the first statement, inside the transaction."""
        db = FakeDatabase(tables=("ships", "weapons", "ship_armaments"),
                          fk_refs=(_fk("ship_armaments", "weapons", "weapon_id", "a"),))
        monkeypatch.setattr(savegame, "Database", db)
        path = _write_sav(tmp_path, {"ships": [], "weapons": []}, partial=["ship_armaments"])
        with pytest.raises(savegame.DetachRefused):
            await savegame.import_sav(path, session_id=5, wipe=True)
        assert db.conn.executed == [], f"no statement may run before the refusal: {db.conn.executed}"
        assert isinstance(db.transaction_error, savegame.DetachRefused), \
            "the refusal must propagate through the transaction so it rolls back"

    async def test_a_crafted_table_name_is_refused_before_any_write(self, tmp_path, monkeypatch):
        """Before: the name went into `INSERT INTO maya_rp.{t}` as written."""
        db = FakeDatabase()
        monkeypatch.setattr(savegame, "Database", db)
        path = _write_sav(tmp_path, {'ships"; DROP TABLE maya_rp.sessions; --': [{"id": 1}]})
        with pytest.raises(ValueError):
            await savegame.import_sav(path, session_id=5, wipe=False)
        assert db.conn.executed == [], f"nothing may run for a crafted name: {db.conn.executed}"


# ─── S2: leftovers roll the import back ─────────────────────────────────

class TestRestoreIncomplete:
    async def test_leftover_rows_roll_the_whole_import_back(self, tmp_path, monkeypatch):
        """Before: the leftovers were logged, the transaction committed, and the result said
        ok True with the wipe kept and the rows gone."""
        db = FakeDatabase(conn=FakeConn(fail_inserts=True))
        monkeypatch.setattr(savegame, "Database", db)
        path = _write_sav(tmp_path, {"ships": [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]})
        with pytest.raises(savegame.RestoreIncomplete) as caught:
            await savegame.import_sav(path, session_id=5, wipe=False)
        assert "2 row(s)" in str(caught.value), str(caught.value)
        assert "foreign key" in str(caught.value), "the first cause must be named"
        assert isinstance(db.transaction_error, savegame.RestoreIncomplete), \
            "the error must be raised inside the transaction so it rolls back"

    async def test_allow_partial_commits_on_purpose(self, tmp_path, monkeypatch):
        db = FakeDatabase(conn=FakeConn(fail_inserts=True))
        monkeypatch.setattr(savegame, "Database", db)
        path = _write_sav(tmp_path, {"ships": [{"id": 1, "name": "a"}]})
        result = await savegame.import_sav(path, session_id=5, wipe=False, allow_partial=True)
        assert result["ok"] and result["row_errors"] == 1, result
        assert db.transaction_error is None, "allow_partial must commit"


# ─── S7: pool lifecycle ─────────────────────────────────────────────────

class TestPoolLifecycle:
    async def test_import_closes_its_own_pool_on_an_early_error(self, tmp_path, monkeypatch):
        """Before: an exception after Database.init() skipped the close and leaked the pool."""
        db = FakeDatabase(fetch_error=RuntimeError("connection reset"))
        monkeypatch.setattr(savegame, "Database", db)
        path = _write_sav(tmp_path, {"ships": [{"id": 1}]})
        with pytest.raises(RuntimeError, match="connection reset"):
            await savegame.import_sav(path, session_id=5, wipe=False)
        assert db.closes == 1, f"the pool this call opened must be closed, closes={db.closes}"

    async def test_import_leaves_a_callers_pool_open(self, tmp_path, monkeypatch):
        """Before: success closed the shared pool of an in-process caller."""
        db = FakeDatabase(pool=object())
        monkeypatch.setattr(savegame, "Database", db)
        path = _write_sav(tmp_path, {"ships": [{"id": 1}]})
        result = await savegame.import_sav(path, session_id=5, wipe=False)
        assert result["ok"], result
        assert db.closes == 0, f"a pool this call did not open must stay open, closes={db.closes}"

    async def test_export_closes_its_own_pool_on_an_early_error(self, tmp_path, monkeypatch):
        """Before: a failing schema read after init raised past the close."""
        db = FakeDatabase(session_row={"id": 5, "game_day": 1},
                          fetch_error=RuntimeError("connection reset"))
        monkeypatch.setattr(savegame, "Database", db)
        with pytest.raises(RuntimeError, match="connection reset"):
            await savegame.export_sav(session_id=5, out_dir=str(tmp_path))
        assert db.closes == 1, f"the pool this call opened must be closed, closes={db.closes}"

    async def test_export_leaves_a_callers_pool_open(self, tmp_path, monkeypatch):
        """The orchestrator exports after every tick on its own pool; the refusal closed it."""
        db = FakeDatabase(pool=object(), session_row=None)
        monkeypatch.setattr(savegame, "Database", db)
        with pytest.raises(ValueError):
            await savegame.export_sav(session_id=5, out_dir=str(tmp_path))
        assert db.closes == 0, f"a pool this call did not open must stay open, closes={db.closes}"


# ─── S8: checksum and sequences ─────────────────────────────────────────

class TestChecksum:
    async def test_a_mismatch_refuses_without_force(self, tmp_path, monkeypatch):
        """Before: "proceeding anyway", then the wipe."""
        db = FakeDatabase()
        monkeypatch.setattr(savegame, "Database", db)
        path = _write_sav(tmp_path, {"ships": [{"id": 1}]}, checksum="0000000000000000")
        result = await savegame.import_sav(path, session_id=5, wipe=True)
        assert result["ok"] is False and "checksum" in result["error"], result
        assert db.transactions == 0 and db.conn.executed == [], \
            "a refused file must not open a transaction"

    async def test_force_restores_a_mismatched_file(self, tmp_path, monkeypatch):
        db = FakeDatabase()
        monkeypatch.setattr(savegame, "Database", db)
        path = _write_sav(tmp_path, {"ships": [{"id": 1}]}, checksum="0000000000000000")
        result = await savegame.import_sav(path, session_id=5, wipe=False, force=True)
        assert result["ok"] and result["checksum_ok"] is False, result


class TestSequences:
    async def test_restored_ids_advance_the_serial_sequence(self, tmp_path, monkeypatch):
        """Before: explicit ids left ships_id_seq behind max(id); the next INSERT collided."""
        db = FakeDatabase()
        monkeypatch.setattr(savegame, "Database", db)
        path = _write_sav(tmp_path, {"ships": [{"id": 7}]})
        result = await savegame.import_sav(path, session_id=5, wipe=False)
        setvals = [s for s in db.conn.executed if "setval" in s]
        assert setvals and 'maya_rp."ships"' in setvals[0], \
            f"no setval for ships after restore: {db.conn.executed}"
        assert result["sequences_reset"] == 1, result
