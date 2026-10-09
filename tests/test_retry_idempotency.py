"""The retry in `Database._run` must not replay a statement that already reached the server.

`_run` reconnects once when a connection dies. The reconnect is right; re-issuing the call is only
safe when the failure happened before anything was written. A replayed relative write applies twice:
`modules/_economy._deduct_resources` charges with `SET credits = GREATEST(0, credits - $1)`, so the
second charge is silent, and once the column reaches zero the clamp leaves no trace of it at all.

Measured against the live database, read-only:

    MID-FLIGHT           : asyncpg.exceptions.ConnectionDoesNotExistError,
                           "connection was closed in the middle of operation"
    NEXT ACQUIRE + QUERY : ok -> 1   (the pool heals a dead holder at acquire, with no retry)

So the recovery the retry exists for already happens inside the pool, while the replay itself only
adds a second execution. The raise site is `protocol/protocol.pyx:691`, the protocol's
`connection_lost` handler, which fires after the statement was written to the socket.

No database: every test drives fake pools and connections, and the fixture replaces `_ensure_pool`,
`init` and `close`, so nothing here can open a socket to `maya_rp`.
"""
from __future__ import annotations

import asyncpg
import pytest

from core import db
from modules._economy import _deduct_resources

#: What asyncpg raises when the socket dies mid-statement. Copied from `protocol/protocol.pyx:691`,
#: not typed from memory.
MID_FLIGHT = "connection was closed in the middle of operation"


class FakeConn:
    """One server connection: records the statements it receives, then loses the socket."""

    def __init__(self, received: list, die_on_call: int, raise_with: Exception):
        self.received = received
        self.calls = 0
        self.die_on_call = die_on_call
        self.raise_with = raise_with

    async def fetchval(self, sql, *args):
        self.calls += 1
        if self.calls == self.die_on_call:
            if isinstance(self.raise_with, asyncpg.exceptions.InterfaceError):
                # `Connection._check_open()` refuses before the statement is serialised. Nothing
                # was sent, so this is the one failure the retry can serve without applying a
                # write twice.
                raise self.raise_with
            # The statement reached the server, which is what makes a replay a second execution.
            self.received.append((" ".join(sql.split()), args))
            raise self.raise_with
        self.received.append((" ".join(sql.split()), args))
        return 0.0

    async def fetchrow(self, sql, *args):
        # The charge is `fetchrow(UPDATE ... RETURNING ...)` now, one guarded statement, not a
        # `fetchval` per resource. It has to come back with a mapping: the caller logs `dict(row)`,
        # and the float `fetchval` returns raised TypeError on the success path.
        result = await self.fetchval(sql, *args)
        return {} if result is not None else None

    async def execute(self, sql, *args):
        return await self.fetchval(sql, *args)


class _Acquire:
    """Mirrors asyncpg's PoolAcquireContext: awaitable and an async context manager.

    `raise_with` models the pool losing the connection while it was establishing one. That failure
    happens before `fn` exists, so no statement can have been written by it.
    """

    def __init__(self, conn, raise_with: Exception | None = None):
        self.conn = conn
        self.raise_with = raise_with

    async def __aenter__(self):
        if self.raise_with is not None:
            raise self.raise_with
        return self.conn

    async def __aexit__(self, *exc):
        return False

    def __await__(self):
        async def _get():
            if self.raise_with is not None:
                raise self.raise_with
            return self.conn

        return _get().__await__()


class FakePool:
    """Hands out a fresh connection per acquire, the way a real reconnect does.

    Only the first connection dies, so a replay reaches a working server and its write lands. That
    is the sequence that doubles a charge.
    """

    def __init__(self, received: list, raise_with: Exception | None = None):
        self.received = received
        self.raise_with = raise_with or asyncpg.exceptions.ConnectionDoesNotExistError(MID_FLIGHT)
        #: Set to make the FIRST acquire fail, which is the handshake dropping before `fn` runs.
        self.acquire_fail: Exception | None = None
        self.served = 0

    def acquire(self):
        self.served += 1
        return _Acquire(FakeConn(self.received, 1 if self.served == 1 else 0, self.raise_with),
                        self.acquire_fail if self.served == 1 else None)


@pytest.fixture
def pool(monkeypatch):
    received: list = []
    fake = FakePool(received)
    calls = {"init": 0, "close": 0}

    async def ensure_pool():
        return fake

    async def init():
        calls["init"] += 1
        return fake

    # Every door to a real socket is replaced, so a failing assertion cannot become a live write.
    # The reconnect terminates the dead pool and builds the replacement under the pool lock, so
    # "closed" and "init" are counted at those two seams.
    monkeypatch.setattr(db.Database, "pool", fake)
    monkeypatch.setattr(db.Database, "_ensure_pool", staticmethod(ensure_pool))
    monkeypatch.setattr(db.Database, "init", staticmethod(init))
    monkeypatch.setattr(db.Database, "_create_locked", staticmethod(init))
    monkeypatch.setattr(fake, "terminate", lambda: calls.__setitem__("close", calls["close"] + 1), raising=False)
    return fake, calls, received


async def test_a_statement_that_reached_the_server_is_not_replayed(pool):
    """The defect: the statement landed, the socket died, and the retry ran the write again."""
    _, calls, received = pool

    with pytest.raises(asyncpg.exceptions.ConnectionDoesNotExistError):
        await db.Database.execute(
            "UPDATE maya_rp.resources SET credits = credits - $1 WHERE session_id = $2", 100, 5)

    assert len(received) == 1, f"the statement ran {len(received)} times: {received}"
    assert calls == {"init": 1, "close": 1}, calls


async def test_the_ledger_charge_runs_once_when_the_socket_dies_mid_charge(pool):
    """The sharpest site: a replayed charge is a second charge, and nothing in the row shows it.

    `GREATEST(0, credits - $1)` used to clamp, so a replay onto a zero balance changed nothing a
    reader could see. The charge is one guarded `UPDATE ... WHERE COALESCE(credits, 0) >= $n` now, so
    the clamp is gone, but a replay with enough left in the treasury still debits twice. The
    statement must therefore reach the server exactly once.
    """
    _, _, received = pool

    with pytest.raises(asyncpg.exceptions.ConnectionDoesNotExistError):
        await _deduct_resources(5, {"credits": 100})

    updates = [sql for sql, _ in received if sql.startswith("UPDATE")]
    assert len(updates) == 1, f"the treasury was charged {len(updates)} times: {received}"
    assert "COALESCE(credits, 0) - $2" in updates[0], updates


async def test_a_socket_failure_is_not_replayed_either(pool):
    """`PostgresConnectionError` is the parent of the mid-flight error, so it refuses the same way."""
    fake, calls, received = pool
    fake.raise_with = asyncpg.exceptions.PostgresConnectionError("connection lost")

    with pytest.raises(asyncpg.exceptions.PostgresConnectionError):
        await db.Database.fetchval("SELECT 1")

    assert len(received) == 1, f"the statement ran {len(received)} times: {received}"
    assert calls == {"init": 1, "close": 1}, calls


async def test_a_call_that_never_reached_the_socket_is_still_replayed(pool):
    """The recovery the retry exists for: the pool refused before anything was written."""
    fake, calls, received = pool
    # `Connection._check_open()` and the pool guards raise this; no bytes were sent.
    fake.raise_with = asyncpg.exceptions.InterfaceError("connection is closed")

    assert await db.Database.fetchval("SELECT 1") == 0.0

    assert fake.served == 2, "the pre-flight failure was not re-issued on a second connection"
    assert len(received) == 1, f"the statement ran {len(received)} times: {received}"
    assert calls == {"init": 1, "close": 1}, calls


async def test_a_handshake_that_dropped_before_fn_ran_is_still_replayed(pool):
    """The pool can lose a connection while establishing one, with no statement in existence.

    `ConnectionDoesNotExistError` is raised on whatever the protocol is awaiting, and during a
    handshake that waiter is the connect future (`protocol/protocol.pyx:85`), so the exception type
    cannot decide on its own. The failure happening outside `fn` is what makes the retry safe.
    """
    fake, calls, received = pool
    fake.acquire_fail = asyncpg.exceptions.ConnectionDoesNotExistError(MID_FLIGHT)

    assert await db.Database.fetchval("SELECT 1") == 0.0

    assert fake.served == 2, "the handshake failure was not re-issued on a second connection"
    assert len(received) == 1, f"the statement ran {len(received)} times: {received}"
    assert calls == {"init": 1, "close": 1}, calls
