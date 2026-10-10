"""`_spawn` reads only this session's `pirate_zones`.

Real database, scratch sessions only (900-999). `_spawn_fleet` is replaced, so a spawn writes no ship,
faction or alert row: the test reads the zones and records what would have spawned. Session B's zone
carries the same danger level and sits one session away, so a read that forgets `session_id` spawns in
it as well, and in the reference campaign's unprotected zones.
"""
from __future__ import annotations

import pytest_asyncio

from core.db import Database
from modules import pirates
from tests.conftest import _clear_session_rows

#: `scratch_session` is session A. Session B sits 50 ids away and stays inside 900-999.
SECOND_OFFSET = 50

#: Explicit ids above the live serial, so the sequences do not move.
ZONE_A = 990_001
ZONE_B = 990_002
SYSTEM_A = 990_001
SYSTEM_B = 990_002

#: Danger 2 maps to "patrol", and the catalogue holds a patrol template, so the roll reaches
#: `_spawn_fleet` for every zone that comes back from the read.
DANGER = 2


async def _zones_of(session_id: int) -> list[int]:
    rows = await Database.fetch(
        "SELECT system_id FROM maya_rp.pirate_zones WHERE session_id = $1 ORDER BY system_id", session_id)
    return [row["system_id"] for row in rows]


@pytest_asyncio.fixture
async def zones(scratch_session):
    """One active, unprotected zone for session A and one for session B."""
    session_b = 900 + (scratch_session - 900 + SECOND_OFFSET) % 100
    await Database.init()
    await _clear_session_rows(scratch_session)
    await _clear_session_rows(session_b)
    for zone_id, system_id, session_id in ((ZONE_A, SYSTEM_A, scratch_session),
                                           (ZONE_B, SYSTEM_B, session_b)):
        await Database.execute(
            "INSERT INTO maya_rp.pirate_zones"
            " (id, system_id, danger_level, active, protected, session_id)"
            " VALUES ($1, $2, $3, true, false, $4)",
            zone_id, system_id, DANGER, session_id)
    try:
        yield scratch_session, session_b
    finally:
        await _clear_session_rows(scratch_session)
        await _clear_session_rows(session_b)


async def test_spawn_reads_only_this_sessions_zones(zones, monkeypatch):
    session_a, session_b = zones
    assert await _zones_of(session_b) == [SYSTEM_B], "session B's zone is not in place"
    spawned: list[tuple[int, int, str]] = []
    reads: list[str] = []

    async def fake_spawn_fleet(session_id, system_id, template):
        spawned.append((session_id, system_id, template))

    original_fetch = Database.fetch

    async def recording_fetch(sql, *args):
        reads.append(" ".join(sql.split()))
        return await original_fetch(sql, *args)

    monkeypatch.setattr(pirates, "_spawn_fleet", fake_spawn_fleet)
    monkeypatch.setattr(pirates.Database, "fetch", recording_fetch)
    monkeypatch.setattr(pirates.random, "random", lambda: 0.0)   # every zone rolls to a spawn

    await pirates._spawn(session_a)

    assert spawned, "no zone rolled a spawn; the test proves nothing"
    assert {system_id for _, system_id, _ in spawned} == {SYSTEM_A}, spawned
    assert {session_id for session_id, _, _ in spawned} == {session_a}, spawned
    zone_reads = [sql for sql in reads if "pirate_zones" in sql]
    assert zone_reads and "session_id=$1" in zone_reads[0], zone_reads
