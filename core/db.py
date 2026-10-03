#!/usr/bin/env python3
"""Database — asyncpg pool with reconnection, transaction support, driven by Config.

QA fix 2026-08-14 (BUG-4): dead-pool reconnection. If PostgreSQL restarts,
asyncpg connections die but the pool object stays non-None, so every query
raised ConnectionDoesNotExistError until process restart. `_run()` now catches
dead-pool errors, closes the stale pool, re-inits once, and retries the query.
No health-check-per-query (that was removed in the Jul-31 perf pass); the
reconnect path only executes on actual errors.
"""

from __future__ import annotations
import asyncpg
from contextlib import asynccontextmanager
from core.config import Config
from core.log import warn
from core.log import info

# Errors that indicate a dead/lost pool (PG restart, network blip).
_RECONNECT_ERRORS = (
    asyncpg.exceptions.ConnectionDoesNotExistError,
    asyncpg.exceptions.InterfaceError,
    asyncpg.exceptions.PostgresConnectionError,
)

#: The only reconnect errors that prove nothing reached the socket.
#:
#: `Connection._check_open()` and the pool's own guards raise `InterfaceError` before a statement is
#: sent, so re-issuing the call cannot apply a write twice.
#:
#: The other two are not replayable. `ConnectionDoesNotExistError` has exactly one raise site in
#: asyncpg 0.31.0, `protocol/protocol.pyx:691`, the `connection_lost` handler, which fires after the
#: statement was written to the socket. Whether the server applied it is unknown to the client, and
#: `PostgresConnectionError` is that error's parent. Replaying either runs the write a second time
#: whenever the first one landed. Nothing is lost by refusing: measured against the live database, a
#: holder whose connection died is reconnected by the next `acquire()`, so the common case never
#: reaches this handler.
_PRE_FLIGHT_ERRORS = (asyncpg.exceptions.InterfaceError,)


class Database:
    """One pool, one DSN, reconnection + transaction support."""

    pool: asyncpg.Pool | None = None

    @classmethod
    async def init(cls) -> asyncpg.Pool:
        if cls.pool is None:
            cls.pool = await asyncpg.create_pool(
                dsn=Config.DSN,
                min_size=Config.DB_MIN_SIZE,
                max_size=Config.DB_MAX_SIZE,
                timeout=Config.DB_TIMEOUT,
            )
            # The name generator keeps a module-level connection. `set_global_conn` was its one
            # caller-less function: it had no init hook, so the generator it configures could never be
            # reached without a caller passing a connection in. Imported here rather than at the top to
            # keep the DB layer free of an import cycle.
            try:
                from core import name_gen
                name_gen.set_global_conn(cls.pool)
            except Exception as exc:  # noqa: BLE001 - the pool is what matters; the hook is best effort
                # Logged rather than swallowed: the silent-handler gate refused the bare pass, and it is
                # right to. A name generator without a connection is a symptom worth seeing.
                warn("db", f"name_gen hook not installed: {exc}")
        return cls.pool

    @classmethod
    async def close(cls) -> None:
        if cls.pool:
            try:
                await cls.pool.close()
            except Exception:  # deliberate: a failing close during shutdown must not raise
                pass
            cls.pool = None

    @classmethod
    async def _ensure_pool(cls) -> asyncpg.Pool:
        """Return pool, reconnecting only if explicitly closed/null."""
        if cls.pool is not None:
            return cls.pool
        pool = await cls.init()
        info("db", "Pool initialized.")
        return pool

    @classmethod
    async def _run(cls, fn, *args):
        """Run fn(conn, *args) with ONE reconnect retry on dead-pool errors.

        The retry re-issues the call only when the failure happened before anything reached the
        socket. A statement that was already written is never replayed: the client cannot tell
        whether the server applied it, and a second execution of a relative write
        (`SET credits = credits - $1`) charges the session twice with no way to detect it.
        """
        try:
            pool = await cls._ensure_pool()
            async with pool.acquire() as conn:
                return await fn(conn, *args)
        except _RECONNECT_ERRORS as e:
            info("db", f"Pool connection lost ({type(e).__name__}) — reconnecting once")
            await cls.close()
            pool = await cls.init()
            if not isinstance(e, _PRE_FLIGHT_ERRORS):
                raise
            async with pool.acquire() as conn:
                return await fn(conn, *args)

    @classmethod
    async def fetchrow(cls, query: str, *args) -> asyncpg.Record | None:
        return await cls._run(lambda conn: conn.fetchrow(query, *args))

    @classmethod
    async def fetch(cls, query: str, *args) -> list[asyncpg.Record]:
        return await cls._run(lambda conn: conn.fetch(query, *args))

    @classmethod
    async def execute(cls, query: str, *args) -> str:
        return await cls._run(lambda conn: conn.execute(query, *args))

    @classmethod
    async def fetch_readonly(cls, query: str, *args):
        """Run a SELECT inside a real READ ONLY transaction.

        The CLI/bridge query path is advertised as read-only; a start-anchored
        regex is not an enforcement (multi-statement and SELECT … INTO slip
        through). PostgreSQL rejects writes itself here:
        `cannot execute INSERT in a read-only transaction`.
        """
        async def _fn(conn):
            async with conn.transaction(readonly=True):
                return await conn.fetch(query, *args)

        return await cls._run(_fn)

    @classmethod
    async def fetchval(cls, query: str, *args):
        """Fetch a single value from the first column using native asyncpg fetchval."""
        return await cls._run(lambda conn: conn.fetchval(query, *args))

    @classmethod
    @asynccontextmanager
    async def transaction(cls):
        """Transaction context manager — auto-rollback on exception.
        Reconnects once if the pool is dead at acquire time, which is what this
        docstring always claimed: `_ensure_pool` only covers the pool being None,
        so a pool that is non-None but closed failed at `pool.acquire()` without
        the reconnect `_run` performs."""
        try:
            pool = await cls._ensure_pool()
            conn = await pool.acquire()
        except _RECONNECT_ERRORS as e:
            info("db", f"Pool lost at transaction start ({type(e).__name__}) — reconnecting once")
            await cls.close()
            pool = await cls.init()
            conn = await pool.acquire()
        try:
            tx = conn.transaction()
            await tx.start()
            try:
                yield conn
                await tx.commit()
            except Exception:
                await tx.rollback()
                raise
        finally:
            await pool.release(conn)

    @classmethod
    async def status(cls) -> dict:
        """Quick health check — connection + table count + session row."""
        pool = await cls._ensure_pool()
        async with pool.acquire() as conn:
            tables = await conn.fetchval(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema='maya_rp' AND table_type='BASE TABLE'"
            )
            session = await conn.fetchrow(
                "SELECT id, name, status, game_day FROM maya_rp.sessions WHERE id=$1",
                Config.SESSION_ID,
            )
            return {
                "connected": True,
                "tables": tables,
                "session": dict(session) if session else None,
            }
