"""A pool made on an event loop that has closed is replaced, not reused.

Two `asyncio.run` calls in one process, and every pytest-asyncio test after the first, hit this: the
second run found `Database.pool` set and handed out connections bound to the first, closed loop.
"""
from __future__ import annotations

import asyncio

from core.db import Database


class _FakePool:
    def __init__(self):
        self.terminated = False

    def terminate(self):
        self.terminated = True


def test_a_pool_on_a_closed_loop_is_orphaned():
    loop = asyncio.new_event_loop()
    loop.close()
    fake = _FakePool()
    old = (Database.pool, Database._pool_loop, Database._pool_made)
    try:
        Database.pool, Database._pool_loop, Database._pool_made = fake, loop, fake
        assert Database._pool_orphaned() is True
    finally:
        Database.pool, Database._pool_loop, Database._pool_made = old


def test_a_pool_with_no_recorded_loop_is_not_orphaned():
    """Tests that assign a fake pool directly record no loop and must stay untouched."""
    fake = _FakePool()
    old = (Database.pool, Database._pool_loop, Database._pool_made)
    try:
        Database.pool, Database._pool_loop = fake, None
        assert Database._pool_orphaned() is False
    finally:
        Database.pool, Database._pool_loop, Database._pool_made = old


def test_dropping_an_orphan_terminates_it_and_clears_the_slot():
    loop = asyncio.new_event_loop()
    loop.close()
    fake = _FakePool()
    old = (Database.pool, Database._pool_loop, Database._pool_made)
    try:
        Database.pool, Database._pool_loop, Database._pool_made = fake, loop, fake
        Database._drop_orphaned_pool()
        assert fake.terminated is True
        assert Database.pool is None and Database._pool_loop is None
    finally:
        Database.pool, Database._pool_loop, Database._pool_made = old


def test_a_live_pool_is_left_alone():
    loop = asyncio.new_event_loop()
    try:
        fake = _FakePool()
        old = (Database.pool, Database._pool_loop, Database._pool_made)
        try:
            Database.pool, Database._pool_loop, Database._pool_made = fake, loop, fake
            Database._drop_orphaned_pool()
            assert fake.terminated is False and Database.pool is fake
        finally:
            Database.pool, Database._pool_loop, Database._pool_made = old
    finally:
        loop.close()


async def _use_the_pool():
    pool = await Database.init()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT 1")


def test_a_second_asyncio_run_gets_a_working_pool():
    old = (Database.pool, Database._pool_loop, Database._pool_made)
    Database.pool, Database._pool_loop, Database._pool_made = None, None, None
    try:
        assert asyncio.run(_use_the_pool()) == 1
        assert asyncio.run(_use_the_pool()) == 1
    finally:
        Database.pool, Database._pool_loop, Database._pool_made = old


def test_a_directly_assigned_pool_is_not_orphaned_by_an_old_loop_marker():
    """A test that sets `Database.pool` to a fake must not inherit the previous pool's closed loop."""
    loop = asyncio.new_event_loop()
    loop.close()
    real, fake = _FakePool(), _FakePool()
    old = (Database.pool, Database._pool_loop, Database._pool_made)
    try:
        Database.pool, Database._pool_loop, Database._pool_made = fake, loop, real
        assert Database._pool_orphaned() is False
    finally:
        Database.pool, Database._pool_loop, Database._pool_made = old
