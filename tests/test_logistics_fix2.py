"""Second pass on modules/logistics.py, against the real database and a scratch session.

Defects covered:

1. A delivery claimed the mission and moved the cargo in two commits. An error between them left the
   mission delivered and the cargo unmoved, and no tick retried it. Both writes share one transaction.
2. "Already in transit" was a check followed by an INSERT. Two simultaneous `transport` calls for one
   cargo both passed the check and made two missions. The cargo row lock serialises them.
3. NaN and inf passed the quantity check. `cargo.quantity` is numeric and stores NaN.
4. The three entry points fell back to `Config.SESSION_ID`, fixed at import. They resolve at call time.
"""
from __future__ import annotations

import asyncio
import contextlib
import pathlib

import pytest
import pytest_asyncio

import modules.image_gen as image_gen
import modules.ideology as ideology
import modules.logistics as logistics
from core.db import Database


async def _wipe(session_id: int) -> None:
    for table in ("transport_missions", "cargo"):
        await Database.execute(f"DELETE FROM maya_rp.{table} WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", session_id)


@pytest_asyncio.fixture
async def sid(scratch_session, monkeypatch):
    await Database.init()
    await _wipe(scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status, game_day) "
        "VALUES ($1,'logistics fix2 scratch','active',10)", scratch_session)
    monkeypatch.setattr("core.config.Config.SESSION_ID", scratch_session)
    monkeypatch.setenv("RP_SESSION", str(scratch_session))
    yield scratch_session
    await Database.init()
    await _wipe(scratch_session)
    await Database.close()


async def _cargo(session_id: int) -> int:
    return await Database.fetchval(
        "INSERT INTO maya_rp.cargo (session_id, item_type, quantity, location_type, location_id) "
        "VALUES ($1,'T3 grain',5,'ship',1) RETURNING id", session_id)


async def _mission_status(session_id: int, mission_id: int) -> str:
    return await Database.fetchval(
        "SELECT status FROM maya_rp.transport_missions WHERE id=$1 AND session_id=$2",
        mission_id, session_id)


async def _location(session_id: int, cargo_id: int):
    row = await Database.fetchrow(
        "SELECT location_type, location_id FROM maya_rp.cargo WHERE id=$1 AND session_id=$2",
        cargo_id, session_id)
    return row["location_type"], row["location_id"]


# ── 1. A delivery commits with its cargo ────────────────────────────────

async def test_a_delivery_moves_the_cargo_and_marks_the_mission(sid):
    cid = await _cargo(sid)
    sent = await logistics.transport(cid, "sector", 3, 12, sid)
    await Database.execute("UPDATE maya_rp.sessions SET game_day=13 WHERE id=$1", sid)

    out = await logistics.run_tick(sid)

    assert out == {"deliveries": 1, "cargo_moved": 1}
    assert await _location(sid, cid) == ("sector", 3)
    assert await _mission_status(sid, sent["mission_id"]) == "delivered"


async def test_a_cargo_write_error_rolls_the_claim_back(sid, monkeypatch):
    cid = await _cargo(sid)
    sent = await logistics.transport(cid, "sector", 3, 12, sid)
    await Database.execute("UPDATE maya_rp.sessions SET game_day=13 WHERE id=$1", sid)

    real_tx = Database.transaction

    class _Proxy:
        def __init__(self, conn):
            self._conn = conn

        async def execute(self, sql, *args, **kw):
            if sql.lstrip().startswith("UPDATE maya_rp.cargo"):
                raise RuntimeError("cargo write failed")
            return await self._conn.execute(sql, *args, **kw)

        def __getattr__(self, name):
            return getattr(self._conn, name)

    @contextlib.asynccontextmanager
    async def failing_tx():
        async with real_tx() as conn:
            yield _Proxy(conn)

    monkeypatch.setattr(Database, "transaction", failing_tx)

    with pytest.raises(RuntimeError):
        await logistics.run_tick(sid)

    assert await _mission_status(sid, sent["mission_id"]) == "in_transit"
    assert await _location(sid, cid) == ("ship", 1)


# ── 2. One cargo takes one mission ──────────────────────────────────────

async def test_two_simultaneous_transports_make_one_mission(sid, monkeypatch):
    cid = await _cargo(sid)
    arrivals: list[int] = []
    both_in = asyncio.Event()

    async def slow_day(session_id, conn=None):
        arrivals.append(session_id)
        if len(arrivals) >= 2:
            both_in.set()
        try:
            await asyncio.wait_for(both_in.wait(), 0.5)
        except asyncio.TimeoutError:
            pass
        return 10

    monkeypatch.setattr(logistics, "_game_day", slow_day)

    results = await asyncio.gather(
        logistics.transport(cid, "sector", 3, 12, sid),
        logistics.transport(cid, "sector", 3, 12, sid))

    made = [r for r in results if "mission_id" in r]
    refused = [r for r in results if "error" in r and "already in transit" in r["error"]]
    open_rows = await Database.fetchval(
        "SELECT count(*) FROM maya_rp.transport_missions "
        "WHERE session_id=$1 AND cargo_id=$2 AND status='in_transit'", sid, cid)
    assert (len(made), len(refused), open_rows) == (1, 1, 1)


# ── 3. A quantity is a finite number above zero ─────────────────────────

@pytest.mark.parametrize("qty", [float("nan"), float("inf"), float("-inf")])
async def test_a_non_finite_quantity_is_refused(sid, qty):
    out = await logistics.create_cargo("grain", qty, "sector", 3, sid)

    assert "greater than zero" in out["error"]
    assert await Database.fetchval(
        "SELECT count(*) FROM maya_rp.cargo WHERE session_id=$1", sid) == 0


# ── 4. The session resolves at call time ────────────────────────────────

@pytest.mark.parametrize("module", [logistics, image_gen, ideology])
def test_no_module_reads_config_for_a_session(module):
    assert "Config.SESSION_ID" not in pathlib.Path(module.__file__).read_text()
