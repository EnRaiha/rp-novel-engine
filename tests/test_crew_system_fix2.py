"""crew_system: the pool debit is relative and guarded, a destroyed hull stays destroyed, and the
allocator spends the pool on an empty roster.

Every test runs on a scratch session with its own `sessions`, `resources` and `ships` rows.
"""
from __future__ import annotations

import asyncio
import contextlib
import pathlib
import sys

import pytest
import pytest_asyncio

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import Database  # noqa: E402
from modules import crew_system  # noqa: E402

#: Child rows first: crew_roster and the logs reference ships.
_OWNED = ("crew_allocation_log", "crew_consumption_log", "crew_production_log", "crew_roster",
          "ships", "resources")


async def _clear(sid: int) -> None:
    for table in _OWNED:
        await Database.execute(f"DELETE FROM maya_rp.{table} WHERE session_id = $1", sid)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", sid)


@pytest_asyncio.fixture
async def crew_session(scratch_session):
    """A scratch campaign at day 100 with `crew_pool = 10` and no ships."""
    await Database.init()
    await _clear(scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status, game_day) VALUES ($1, 'crew fix2', 'active', 100)",
        scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.resources (session_id, crew_pool) VALUES ($1, 10)", scratch_session)
    yield scratch_session
    await _clear(scratch_session)
    await Database.close()


async def _ship(sid: int, *, crew: int = 10, crew_current: int = 0, status: str = "active",
                tier: int = 1, min_clearance: int = 1) -> int:
    return await Database.fetchval(
        "INSERT INTO maya_rp.ships (session_id, name, crew, crew_current, status, tier, min_clearance)"
        " VALUES ($1, 'fix2 hull', $2, $3, $4, $5, $6) RETURNING id",
        sid, crew, crew_current, status, tier, min_clearance)


async def _pool(sid: int) -> int:
    return await Database.fetchval("SELECT crew_pool FROM maya_rp.resources WHERE session_id = $1", sid)


async def _consumed(sid: int) -> int:
    return await Database.fetchval(
        "SELECT crew_consumed_total FROM maya_rp.resources WHERE session_id = $1", sid)


async def _ship_row(ship_id: int):
    return await Database.fetchrow(
        "SELECT status, crew_current, undercrewed_penalty FROM maya_rp.ships WHERE id = $1", ship_id)


class _ConnSpy:
    """A pooled connection that records every statement it runs."""

    def __init__(self, conn, log):
        self._conn, self._log = conn, log

    def __getattr__(self, name):
        attr = getattr(self._conn, name)
        if name not in ("fetch", "fetchrow", "fetchval", "execute", "executemany"):
            return attr

        async def recorded(query, *args):
            self._log.append(" ".join(query.split()))
            return await attr(query, *args)
        return recorded


class _DatabaseSpy:
    """`Database` with every statement, in or out of a transaction, recorded in `log`."""

    def __init__(self, log):
        self.log = log

    def __getattr__(self, name):
        attr = getattr(Database, name)
        if name not in ("fetch", "fetchrow", "fetchval", "execute"):
            return attr

        async def recorded(query, *args):
            self.log.append(" ".join(query.split()))
            return await attr(query, *args)
        return recorded

    @contextlib.asynccontextmanager
    async def transaction(self):
        async with Database.transaction() as conn:
            yield _ConnSpy(conn, self.log)


# ── M2: consume_crew ─────────────────────────────────────────────────────


async def test_a_negative_requirement_does_not_mint_crew(crew_session):
    ship = await _ship(crew_session)

    out = await crew_system.consume_crew(crew_session, ship, -5)

    assert "error" in out, out
    assert await _pool(crew_session) == 10
    assert await _consumed(crew_session) == 0
    assert (await _ship_row(ship))["crew_current"] == 0


@pytest.mark.parametrize("status", ["destroyed", "lost"])
async def test_a_destroyed_or_lost_ship_is_not_revived(crew_session, status):
    ship = await _ship(crew_session, status=status)

    out = await crew_system.consume_crew(crew_session, ship, 5)

    assert "error" in out, out
    row = await _ship_row(ship)
    assert row["status"] == status
    assert row["crew_current"] == 0
    assert await _pool(crew_session) == 10
    assert await _consumed(crew_session) == 0


async def test_a_shortage_does_not_revive_a_destroyed_ship_either(crew_session):
    ship = await _ship(crew_session, status="destroyed")

    out = await crew_system.consume_crew(crew_session, ship, 50)

    assert "error" in out, out
    assert (await _ship_row(ship))["status"] == "destroyed"


async def test_a_launch_debits_the_pool_and_logs_it(crew_session):
    ship = await _ship(crew_session, status="in_build")

    out = await crew_system.consume_crew(crew_session, ship, 4)

    assert out == {"consumed": 4, "pool_after": 6, "status": "active"}
    assert await _pool(crew_session) == 6
    assert await _consumed(crew_session) == 4
    row = await _ship_row(ship)
    assert (row["status"], row["crew_current"]) == ("active", 4)
    logged = await Database.fetchrow(
        "SELECT amount, pool_after, game_day FROM maya_rp.crew_consumption_log WHERE session_id = $1",
        crew_session)
    assert (logged["amount"], logged["pool_after"], logged["game_day"]) == (4, 6, 100)


async def test_a_shortage_marks_the_hull_undercrewed(crew_session):
    ship = await _ship(crew_session)

    out = await crew_system.consume_crew(crew_session, ship, 20)

    assert out["status"] == "undercrewed" and out["consumed"] == 10 and out["deficit"] == 10, out
    row = await _ship_row(ship)
    assert (row["status"], row["crew_current"]) == ("undercrewed", 10)


async def test_a_missing_ship_is_still_refused_by_session(crew_session):
    out = await crew_system.consume_crew(crew_session, 999_999_999, 5)

    assert f"not in session {crew_session}" in out["error"], out
    assert await _pool(crew_session) == 10


async def test_the_debit_is_one_guarded_relative_statement(crew_session, monkeypatch):
    ship = await _ship(crew_session)
    log: list[str] = []
    monkeypatch.setattr(crew_system, "Database", _DatabaseSpy(log))

    await crew_system.consume_crew(crew_session, ship, 5)

    debits = [q for q in log if "crew_pool = crew_pool -" in q]
    assert len(debits) == 1, log
    assert "crew_pool >=" in debits[0] and "RETURNING crew_pool" in debits[0], debits[0]
    assert not [q for q in log if "SET crew_pool=$1" in q or "SET crew_pool = $1" in q], log


async def test_two_launches_cannot_both_spend_the_same_crew(crew_session):
    ship_a = await _ship(crew_session)
    ship_b = await _ship(crew_session)

    a, b = await asyncio.gather(
        crew_system.consume_crew(crew_session, ship_a, 10),
        crew_system.consume_crew(crew_session, ship_b, 10))

    assert sorted([a["status"], b["status"]]) == ["active", "undercrewed"], (a, b)
    assert await _pool(crew_session) == 0
    assert await _consumed(crew_session) == 10
    crewed = await Database.fetchval(
        "SELECT SUM(crew_current) FROM maya_rp.ships WHERE session_id = $1 AND status = 'active'",
        crew_session)
    assert crewed == 10


# ── M3: ai_allocate_crew ─────────────────────────────────────────────────


async def _roster(sid: int, ship_id: int | None = None) -> int:
    if ship_id is None:
        return await Database.fetchval(
            "SELECT COUNT(*) FROM maya_rp.crew_roster WHERE session_id = $1", sid)
    return await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.crew_roster WHERE session_id = $1 AND ship_id = $2"
        " AND status = 'active'", sid, ship_id)


async def test_the_allocator_spends_the_pool_when_the_roster_is_empty(crew_session):
    await Database.execute("UPDATE maya_rp.resources SET crew_pool = 30 WHERE session_id = $1", crew_session)
    ship = await _ship(crew_session, crew=10)
    assert await _roster(crew_session) == 0

    out = await crew_system.ai_allocate_crew(crew_session)

    assert out["allocated"] == 10 and out["pool_after"] == 20, out
    assert await _pool(crew_session) == 20
    assert await _roster(crew_session, ship) == 10
    row = await _ship_row(ship)
    assert (row["status"], row["crew_current"]) == ("active", 10)
    logged = await Database.fetchval(
        "SELECT crew_assigned FROM maya_rp.crew_allocation_log WHERE session_id = $1 AND ship_id = $2",
        crew_session, ship)
    assert logged == 10


async def test_the_allocator_creates_only_the_shortfall_of_roster_rows(crew_session):
    await Database.execute("UPDATE maya_rp.resources SET crew_pool = 30 WHERE session_id = $1", crew_session)
    ship = await _ship(crew_session, crew=10)
    for i in range(3):
        await Database.execute(
            "INSERT INTO maya_rp.crew_roster (session_id, name) VALUES ($1, $2)",
            crew_session, f"fix2 free hand {i}")

    out = await crew_system.ai_allocate_crew(crew_session)

    assert out["allocated"] == 10, out
    assert await _roster(crew_session) == 10
    assert await _roster(crew_session, ship) == 10
    assert await _pool(crew_session) == 20


async def test_a_short_pool_leaves_the_hull_undercrewed(crew_session):
    ship = await _ship(crew_session, crew=14)

    out = await crew_system.ai_allocate_crew(crew_session)

    assert out["allocated"] == 10 and out["pool_after"] == 0, out
    row = await _ship_row(ship)
    assert (row["status"], row["crew_current"]) == ("undercrewed", 10)
    assert float(row["undercrewed_penalty"]) == pytest.approx(round(4 / 14, 3))
    assert await _pool(crew_session) == 0


async def test_a_c5_hull_gets_screened_clearance_5_crew(crew_session):
    ship = await _ship(crew_session, crew=4, tier=5, min_clearance=5)

    out = await crew_system.ai_allocate_crew(crew_session)

    assert out["allocated"] == 4, out
    rows = await Database.fetch(
        "SELECT clearance_level, screened FROM maya_rp.crew_roster WHERE session_id = $1 AND ship_id = $2",
        crew_session, ship)
    assert len(rows) == 4 and all(r["clearance_level"] == 5 and r["screened"] for r in rows), rows


async def test_the_pool_debit_is_guarded_and_relative(crew_session, monkeypatch):
    await Database.execute("UPDATE maya_rp.resources SET crew_pool = 30 WHERE session_id = $1", crew_session)
    await _ship(crew_session, crew=10)
    log: list[str] = []
    monkeypatch.setattr(crew_system, "Database", _DatabaseSpy(log))

    await crew_system.ai_allocate_crew(crew_session)

    debits = [q for q in log if "crew_pool = crew_pool -" in q]
    assert len(debits) == 1, log
    assert "crew_pool >=" in debits[0] and "RETURNING crew_pool" in debits[0], debits[0]
    assert not [q for q in log if "SET crew_pool=$1" in q or "SET crew_pool = $1" in q], log


async def test_the_debit_applies_to_the_pool_as_it_is_now_not_as_it_was_read(crew_session, monkeypatch):
    """Another writer takes 5 after the allocator read 30: 30 - 5 - 10 = 15, not 30 - 10 = 20."""
    from core import name_gen

    await Database.execute("UPDATE maya_rp.resources SET crew_pool = 30 WHERE session_id = $1", crew_session)
    await _ship(crew_session, crew=10)
    real = name_gen.NameGenerator.unique_crew_name
    state = {"fired": False}

    async def meanwhile(self, prefix=""):
        if not state["fired"]:
            state["fired"] = True
            await Database.execute(
                "UPDATE maya_rp.resources SET crew_pool = crew_pool - 5 WHERE session_id = $1", crew_session)
        return await real(self, prefix)

    monkeypatch.setattr(name_gen.NameGenerator, "unique_crew_name", meanwhile)

    out = await crew_system.ai_allocate_crew(crew_session)

    assert state["fired"], "the concurrent debit never ran"
    assert out["allocated"] == 10, out
    assert await _pool(crew_session) == 15


async def test_the_allocator_leaves_a_hull_destroyed_after_the_read(crew_session, monkeypatch):
    """The hull is destroyed between the allocator's ship read and its write."""
    from core import name_gen

    await Database.execute("UPDATE maya_rp.resources SET crew_pool = 30 WHERE session_id = $1", crew_session)
    ship = await _ship(crew_session, crew=10)
    real = name_gen.NameGenerator.unique_crew_name
    state = {"fired": False}

    async def meanwhile(self, prefix=""):
        if not state["fired"]:
            state["fired"] = True
            await Database.execute("UPDATE maya_rp.ships SET status = 'destroyed' WHERE id = $1", ship)
        return await real(self, prefix)

    monkeypatch.setattr(name_gen.NameGenerator, "unique_crew_name", meanwhile)

    out = await crew_system.ai_allocate_crew(crew_session)

    assert state["fired"], "the destruction never ran"
    assert out["allocated"] == 0, out
    row = await _ship_row(ship)
    assert (row["status"], row["crew_current"]) == ("destroyed", 0)
    assert await _pool(crew_session) == 30
    assert await _roster(crew_session, ship) == 0


async def test_an_empty_pool_allocates_nothing(crew_session):
    await Database.execute("UPDATE maya_rp.resources SET crew_pool = 0 WHERE session_id = $1", crew_session)
    ship = await _ship(crew_session, crew=10)

    out = await crew_system.ai_allocate_crew(crew_session)

    assert out["allocated"] == 0, out
    assert out["pool_after"] == 0, "run_tick reads pool_after from every result"
    assert await _roster(crew_session, ship) == 0
