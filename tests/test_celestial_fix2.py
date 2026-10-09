"""celestial fix 2: LIKE input is literal, a reveal of a missing system says so, one level rule.

Every write lands in a scratch session (900-999). Sessions 3 and 5 are not touched.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest_asyncio  # noqa: E402

from core.config import Config  # noqa: E402
from core.db import Database  # noqa: E402
from modules import celestial  # noqa: E402

#: Children of `sessions` this file writes, removed before the session row.
_TABLES = ("planets", "territory")


async def _wipe(session_id):
    for table in _TABLES:
        await Database.execute(f"DELETE FROM maya_rp.{table} WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", session_id)


@pytest_asyncio.fixture
async def sid(scratch_session, monkeypatch):
    """A scratch session on game day 10 with no territory and no planets."""
    monkeypatch.setattr(Config, "SESSION_ID", scratch_session)
    await Database.init()
    await _wipe(scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status, game_day) "
        "VALUES ($1, 'celestial fix2', 'active', 10)", scratch_session)
    try:
        yield scratch_session
    finally:
        await _wipe(scratch_session)
        await Database.close()


async def _territory(session_id, name, status, fleet=0):
    await Database.execute(
        "INSERT INTO maya_rp.territory (session_id, system_name, controlling_faction, status, "
        "fleet_presence) VALUES ($1, $2, 'Iron Concord', $3, $4)",
        session_id, name, status, fleet)


async def _planet(session_id, name):
    await Database.execute(
        "INSERT INTO maya_rp.planets (session_id, name, system_name) VALUES ($1, $2, 'fix2-sys')",
        session_id, name)


async def _four_systems(session_id):
    await _territory(session_id, "A", "contested")
    await _territory(session_id, "B", "controlled")
    await _territory(session_id, "C", "lost", fleet=3)
    await _territory(session_id, "D", "neutral", fleet=0)


class TestSearchTreatsInputLiterally:
    async def test_search_matches_wildcards_literally(self, sid):
        for name in ("Port_One", "PortXOne", "100% Ore"):
            await _planet(sid, name)
        underscore = await celestial.search_all(sid, "t_o")
        assert [h["name"] for h in underscore] == ["Port_One"], underscore
        percent = await celestial.search_all(sid, "%")
        assert [h["name"] for h in percent] == ["100% Ore"], percent


class TestARevealOfAMissingSystem:
    async def test_a_reveal_of_an_unknown_system_says_nothing_changed(self, sid):
        out = await celestial.reveal_system(sid, "nowhere-fix2", "scanned")
        assert out["revealed"] is False, out
        assert "no territory row" in out["reason"], out
        rows = await Database.fetchval(
            "SELECT COUNT(*) FROM maya_rp.territory WHERE session_id=$1", sid)
        assert rows == 0


class TestOneLevelRule:
    async def test_both_readers_agree_on_a_contested_system(self, sid):
        await _four_systems(sid)
        expected = {"A": "explored", "B": "colonized", "C": "surveyed", "D": "scanned"}
        listed = {s["system"]: s["level"] for s in await celestial.get_visible_systems(sid, "scanned")}
        for name, level in expected.items():
            single = (await celestial.get_visibility(sid, name))["level"]
            assert single == level, (name, single)
            assert listed[name] == single, (name, listed[name], single)

    async def test_min_level_explored_keeps_a_contested_system(self, sid):
        await _four_systems(sid)
        names = [s["system"] for s in await celestial.get_visible_systems(sid, "explored")]
        assert names == ["A", "B"], names
