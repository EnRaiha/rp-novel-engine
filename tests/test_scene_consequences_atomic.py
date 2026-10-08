"""Live-database tests for the atomic paths of consequences, scene_tracker, scene_stack and context.

Defects covered (each test fails on the code before the fix):

1. `consequences.process_due` read the planted seeds, fired each effect through its own autocommit and
   updated the seed afterwards: overlapping ticks fired one effect twice, an exception in effect N left
   effects 0..N-1 landed and due again, and a `_fire` that returned False was dropped for good.
2. `scene_tracker.apply_declaration` wrote NULL over an entrant's scene_location when `masuk` came without
   `lokasi`.
3. `context.scene_state` read the location from characters.presence='present', which the tracker never
   sets, instead of player_context.location, which it does.
4. `scene_stack.pop` was a SELECT then an UPDATE: two concurrent pops resumed the same scene. Urgency
   ordered as text, so '10' came before '2'.

Scratch session: the slot `scratch_session` hands out (900-999). Sessions 3 and 5 are never written. Every
row is removed in `finally`.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import consequences, context, scene_stack, scene_tracker  # noqa: E402
from core.db import Database  # noqa: E402


async def _open(sid: int, morale: float | None = None) -> None:
    """A scratch sessions row, plus a resources row when `morale` is given."""
    await Database.init()
    await _clear(sid)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1,'Atomic scratch','active')", sid)
    if morale is not None:
        await Database.execute(
            "INSERT INTO maya_rp.resources (session_id, aggregate_morale) VALUES ($1,$2)", sid, morale)


async def _clear(sid: int) -> None:
    for table in ("consequence_seeds", "scene_stack", "characters", "player_context", "resources"):
        await Database.execute(f"DELETE FROM maya_rp.{table} WHERE session_id=$1", sid)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", sid)


async def _plant(sid: int, effects: list[dict]) -> int:
    row = await Database.fetchrow(
        "INSERT INTO maya_rp.consequence_seeds (session_id, trigger_type, cause_description, effects_jsonb,"
        " planted_at_tick, status) VALUES ($1,'t','cause',$2,1,'planted') RETURNING id",
        sid, json.dumps(effects))
    return int(row["id"])


async def _morale(sid: int) -> float:
    return float(await Database.fetchval(
        "SELECT aggregate_morale FROM maya_rp.resources WHERE session_id=$1", sid))


async def _seed(seed_id: int) -> dict:
    row = await Database.fetchrow(
        "SELECT status, effects_jsonb FROM maya_rp.consequence_seeds WHERE id=$1", seed_id)
    effects = row["effects_jsonb"]
    return {"status": row["status"], "effects": json.loads(effects) if isinstance(effects, str) else effects}


class TestProcessDueAtomic:
    async def test_two_overlapping_ticks_fire_a_due_effect_once(self, scratch_session, monkeypatch):
        """Both ticks read the planted seed before either updated it, so the -10 stat landed twice.

        A sleep inside `_fire` forces the overlap the old code allowed; the claim lock makes the
        second tick skip the seed the first holds.
        """
        sid = scratch_session
        try:
            await _open(sid, morale=50)
            await _plant(sid, [{"type": "stat", "target": "aggregate_morale", "delta": -10, "delay_ticks": 0}])
            real = consequences._fire

            async def slow(*args, **kwargs):
                await asyncio.sleep(0.3)
                return await real(*args, **kwargs)

            monkeypatch.setattr(consequences, "_fire", slow)
            await asyncio.gather(consequences.process_due(sid), consequences.process_due(sid))
            assert await _morale(sid) == 40, "the due -10 must land exactly once across two overlapping ticks"
        finally:
            await _clear(sid)

    async def test_a_raising_second_effect_rolls_back_the_first(self, scratch_session):
        """Effect 0 landed in its own autocommit and effect 1 raised, so the next tick fired effect 0 again.

        The bad delta fails at bind time. The whole seed rolls back, stays planted, and once the bad
        effect is removed the next tick lands the first effect once.
        """
        sid = scratch_session
        try:
            await _open(sid, morale=50)
            seed_id = await _plant(sid, [
                {"type": "stat", "target": "aggregate_morale", "delta": -10, "delay_ticks": 0},
                {"type": "stat", "target": "fuel", "delta": "not-a-number", "delay_ticks": 0},
            ])
            fired = await consequences.process_due(sid)
            assert fired == [], "a rolled-back seed reports nothing as fired"
            assert await _morale(sid) == 50, "effect 0 must not stay applied when effect 1 raised"
            seed = await _seed(seed_id)
            assert seed["status"] == "planted", "a rolled-back seed stays planted"
            assert len(seed["effects"]) == 2, "the stored effects are untouched by the rollback"

            await Database.execute(
                "UPDATE maya_rp.consequence_seeds SET effects_jsonb=$1 WHERE id=$2",
                json.dumps(seed["effects"][:1]), seed_id)
            fired = await consequences.process_due(sid)
            assert len(fired) == 1, "the next tick fires the surviving effect"
            assert await _morale(sid) == 40, "the surviving effect lands exactly once"
            assert (await _seed(seed_id))["status"] == "exhausted"
        finally:
            await _clear(sid)

    async def test_a_failed_effect_stays_in_remaining(self, scratch_session):
        """`_fire` returned False (no resources row) and the effect never reached `remaining`, so the seed
        went exhausted with the consequence undelivered."""
        sid = scratch_session
        try:
            await _open(sid)  # no resources row: the stat update matches nothing
            seed_id = await _plant(sid, [{"type": "stat", "target": "aggregate_morale", "delta": -5, "delay_ticks": 0}])
            assert await consequences.process_due(sid) == []
            seed = await _seed(seed_id)
            assert seed["status"] == "planted", "a transient miss must not exhaust the seed"
            assert len(seed["effects"]) == 1, "the failed effect is kept for the next tick"

            await Database.execute(
                "INSERT INTO maya_rp.resources (session_id, aggregate_morale) VALUES ($1,50)", sid)
            fired = await consequences.process_due(sid)
            assert len(fired) == 1, "the kept effect fires once the row exists"
            assert await _morale(sid) == 45
        finally:
            await _clear(sid)


class TestSceneTrackerMasuk:
    async def test_masuk_without_lokasi_keeps_the_entrants_location(self, scratch_session):
        """`masuk=Ersya` alone bound lokasi=None and wrote NULL over where Ersya already was."""
        sid = scratch_session
        try:
            await _open(sid)
            await Database.execute(
                "INSERT INTO maya_rp.characters (session_id, name, scene_location) VALUES ($1,'Ersya Scratch','dapur')", sid)
            moved = await scene_tracker.apply_declaration(
                sid, {"lokasi": None, "masuk": ["Ersya Scratch"], "keluar": []})
            assert moved["entered"] == ["Ersya Scratch"]
            where = await Database.fetchval(
                "SELECT scene_location FROM maya_rp.characters WHERE session_id=$1 AND name='Ersya Scratch'", sid)
            assert where == "dapur", "an entrant with no declared lokasi keeps the location it had"
        finally:
            await _clear(sid)

    async def test_masuk_with_lokasi_moves_the_entrant_and_the_scene(self, scratch_session):
        sid = scratch_session
        try:
            await _open(sid)
            await Database.execute(
                "INSERT INTO maya_rp.characters (session_id, name, scene_location) VALUES ($1,'Ersya Scratch','dapur')", sid)
            moved = await scene_tracker.apply_declaration(
                sid, {"lokasi": "balai", "masuk": ["Ersya Scratch"], "keluar": []})
            assert moved["location"] == "balai"
            where = await Database.fetchval(
                "SELECT scene_location FROM maya_rp.characters WHERE session_id=$1 AND name='Ersya Scratch'", sid)
            assert where == "balai"
        finally:
            await _clear(sid)


class TestSceneStateLocation:
    async def test_scene_state_returns_the_player_context_location(self, scratch_session):
        """The tracker writes player_context.location and never sets presence, so the presence-based mode
        read nothing and the block carried no location after every declaration."""
        sid = scratch_session
        try:
            await _open(sid)
            await Database.execute(
                "INSERT INTO maya_rp.player_context (session_id, location) VALUES ($1,'balai')", sid)
            await Database.execute(
                "INSERT INTO maya_rp.characters (session_id, name, presence, scene_location)"
                " VALUES ($1,'Mode Scratch','present','dapur')", sid)
            state = await context.scene_state(sid)
            assert state["location"] == "balai", "player_context.location wins over the character mode"
        finally:
            await _clear(sid)

    async def test_scene_state_falls_back_to_the_character_mode(self, scratch_session):
        sid = scratch_session
        try:
            await _open(sid)
            await Database.execute(
                "INSERT INTO maya_rp.characters (session_id, name, presence, scene_location)"
                " VALUES ($1,'Mode Scratch','present','dapur')", sid)
            state = await context.scene_state(sid)
            assert state["location"] == "dapur", "with no player_context row the mode still answers"
        finally:
            await _clear(sid)


class TestScenePop:
    async def _push(self, sid: int, urgency, what: str) -> None:
        await scene_stack.push("interrupt", {"what_was_happening": what, "urgency": urgency}, sid)

    async def test_two_concurrent_pops_resume_different_scenes(self, scratch_session):
        """Both pops selected the same suspended row and resumed it twice."""
        sid = scratch_session
        try:
            await _open(sid)
            await self._push(sid, "high", "scene a")
            await self._push(sid, "high", "scene b")
            first, second = await asyncio.gather(scene_stack.pop(sid), scene_stack.pop(sid))
            ids = [r["id"] for r in (first, second) if r is not None]
            assert len(ids) == len(set(ids)), "one scene must never be resumed by two pops"
            assert len(ids) == 2, "with two suspended scenes, two pops get one each"
        finally:
            await _clear(sid)

    async def test_numeric_urgency_orders_by_value(self, scratch_session):
        """Urgency ordered as text, so '10' popped before '2'."""
        sid = scratch_session
        try:
            await _open(sid)
            await self._push(sid, "10", "ten")
            await self._push(sid, "2", "two")
            popped = await scene_stack.pop(sid)
            assert popped["context"]["what_was_happening"] == "two", "urgency 2 outranks urgency 10"
        finally:
            await _clear(sid)

    async def test_named_urgency_orders_critical_first(self, scratch_session):
        sid = scratch_session
        try:
            await _open(sid)
            await self._push(sid, "low", "low")
            await self._push(sid, "critical", "critical")
            await self._push(sid, "medium", "medium")
            popped = await scene_stack.pop(sid)
            assert popped["context"]["what_was_happening"] == "critical"
        finally:
            await _clear(sid)

    async def test_pop_records_the_resolution_day(self, scratch_session):
        sid = scratch_session
        try:
            await _open(sid)
            await self._push(sid, "high", "scene")
            popped = await scene_stack.pop(sid)
            day = await Database.fetchval(
                "SELECT resolved_at_game_day FROM maya_rp.scene_stack WHERE id=$1", popped["id"])
            assert day == 1, "resolved_at_game_day carries the session's game day"
        finally:
            await _clear(sid)
