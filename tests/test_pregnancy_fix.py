"""pregnancy fix: a birth is claimed once and commits with its event, and a stale tick cannot revert it.

Real database. Every write lands in a scratch session (900-999) and `Config.SESSION_ID` points at it,
so no default can reach sessions 3 and 5.
"""
from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio

import core.config
from core.db import Database
from modules import pregnancy

_TABLES = ("events", "pregnancies")


async def _wipe(session_id):
    for table in _TABLES:
        await Database.execute(f"DELETE FROM maya_rp.{table} WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", session_id)


@pytest_asyncio.fixture
async def sid(scratch_session, monkeypatch):
    """A scratch session row at game day 400. `Config.SESSION_ID` points at it."""
    monkeypatch.setattr(core.config.Config, "SESSION_ID", scratch_session)
    await Database.init()
    await _wipe(scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status, game_day) "
        "VALUES ($1, 'pregnancy fix scratch', 'active', 400)", scratch_session)
    try:
        yield scratch_session
    finally:
        await _wipe(scratch_session)
        await Database.close()


async def _preg(sid, status="active", conceived=100, due=370, trimester=1, mother="Seraphina"):
    return await Database.fetchval(
        """INSERT INTO maya_rp.pregnancies
           (session_id, mother_name, conceived_game_day, due_game_day, status, trimester)
           VALUES ($1,$2,$3,$4,$5,$6) RETURNING id""",
        sid, mother, conceived, due, status, trimester)


async def _births(sid):
    return await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.events WHERE session_id=$1 AND event_type='birth'", sid)


async def _status(pid):
    return await Database.fetchval("SELECT status FROM maya_rp.pregnancies WHERE id=$1", pid)


async def test_a_birth_is_claimed_once(sid):
    pid = await _preg(sid)

    first = await pregnancy._roll_birth(sid, 400, pid, "Seraphina")
    second = await pregnancy._roll_birth(sid, 400, pid, "Seraphina")

    assert isinstance(first, dict), first
    assert second is None, second
    assert await _births(sid) == 1
    stored = await Database.fetchval("SELECT baby_name FROM maya_rp.pregnancies WHERE id=$1", pid)
    assert stored == first["name"]


async def test_a_failed_event_keeps_the_pregnancy_open(sid):
    pid = await _preg(sid)

    with pytest.raises(Exception):
        await pregnancy._roll_birth(sid, 400, pid, "Bad\x00Name")

    assert await _status(pid) == "active"
    assert await _births(sid) == 0


async def test_a_stale_snapshot_does_not_revert_a_birth(sid, monkeypatch):
    pid = await _preg(sid, conceived=100, due=500, trimester=1)
    real_fetch = Database.fetch

    async def stale_fetch(sql, *args):
        rows = await real_fetch(sql, *args)
        await Database.execute(
            "UPDATE maya_rp.pregnancies SET status='birthed' WHERE session_id=$1", sid)
        return rows

    monkeypatch.setattr(pregnancy.Database, "fetch", stale_fetch)

    await pregnancy.advance(sid)

    assert await _status(pid) == "birthed"


async def test_one_bad_row_keeps_the_other_birth(sid, monkeypatch):
    bad = await _preg(sid, mother="Alma")
    good = await _preg(sid, mother="Beatrix")
    real_roll = pregnancy._roll_birth

    async def flaky(session_id, gd, preg_id, mother_name):
        if preg_id == bad:
            raise RuntimeError("roll failed")
        return await real_roll(session_id, gd, preg_id, mother_name)

    monkeypatch.setattr(pregnancy, "_roll_birth", flaky)

    out = await pregnancy.advance(sid)

    assert len(out["births"]) == 1, out
    assert len(out["errors"]) == 1, out
    assert out["errors"][0]["id"] == bad
    assert await _status(good) == "birthed"
    assert await _status(bad) == "active"


async def test_concurrent_births_write_one_event(sid):
    pid = await _preg(sid)
    await asyncio.gather(*[Database.fetchval("SELECT 1") for _ in range(4)])

    results = await asyncio.gather(
        pregnancy._roll_birth(sid, 400, pid, "Seraphina"),
        pregnancy._roll_birth(sid, 400, pid, "Seraphina"))

    assert sum(r is not None for r in results) == 1, results
    assert await _births(sid) == 1
