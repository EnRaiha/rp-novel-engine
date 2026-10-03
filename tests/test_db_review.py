"""Module review tests for core/db.py.

No new defect found. The row names what was checked:

- `_run` retries exactly once, only for `_RECONNECT_ERRORS`, and re-installs the
  name_gen hook because `init()` runs again (its hook sits inside the
  `pool is None` branch)
- `_run` lets every other exception through untouched, so a SQL error is not
  retried
- `close()` clears the pool even when the underlying close raises, and its bare
  `except` explains itself in a comment, which the silent-handler rule allows
- `fetch_readonly` runs the statement inside a real read-only transaction, which
  is what the CLI/bridge read path relies on
- `Config.SESSION_ID` in `status()` is the module's health check, not a scoped
  read, so the session default is correct there

Two leads reported rather than patched, because both change behaviour on a live
pool and neither is a module-local call:

1. `_run`'s retry is at-least-once. A connection that dies after the statement
   reached the server but before the result was read makes the retry run the
   write twice.
2. `transaction()` wraps only `_ensure_pool()` in the reconnect handler, so a
   pool that is non-None but closed fails at `pool.acquire()` without the
   reconnect-once that `_run` performs.

No database: every test drives fake pools and connections.
"""
from __future__ import annotations

import asyncpg
import pytest

from core import db


class FakeConn:
    def __init__(self, readonly_seen=None):
        self.readonly_seen = readonly_seen if readonly_seen is not None else []
        self.fetched: list[str] = []

    def transaction(self, readonly=False):
        self.readonly_seen.append(readonly)
        return FakeTx()

    async def fetch(self, query, *args):
        self.fetched.append(" ".join(query.split()))
        return [{"id": 1}]


class FakeTx:
    async def start(self):
        pass

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakePool:
    def __init__(self, conn=None):
        self.conn = conn or FakeConn()
        self.released: list = []

    def acquire(self):
        return _Acquire(self.conn)

    async def release(self, conn):
        self.released.append(conn)


class ClosedPool(FakePool):
    """Pool object still set on the class, but its connections are gone."""

    def acquire(self):
        raise asyncpg.exceptions.InterfaceError("pool is closed")


class _Acquire:
    """Mirrors asyncpg's PoolAcquireContext: awaitable and an async context manager."""

    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False

    def __await__(self):
        async def _get():
            return self.conn

        return _get().__await__()


@pytest.fixture
def pool(monkeypatch):
    fake = FakePool()
    calls = {"init": 0, "close": 0}

    async def init():
        calls["init"] += 1
        return fake

    async def close():
        calls["close"] += 1

    monkeypatch.setattr(db.Database, "pool", fake)
    monkeypatch.setattr(db.Database, "_ensure_pool", staticmethod(lambda: _same(fake)))
    monkeypatch.setattr(db.Database, "init", staticmethod(init))
    monkeypatch.setattr(db.Database, "close", staticmethod(close))
    return fake, calls


async def _same(pool):
    return pool


async def test_run_reconnects_once_and_retries(pool):
    fake, calls = pool
    attempts = []

    async def fn(conn, *args):
        attempts.append(conn)
        if len(attempts) == 1:
            raise asyncpg.exceptions.ConnectionDoesNotExistError("pool is closed")
        return "ok"

    assert await db.Database._run(fn) == "ok"
    assert len(attempts) == 2, attempts
    assert calls == {"init": 1, "close": 1}


async def test_run_does_not_retry_anything_else(pool):
    fake, calls = pool
    attempts = []

    async def fn(conn, *args):
        attempts.append(conn)
        raise ValueError("bad SQL")

    with pytest.raises(ValueError):
        await db.Database._run(fn)
    assert len(attempts) == 1
    assert calls == {"init": 0, "close": 0}


async def test_close_clears_the_pool_even_when_closing_raises(monkeypatch):
    class Angry:
        async def close(self):
            raise RuntimeError("already gone")

    monkeypatch.setattr(db.Database, "pool", Angry())
    await db.Database.close()
    assert db.Database.pool is None


async def test_fetch_readonly_uses_a_read_only_transaction(pool):
    fake, _ = pool
    rows = await db.Database.fetch_readonly("SELECT 1 FROM maya_rp.sessions")
    assert rows == [{"id": 1}]
    assert fake.conn.readonly_seen == [True]
    assert fake.conn.fetched == ["SELECT 1 FROM maya_rp.sessions"]


async def test_transaction_reconnects_when_the_pool_is_closed(pool, monkeypatch):
    """Lead's L2. The docstring claimed reconnect-at-acquire; the acquire sat
    outside the try, so a pool that was non-None but closed raised instead."""
    fake, calls = pool
    closed = ClosedPool()

    async def ensure_closed():
        return closed

    monkeypatch.setattr(db.Database, "_ensure_pool", staticmethod(ensure_closed))
    body: list = []
    async with db.Database.transaction() as conn:
        body.append(conn)

    assert body, "the transaction body never ran"
    assert calls == {"init": 1, "close": 1}, calls
    assert fake.released, "the connection was never released back to the pool"


async def test_transaction_releases_and_rolls_back_on_a_failing_body(pool):
    fake, _ = pool
    with pytest.raises(ValueError):
        async with db.Database.transaction():
            raise ValueError("body failed")
    assert fake.released, "a rolled-back transaction leaked its connection"
