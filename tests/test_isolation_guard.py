"""The isolation guard in tests/conftest.py refuses writes to live sessions 3 and 5.

Nothing here reaches the database. `Database._run` is replaced by a recorder, and the transaction and
connection layers are fakes, so a guard that fails to trip still writes nothing.

Every test that provokes a trip clears `_isolation_guard` afterwards. A trip left in that list fails the
test at teardown, which is how a swallowed exception stays visible.
"""
from __future__ import annotations

import types
import zlib
from contextlib import asynccontextmanager

import pytest

from core.db import Database
from tests.conftest import SCRATCH_BASE, install_isolation_guard, live_session_write

INSERT = "INSERT INTO maya_rp.complaint_boxes (session_id, note) VALUES ($1, $2)"
UPDATE = "UPDATE maya_rp.resources SET credits = credits - $1 WHERE session_id = $2"


@pytest.fixture
def recorder(monkeypatch):
    """Replace the pool call under `Database.execute` and friends with a recorder."""
    seen = types.SimpleNamespace(calls=[])

    class Conn:
        async def execute(self, sql, *args):
            seen.calls.append(("execute", sql, args))
            return "OK"

        async def fetch(self, sql, *args):
            seen.calls.append(("fetch", sql, args))
            return []

        async def fetchrow(self, sql, *args):
            seen.calls.append(("fetchrow", sql, args))

        async def fetchval(self, sql, *args):
            seen.calls.append(("fetchval", sql, args))

    async def fake_run(fn, *args):
        return await fn(Conn(), *args)

    monkeypatch.setattr(Database, "_run", fake_run)
    return seen


# ── The guard on the real Database layer ─────────────────────────────────────────────────────────────

async def test_an_insert_for_session_5_trips(recorder, _isolation_guard):
    with pytest.raises(AssertionError) as raised:
        await Database.execute(INSERT, 5, "x")

    message = str(raised.value)
    assert "live session 5" in message
    assert INSERT in message, "the message does not name the SQL"
    assert "test_an_insert_for_session_5_trips" in message, "the message does not name the test"
    assert not recorder.calls, "the statement reached the pool"
    assert len(_isolation_guard) == 1
    _isolation_guard.clear()


async def test_an_update_for_session_3_trips(recorder, _isolation_guard):
    with pytest.raises(AssertionError, match="live session 3"):
        await Database.execute(UPDATE, 100, 3)

    assert not recorder.calls
    _isolation_guard.clear()


async def test_a_scratch_session_passes(recorder):
    await Database.execute(INSERT, 905, "x")
    await Database.execute(UPDATE, 5, 905)

    assert [c[0] for c in recorder.calls] == ["execute", "execute"]
    assert recorder.calls[1][2] == (5, 905), "an amount of 5 is not a session"


@pytest.mark.parametrize("method", ["execute", "fetch", "fetchrow", "fetchval"])
async def test_every_executor_is_guarded(method, recorder, _isolation_guard):
    sql = "DELETE FROM maya_rp.resources WHERE session_id = $1 RETURNING credits"
    with pytest.raises(AssertionError, match="live session 5"):
        await getattr(Database, method)(sql, 5)

    assert not recorder.calls
    _isolation_guard.clear()


async def test_reads_of_a_live_session_pass(recorder):
    await Database.fetch("SELECT * FROM maya_rp.resources WHERE session_id = $1", 5)
    await Database.fetchrow("SELECT * FROM maya_rp.resources WHERE session_id = $1 FOR UPDATE", 3)
    await Database.fetchval("SELECT count(*) FROM maya_rp.resources WHERE session_id = 5")

    assert len(recorder.calls) == 3


async def test_a_swallowed_trip_stays_recorded(recorder, _isolation_guard):
    """Code that catches the AssertionError still fails the test at teardown."""
    try:
        await Database.execute(INSERT, 5, "x")
    except Exception:
        pass

    assert len(_isolation_guard) == 1
    _isolation_guard.clear()


@pytest.mark.live_session_ok
async def test_the_marker_opts_out(recorder, _isolation_guard):
    await Database.execute(INSERT, 5, "x")

    assert recorder.calls == [("execute", INSERT, (5, "x"))]
    assert not _isolation_guard


# ── What counts as a write to a live session ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("sql, args, expected", [
    (INSERT, (5, "x"), 5),
    (UPDATE, (1, 3), 3),
    (UPDATE, (1, 905), None),
    (UPDATE, (5, 905), None),
    (UPDATE, (905, 5), 5),
    ("UPDATE maya_rp.x SET n = $1 WHERE session_id = $2 RETURNING session_id", (5, 905), None),
    ("UPDATE maya_rp.x SET n = $1 WHERE session_id = $2 RETURNING session_id", (905, 5), 5),
    ("INSERT INTO maya_rp.x (session_id, n) VALUES ($1, $2) ON CONFLICT (session_id) DO UPDATE SET n = $2",
     (905, 5), None),
    ("INSERT INTO maya_rp.x (session_id, n) VALUES ($1, $2) ON CONFLICT (session_id) DO UPDATE SET n = $2",
     (5, 905), 5),
    ("INSERT INTO maya_rp.x (session_id, n) SELECT $1, n FROM maya_rp.x WHERE session_id = $2", (905, 5), 5),
    ("INSERT INTO maya_rp.x (session_id, name, level) SELECT $1::int, n, $3::int FROM unnest($2::text[]) AS n",
     (905, ["a"], 5), None),
    ("INSERT INTO maya_rp.x (session_id, name, level) SELECT $1::int, n, $3::int FROM unnest($2::text[]) AS n",
     (5, ["a"], 7), 5),
    ("INSERT INTO maya_rp.x (name, session_id) SELECT n, 3 FROM unnest($1::text[]) AS n", (["a"],), 3),
    ("UPDATE maya_rp.x SET n = $1 WHERE session_id = (SELECT id FROM maya_rp.sessions WHERE name = $2)",
     (1, 5), 5),
    ("INSERT INTO maya_rp.x (n, session_id) VALUES ($1, $2)", (5, 905), None),
    ("INSERT INTO maya_rp.x (n, session_id) VALUES ($1, $2), ($3, $4)", (1, 905, 2, 5), 5),
    ("SELECT * FROM maya_rp.resources WHERE session_id = $1", (5,), None),
    ("UPDATE maya_rp.factions SET reputation = $1 WHERE id = $2", (5, 3), None),
    ("  -- note\n  /* more */ delete from maya_rp.x where session_id = $1", (3,), 3),
    ("WITH a AS (SELECT 1) UPDATE maya_rp.x SET n = 1 WHERE session_id = $1", (5,), 5),
    ("WITH a AS (SELECT 1) SELECT * FROM maya_rp.x WHERE session_id = $1", (5,), None),
    ("SELECT 1; DELETE FROM maya_rp.x WHERE session_id = $1", (5,), 5),
    ("UPDATE maya_rp.x SET n = 1 WHERE session_id = ANY($1)", ([1, 5],), 5),
    ("UPDATE maya_rp.sessions SET king_present = false WHERE id = $1", (5,), 5),
    ("UPDATE maya_rp.sessions SET king_present = false WHERE id = $1", (905,), None),
    ("DELETE FROM maya_rp.x WHERE session_id = 5", (), 5),
    ("DELETE FROM maya_rp.x WHERE session_id = 3", (), 3),
    ("DELETE FROM maya_rp.x WHERE session_id = 35", (), None),
    ("DELETE FROM maya_rp.x WHERE session_id IN (1, 5)", (), 5),
    ("INSERT INTO maya_rp.sectors (name, session_id, x) VALUES ('a, b', 5, 0)", (), 5),
    ("INSERT INTO maya_rp.sectors (name, session_id, x) VALUES ('a', 7, 5)", (), None),
])
def test_what_the_guard_calls_a_live_write(sql, args, expected):
    assert live_session_write(sql, args) == expected


async def test_an_interpolated_literal_trips(recorder, _isolation_guard):
    session = 5
    with pytest.raises(AssertionError, match="live session 5"):
        await Database.execute(f"DELETE FROM maya_rp.x WHERE session_id = {session}")

    assert not recorder.calls
    _isolation_guard.clear()


# ── The transaction connection, executemany and the connection class, on fake layers ─────────────────

def _fake_database():
    seen = []

    class Conn:
        async def execute(self, sql, *args):
            seen.append(("execute", args))

        async def executemany(self, sql, rows):
            seen.append(("executemany", list(rows)))

        def is_closed(self):
            return False

    class FakeDatabase:
        @classmethod
        @asynccontextmanager
        async def transaction(cls):
            yield Conn()

    return FakeDatabase, seen


async def test_the_transaction_connection_is_guarded(monkeypatch, _isolation_guard):
    database, seen = _fake_database()
    install_isolation_guard(monkeypatch, database)

    async with database.transaction() as conn:
        await conn.execute(INSERT, 905, "x")
        assert conn.is_closed() is False, "an attribute that is not an executor must pass through"
        with pytest.raises(AssertionError, match="live session 5"):
            await conn.execute(INSERT, 5, "x")

    assert seen == [("execute", (905, "x"))]
    assert len(_isolation_guard) == 1
    _isolation_guard.clear()


async def test_executemany_checks_every_row(monkeypatch, _isolation_guard):
    database, seen = _fake_database()
    install_isolation_guard(monkeypatch, database)

    async with database.transaction() as conn:
        await conn.executemany(INSERT, iter([(905, "a"), (906, "b")]))
        with pytest.raises(AssertionError, match="live session 3"):
            await conn.executemany(INSERT, iter([(905, "a"), (3, "b")]))

    assert seen == [("executemany", [(905, "a"), (906, "b")])]
    _isolation_guard.clear()


async def test_the_connection_class_is_guarded(monkeypatch, _isolation_guard):
    """A test that calls `pool.acquire()` skips `Database`; the connection class is the floor."""
    seen = []

    class Connection:
        async def execute(self, sql, *args):
            seen.append(args)

    database, _ = _fake_database()
    install_isolation_guard(monkeypatch, database, Connection)

    await Connection().execute(UPDATE, 1, 905)
    with pytest.raises(AssertionError, match="live session 5"):
        await Connection().execute(UPDATE, 1, 5)

    assert seen == [(1, 905)]
    _isolation_guard.clear()


# ── The scratch id and the marker ────────────────────────────────────────────────────────────────────

async def test_the_scratch_id_is_fixed_by_the_file(scratch_session):
    assert scratch_session == SCRATCH_BASE + zlib.crc32(__name__.encode()) % 100
    assert 900 <= scratch_session <= 999


def test_the_marker_is_registered(pytestconfig):
    assert any(line.startswith("live_session_ok") for line in pytestconfig.getini("markers"))
