"""faction_ai fix 2: pirate drift writes relative values scoped by session, a debit never empties the treasury.

Every write lands in a scratch session (900-999). Sessions 3 and 5 are not touched.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest_asyncio  # noqa: E402

import core.config  # noqa: E402
from core.db import Database  # noqa: E402
from modules import faction_ai  # noqa: E402


async def _wipe(session_id):
    for table in ("ai_decision_log", "factions"):
        await Database.execute(f"DELETE FROM maya_rp.{table} WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", session_id)


@pytest_asyncio.fixture
async def sid(scratch_session, monkeypatch):
    """A scratch session on game day 10 with one pirate (treasury 1000, fleet power 10) and no relations."""
    monkeypatch.setattr(core.config.Config, "SESSION_ID", scratch_session)
    monkeypatch.setenv("RP_SESSION", str(scratch_session))
    monkeypatch.setattr(faction_ai, "_chance", lambda p: True)
    await Database.init()
    await _wipe(scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status, game_day) "
        "VALUES ($1, 'faction ai fix2 scratch', 'active', 10)", scratch_session)
    # factions.name is globally unique; with no relation rows the pirate classifies as `free`.
    fid = await Database.fetchval(
        "INSERT INTO maya_rp.factions (session_id, name, standing, is_pirate, treasury, pirate_fleet_power) "
        "VALUES ($1, $2, 'hostile', true, 1000, 10) RETURNING id",
        scratch_session, f"T3 Pirates {scratch_session}")
    try:
        yield scratch_session, fid
    finally:
        await _wipe(scratch_session)
        await Database.close()


async def _row(fid):
    row = await Database.fetchrow(
        "SELECT treasury, pirate_fleet_power FROM maya_rp.factions WHERE id=$1", fid)
    return row["treasury"], row["pirate_fleet_power"]


async def _set_treasury(fid, treasury):
    await Database.execute("UPDATE maya_rp.factions SET treasury=$1 WHERE id=$2", treasury, fid)


def _fixed(n):
    return lambda a, b: n


class TestTheDriftWritesRelativeValues:
    async def test_a_concurrent_credit_survives_the_drift(self, sid, monkeypatch):
        scratch, fid = sid
        monkeypatch.setattr(faction_ai, "_randint", _fixed(100))

        async def concurrent_writer(*args, **kwargs):
            # Runs after the snapshot read and before the drift writes.
            await Database.execute(
                "UPDATE maya_rp.factions SET treasury = treasury + 500, "
                "pirate_fleet_power = pirate_fleet_power + 7 WHERE id=$1", fid)

        monkeypatch.setattr(faction_ai, "log_decision", concurrent_writer)
        out = await faction_ai.run_tick(scratch)
        assert out == {"factions": 1, "decisions": 1}, out
        assert await _row(fid) == (1600, 117)

    async def test_a_debit_the_treasury_cannot_cover_is_skipped(self, sid, monkeypatch):
        scratch, fid = sid
        await _set_treasury(fid, 50)
        monkeypatch.setattr(faction_ai, "_randint", lambda a, b: a)
        out = await faction_ai.run_tick(scratch)
        assert out == {"factions": 1, "decisions": 1}, out
        assert await _row(fid) == (50, 10)

    async def test_a_debit_the_treasury_covers_applies(self, sid, monkeypatch):
        scratch, fid = sid
        await _set_treasury(fid, 20000)
        monkeypatch.setattr(faction_ai, "_randint", lambda a, b: a)
        await faction_ai.run_tick(scratch)
        assert await _row(fid) == (5000, 10)

    async def test_a_credit_applies_to_a_negative_balance(self, sid, monkeypatch):
        scratch, fid = sid
        await _set_treasury(fid, -100)
        monkeypatch.setattr(faction_ai, "_randint", lambda a, b: b)
        await faction_ai.run_tick(scratch)
        assert await _row(fid) == (14900, 15)


class TestTheSessionIsResolved:
    def test_the_module_never_reads_config_for_a_session(self):
        source = pathlib.Path(faction_ai.__file__).read_text()
        assert "Config.SESSION_ID" not in source
