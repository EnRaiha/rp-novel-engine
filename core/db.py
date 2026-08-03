#!/usr/bin/env python3
"""Database — asyncpg pool with reconnection, transaction support, driven by Config."""
from __future__ import annotations
import asyncpg
from contextlib import asynccontextmanager
from core.config import Config
from core.log import info


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
        return cls.pool

    @classmethod
    async def close(cls) -> None:
        if cls.pool:
            await cls.pool.close()
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
    async def fetchrow(cls, query: str, *args) -> asyncpg.Record | None:
        pool = await cls._ensure_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    @classmethod
    async def fetch(cls, query: str, *args) -> list[asyncpg.Record]:
        pool = await cls._ensure_pool()
        async with pool.acquire() as conn:
            return await conn.fetch(query, *args)

    @classmethod
    async def execute(cls, query: str, *args) -> str:
        pool = await cls._ensure_pool()
        async with pool.acquire() as conn:
            return await conn.execute(query, *args)

    @classmethod
    async def fetchval(cls, query: str, *args):
        """Fetch a single value from the first column using native asyncpg fetchval."""
        pool = await cls._ensure_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(query, *args)

    @classmethod
    @asynccontextmanager
    async def transaction(cls):
        """Transaction context manager — auto-rollback on exception."""
        pool = await cls._ensure_pool()
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
        """Quick health check — table count + session row."""
        pool = await cls._ensure_pool()
        async with pool.acquire() as conn:
            tables = await conn.fetchval(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema='maya_rp' AND table_type='BASE TABLE'"
            )
            session = await conn.fetchrow(
                "SELECT id, name, status FROM maya_rp.sessions WHERE id=$1",
                Config.SESSION_ID,
            )
        return {
            "connected": True,
            "tables": tables,
            "session": dict(session) if session else None,
        }
