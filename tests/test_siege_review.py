"""Siege review: what reading `modules/siege.py` in full turned up.

Two defects, one of them a cross-campaign write on a victory. Sessions 3 and 5 are frozen reference
data and are never written: the rows live in two scratch sessions (900 + pid % 100, and 50 above it),
and every row this file creates is removed in the test's `finally`.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from core.db import Database  # noqa: E402
from modules import siege  # noqa: E402

SESSION = 900 + os.getpid() % 100
OTHER = 900 + (os.getpid() + 50) % 100
SYSTEM = "review siege system"


async def _ensure_session(session_id):
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1,'Siege review scratch','active')"
        " ON CONFLICT (id) DO NOTHING", session_id)


async def _territory(session_id=SESSION, name=SYSTEM, faction="Iron Concord"):
    await _ensure_session(session_id)
    return await Database.fetchval(
        "INSERT INTO maya_rp.territory (id, session_id, system_name, controlling_faction, status) "
        "VALUES ((SELECT COALESCE(MAX(id), 0) + 500000 FROM maya_rp.territory), $1, $2, $3, 'contested') "
        "RETURNING id",
        session_id, name, faction)


async def _siege(session_id=SESSION, system=SYSTEM, attacker=10 ** 9, defender=1000, damage=1900):
    """Damage is set just short of the capture threshold: victory needs 2x defender_power."""
    await _ensure_session(session_id)
    return await Database.fetchval(
        "INSERT INTO maya_rp.sieges "
        "(session_id, target_system, target_faction, attacker_power, defender_power, phase, "
        " max_phases, damage_dealt, casualties_taken, status) "
        "VALUES ($1, $2, 'Iron Concord', $3, $4, 1, 10, $5, 0, 'active') RETURNING id",
        session_id, system, attacker, defender, damage)


async def _drop(siege_id, territory_ids):
    await Database.execute("DELETE FROM maya_rp.sieges WHERE id = $1", siege_id)
    for tid in territory_ids:
        await Database.execute("DELETE FROM maya_rp.territory WHERE id = $1", tid)
    await Database.execute(
        "DELETE FROM maya_rp.events WHERE session_id = $1 AND event_type = 'siege' "
        "AND description LIKE '%review siege system%'", SESSION)
    for scratch in (SESSION, OTHER):
        await Database.execute("DELETE FROM maya_rp.events WHERE session_id = $1", scratch)
        await Database.execute("DELETE FROM maya_rp.sieges WHERE session_id = $1", scratch)
        await Database.execute("DELETE FROM maya_rp.territory WHERE session_id = $1", scratch)
        await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", scratch)


class TestTheSiegeBelongsToItsCampaign:
    async def test_another_campaign_cannot_advance_this_siege(self):
        """The read filtered on status alone, so any session could advance any siege."""
        await Database.init()
        sid = await _siege()
        try:
            out = await siege.advance_siege(sid, OTHER)
            assert "not found" in out.get("error", ""), out
            phase = await Database.fetchval("SELECT phase FROM maya_rp.sieges WHERE id = $1", sid)
            assert phase == 1, "another campaign's tick advanced this siege"
        finally:
            await _drop(sid, [])
            await Database.close()


class TestTheVictory:
    async def test_a_victory_captures_only_its_own_campaign(self):
        """The capture was written by system name alone, across every campaign."""
        await Database.init()
        mine = await _territory()
        theirs = await _territory(session_id=OTHER, name=SYSTEM)
        sid = await _siege()
        try:
            out = await siege.advance_siege(sid, SESSION)
            assert out["status"] == "victory", out
            ours = await Database.fetchval(
                "SELECT controlling_faction FROM maya_rp.territory WHERE id = $1", mine)
            theirs_now = await Database.fetchval(
                "SELECT controlling_faction FROM maya_rp.territory WHERE id = $1", theirs)
            assert ours == "Setia Empire", ours
            assert theirs_now == "Iron Concord", "a victory in one campaign captured another's system"
        finally:
            await _drop(sid, [mine, theirs])
            await Database.close()

    async def test_a_stalemate_writes_no_capture(self):
        await Database.init()
        mine = await _territory()
        sid = await _siege(attacker=1, defender=10 ** 9, damage=0)
        try:
            out = await siege.advance_siege(sid, SESSION)
            assert out["status"] != "victory", out
            faction = await Database.fetchval(
                "SELECT controlling_faction FROM maya_rp.territory WHERE id = $1", mine)
            assert faction == "Iron Concord", faction
        finally:
            await _drop(sid, [mine])
            await Database.close()


class TestTheTick:
    async def test_the_tick_advances_only_this_campaign(self):
        await Database.init()
        mine = await _territory()
        theirs = await _territory(session_id=OTHER, name=SYSTEM)
        sid = await _siege(attacker=1, defender=10 ** 9, damage=0)
        try:
            out = await siege.run_tick(SESSION)
            assert out == {"sieges_advanced": 1}, out
            phase = await Database.fetchval("SELECT phase FROM maya_rp.sieges WHERE id = $1", sid)
            assert phase == 2, phase
        finally:
            await _drop(sid, [mine, theirs])
            await Database.close()

    async def test_a_failing_advance_is_logged_as_a_fault(self, monkeypatch):
        await Database.init()
        sid = await _siege()
        seen = []

        async def boom(siege_id, session_id=None):
            raise RuntimeError("siege row died")

        monkeypatch.setattr(siege, "advance_siege", boom)
        monkeypatch.setattr(siege, "error", lambda module, message: seen.append(message))
        try:
            out = await siege.run_tick(SESSION)
            # The counter counts successes: the attempt raised, so nothing advanced and the fault is
            # the only record of it.
            assert out == {"sieges_advanced": 0}, out
            assert seen and "siege row died" in seen[0], seen
        finally:
            await _drop(sid, [])
            await Database.close()


class TestTheReads:
    async def test_listing_is_scoped_to_its_session(self):
        await Database.init()
        sid = await _siege()
        try:
            assert [s["id"] for s in await siege.list_sieges(SESSION)] == [sid]
            assert await siege.list_sieges(OTHER) == []
        finally:
            await _drop(sid, [])
            await Database.close()

    async def test_an_unknown_system_is_refused(self):
        await Database.init()
        try:
            out = await siege.start_siege("nowhere at all", SESSION)
            assert "not found" in out["error"], out
        finally:
            await Database.close()
