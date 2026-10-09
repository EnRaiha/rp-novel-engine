"""memories, mystery, narrative: expiry marks a row once, a cold case logs once, story writes commit together.

Every write lands in a scratch session (900-999) and `Config.SESSION_ID` points at it. Sessions 3 and 5
are read by nothing here.
"""
from __future__ import annotations

import json
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

import core.config  # noqa: E402
from core.db import Database  # noqa: E402
from modules import memories, mystery, narrative  # noqa: E402

#: Children of `sessions` this file writes, in delete order.
_TABLES = ("investigation_log", "clues", "investigations", "narrative_hooks", "story_log", "events",
           "character_memories", "characters", "resources")

MYSTERY_HOOK = "An ancient structure pulses with unknown energy on a distant moon."


async def _wipe(session_id):
    for table in _TABLES:
        await Database.execute(f"DELETE FROM maya_rp.{table} WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", session_id)


@pytest_asyncio.fixture
async def sid(scratch_session, monkeypatch):
    """A scratch session on game day 100 whose tick clock is 6 hours old (`calc_game_days` gives 1.0)."""
    monkeypatch.setattr(core.config.Config, "SESSION_ID", scratch_session)
    await Database.init()
    await _wipe(scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status, game_day) "
        "VALUES ($1, 'mmn fix scratch', 'active', 100)", scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.resources (session_id, research_points, last_tick_at) "
        "VALUES ($1, 0, NOW() - INTERVAL '6 hours')", scratch_session)
    try:
        yield scratch_session
    finally:
        await _wipe(scratch_session)
        await Database.close()


async def _char(session_id, name="Test Char"):
    return await Database.fetchval(
        "INSERT INTO maya_rp.characters (session_id, name) VALUES ($1, $2) RETURNING id",
        session_id, name)


async def _mem(session_id, character_id, expires=None, weight=5, day=1):
    return await Database.fetchval(
        "INSERT INTO maya_rp.character_memories (session_id, character_id, memory_type, content, "
        "created_at_game_day, emotional_weight, expires_at_game_day) "
        "VALUES ($1, $2, 'minor', 'a minor thing', $3, $4, $5) RETURNING id",
        session_id, character_id, day, weight, expires)


async def _case(session_id, age_days=0):
    return await Database.fetchval(
        "INSERT INTO maya_rp.investigations (session_id, title, template_name, difficulty, status, created_at) "
        "VALUES ($1, 'mmn case', 'generic', 5, 'active', NOW() - make_interval(days => $2::int)) "
        "RETURNING id", session_id, age_days)


async def _count(table, session_id, where=""):
    return await Database.fetchval(
        f"SELECT COUNT(*) FROM maya_rp.{table} WHERE session_id=$1 {where}", session_id)


def _boom_json():
    """A `json` stand-in whose `dumps` raises after the first INSERT of a story entry."""
    def boom(*_a, **_k):
        raise RuntimeError("boom: dumps")
    return types.SimpleNamespace(dumps=boom, loads=json.loads)


def _rolls(monkeypatch, first=0.99, second=0.0):
    """Skip the ambient event (first roll), then make a hook (second roll), picking the first choice.

    A third roll raises IndexError, which no test catches as RuntimeError.
    """
    rolls = [first, second]
    monkeypatch.setattr(narrative.random, "random", lambda: rolls.pop(0))
    monkeypatch.setattr(narrative.random, "choice", lambda seq: seq[0])


# ── memories ──────────────────────────────────────────────────────────────────────────────────────────

class TestMemories:
    async def test_the_tick_does_not_rematch_expired_rows(self, sid):
        cid = await _char(sid)
        await _mem(sid, cid, expires=5)
        await _mem(sid, cid, expires=0)
        assert await memories.run_tick(sid) == {"memories_expired": 1}
        assert await memories.run_tick(sid) == {"memories_expired": 0}

    async def test_a_null_weight_does_not_crash_the_inner_world(self, sid):
        cid = await _char(sid)
        await _mem(sid, cid, weight=None)
        out = await memories.get_inner_world(cid, sid)
        assert out["total_memories"] == 1, out
        assert out["high_impact"] == [], out

    async def test_the_name_search_escapes_wildcards(self, sid, monkeypatch, capsys):
        seen = []

        async def record(sql, *args):
            seen.append((sql, args))
            return None

        with monkeypatch.context() as patch:
            patch.setattr(memories.Database, "fetchrow", record)
            await memories.cmd_memory_surface("A_B%", "ctx", sid)
        sql, args = seen[0]
        assert args[1] == "%A\\_B\\%%", args
        assert "ESCAPE" in sql, sql
        assert "ORDER BY id" in sql, sql

        # The statement must also run: `AXB` comes first by id and must not match `A_B`.
        await _char(sid, "AXB")
        await _char(sid, "A_B")
        capsys.readouterr()
        await memories.cmd_memory_surface("A_B", "ctx", sid)
        assert "Memories for A_B" in capsys.readouterr().out

    async def test_a_gist_with_no_text_keeps_the_originals(self, sid, monkeypatch):
        cid = await _char(sid)
        for _ in range(10):
            await _mem(sid, cid, day=1)

        async def empty_gist(_contents):
            return "."

        monkeypatch.setattr(memories, "_summarize", empty_gist)
        out = await memories.consolidate_memories(sid)
        remaining = await _count("character_memories", sid, "AND memory_type='minor'")
        assert remaining == 10, (remaining, out)
        assert out["consolidated"] == 0 and out["archived"] == 0, out
        assert await _count("character_memories", sid, "AND memory_type='consolidated'") == 0


# ── mystery ───────────────────────────────────────────────────────────────────────────────────────────

class TestMystery:
    async def test_a_link_to_a_clue_with_no_case_is_refused(self, sid):
        case = await _case(sid)
        orphan = await Database.fetchval(
            "INSERT INTO maya_rp.clues (session_id, source, source_type, text, revealed) "
            "VALUES ($1, 'x', 'discovery', 't', true) RETURNING id", sid)
        out = await mystery.add_clue(sid, case, "n", connects_to=orphan)
        assert "belongs to no investigation" in out.get("error", ""), out
        assert await _count("clues", sid, "AND investigation_id IS NOT NULL") == 0

    async def test_a_link_to_a_clue_in_another_case_names_that_case(self, sid):
        case = await _case(sid)
        other = await _case(sid)
        first = (await mystery.add_clue(sid, other, "a"))["clue_id"]
        out = await mystery.add_clue(sid, case, "b", connects_to=first)
        assert f"belongs to investigation {other}, not {case}" in out.get("error", ""), out

    async def test_a_cold_case_is_logged_once(self, sid):
        case = await _case(sid, age_days=30)
        first = await mystery.run_tick(sid)
        assert first == {"active": 1, "decayed": 1}, first
        second = await mystery.run_tick(sid)
        logged = await Database.fetchval(
            "SELECT COUNT(*) FROM maya_rp.investigation_log "
            "WHERE investigation_id=$1 AND entry_type='dead_end'", case)
        assert logged == 1, logged
        assert second == {"active": 0, "decayed": 0}, second
        status = await Database.fetchval("SELECT status FROM maya_rp.investigations WHERE id=$1", case)
        assert status == "cold"

    async def test_a_young_case_stays_active(self, sid):
        case = await _case(sid, age_days=1)
        assert await mystery.run_tick(sid) == {"active": 1, "decayed": 0}
        status = await Database.fetchval("SELECT status FROM maya_rp.investigations WHERE id=$1", case)
        assert status == "active"

    async def test_a_link_inside_one_case_still_writes(self, sid):
        case = await _case(sid)
        first = (await mystery.add_clue(sid, case, "a"))["clue_id"]
        second = (await mystery.add_clue(sid, case, "b", connects_to=first))["clue_id"]
        link = await Database.fetchval(
            "SELECT connects_to_clue FROM maya_rp.clues WHERE id=$1", second)
        assert link == first, link


# ── narrative ─────────────────────────────────────────────────────────────────────────────────────────

class TestNarrative:
    async def test_a_story_entry_is_all_or_nothing(self, sid, monkeypatch):
        monkeypatch.setattr(narrative, "json", _boom_json())
        with pytest.raises(RuntimeError, match="boom: dumps"):
            await narrative._story_entry(sid, "economy", "T", "C", 1)
        assert await _count("story_log", sid) == 0
        assert await _count("events", sid) == 0

    async def test_a_story_entry_writes_both_rows(self, sid):
        await narrative._story_entry(sid, "economy", "T", "C", 1)
        assert await _count("story_log", sid) == 1
        assert await _count("events", sid) == 1

    async def test_a_hook_and_its_story_entry_are_all_or_nothing(self, sid, monkeypatch):
        _rolls(monkeypatch)
        monkeypatch.setattr(narrative, "json", _boom_json())
        with pytest.raises(RuntimeError, match="boom: dumps"):
            await narrative.run_tick(sid)
        assert await _count("narrative_hooks", sid) == 0
        assert await _count("story_log", sid) == 0

    async def test_a_new_hook_lands_with_its_story_entry(self, sid, monkeypatch):
        _rolls(monkeypatch)
        out = await narrative.run_tick(sid)
        assert out["hooks"] == 1 and out["hooks_active"] == 0, out
        assert await _count("narrative_hooks", sid, "AND status='active'") == 1
        assert await _count("story_log", sid, "AND category='narrative'") == 1

    async def test_an_identical_active_hook_is_not_stacked(self, sid, monkeypatch):
        await Database.execute(
            "INSERT INTO maya_rp.narrative_hooks (session_id, hook_type, description, status) "
            "VALUES ($1, 'mystery', $2, 'active')", sid, MYSTERY_HOOK)
        _rolls(monkeypatch)
        out = await narrative.run_tick(sid)
        assert out["hooks"] == 0, out
        assert await _count("narrative_hooks", sid, "AND status='active'") == 1
        assert await _count("story_log", sid, "AND category='narrative'") == 0

    async def test_the_hook_cap_holds_in_the_insert(self, sid, monkeypatch):
        for text in ("one", "two", "three"):
            await Database.execute(
                "INSERT INTO maya_rp.narrative_hooks (session_id, hook_type, description, status) "
                "VALUES ($1, 'intrigue', $2, 'active')", sid, text)
        # Report two active rows to the Python gate so only the INSERT can hold the cap.
        real_fetch = narrative.Database.fetch

        async def stale_count(sql, *args):
            if "COUNT(*) AS c FROM narrative_hooks" in sql:
                return [{"c": 2}]
            return await real_fetch(sql, *args)

        monkeypatch.setattr(narrative.Database, "fetch", stale_count)
        _rolls(monkeypatch)
        out = await narrative.run_tick(sid)
        assert out["hooks"] == 0, out
        assert await _count("narrative_hooks", sid, "AND status='active'") == 3
