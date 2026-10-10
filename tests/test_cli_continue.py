"""`cli.py continue "<novel title>"` and `cli.py clear`.

Every test here stubs `Database`, so no statement reaches the live campaign database and the nine
play-state tables are never deleted. The arc file is a temp path in every test, because a successful
`continue` writes it: the autouse fixture below applies before the CLI module runs, so even the red
proof against the unfixed tree cannot move the live arc.

`clear --yes` runs against a fake transaction that holds the session's rows and applies every
statement to them. The assertion is the scope itself: the nine play-state tables, and one UPDATE that
releases the `roll_history` reference to `events`, nothing else. A dry run that deletes, or an export
failure that still deletes, fails here rather than in the live database.

One test reaches the server: the `roll_history.context_event_id` release, whose failure mode is a
foreign key violation and cannot be proved against a stub alone. It writes only inside its own
`scratch_campaign`, and it stubs the export.

Reading: `main/reference/rp-loadout.md` section 3 names `cli.py status` as the engine-state line, so
the status headline `continue` prints is the same print `cmd_status` makes.
"""
from __future__ import annotations

import asyncio
import contextlib
import io
import re

import pytest

from core import session
from core.db import Database
from scripts import cli

#: The statement `clear` must run before it deletes `events`. Roll rows carry the reference; the
#: events they name are what `clear` removes, so the column is what gives way.
CLEAR_REFERENCE_SQL = ("UPDATE maya_rp.roll_history SET context_event_id = NULL "
                       "WHERE session_id = $1")


# ── stubs ────────────────────────────────────────────────────────────────────────────────────────

class FakeNovels:
    """The `novels` reads of `continue`, answered by one tagged row each."""

    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []
        self.exact: list = []
        self.prefix: list = []
        self.listed: list = []
        self.by_id: list = []
        self.successor: list = []

    async def __call__(self, sql, *args):
        self.calls.append((sql, args))
        flat = " ".join(sql.split())
        if "lower(title) = lower($1)" in flat:
            return self.exact
        if "title ILIKE $1" in flat:
            return self.prefix
        if "FROM maya_rp.novels n LEFT JOIN" in flat:
            return self.listed
        if "WHERE novel_id = $1" in flat:
            return self.by_id
        if "WHERE supersedes = $1" in flat:
            return self.successor
        raise AssertionError(f"unexpected novels read: {flat}")


class FakeSessions:
    """The `sessions` reads of `continue`, answered by one tagged row each."""

    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []
        self.playing: list = []
        self.name = "scratch"

    async def __call__(self, sql, *args):
        self.calls.append((sql, args))
        flat = " ".join(sql.split())
        if "s.novel_id = $1" in flat:
            return self.playing
        if "victory_tracking" in flat:
            return {"progress": 42.0}
        if "SELECT name, status FROM sessions WHERE id=$1" in flat:
            return {"name": self.name, "status": "active"}
        if "SELECT credits, alloys, fuel" in flat:
            return {"credits": 1234, "alloys": 56, "fuel": 7}
        raise AssertionError(f"unexpected sessions read: {flat}")


class FakeCount:
    """The reads whose answer is one number: `sessions.game_day`, ship and territory counts, rows."""

    def __init__(self, values):
        self.values = values
        self.calls: list[tuple[str, tuple]] = []

    async def __call__(self, sql, *args):
        self.calls.append((sql, args))
        flat = " ".join(sql.split())
        for table, count in self.values.items():
            if f'FROM maya_rp."{table}"' in flat:
                return count
        if "SELECT COUNT(*) FROM ships" in flat or "territory" in flat:
            return 0
        return 3


class FakeDatabase:
    """`Database` with every reader stubbed and every writer refused.

    `continue` must never write a row, so a write arriving here is a defect and raises before it can
    reach the pool. `clear` writes only through its transaction connection, which is `ClearConnection`.

    A stub reader answers a `fetchrow` with one dict. A list is accepted and reduced to its first row,
    so a reader written for `fetch` reads correctly through both.
    """

    def __init__(self, novels, sessions, count):
        self._novels, self._sessions, self._count = novels, sessions, count
        self.counts: dict[str, int] = {}
        self.writes: list[tuple[str, tuple]] = []
        self.opened = 0
        self.closed = 0

    async def init(self):
        self.opened += 1

    async def close(self):
        self.closed += 1

    @staticmethod
    def _one(row):
        if isinstance(row, list):
            return row[0] if row else None
        return row

    async def fetch(self, sql, *args):
        flat = " ".join(sql.split())
        if "FROM maya_rp.novels" in flat:
            return await self._novels(sql, *args)
        if "sessions" in flat:
            return await self._sessions(sql, *args)
        raise AssertionError(f"unexpected fetch: {flat}")

    async def fetchrow(self, sql, *args):
        flat = " ".join(sql.split())
        if "FROM maya_rp.novels" in flat:
            return self._one(await self._novels(sql, *args))
        if "victory_tracking" in flat:
            return self._one(await self._sessions(sql, *args))
        if "sessions" in flat:
            return self._one(await self._sessions(sql, *args))
        # The rest of the status headline (`resources`, and whatever it gains later) answers empty:
        # this file proves the novel resolution and the arc switch, not the headline's own reads.
        return {}

    async def fetchval(self, sql, *args):
        return await self._count(sql, *args)

    async def execute(self, sql, *args):
        self.writes.append((sql, args))
        raise AssertionError(f"an unexpected write reached Database: {' '.join(sql.split())}")

    def transaction(self):
        """`clear` replaces this with `FakeTx`; any other verb that opens one is a defect here."""
        raise AssertionError("a transaction was opened without a stub")


class FakeTx:
    """`Database.transaction()` yielding the recording connection."""

    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


class ClearConnection:
    """The connection `clear` deletes through, holding the session's rows the way Postgres holds them.

    `execute` is a small Postgres: it parses the table and the bound session out of every DELETE and
    UPDATE, applies it to `rows`, and raises where the server would. The one constraint modelled is
    the one that aborts a real `clear`: `maya_rp.roll_history.context_event_id` references
    `events(id)` with NO ACTION, so deleting an `events` row a roll row still names is a foreign key
    violation. A stub that only recorded statements cannot tell the two orders apart.

    The SQL is read from a normalised copy: the statement text itself stays verbatim in `sql`.
    """

    _SESSION = re.compile(r"session_id\s*=\s*\$1")
    _CLEAR_REFERENCE = re.compile(
        r"^\s*UPDATE\s+(?:\w+\.)?\"?roll_history\"?\s+SET\s+context_event_id\s*=\s*NULL\s+WHERE\s+")
    _EVENTS = re.compile(r"^\s*DELETE\s+FROM\s+(?:\w+\.)?\"?events\"?\s+WHERE\s+")

    def __init__(self, deleted: int, rows=None):
        self.deleted = deleted
        #: `(table, id, context_event_id)` for every row the database logically holds.
        self.rows = list(rows or [])
        self.sql: list[str] = []
        self.tables: list[str] = []
        self.deletes: list[str] = []

    async def execute(self, sql, *args):
        flat = " ".join(sql.split())
        self.sql.append(flat)
        match = cli._DELETE_FROM.match(sql)
        if match:
            self.tables.append(match.group(1))
            self.deletes.append(flat)
        self._apply(flat, args)
        return f"DELETE {self.deleted}"

    def _apply(self, flat, args) -> None:
        """Apply one statement to `rows`, raising where Postgres would."""
        session = args[0] if args else None
        if self._EVENTS.match(flat) and self._SESSION.search(flat):
            # `row[2]` is the reference a roll row carries: its own id proves nothing.
            named = {row[2] for row in self.rows
                     if row[0] == "roll_history" and row[2] is not None}
            hit = sorted(named & {row[1] for row in self.rows if row[0] == "events"})
            if hit:
                raise AssertionError(
                    f"foreign key violation: {len(hit)} roll_history row(s) still name event(s) "
                    f"{hit} in session {session}, so the delete of this transaction fails and "
                    f"nothing is removed")
            self.rows = [row for row in self.rows if row[0] != "events"]
            return
        if self._CLEAR_REFERENCE.match(flat) and self._SESSION.search(flat):
            self.rows = [(table, id_, None if table == "roll_history" else event_id)
                         for table, id_, event_id in self.rows]
            return
        if match := cli._DELETE_FROM.match(flat):
            if self._SESSION.search(flat):
                table = match.group(1).strip('"')
                self.rows = [row for row in self.rows if row[0] != table]
            return


# ── fixtures ─────────────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def state_dir(tmp_path, monkeypatch):
    """A private arc file and no RP_SESSION, for every test in this file.

    Autouse on purpose: it must apply before the CLI can run at all, including on the unfixed tree
    where `continue` does not exist yet.
    """
    monkeypatch.setattr(session, "ACTIVE_ARC", tmp_path / "active_arc")
    monkeypatch.setattr(session, "FROZEN", tmp_path / "frozen_sessions")
    monkeypatch.setattr(session, "_maintenance_active", lambda: False)
    monkeypatch.delenv("RP_SESSION", raising=False)
    return tmp_path


@pytest.fixture
def fake_db(monkeypatch):
    """Install the stubs on the CLI's `Database`, and hand back the reader they answer through."""
    novels, sessions, count = FakeNovels(), FakeSessions(), FakeCount({})
    db = FakeDatabase(novels, sessions, count)
    monkeypatch.setattr(cli, "Database", db)
    return db


def _arm_clear(monkeypatch, fake_db, argv, explicit, deleted: int = 0, export=None, rows=None):
    """Install the clear stubs, hold `EXPLICIT_SESSION` for one call, and capture both streams.

    `EXPLICIT_SESSION` is read at call time, so it is put back by hand. The refusal message is the
    assertion in three of these tests, so `stderr` is captured at the source rather than through
    `capsys`.

    @param rows - the session's rows as `(table, id, context_event_id)`; the connection applies every
        statement to them, so a delete the server would refuse raises here.
    @returns `(connection, export_calls, stdout, stderr, exit code)`.
    """
    conn = ClearConnection(deleted, rows)
    calls: list[tuple[str, tuple]] = []
    out, errors = io.StringIO(), io.StringIO()

    async def fake_export(session_id, out_dir=None):
        return "/tmp/backup/tkg.sav"

    inner = export if export is not None else fake_export

    async def recording_export(session_id, out_dir=None):
        calls.append(("export", (session_id,)))
        return await inner(session_id, out_dir)

    monkeypatch.setattr(cli.Database, "transaction", lambda: FakeTx(conn))
    monkeypatch.setattr("core.savegame.export_sav", recording_export)
    fake_db._count.values = fake_db.counts
    before, cli.EXPLICIT_SESSION = cli.EXPLICIT_SESSION, explicit
    own_argv = cli.sys.argv
    cli.sys.argv = ["cli.py", *argv]
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(errors):
            asyncio.run(cli.cmd_clear())
    except SystemExit as exc:
        code = exc.code
    else:
        code = None
    finally:
        cli.EXPLICIT_SESSION = before
        cli.sys.argv = own_argv
    return conn, calls, out.getvalue(), errors.getvalue(), code


def _raising_export():
    """An export that fails, for the abort arm."""
    async def export(session_id, out_dir=None):
        raise RuntimeError("no space left on device")

    return export


# ── continue: the novel resolves ─────────────────────────────────────────────────────────────────

def test_continue_writes_the_arc_and_prints_the_session(fake_db, state_dir, capsys):
    """The whole change in one call: the arc moves, and the headline names the novel."""
    fake_db._novels.exact = [{"novel_id": "tkg-the-sunrise", "title": "TKG — Arc I: The Sunrise"}]
    fake_db._novels.by_id = [{"novel_id": "tkg-the-sunrise", "title": "TKG — Arc I: The Sunrise",
                              "status": "active", "supersedes": "tkg-prequel",
                              "adventures_dir": "adventures/tkg-arc1-restart"}]
    fake_db._sessions.playing = [{
        "id": 918, "name": "Sunrise scratch", "status": "active", "game_day": 34,
        "story_path": "/home/maya/Bumi-Hijau/adventures/tkg-arc1-restart/story.md",
        "novel_id": "tkg-the-sunrise"}]
    fake_db._sessions.name = "Sunrise scratch"
    cli.sys.argv = ["cli.py", "continue", "TKG — Arc I: The Sunrise"]
    asyncio.run(cli.cmd_continue())

    assert (state_dir / "active_arc").read_text().strip() == "918"
    out = capsys.readouterr().out
    assert "continued: TKG — Arc I: The Sunrise (tkg-the-sunrise) → session 918" in out
    assert "Game day:    34" in out
    assert "tkg-arc1-restart/story.md" in out
    assert "cli.py status" in out
    assert not fake_db.writes


def test_continue_takes_a_unique_prefix(fake_db, state_dir, capsys):
    fake_db._novels.prefix = [{"novel_id": "tkg-setia-kingdom", "title": "TKG Setia Kingdom"}]
    fake_db._novels.by_id = [{"novel_id": "tkg-setia-kingdom", "title": "TKG Setia Kingdom",
                              "status": "active", "supersedes": None,
                              "adventures_dir": "adventures/tkg"}]
    fake_db._sessions.playing = [{"id": 918, "name": "Setia scratch", "status": "active",
                                  "game_day": 2253, "story_path": None,
                                  "novel_id": "tkg-setia-kingdom"}]
    fake_db._sessions.name = "Setia scratch"
    cli.sys.argv = ["cli.py", "continue", "TKG Setia"]
    asyncio.run(cli.cmd_continue())

    assert (state_dir / "active_arc").read_text().strip() == "918"
    out = capsys.readouterr().out
    assert "session 918" in out
    # No `story_path`, so the brief falls back to the novel's own directory.
    assert "adventures/tkg/story.md" in out


def test_continue_lists_the_candidates_when_a_prefix_matches_several(fake_db, state_dir, capsys):
    fake_db._novels.prefix = [{"novel_id": "tkg-prequel", "title": "TKG Prequel"},
                              {"novel_id": "tkg-setia-kingdom", "title": "TKG Setia Kingdom"},
                              {"novel_id": "tkg-the-sunrise", "title": "TKG — Arc I: The Sunrise"}]
    cli.sys.argv = ["cli.py", "continue", "TKG"]
    with pytest.raises(SystemExit) as raised:
        asyncio.run(cli.cmd_continue())

    assert raised.value.code == 1
    err = capsys.readouterr().err
    assert "candidates" in err
    for title in ("TKG Setia Kingdom", "TKG Prequel", "TKG — Arc I: The Sunrise"):
        assert title in err, title
    assert not (state_dir / "active_arc").exists()
    assert not fake_db.writes


def test_continue_refuses_an_unknown_title(fake_db, state_dir, capsys):
    cli.sys.argv = ["cli.py", "continue", "No Such Novel"]
    with pytest.raises(SystemExit) as raised:
        asyncio.run(cli.cmd_continue())

    assert raised.value.code == 1
    assert "no novel is titled" in capsys.readouterr().err
    assert not (state_dir / "active_arc").exists()


def test_continue_escapes_a_wildcard_in_the_title(fake_db, state_dir):
    """A `%` in the title is a literal, not a wildcard that matches every novel.

    The prefix pattern is the escaped title plus a trailing `%`, so the assertion names both halves.
    """
    cli.sys.argv = ["cli.py", "continue", "100%"]
    with pytest.raises(SystemExit):
        asyncio.run(cli.cmd_continue())

    pattern = fake_db._novels.calls[-1][1][0]
    assert pattern == "100\\%" + "%", pattern


# ── continue: the refusals ───────────────────────────────────────────────────────────────────────

def test_continue_refuses_a_superseded_novel_and_names_its_successor(fake_db, state_dir, capsys):
    fake_db._novels.exact = [{"novel_id": "tkg-prequel", "title": "TKG Prequel"}]
    fake_db._novels.by_id = [{"novel_id": "tkg-prequel", "title": "TKG Prequel",
                              "status": "superseded", "supersedes": None,
                              "adventures_dir": "adventures/tkg/novel"}]
    fake_db._novels.successor = {"novel_id": "tkg-the-sunrise",
                                 "title": "TKG — Arc I: The Sunrise"}
    cli.sys.argv = ["cli.py", "continue", "TKG Prequel"]
    with pytest.raises(SystemExit) as raised:
        asyncio.run(cli.cmd_continue())

    assert raised.value.code == 1
    err = capsys.readouterr().err
    assert "superseded by" in err and "TKG — Arc I: The Sunrise" in err
    assert not (state_dir / "active_arc").exists()


def test_continue_refuses_a_novel_no_session_plays(fake_db, state_dir, capsys):
    fake_db._novels.exact = [{"novel_id": "tkg-the-sunrise", "title": "TKG — Arc I: The Sunrise"}]
    fake_db._novels.by_id = [{"novel_id": "tkg-the-sunrise", "title": "TKG — Arc I: The Sunrise",
                              "status": "active", "supersedes": "tkg-prequel",
                              "adventures_dir": "adventures/tkg-arc1-restart"}]
    cli.sys.argv = ["cli.py", "continue", "The Sunrise"]
    with pytest.raises(SystemExit) as raised:
        asyncio.run(cli.cmd_continue())

    assert raised.value.code == 1
    assert "has no session to continue" in capsys.readouterr().err
    assert not (state_dir / "active_arc").exists()


def test_continue_refuses_a_novel_several_sessions_play(fake_db, state_dir, capsys):
    fake_db._novels.exact = [{"novel_id": "tkg-setia-kingdom", "title": "TKG Setia Kingdom"}]
    fake_db._novels.by_id = [{"novel_id": "tkg-setia-kingdom", "title": "TKG Setia Kingdom",
                              "status": "active", "supersedes": None,
                              "adventures_dir": "adventures/tkg"}]
    fake_db._sessions.playing = [{"id": 3, "name": "TKG", "status": "active", "game_day": 1,
                                  "story_path": None, "novel_id": "tkg-setia-kingdom"},
                                 {"id": 7, "name": "TKG second copy", "status": "active",
                                  "game_day": 1, "story_path": None,
                                  "novel_id": "tkg-setia-kingdom"}]
    cli.sys.argv = ["cli.py", "continue", "TKG Setia Kingdom"]
    with pytest.raises(SystemExit) as raised:
        asyncio.run(cli.cmd_continue())

    assert raised.value.code == 1
    err = capsys.readouterr().err
    assert "played by 2 sessions" in err and "TKG second copy" in err
    assert not (state_dir / "active_arc").exists()


def test_continue_refuses_scratch(fake_db, state_dir, capsys):
    fake_db._novels.exact = [{"novel_id": "scratch", "title": "Scratch"}]
    fake_db._sessions.playing = [{"id": 918, "name": "scratch", "status": "active", "game_day": 1,
                                  "story_path": None, "novel_id": "scratch"}]
    cli.sys.argv = ["cli.py", "continue", "Scratch"]
    with pytest.raises(SystemExit) as raised:
        asyncio.run(cli.cmd_continue())

    assert raised.value.code == 1
    assert "scratch" in capsys.readouterr().err
    assert not (state_dir / "active_arc").exists()


def test_continue_refuses_a_frozen_session(fake_db, state_dir, capsys):
    session.set_frozen([918])
    fake_db._novels.exact = [{"novel_id": "tkg-the-sunrise", "title": "TKG — Arc I: The Sunrise"}]
    fake_db._novels.by_id = [{"novel_id": "tkg-the-sunrise", "title": "TKG — Arc I: The Sunrise",
                              "status": "active", "supersedes": "tkg-prequel",
                              "adventures_dir": "adventures/tkg-arc1-restart"}]
    fake_db._sessions.playing = [{"id": 918, "name": "frozen copy", "status": "active",
                                  "game_day": 5, "story_path": None,
                                  "novel_id": "tkg-the-sunrise"}]
    cli.sys.argv = ["cli.py", "continue", "The Sunrise"]
    with pytest.raises(SystemExit) as raised:
        asyncio.run(cli.cmd_continue())

    assert raised.value.code == 1
    assert "frozen for reference" in capsys.readouterr().err
    assert not (state_dir / "active_arc").exists()


# ── continue: the list form ──────────────────────────────────────────────────────────────────────

def test_continue_without_a_title_lists_the_novels_and_their_sessions(fake_db, state_dir, capsys):
    def played(novel_id, title, status, supersedes, adventures_dir, session_id, name, day):
        return {"novel_id": novel_id, "title": title, "status": status, "supersedes": supersedes,
                "adventures_dir": adventures_dir, "session_id": session_id, "session_name": name,
                "session_status": "active", "game_day": day}

    fake_db._novels.listed = [
        played("scratch", "Scratch", "active", None, None, 918, "scratch", 1),
        played("tkg-prequel", "TKG Prequel", "superseded", None, "adventures/tkg/novel", None,
               None, None),
        played("tkg-setia-kingdom", "TKG Setia Kingdom", "active", None, "adventures/tkg", 3,
               "TKG", 2253),
        played("tkg-the-sunrise", "TKG — Arc I: The Sunrise", "active", "tkg-prequel",
               "adventures/tkg-arc1-restart", 5, "TKG — Arc I: The Sunrise", 34),
    ]
    cli.sys.argv = ["cli.py", "continue"]
    asyncio.run(cli.cmd_continue())

    out = capsys.readouterr().out
    assert "novels — 4" in out
    assert "tkg-setia-kingdom" in out and "session 3" in out
    assert "tkg-the-sunrise" in out and "session 5" in out
    assert "supersedes tkg-prequel" in out
    assert "(no session plays this novel)" in out.split("tkg-prequel")[1].split("tkg-setia")[0]
    assert not (state_dir / "active_arc").exists()


# ── clear ────────────────────────────────────────────────────────────────────────────────────────

def test_clear_dry_run_counts_every_table_and_deletes_nothing(fake_db, monkeypatch):
    fake_db.counts = {table: index + 1 for index, table in enumerate(cli.PLAY_STATE_TABLES)}
    conn, calls, out, err, code = _arm_clear(monkeypatch, fake_db, ["clear"], "918")

    for table in cli.PLAY_STATE_TABLES:
        assert table in out, table
    assert "TOTAL" in out and "dry run: nothing deleted" in out
    assert code is None and err == ""
    assert conn.tables == [] and calls == []
    assert not fake_db.writes


def test_clear_yes_exports_first_then_deletes_only_the_nine(fake_db, monkeypatch):
    fake_db.counts = {table: 0 for table in cli.PLAY_STATE_TABLES}
    conn, calls, out, err, code = _arm_clear(
        monkeypatch, fake_db, ["clear", "--yes"], "918", deleted=3)

    assert code is None and err == ""
    assert calls == [("export", (918,))], calls
    assert conn.tables == list(cli.PLAY_STATE_TABLES), conn.tables
    # The transaction holds one statement that is not a DELETE: the reference release below. Every
    # other statement must be a DELETE of the nine, so a scope that grew past the list fails here.
    assert [text for text in conn.sql if not cli._DELETE_FROM.match(text)] == [CLEAR_REFERENCE_SQL]
    for statement in conn.sql:
        match = cli._DELETE_FROM.match(statement)
        assert not match or match.group(1) in cli.PLAY_STATE_TABLES, statement
    assert "savegame: /tmp/backup/tkg.sav" in out
    assert "cleared session 918" in out
    assert not fake_db.writes


def test_clear_releases_the_roll_history_reference_before_it_deletes_events(fake_db, monkeypatch):
    """E1: a roll row that names an event aborts the delete of the whole transaction.

    `maya_rp.roll_history.context_event_id` references `events(id)` with NO ACTION, so the order of
    the two statements decides whether `clear --yes` removes anything. The connection applies every
    statement to the session's rows and raises where the server would.
    """
    fake_db.counts = {table: 0 for table in cli.PLAY_STATE_TABLES}
    rows = [("events", 42, None), ("roll_history", 7, 42)]
    conn, calls, out, err, code = _arm_clear(
        monkeypatch, fake_db, ["clear", "--yes"], "918", deleted=1, rows=rows)

    assert code is None and err == "", err
    assert conn.sql[0] == CLEAR_REFERENCE_SQL, conn.sql
    assert conn.sql.index(CLEAR_REFERENCE_SQL) < conn.sql.index(conn.deletes[0])
    assert conn.rows == [("roll_history", 7, None)], conn.rows
    assert "cleared session 918" in out
    assert not fake_db.writes


def test_clear_keeps_the_roll_row_and_drops_only_the_reference(fake_db, monkeypatch):
    """The roll history is not play state: `clear` releases the reference and leaves the row."""
    fake_db.counts = {table: 0 for table in cli.PLAY_STATE_TABLES}
    rows = [("events", 42, None), ("roll_history", 7, 42)]
    conn, _, _, _, code = _arm_clear(
        monkeypatch, fake_db, ["clear", "--yes"], "918", deleted=1, rows=rows)

    assert code is None
    assert conn.rows == [("roll_history", 7, None)], conn.rows
    for table in cli.PLAY_STATE_TABLES:
        assert table not in {row[0] for row in conn.rows}, table


def test_clear_runs_the_roll_history_release_on_a_real_database(scratch_campaign, monkeypatch):
    """E1 against the server: one event, one roll row naming it, then `clear --yes`.

    The stub above cannot fail the way the server fails. This arm reaches the real constraint: an
    `events` row with a `roll_history` row pointing at it, deleted through `Database.transaction()`.
    The export is stubbed, so no backup file is written and nothing outside this scratch session is
    read or written.
    """
    event_id = 0

    async def seed():
        await Database.init()
        nonlocal event_id
        event_id = await Database.fetchval(
            "INSERT INTO maya_rp.events (session_id, event_type, title) VALUES ($1, $2, $3)"
            " RETURNING id", scratch_campaign, "test", "clear reference scratch")
        roll_id = await Database.fetchval(
            "INSERT INTO maya_rp.roll_history"
            " (session_id, roll_code, source_table, source_id, dice_used, raw_roll, final_score,"
            "  dc, outcome, context_event_id)"
            " VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10) RETURNING id",
            scratch_campaign, "clear-fk", "events", int(event_id), "1d100", 50, 50, 50, "success",
            int(event_id))
        await Database.close()
        return int(event_id), int(roll_id)

    async def read_back():
        await Database.init()
        events = await Database.fetchval("SELECT COUNT(*) FROM maya_rp.events WHERE id = $1",
                                        int(event_id))
        roll = await Database.fetchrow(
            "SELECT context_event_id FROM maya_rp.roll_history WHERE session_id = $1",
            scratch_campaign)
        await Database.close()
        return events, roll

    event_id, roll_id = asyncio.run(seed())
    assert event_id and roll_id
    # The nine counts, the reference release and the nine deletes all run against the server: the
    # point of this arm is the constraint itself. Only `export_sav` is stubbed, so no file is written
    # and the export cannot fail the test for a reason of its own.
    async def export_without_a_file(session_id, out_dir=None):
        return "/tmp/backup/scratch.sav"

    monkeypatch.setattr("core.savegame.export_sav", export_without_a_file)
    before, cli.EXPLICIT_SESSION = cli.EXPLICIT_SESSION, str(scratch_campaign)
    own_argv = cli.sys.argv
    cli.sys.argv = ["cli.py", "clear", "--yes"]
    try:
        asyncio.run(cli.cmd_clear())
    finally:
        cli.EXPLICIT_SESSION = before
        cli.sys.argv = own_argv

    events, roll = asyncio.run(read_back())
    assert events == 0, "the event survived, so the delete did not complete"
    assert roll is not None, "the roll history row was deleted; clear releases the reference only"
    assert roll["context_event_id"] is None, "the reference still points at a deleted event"


def test_clear_takes_the_space_form_of_the_session_flag(fake_db, monkeypatch):
    fake_db.counts = {table: 0 for table in cli.PLAY_STATE_TABLES}
    conn, calls, out, err, code = _arm_clear(
        monkeypatch, fake_db, ["clear", "--session", "918", "--yes"], None, deleted=1)

    assert code is None and err == "", err
    assert calls == [("export", (918,))], calls
    assert conn.tables == list(cli.PLAY_STATE_TABLES), conn.tables


def test_clear_aborts_the_delete_when_the_export_fails(fake_db, monkeypatch):
    fake_db.counts = {table: 0 for table in cli.PLAY_STATE_TABLES}
    conn, calls, out, err, code = _arm_clear(
        monkeypatch, fake_db, ["clear", "--yes"], "918", export=_raising_export())

    assert code == 1
    assert calls == [("export", (918,))], calls
    assert conn.tables == [], conn.tables
    assert "nothing deleted" in err
    assert not fake_db.writes


def test_clear_refuses_a_frozen_session_before_it_exports_or_deletes(fake_db, monkeypatch):
    session.set_frozen([918])
    conn, calls, out, err, code = _arm_clear(monkeypatch, fake_db, ["clear", "--yes"], "918")

    assert code == 1
    assert calls == [] and conn.tables == []
    assert "frozen for reference" in err
    assert not fake_db.writes


def test_the_nine_tables_are_the_scope_the_card_names():
    """The scope list is the contract: a tenth table added here is a new decision, not an edit."""
    assert cli.PLAY_STATE_TABLES == (
        "events", "story_log", "news_articles", "tick_summaries", "adjutant_prompts",
        "morale_history", "crew_production_log", "pirate_alerts", "npc_offscreen_interactions",
    )
