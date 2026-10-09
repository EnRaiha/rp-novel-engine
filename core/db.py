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
import asyncio
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

#: The reconnect errors that prove nothing was sent even though `fn` ran.
#:
#: `Connection._check_open()` and the pool's own guards raise `InterfaceError` before a statement is
#: serialised, so re-issuing the call cannot apply a write twice.
#:
#: The other two prove nothing on their own. `ConnectionDoesNotExistError` has one raise site in
#: asyncpg 0.31.0, `protocol/protocol.pyx:691`, and it fires on whatever the protocol is awaiting
#: when the connection is lost: the operation's future for a statement, and the connect future
#: during a handshake (`protocol/protocol.pyx:85`). The type cannot say whether a statement exists,
#: so `_run` decides on where the failure happened rather than on the type alone.
_PRE_FLIGHT_ERRORS = (asyncpg.exceptions.InterfaceError,)


class Database:
    """One pool, one DSN, reconnection + transaction support."""

    pool: asyncpg.Pool | None = None
    _lock: asyncio.Lock | None = None
    _lock_loop: asyncio.AbstractEventLoop | None = None
    _fallback_warned: bool = False

    @classmethod
    def _pool_lock(cls) -> asyncio.Lock:
        """The pool-creation lock of the running loop, created on first use.

        An `asyncio.Lock` belongs to one loop; the test suite and the CLI start several. A lock
        made at import would be bound to the wrong one, so it is rebuilt when the loop changes.

        @returns the lock for the running event loop.
        """
        loop = asyncio.get_running_loop()
        if cls._lock is None or cls._lock_loop is not loop:
            cls._lock, cls._lock_loop = asyncio.Lock(), loop
        return cls._lock

    @classmethod
    async def init(cls) -> asyncpg.Pool:
        """Return the pool, creating it once.

        After a PG restart N tasks hit a dead pool together; each saw `pool is None` across the
        `create_pool` await and built its own, so the earlier pools leaked. The lock plus the
        re-check inside makes the first creator the only one.

        @returns the live pool.
        """
        if cls.pool is not None:
            return cls.pool
        async with cls._pool_lock():
            return await cls._create_locked()

    @classmethod
    async def _create_locked(cls) -> asyncpg.Pool:
        """Create the pool if absent. The caller holds `_pool_lock()`."""
        if cls.pool is None:
            if Config.DSN_FALLBACK_USED and not cls._fallback_warned:
                cls._fallback_warned = True
                warn("db", "RP_ENGINE_DSN is not set: using the DSN built into core/config.py")
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
    async def _reconnect(cls, failed: asyncpg.Pool | None) -> asyncpg.Pool:
        """Replace `failed` with a fresh pool, once however many tasks saw it die.

        Each failing task used to `close()` then `init()`: one task's close could shut the pool
        another had just built, and a waiting `close()` on a dead pool hangs on its connections.
        Only the task whose failing pool is still `cls.pool` swaps it; the rest reuse the new one.
        The dead pool is terminated, not closed: `close()` waits for connections that will never
        return.

        @param failed - the pool the caller was using when it failed (None when it never got one).
        @returns the live pool.
        """
        async with cls._pool_lock():
            if failed is not None and cls.pool is failed:
                cls.pool = None
                try:
                    failed.terminate()
                except Exception as exc:  # noqa: BLE001 - a dead pool failing to die must not mask the retry
                    warn("db", f"terminate of dead pool failed: {exc}")
            return await cls._create_locked()

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

        The retry re-issues the call only when nothing can have been written. Two cases qualify:
        the pool failed before `fn` ran, or `fn` met asyncpg's own pre-flight guard, which refuses
        before a statement is serialised. An error raised from inside `fn` that is not pre-flight
        means the statement was written, so it is not replayed: the client cannot tell whether the
        server applied it, and a second execution of a relative write
        (`SET credits = credits - $1`) charges the session twice with no way to detect it.
        """
        entered = False
        pool = None
        try:
            pool = await cls._ensure_pool()
            async with pool.acquire() as conn:
                entered = True
                return await fn(conn, *args)
        except _RECONNECT_ERRORS as e:
            info("db", f"Pool connection lost ({type(e).__name__}) — reconnecting once")
            pool = await cls._reconnect(pool)
            if entered and not isinstance(e, _PRE_FLIGHT_ERRORS):
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
        pool = None
        try:
            pool = await cls._ensure_pool()
            conn = await pool.acquire()
        except _RECONNECT_ERRORS as e:
            info("db", f"Pool lost at transaction start ({type(e).__name__}) — reconnecting once")
            pool = await cls._reconnect(pool)
            conn = await pool.acquire()
        try:
            tx = conn.transaction()
            await tx.start()
            committing = False
            try:
                yield conn
                committing = True
                await tx.commit()
            except Exception:
                # A failed commit leaves the transaction finished; rolling it back raised
                # "already committed/rolled back" and replaced the real error (serialization
                # failure, deferred constraint) with that one.
                if not committing:
                    try:
                        await tx.rollback()
                    except Exception as rb:  # noqa: BLE001 - the caller's error is the one to surface
                        warn("db", f"rollback failed after {type(rb).__name__}: {rb}")
                raise
        finally:
            await pool.release(conn)

    @classmethod
    async def status(cls) -> dict:
        """Quick health check — connection + table count + session row."""
        # Resolved per call: Config.SESSION_ID is fixed at import and a long-lived process would
        # report the session it started on. An unresolved session is reported, not raised, so the
        # health check still says whether the database is up.
        from core.session import resolve_session

        sid = None
        error = None
        try:
            sid = resolve_session(None)
            if sid is None:
                error = "maintenance mode resolves no session"
        except RuntimeError as exc:
            error = str(exc)
        pool = await cls._ensure_pool()
        async with pool.acquire() as conn:
            tables = await conn.fetchval(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema='maya_rp' AND table_type='BASE TABLE'"
            )
            session = None
            if sid is not None:
                session = await conn.fetchrow(
                    "SELECT id, name, status, game_day FROM maya_rp.sessions WHERE id=$1",
                    sid,
                )
            out = {
                "connected": True,
                "tables": tables,
                "session": dict(session) if session else None,
            }
            if error:
                out["error"] = error
            return out
