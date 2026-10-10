"""One suite at a time against the live campaign database.

Four reviewers run pytest concurrently against the same `maya_rp` database, and every failure set
changed between runs: crew_system, celestial, prison, weapon_upgrade and dry_run_safety failed in
different combinations, and each of them passed together in isolation. One teammate measured it
directly — 38 of 38 pass alone, and 1053-1055 pass in a clean worktree with only his change, with the
remaining one to three failures always belonging to another module.

The cause is not the tests being wrong. It is two processes writing session-scoped rows at once, the same
race that made `test_ooc.py` fail before its scratch session was derived from the process id.

A suite that reports different failures each run teaches the team to ignore failures, which is worse than
a slow suite. This fixture takes an exclusive lock for the whole session, so a second concurrent run waits
its turn instead of interleaving.

Set RP_TEST_NO_LOCK=1 to skip the lock deliberately. If a run dies while holding it, the lock is released
by the kernel when the process exits; there is no stale lock to clear.
"""
from __future__ import annotations

import fcntl
import os
import pathlib
import re
import tempfile
import time
import types
import zlib
from contextlib import asynccontextmanager

import asyncpg
import pytest
import pytest_asyncio

#: Four tests in tests/test_deepseek_client.py fail without an API key, and the key's absence is not a
#: defect: it is how the module reports a missing key. Three reviewers reported those four as failures in
#: their suite lines and one of them spent a round deciding whether they were his. A dummy value here makes
#: the suite self-contained, so a red line means a real defect and every reviewer's line counts the same
#: things. Tests that need a real key should skip on a placeholder rather than fail.
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

#: `mirror_state_file` writes to the harness plugin's live store by default. Every audit in the suite mirrors
#: its scratch session there, and the plugin picked the newest entry as the campaign, so it followed a test
#: id instead of the arc. A temp path for the whole run keeps scratch sessions out of the live file.
os.environ["OOC_STATE_FILE"] = os.path.join(tempfile.mkdtemp(prefix="rp-engine-pytest-"), "tkg-state.json")

LOCK_PATH = pathlib.Path(os.environ.get("RP_TEST_LOCK", "/tmp/rp-engine-pytest.lock"))


@pytest.fixture(scope="session", autouse=True)
def _one_suite_at_a_time():
    if os.environ.get("RP_TEST_NO_LOCK") == "1":
        yield
        return
    handle = LOCK_PATH.open("w")
    start = time.monotonic()
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print(f"\nwaiting for the other pytest run to finish ({LOCK_PATH})")
        fcntl.flock(handle, fcntl.LOCK_EX)
        waited = time.monotonic() - start
        print(f"lock acquired after {waited:.0f}s; another run was using the database")
    try:
        yield
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()

#: Session ids reserved for test scratch work. 900-999 sits above the live arc (5) and the frozen
#: reference (3), and below nothing that matters, so a test can write freely inside its own slot.
SCRATCH_BASE = 900


def scratch_id(module_name: str) -> int:
    """The scratch session id of the test module `module_name`, as `scratch_session` hands it out."""
    return SCRATCH_BASE + zlib.crc32(module_name.encode()) % 100


@pytest_asyncio.fixture
async def scratch_session(request) -> int:
    """A scratch session id for the test file, inside 900-999.

    The id is `900 + crc32(module name) % 100`: every test in one file gets the same id, and a run gets
    the same ids as the run before. Two files can hash to one slot. They never overlap, because the
    suite lock runs one pytest process at a time and the teardown below clears the slot after each test.
    Never write sessions 3 and 5: the `_isolation_guard` fixture below refuses those writes.

    Use it for anything that inserts, updates or deletes. Read-only tests can keep naming the arc they are
    reading, because reading a campaign is not what collides.

        async def test_something(scratch_session):
            await Database.init()
            await Database.execute("INSERT INTO maya_rp.x (session_id, ...) VALUES ($1, ...)",
                                   scratch_session, ...)

    The fixture deletes that session's rows afterwards, and it discovers them rather than assuming: it reads
    every `maya_rp` table that has a `session_id` column and deletes this session's rows from each. That is
    the contract a test author needs to rely on.

    It said that before it did it. The first version ended at `yield session_id`, so a generator with no code
    after its yield performed no teardown at all, while the docstring told eleven test files they could skip
    their own `finally`. A false contract in a cleanup helper is worse than no helper, because it is the
    helper that stops the author writing the cleanup themselves, and it was named as the remedy for the very
    hazard that destroyed the live arc's resources row.
    """
    session_id = scratch_id(request.module.__name__)
    yield session_id
    await _clear_session_rows(session_id)


async def _clear_session_rows(session_id: int) -> None:
    """Delete `session_id`'s rows from every `maya_rp` table that has a `session_id` column."""
    from core.db import Database

    # The test usually called Database.close() before this runs, so the pool may be shut. Without this the
    # fetch below raised, the except returned, and the teardown did nothing — silently, which is the exact
    # defect this fixture was written to stop. The proof test caught it: one row left in complaint_boxes.
    try:
        await Database.init()
    except Exception as e:
        print(f"scratch_session: could not open the pool, rows may remain: {e!r}")
        return

    try:
        # Every column is qualified. Unqualified `table_schema` and `table_name` are ambiguous across the
        # two joined information_schema views, which raised, which the except swallowed.
        tables = await Database.fetch(
            "SELECT c.table_name FROM information_schema.columns c"
            " JOIN information_schema.tables t ON t.table_schema = c.table_schema"
            " AND t.table_name = c.table_name AND t.table_type = 'BASE TABLE'"
            " WHERE c.table_schema = 'maya_rp' AND c.column_name = 'session_id'")
    except Exception as e:
        print(f"scratch_session: could not list the tables it must clear: {e!r}")
        return
    for row in tables:
        try:
            await Database.execute(
                f'DELETE FROM maya_rp."{row["table_name"]}" WHERE session_id = $1', session_id)
        except Exception:
            # A table with a session_id column that refuses the delete (a view, a foreign key, a permission)
            # is reported rather than swallowed, because a silent failure here is the defect this file just
            # had. The test author still owns rows the fixture could not remove.
            print(f"scratch_session: could not clear {row['table_name']}")


@pytest_asyncio.fixture
async def scratch_campaign(scratch_session) -> int:
    """`scratch_session` plus its `maya_rp.sessions` row, for a test whose tables carry a foreign key to it.

    118 tables reference `sessions(id)`, and most of them do not cascade. The teardown clears the child
    rows first and removes the row last, so the order of the fixtures in the signature does not matter.
    """
    from core.db import Database

    await Database.init()
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1, 'rp-engine test scratch', 'active')"
        " ON CONFLICT (id) DO NOTHING", scratch_session)
    yield scratch_session
    await _clear_session_rows(scratch_session)
    try:
        await Database.init()
        await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", scratch_session)
    except Exception as e:
        print(f"scratch_campaign: could not remove the sessions row {scratch_session}: {e!r}")


# ── Live-session write guard ──────────────────────────────────────────────────────────────────────────
#
# A write to session 3 (old arc) or 5 (live arc) from a test changes campaign state. A probe measured
# four test files doing it. The guard refuses the statement before it reaches the database.
#
# It wraps three layers: `Database.execute/executemany/fetch/fetchrow/fetchval`, the connection that
# `Database.transaction()` yields, and the `asyncpg.Connection` class (a test that calls `pool.acquire()`
# skips `Database`). A statement trips when all hold:
#   - it starts with INSERT, UPDATE or DELETE (after whitespace, comments and a WITH clause that writes),
#   - it mentions `session_id` or targets the `sessions` table,
#   - a positional arg is the int 3 or 5 (a list arg counts per element), or the SQL itself holds a
#     literal `session_id = 3`, `session_id IN (3, ...)` or an INSERT whose `session_id` value is 3 or 5.
# When every `session_id` in the statement is bound to a `$n` (`= $n`, `= ANY($n)`, `IN ($n, ...)` or an
# INSERT column), only those args count, so `credits - $1` with 5 and a scratch session passes. Any
# other shape (a subquery, an INSERT ... SELECT, a multi-row VALUES) counts every arg. A conflict target
# and a RETURNING list are not bindings.
# Reads pass. A trip raises AssertionError and records itself, so a test whose code swallows the
# exception still fails at teardown.
#
# Opt out with `@pytest.mark.live_session_ok`. Use it only when the test must write session 3 or 5.

#: Sessions no test writes: 3 is the old arc, 5 is the live arc.
LIVE_SESSIONS = frozenset({3, 5})

_LEADING = re.compile(r"(?:\s+|--[^\n]*(?:\n|\Z)|/\*.*?\*/)*", re.S)
_WRITE_VERB = re.compile(r"(?:INSERT|UPDATE|DELETE)\b", re.I)
_WITH = re.compile(r"WITH\b", re.I)
_WRITE_IN_CTE = re.compile(
    r"\b(?:INSERT\s+INTO|DELETE\s+FROM|UPDATE\s+[\w.\"]+(?:\s+(?:AS\s+)?\w+)?\s+SET)\b", re.I)
_SESSIONS_TABLE = re.compile(
    r"(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+(?:\w+\.)?\"?sessions\"?(?![\w.])", re.I)
_SESSION_ID = re.compile(r"\bsession_id\b", re.I)
_CONFLICT_TARGET = re.compile(r"\bON\s+CONFLICT\s*\([^)]*\)", re.I)
_RETURNING = re.compile(r"\bRETURNING\b", re.I)
_SESSION_EQ = re.compile(r"\bsession_id\s*=\s*([35])(?![\w.$])", re.I)
_SESSION_BIND = re.compile(r"\bsession_id\s*=\s*(?:ANY\s*\(\s*)?\$(\d+)", re.I)
_ID_BIND = re.compile(r"(?<!\w)(?:\w+\.)?id\s*=\s*(?:ANY\s*\(\s*)?\$(\d+)", re.I)
_PLACEHOLDER = re.compile(r"\$(\d+)")
_PLAIN_VALUE = re.compile(r"\s*(?:\$\d+|\d+)\s*(?:::\w+)?\s*\Z")
_SESSION_IN = re.compile(r"\bsession_id\s+IN\s*\(([^)]*)\)", re.I)
_INSERT_HEAD = re.compile(r"\bINSERT\s+INTO\s+[\w.\"]+\s*\(([^)]*)\)\s*(VALUES\s*\(|SELECT\s+)", re.I)
_FROM = re.compile(r"FROM\b", re.I)
_LIVE_LITERAL = re.compile(r"\s*([35])\s*(?:::\w+)?\s*\Z")

#: Per-test state: the node id the message names, and the trips recorded so far.
_guard_state = types.SimpleNamespace(test="", trips=[])


def _write_statements(sql: str) -> list[str]:
    """The statements of `sql` that write, each stripped of leading space and comments."""
    found = []
    for part in sql.split(";"):
        body = part[_LEADING.match(part).end():]
        if _WRITE_VERB.match(body) or (_WITH.match(body) and _WRITE_IN_CTE.search(body)):
            found.append(body)
    return found


def _split_items(text: str, *, select: bool) -> tuple[list[str], str]:
    """Split the items that start `text` on top-level commas. Also return what follows them.

    With `select` false the items are a parenthesised VALUES tuple and end at its closing paren. With
    `select` true they are a SELECT list and end at a top-level FROM or the end of the statement.
    """
    items, depth, quoted, current = [], 0, False, []
    for index, ch in enumerate(text):
        if quoted:
            current.append(ch)
            quoted = ch != "'"
        elif ch == "'":
            current.append(ch)
            quoted = True
        elif ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")" and depth == 0 and not select:
            items.append("".join(current))
            return items, text[index + 1:]
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            items.append("".join(current))
            current = []
        elif select and depth == 0 and ch.isspace() and _FROM.match(text, index + 1):
            items.append("".join(current))
            return items, text[index:]
        else:
            current.append(ch)
    items.append("".join(current))
    return items, ""


def _insert_session_item(stmt: str) -> tuple[str | None, bool]:
    """The VALUES or SELECT item that fills `session_id` in an INSERT, and whether the row is the only one."""
    head = _INSERT_HEAD.search(stmt)
    if not head:
        return None, False
    columns = [c.strip().strip('"').lower() for c in head.group(1).split(",")]
    if "session_id" not in columns:
        return None, False
    items, rest = _split_items(stmt[head.end():], select=not head.group(2).upper().startswith("VALUES"))
    index = columns.index("session_id")
    if index >= len(items):
        return None, False
    return items[index], not rest.lstrip().startswith(",")


def _insert_session_numbers(stmt: str) -> set[int]:
    """Every `$n` that fills `session_id` in an INSERT, one per `VALUES` tuple.

    The `VALUES` clause is read as a flat `$n` token stream, so a multi-row statement yields one
    placeholder per tuple at the column's stride. A clause whose items are not one placeholder each
    does not divide evenly and yields nothing, which leaves the caller its wider fallback.
    """
    head = _INSERT_HEAD.search(stmt)
    if not head:
        return set()
    columns = [c.strip().strip('"').lower() for c in head.group(1).split(",")]
    if "session_id" not in columns or not columns:
        return set()
    numbers = [int(n) for n in _PLACEHOLDER.findall(stmt[head.end():])]
    if not numbers or len(numbers) % len(columns):
        return set()
    index = columns.index("session_id")
    return {numbers[position] for position in range(index, len(numbers), len(columns))}


def _literal_live_session(stmt: str) -> int | None:
    """The live session id written as a SQL literal in `stmt`, else None."""
    match = _SESSION_EQ.search(stmt)
    if match:
        return int(match.group(1))
    for match in _SESSION_IN.finditer(stmt):
        for token in match.group(1).split(","):
            literal = _LIVE_LITERAL.match(token)
            if literal:
                return int(literal.group(1))
    item, _ = _insert_session_item(stmt)
    literal = _LIVE_LITERAL.match(item) if item is not None else None
    return int(literal.group(1)) if literal else None


def _session_placeholders(stmt: str) -> tuple[set[int], int]:
    """The `$n` numbers that `stmt` binds to `session_id`, and how many `session_id` mentions they explain."""
    numbers, explained = set(), 0
    for match in _SESSION_BIND.finditer(stmt):
        numbers.add(int(match.group(1)))
        explained += 1
    for match in _SESSION_IN.finditer(stmt):
        found = _PLACEHOLDER.findall(match.group(1))
        numbers.update(int(n) for n in found)
        explained += bool(found)
    item, single = _insert_session_item(stmt)
    if item is not None and single and _PLAIN_VALUE.match(item):
        explained += 1
        numbers.update(int(n) for n in _PLACEHOLDER.findall(item))
    else:
        # A multi-row `VALUES` list binds one session per tuple; `_insert_session_numbers` reads the
        # column stride so a live session in any tuple is caught.
        per_tuple = _insert_session_numbers(stmt)
        if per_tuple:
            explained += 1
            numbers.update(per_tuple)
    return numbers, explained


def _args_at(args, numbers) -> list:
    return [args[n - 1] for n in sorted(numbers) if 0 < n <= len(args)]


def _live_arg(args) -> int | None:
    """The first positional arg that is the int 3 or 5. A list or tuple arg counts per element."""
    for arg in args:
        for item in arg if isinstance(arg, (list, tuple, set, frozenset)) else (arg,):
            if type(item) is int and item in LIVE_SESSIONS:
                return item
    return None


def live_session_write(sql, args=()) -> int | None:
    """The live session id that `sql` writes with `args`, else None. A read returns None."""
    if not isinstance(sql, str):
        return None
    for stmt in _write_statements(sql):
        literal = _literal_live_session(stmt)
        if literal is not None:
            return literal
        if _SESSION_ID.search(stmt):
            numbers, explained = _session_placeholders(stmt)
            # A conflict target and a RETURNING list name the column and write no value into it.
            mentions = _RETURNING.split(_CONFLICT_TARGET.sub("", stmt))[0]
            exact = bool(numbers) and explained >= len(_SESSION_ID.findall(mentions))
            bound = _live_arg(_args_at(args, numbers) if exact else args)
        elif _SESSIONS_TABLE.match(stmt):
            numbers = {int(n) for n in _ID_BIND.findall(stmt)}
            bound = _live_arg(_args_at(args, numbers) if numbers else args)
        else:
            continue
        if bound is not None:
            return bound
    return None


def _check_write(sql, args) -> None:
    """Raise AssertionError, and record the trip, when `sql` writes a live session."""
    live = live_session_write(sql, args)
    if live is None:
        return
    message = (f"isolation guard: write to live session {live} blocked in {_guard_state.test or '<no test>'}. "
               f"SQL: {' '.join(str(sql).split())[:240]}. Use the scratch_session fixture, "
               "or mark the test @pytest.mark.live_session_ok if it must write session 3 or 5.")
    _guard_state.trips.append(message)
    raise AssertionError(message)


def _guarded(inner, *, bound: bool, many: bool):
    """Wrap one executor with the guard.

    `bound` is true when `inner` already holds its owner (a `Database` classmethod or a connection
    method). Otherwise `inner` is a plain function that takes the connection first. `many` is true for
    `executemany` and `fetchmany`, whose second argument is a list of arg tuples.
    """
    async def guarded(owner, sql, *args, **kw):
        if many:
            rows = list(args[0])
            for row in rows:
                _check_write(sql, tuple(row))
            args = (rows, *args[1:])
        else:
            _check_write(sql, args)
        return await (inner(sql, *args, **kw) if bound else inner(owner, sql, *args, **kw))

    return guarded


_EXECUTORS = {"execute": False, "fetch": False, "fetchrow": False, "fetchval": False,
              "executemany": True, "fetchmany": True}


class _GuardedConnection:
    """The connection a transaction yields. Writes pass the guard and everything else passes through."""

    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)


def _proxy_executor(name: str, many: bool):
    async def call(self, sql, *args, **kw):
        return await _guarded(getattr(self._conn, name), bound=True, many=many)(None, sql, *args, **kw)

    return call


for _name, _many in _EXECUTORS.items():
    setattr(_GuardedConnection, _name, _proxy_executor(_name, _many))


def install_isolation_guard(monkeypatch, database, connection_cls=None) -> None:
    """Wrap `database`'s executors and its `transaction()`, and `connection_cls`'s methods when given.

    `monkeypatch` undoes every change at teardown. An attribute the target lacks is skipped.
    """
    for name, many in _EXECUTORS.items():
        if hasattr(database, name):
            guarded = _guarded(getattr(database, name), bound=True, many=many)
            monkeypatch.setattr(database, name, classmethod(guarded))
        if connection_cls is not None and hasattr(connection_cls, name):
            guarded = _guarded(getattr(connection_cls, name), bound=False, many=many)
            monkeypatch.setattr(connection_cls, name, guarded)
    if hasattr(database, "transaction"):
        inner_transaction = database.transaction

        @asynccontextmanager
        async def transaction(cls, *args, **kw):
            async with inner_transaction(*args, **kw) as conn:
                yield _GuardedConnection(conn)

        monkeypatch.setattr(database, "transaction", classmethod(transaction))


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "live_session_ok: the test must write session 3 or 5, so the isolation guard stands down for it")


@pytest.fixture(autouse=True)
def _isolation_guard(request):
    """Refuse a write to session 3 or 5 in every test, unless it carries `live_session_ok`.

    Yields the list of trips this test recorded. A test that provokes a trip on purpose clears the list
    before it ends. Any trip left at teardown fails the test, including one the code under test swallowed.

    The guard owns a private `MonkeyPatch` and does not request the `monkeypatch` fixture. A test's own
    `monkeypatch` is set up after the autouse fixtures of its file, so it is undone before their teardown.
    Requesting `monkeypatch` here would move its teardown after them, and a patched `Database.execute`
    would still be live while their cleanup runs.
    """
    trips: list[str] = []
    if request.node.get_closest_marker("live_session_ok"):
        yield trips
        return
    from core.db import Database

    _guard_state.test, _guard_state.trips = request.node.nodeid, trips
    with pytest.MonkeyPatch.context() as patch:
        install_isolation_guard(patch, Database, asyncpg.Connection)
        yield trips
    _guard_state.test, _guard_state.trips = "", []
    assert not trips, "a write to a live session was blocked and the test did not stop:\n" + "\n".join(trips)
