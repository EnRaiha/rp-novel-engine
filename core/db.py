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
        """Run fn(conn, *args) with ONE reconnect retry on dead-pool errors."""
        try:
            pool = await cls._ensure_pool()
            async with pool.acquire() as conn:
                return await fn(conn, *args)
        except _RECONNECT_ERRORS as e:
            info("db", f"Pool connection lost ({type(e).__name__}) — reconnecting once")
            await cls.close()
            pool = await cls.init()
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
        Reconnects once if the pool is dead at acquire time."""
        try:
            pool = await cls._ensure_pool()
        except _RECONNECT_ERRORS:
            info("db", "Pool lost at transaction start — reconnecting once")
            await cls.close()
            pool = await cls.init()
        async with pool.acquire() as conn:
            tx = conn.transaction()
            await tx.start()
            try:
                yield conn
                await tx.commit()
            except Exception:
                await tx.rollback()
                raise

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
