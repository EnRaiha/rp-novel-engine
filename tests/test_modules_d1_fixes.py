"""Fixes in the D1 module batch: diplomacy, environment, characters, espionage, darkops, defense,
collapse, chekhov, calendar_tkg, chrono_engine.

Each test fails against the modules as they stood before the fix. Every row lives in a scratch
session (`900 + pid % 100`, and a second slot for the cross-campaign tests) and is removed in
teardown. Sessions 3 and 5 are frozen reference data and are never written.

The frozen-refusal tests patch `core.session.is_frozen` to True and `core.ooc._maintenance_active`
to False, then check that the writer raises `ooc.FrozenSession` and leaves its rows alone.
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

import pytest

from core import ooc
from core.db import Database
from modules import (calendar_tkg, characters, chekhov, chrono_engine, collapse, darkops,
                     defense, diplomacy, environment, espionage)

SID = 900 + os.getpid() % 100
SID2 = 900 + (os.getpid() + 50) % 100
P = "maya_rp."


# ── fixtures and helpers ─────────────────────────────────────────────────

@pytest.fixture(autouse=True)
async def _scratch():
    """Create both scratch session rows; remove everything they own, children first."""
    await Database.init()
    await _clear()
    for sid in (SID, SID2):
        await Database.execute(
            "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1,'D1 fixes scratch','active')"
            " ON CONFLICT (id) DO NOTHING", sid)
    try:
        yield
    finally:
        await _clear()
        for sid in (SID, SID2):
            await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", sid)


async def _clear() -> None:
    both = [SID, SID2]
    await Database.execute(
        "DELETE FROM maya_rp.character_arcs WHERE character_table='characters' AND character_id IN"
        " (SELECT id FROM maya_rp.characters WHERE session_id = ANY($1::int[]))", both)
    for table in ("espionage_missions", "dark_ops", "defense_installations", "colonies",
                  "chekhov_elements", "story_arcs", "events", "narrative_pacing", "time_skip_log",
                  "technologies", "npc_internal_state", "characters", "factions", "resources"):
        await Database.execute(f"DELETE FROM maya_rp.{table} WHERE session_id = ANY($1::int[])", both)


@pytest.fixture
def frozen(monkeypatch):
    """Every session reads as frozen and maintenance is off."""
    monkeypatch.setattr("core.session.is_frozen", lambda sid: True)
    monkeypatch.setattr("core.ooc._maintenance_active", lambda: False)


async def _resources(sid=SID, **cols) -> None:
    base = {"credits": 1_000_000, "alloys": 100_000, "fuel": 100_000,
            "aggregate_morale": 50, "population": 1_000_000}
    base.update(cols)
    keys = ", ".join(base)
    marks = ", ".join(f"${i + 2}" for i in range(len(base)))
    await Database.execute(
        f"INSERT INTO maya_rp.resources (session_id, {keys}) VALUES ($1, {marks})",
        sid, *base.values())


async def _res(sid=SID) -> dict:
    return dict(await Database.fetchrow("SELECT * FROM maya_rp.resources WHERE session_id=$1", sid))


async def _faction(name, sid=SID, standing="neutral", reputation=0) -> int:
    return await Database.fetchval(
        "INSERT INTO maya_rp.factions (session_id, name, standing, reputation) "
        "VALUES ($1,$2,$3,$4) RETURNING id", sid, name, standing, reputation)


async def _character(name, sid=SID, bond=10) -> int:
    return await Database.fetchval(
        "INSERT INTO maya_rp.characters (id, session_id, name, bond) "
        "VALUES ((SELECT COALESCE(MAX(id), 0) + 1 FROM maya_rp.characters), $1, $2, $3) "
        "RETURNING id", sid, name, bond)


async def _count(table, sid=SID) -> int:
    return await Database.fetchval(f"SELECT COUNT(*) FROM maya_rp.{table} WHERE session_id=$1", sid)


# ── diplomacy ────────────────────────────────────────────────────────────

class TestDiplomacy:
    async def _envoy_world(self, monkeypatch, target_standing):
        await _resources(last_tick_at=None)
        await Database.execute(
            "UPDATE maya_rp.resources SET last_tick_at=NOW() - INTERVAL '1 day' WHERE session_id=$1", SID)
        sender = await _faction("D1 Sender")
        target = await _faction("D1 Target", standing=target_standing)
        await Database.execute(
            "INSERT INTO maya_rp.envoys (faction_id, target_faction_id, started_at, duration_days, status) "
            "VALUES ($1,$2, NOW() - INTERVAL '400 days', 1, 'active')", sender, target)
        monkeypatch.setattr("modules.diplomacy.calc_game_days", lambda when: 1.0)
        monkeypatch.setattr("modules.diplomacy.random.random", lambda: 0.0)
        return target

    async def test_a_due_envoy_resolves_against_a_naive_started_at(self, monkeypatch):
        """`envoys.started_at` is timestamp without time zone. The tick subtracted it from an
        aware datetime, raised TypeError, and aborted before any envoy resolved."""
        await self._envoy_world(monkeypatch, "neutral")

        await diplomacy.run_tick(SID)

        status = await Database.fetchval(
            "SELECT e.status FROM maya_rp.envoys e JOIN maya_rp.factions f ON f.id=e.faction_id "
            "WHERE f.session_id=$1", SID)
        assert status == "completed", f"the envoy stayed {status!r}: the tick aborted"

    async def test_a_successful_envoy_lifts_the_targets_real_standing(self, monkeypatch):
        """`envoys` has no `standing` column, so the odds and the ladder always read neutral.
        A hostile target must step to neutral, not jump to friendly."""
        target = await self._envoy_world(monkeypatch, "hostile")

        await diplomacy.run_tick(SID)

        standing = await Database.fetchval("SELECT standing FROM maya_rp.factions WHERE id=$1", target)
        assert standing == "neutral", f"hostile target ended {standing!r}"

    @pytest.mark.parametrize("action,expected", [("hostile", "hostile"), ("neutral", "neutral"),
                                                 ("enemy", "enemy")])
    async def test_a_standing_action_sets_that_standing(self, action, expected):
        """KNOWN_ACTIONS accepted hostile/neutral/enemy, then reported success and changed nothing."""
        fid = await _faction("D1 Iron Concord", standing="friendly")

        out = await diplomacy.resolve_intent(SID, action, "Iron Concord")

        standing = await Database.fetchval("SELECT standing FROM maya_rp.factions WHERE id=$1", fid)
        assert standing == expected, (out, standing)
        assert out["standing_change"] == expected

    async def test_a_percent_target_matches_no_faction(self):
        """`%` was a wildcard: the first faction by id took the war declaration."""
        fid = await _faction("D1 Iron Concord")

        out = await diplomacy.resolve_intent(SID, "war", "%")

        assert out["success"] is False, out
        assert await Database.fetchval("SELECT standing FROM maya_rp.factions WHERE id=$1", fid) == "neutral"

    async def test_a_frozen_session_is_refused_and_nothing_is_written(self, frozen):
        fid = await _faction("D1 Iron Concord")
        await _resources(last_tick_at=None)

        with pytest.raises(ooc.FrozenSession):
            await diplomacy.resolve_intent(SID, "war", "Iron")
        with pytest.raises(ooc.FrozenSession):
            await diplomacy.run_tick(SID)

        assert await Database.fetchval("SELECT standing FROM maya_rp.factions WHERE id=$1", fid) == "neutral"


# ── environment ──────────────────────────────────────────────────────────

class TestEnvironment:
    async def test_the_fight_window_reads_a_column_that_exists(self):
        """`combat_results` has `created_at` and no `ended_at`: every call raised UndefinedColumn."""
        out = await environment.generate_details("bridge", SID)

        assert isinstance(out, list)

    async def test_a_null_tension_is_skipped(self):
        """`narrative_pacing.tension` is nullable; `None >= 7` raised TypeError."""
        await Database.execute(
            "INSERT INTO maya_rp.narrative_pacing (session_id, tension) VALUES ($1, NULL)", SID)
        try:
            out = await environment.generate_details("bridge", SID)
        finally:
            await Database.execute("DELETE FROM maya_rp.narrative_pacing WHERE session_id=$1", SID)

        assert isinstance(out, list)


# ── characters ───────────────────────────────────────────────────────────

class TestCharacters:
    async def _arc(self, char_id) -> int:
        return await Database.fetchval(
            "INSERT INTO maya_rp.character_arcs (character_table, character_id, arc_name, status, started_at) "
            "VALUES ('characters', $1, 'D1 arc', 'active', NOW() - INTERVAL '30 days') RETURNING id", char_id)

    async def test_the_stale_sweep_touches_only_this_sessions_arcs(self):
        """`character_arcs` has no `session_id`. The sweep updated every campaign's arcs, so a live
        tick staled the frozen sessions' arcs."""
        mine = await self._arc(await _character("D1 Mine", SID))
        other = await self._arc(await _character("D1 Other", SID2))

        out = await characters.run_tick(SID)

        assert out == {"character_arcs": 0, "stale_arcs": 1}, out
        status = lambda i: Database.fetchval("SELECT status FROM maya_rp.character_arcs WHERE id=$1", i)
        assert await status(mine) == "stale"
        assert await status(other) == "active", "another campaign's arc was staled"

    async def test_a_percent_target_matches_no_character(self):
        await _character("D1 Rika", bond=10)

        out = await characters.resolve_intent(SID, "talk", "%")

        assert out["success"] is False, out

    async def test_a_frozen_session_is_refused_and_nothing_is_written(self, frozen):
        cid = await _character("D1 Rika", bond=10)
        arc = await self._arc(cid)

        with pytest.raises(ooc.FrozenSession):
            await characters.resolve_intent(SID, "gift", "Rika")
        with pytest.raises(ooc.FrozenSession):
            await characters.run_tick(SID)

        assert await Database.fetchval("SELECT bond FROM maya_rp.characters WHERE id=$1", cid) == 10
        assert await Database.fetchval("SELECT status FROM maya_rp.character_arcs WHERE id=$1", arc) == "active"


# ── espionage ────────────────────────────────────────────────────────────

def _pin_rolls(monkeypatch, module, noise_range, roll):
    """Pin the noise draw to 0 and the 1-100 roll to `roll`; every other draw takes its maximum."""
    def randint(a, b):
        if (a, b) == noise_range:
            return 0
        if (a, b) == (1, 100):
            return roll
        return b
    monkeypatch.setattr(module.random, "randint", randint)


class TestEspionage:
    async def test_the_lowest_roll_is_a_success(self, monkeypatch):
        """The ladder tested `roll <= success // 5` first: roll 1 was reported as a captured agent."""
        await _faction("D1 Reavers")
        await _resources()
        _pin_rolls(monkeypatch, espionage, (-15, 15), 1)

        out = await espionage.run_espionage("Reavers", "scout_fleet", "Vane", SID)

        assert out["outcome"] == "success", out

    async def test_the_top_tail_of_failing_rolls_is_the_critical_failure(self, monkeypatch):
        await _faction("D1 Reavers")
        await _resources()
        _pin_rolls(monkeypatch, espionage, (-15, 15), 100)

        out = await espionage.run_espionage("Reavers", "scout_fleet", "Vane", SID)

        assert out["outcome"] == "critical_failure", out

    async def test_a_percent_target_matches_no_faction(self):
        await _faction("D1 Reavers")

        out = await espionage.run_espionage("%", "scout_fleet", "Vane", SID)

        assert "not found" in out.get("error", ""), out
        assert await _count("espionage_missions") == 0

    async def test_a_frozen_session_is_refused_and_nothing_is_written(self, frozen):
        await _faction("D1 Reavers")
        await _resources()

        with pytest.raises(ooc.FrozenSession):
            await espionage.run_espionage("Reavers", "scout_fleet", "Vane", SID)
        with pytest.raises(ooc.FrozenSession):
            await espionage.run_tick(SID)

        assert await _count("espionage_missions") == 0


# ── darkops ──────────────────────────────────────────────────────────────

class TestDarkops:
    async def test_the_lowest_roll_is_a_success(self, monkeypatch):
        """`roll <= chance // 5` was tested first: roll 1 was reported as an exposed operation."""
        await _faction("D1 The Den")
        await _resources()
        _pin_rolls(monkeypatch, darkops, (-10, 20), 1)

        out = await darkops.run_op("sabotage", "The Den", SID)

        assert out["outcome"] == "success", out

    async def test_two_racing_operations_cannot_overspend(self):
        """The check and the debit were separate statements: both calls passed the check on a
        treasury that paid for one, and the balance went negative."""
        await _faction("D1 The Den")
        cost_a, cost_c = darkops.OP_COSTS["sabotage"][:2]
        await _resources(alloys=cost_a, credits=cost_c)

        results = await asyncio.gather(darkops.run_op("sabotage", "The Den", SID),
                                       darkops.run_op("sabotage", "The Den", SID))

        res = await _res()
        assert res["alloys"] == 0 and res["credits"] == 0, res
        assert sum("error" in r for r in results) == 1, results
        assert await _count("dark_ops") == 1

    async def test_a_percent_target_matches_no_faction_and_costs_nothing(self):
        await _faction("D1 The Den")
        await _resources()

        out = await darkops.run_op("sabotage", "%", SID)

        assert "error" in out, out
        assert (await _res())["alloys"] == 100_000

    async def test_a_frozen_session_is_refused_and_nothing_is_written(self, frozen):
        await _faction("D1 The Den")
        await _resources()

        with pytest.raises(ooc.FrozenSession):
            await darkops.run_op("sabotage", "The Den", SID)
        with pytest.raises(ooc.FrozenSession):
            await darkops.run_tick(SID)

        assert (await _res())["alloys"] == 100_000
        assert await _count("dark_ops") == 0


# ── defense ──────────────────────────────────────────────────────────────

class TestDefense:
    async def _colony(self, name="D1 Yard") -> int:
        return await Database.fetchval(
            "INSERT INTO maya_rp.colonies (session_id, name) VALUES ($1,$2) RETURNING id", SID, name)

    async def test_two_racing_builds_cannot_overspend(self):
        """Read-then-debit let both builds pass on alloys that paid for one."""
        await self._colony()
        await _resources(alloys=defense.COSTS["minefield"])

        results = await asyncio.gather(defense.build("Yard", "minefield", SID),
                                       defense.build("Yard", "minefield", SID))

        assert (await _res())["alloys"] == 0
        assert sum("error" in r for r in results) == 1, results
        assert await _count("defense_installations") == 1

    async def test_a_null_level_upgrades_as_level_one(self):
        """`level >= 5` raised TypeError on a NULL level."""
        colony = await self._colony()
        await _resources()
        iid = await Database.fetchval(
            "INSERT INTO maya_rp.defense_installations (session_id, colony_id, system_name, "
            "installation_type, defense_rating, level) VALUES ($1,$2,'Yard','minefield',100,NULL) RETURNING id",
            SID, colony)

        out = await defense.upgrade(iid, SID)

        assert out == {"type": "minefield", "level": 2, "rating": 140, "cost": 2000}, out

    async def test_a_percent_colony_matches_none(self):
        await self._colony()
        await _resources()

        out = await defense.build("%", "minefield", SID)

        assert "not found" in out["error"], out

    async def test_a_frozen_session_is_refused_and_nothing_is_written(self, frozen):
        await self._colony()
        await _resources()

        with pytest.raises(ooc.FrozenSession):
            await defense.build("Yard", "minefield", SID)
        with pytest.raises(ooc.FrozenSession):
            await defense.upgrade(1, SID)
        with pytest.raises(ooc.FrozenSession):
            await defense.run_tick(SID)

        assert (await _res())["alloys"] == 100_000
        assert await _count("defense_installations") == 0


# ── calendar_tkg ─────────────────────────────────────────────────────────

class TestCalendar:
    async def test_concurrent_ticks_each_add_a_day(self):
        """advance_day read `game_day` and wrote `read + 1`: five racing ticks added fewer than five days."""
        await Database.execute("UPDATE maya_rp.sessions SET game_day=100 WHERE id=$1", SID)

        await asyncio.gather(*(calendar_tkg.advance_day(SID) for _ in range(5)))

        assert await Database.fetchval("SELECT game_day FROM maya_rp.sessions WHERE id=$1", SID) == 105

    async def test_a_frozen_session_is_refused_and_nothing_is_written(self, frozen):
        await Database.execute("UPDATE maya_rp.sessions SET game_day=100 WHERE id=$1", SID)
        date = await calendar_tkg.get_game_date(SID, 1)    # day 1 is a holiday

        with pytest.raises(ooc.FrozenSession):
            await calendar_tkg.advance_day(SID)
        with pytest.raises(ooc.FrozenSession):
            await calendar_tkg.apply_holiday(date, SID)
        with pytest.raises(ooc.FrozenSession):
            await calendar_tkg.run_tick(SID)

        assert await Database.fetchval("SELECT game_day FROM maya_rp.sessions WHERE id=$1", SID) == 100
        assert await _count("events") == 0


# ── chekhov ──────────────────────────────────────────────────────────────

class TestChekhov:
    async def test_overdue_elements_sort_by_importance_not_by_spelling(self):
        """`ORDER BY importance DESC` on a varchar put 'medium' and 'low' ahead of 'high' and 'critical'."""
        await Database.execute("UPDATE maya_rp.sessions SET game_day=100 WHERE id=$1", SID)
        for level in ("low", "critical", "medium", "high"):
            await Database.execute(
                "INSERT INTO maya_rp.chekhov_elements (session_id, element_type, description, importance, "
                "introduced_game_day, payoff_deadline, status) VALUES ($1,'gun',$2,$3,1,50,'unpaid')",
                SID, f"D1 {level}", level)

        rows = await chekhov.get_overdue(SID)

        assert [r["importance"] for r in rows] == ["critical", "high", "medium", "low"], rows

    async def test_a_frozen_session_is_refused_and_nothing_is_written(self, frozen):
        with pytest.raises(ooc.FrozenSession):
            await chekhov.introduce("gun", "D1 brass key", session_id=SID)
        with pytest.raises(ooc.FrozenSession):
            await chekhov.payoff(1, "fired", SID)
        with pytest.raises(ooc.FrozenSession):
            await chekhov.run_tick(SID)

        assert await _count("chekhov_elements") == 0


# ── collapse ─────────────────────────────────────────────────────────────

class TestCollapse:
    async def _arc(self, title) -> int:
        return await Database.fetchval(
            "INSERT INTO maya_rp.story_arcs (session_id, title, status) VALUES ($1,$2,'active') RETURNING id",
            SID, title)

    async def _status(self, arc_id):
        return await Database.fetchval("SELECT status FROM maya_rp.story_arcs WHERE id=$1", arc_id)

    async def test_the_ordinary_arc_is_ended_once_not_every_tick(self):
        """Step 1 ran on every tick the condition held: each arc the GM opened after the collapse
        was completed on the next tick."""
        await _resources(fuel=0)
        first = await self._arc("D1 before")
        await collapse.run_tick(SID)
        assert await self._status(first) == "completed"
        reopened = await self._arc("D1 after")

        await collapse.run_tick(SID)

        assert await self._status(reopened) == "active", "the second tick re-completed the GM's new arc"

    async def test_a_recovered_condition_closes_the_collapse_arc(self):
        """Nothing completed a collapse arc: a refuelled fleet kept a live 'Dead in the Water' arc."""
        await _resources(fuel=0)
        await collapse.run_tick(SID)
        arc = await Database.fetchval(
            "SELECT id FROM maya_rp.story_arcs WHERE session_id=$1 AND collapse_type='fuel_zero'", SID)
        await Database.execute("UPDATE maya_rp.resources SET fuel=500000 WHERE session_id=$1", SID)

        out = await collapse.run_tick(SID)

        assert out == {"status": "stable"}, out
        assert await self._status(arc) == "completed"

    async def test_a_still_true_condition_keeps_its_arc_while_another_one_leads(self):
        """Two conditions hold: the second one's arc must stay open when the first is reported."""
        await _resources(fuel=0, aggregate_morale=5)
        await collapse.run_tick(SID)
        await Database.execute(
            "INSERT INTO maya_rp.story_arcs (session_id, title, status, collapse_type) "
            "VALUES ($1,'D1 mutiny','active','morale_collapse')", SID)

        await collapse.run_tick(SID)

        left = await Database.fetchval(
            "SELECT status FROM maya_rp.story_arcs WHERE session_id=$1 AND collapse_type='morale_collapse'", SID)
        assert left == "active", left

    async def test_a_frozen_session_is_refused_and_nothing_is_written(self, frozen):
        await _resources(fuel=0)
        arc = await self._arc("D1 before")

        with pytest.raises(ooc.FrozenSession):
            await collapse.run_tick(SID)
        with pytest.raises(ooc.FrozenSession):
            await collapse.check_for_collapse(SID)

        assert await self._status(arc) == "active"
        assert await _count("story_arcs") == 1

    async def test_a_dry_run_on_a_frozen_session_still_reads(self, frozen):
        await _resources(fuel=0)

        out = await collapse.check_for_collapse(SID, dry_run=True)

        assert out and out["dry_run"] is True


# ── chrono_engine ────────────────────────────────────────────────────────

class TestChrono:
    @pytest.fixture(autouse=True)
    def _quiet_world(self, monkeypatch):
        async def no_turn(session_id):
            return {"events_generated": 0}
        monkeypatch.setattr("modules.geopolitics.run_tick", no_turn)

    @staticmethod
    def _delta(days) -> int:
        base = (chrono_engine.BASE_DAILY_INCOME - chrono_engine.BASE_DAILY_BURN) * days
        return base + int(abs(base) * min(0.08, days / 365.0 * 0.08))

    async def test_income_that_lands_during_the_skip_is_kept(self):
        """The skip wrote `snapshot + delta`. A credit committed between the snapshot and the write
        was overwritten. A second connection holds +777 uncommitted while the skip starts."""
        await _resources(credits=1_000)
        task = None
        async with Database.transaction() as holder:
            await holder.execute(
                "UPDATE maya_rp.resources SET credits=credits+777 WHERE session_id=$1", SID)
            task = asyncio.ensure_future(chrono_engine.execute_time_skip(30, "balanced", SID))
            await asyncio.sleep(0.5)
        out = await task

        assert "error" not in out, out
        assert (await _res())["credits"] == 1_000 + 777 + self._delta(30)

    async def test_a_failed_log_insert_rolls_the_whole_skip_back(self, monkeypatch):
        """No transaction wrapped the skip: a failure at the log row left the economy and the
        calendar advanced with no record of it."""
        await _resources(credits=1_000)
        await Database.execute("UPDATE maya_rp.sessions SET game_day=100 WHERE id=$1", SID)

        def poison(execute):
            async def wrapped(sql, *args):
                if "time_skip_log" in sql:
                    raise RuntimeError("log insert failed")
                return await execute(sql, *args)
            return wrapped

        real_tx = Database.transaction

        @asynccontextmanager
        async def tx():
            async with real_tx() as conn:
                class Proxy:
                    def __getattr__(self, name):
                        return getattr(conn, name)
                    execute = staticmethod(poison(conn.execute))
                yield Proxy()

        monkeypatch.setattr(chrono_engine.Database, "transaction", tx)
        monkeypatch.setattr(chrono_engine.Database, "execute", poison(Database.execute))

        with pytest.raises(RuntimeError, match="log insert failed"):
            await chrono_engine.execute_time_skip(30, "balanced", SID)

        assert (await _res())["credits"] == 1_000, "the economy write survived a failed skip"
        assert await Database.fetchval("SELECT game_day FROM maya_rp.sessions WHERE id=$1", SID) == 100

    async def test_a_frozen_session_is_refused_and_nothing_is_written(self, frozen):
        await _resources(credits=1_000)

        with pytest.raises(ooc.FrozenSession):
            await chrono_engine.execute_time_skip(30, "balanced", SID)

        assert (await _res())["credits"] == 1_000
        assert await _count("time_skip_log") == 0
