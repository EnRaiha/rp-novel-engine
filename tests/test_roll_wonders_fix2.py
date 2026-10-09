"""roll_theater, space_wonders fix 2: a pool, a blessing, an encounter and a discovery resolve once
before they pay, and a jsonb feature list decodes.

Every write lands in a scratch session (900-999). Sessions 3 and 5 are not touched: each call passes
the scratch id and the `sid` fixture points `Config.SESSION_ID` at it. Tests 3 to 7 are races. A
forced 0.2 s window after the read lets both calls read before either claims.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest_asyncio  # noqa: E402

import modules.roll_theater as rt  # noqa: E402
import modules.space_wonders as sw  # noqa: E402
from core.config import Config  # noqa: E402
from core.db import Database  # noqa: E402

#: Children of `sessions` this file writes, removed before the session row.
_TABLES = ("events", "animal_encounters", "discoveries", "story_log", "roll_blessings", "resources")


async def _wipe(session_id):
    await Database.execute(
        "DELETE FROM maya_rp.pool_bets WHERE pool_id IN "
        "(SELECT id FROM maya_rp.roll_pools WHERE session_id=$1)", session_id)
    await Database.execute("DELETE FROM maya_rp.roll_pools WHERE session_id=$1", session_id)
    for table in _TABLES:
        await Database.execute(f"DELETE FROM maya_rp.{table} WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", session_id)


@pytest_asyncio.fixture
async def sid(scratch_session, monkeypatch):
    """A scratch session on game day 40 with a warm pool and no default that reaches session 5."""
    monkeypatch.setattr(Config, "SESSION_ID", scratch_session)
    await Database.init()
    # A pool left by the previous test's teardown is bound to a closed loop: one call replaces it.
    await _wipe(scratch_session)
    # A cold pool opens its second connection late and hides the race: open four first.
    await asyncio.gather(*[Database.fetchval("SELECT 1") for _ in range(4)])
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status, game_day) "
        "VALUES ($1, 'roll wonders fix2', 'active', 40)", scratch_session)
    try:
        yield scratch_session
    finally:
        await _wipe(scratch_session)
        await Database.close()


async def _fund(session_id, credits=0):
    await Database.execute("DELETE FROM maya_rp.resources WHERE session_id=$1", session_id)
    await Database.execute(
        "INSERT INTO maya_rp.resources (session_id, credits, population) VALUES ($1, $2, 0)",
        session_id, credits)


async def _credits(session_id):
    return await Database.fetchval(
        "SELECT credits FROM maya_rp.resources WHERE session_id=$1", session_id)


def delay_after(fragment, seconds=0.2):
    """A `Database` stand-in that sleeps after a `fetchrow` whose SQL holds `fragment`."""

    class _Delayed:
        @staticmethod
        async def fetch(sql, *args):
            return await Database.fetch(sql, *args)

        @staticmethod
        async def fetchrow(sql, *args):
            row = await Database.fetchrow(sql, *args)
            if fragment in sql:
                await asyncio.sleep(seconds)
            return row

        @staticmethod
        async def fetchval(sql, *args):
            return await Database.fetchval(sql, *args)

        @staticmethod
        async def execute(sql, *args):
            return await Database.execute(sql, *args)

    return _Delayed


async def _no_emit(event_type, data):
    """Stands in for `EventBus.emit`, whose events insert starts an embedding task."""


def _slow_credit(monkeypatch):
    """Sleep 0.2 s before `_credit_resources` pays, so a late claim lets both calls pay."""
    real = sw._credit_resources

    async def slow(session_id, loot):
        await asyncio.sleep(0.2)
        return await real(session_id, loot)

    monkeypatch.setattr(sw, "_credit_resources", slow)


class _PlanetDB:
    """Answers `survey_planet` with one planet row and records every write."""

    def __init__(self, planet):
        self.planet = planet
        self.writes = []

    async def fetchrow(self, sql, *args):
        return self.planet if "FROM maya_rp.planets" in sql else None

    async def fetch(self, sql, *args):
        return []

    async def fetchval(self, sql, *args):
        return None

    async def execute(self, sql, *args):
        self.writes.append((sql, args))
        return "OK"


def _planet(features):
    return {
        "id": 9, "name": "Fix2 World", "planet_type": "Carbon World", "habitability": 1,
        "features": features, "resource_modifiers": "{}",
    }


class TestAJsonbFeatureListDecodes:
    async def test_survey_rolls_a_feature_when_the_jsonb_list_is_empty(self, monkeypatch, scratch_session):
        stub = _PlanetDB(_planet("[]"))
        monkeypatch.setattr(sw, "Database", stub)

        async def roll(planet_type):
            return {"name": "Aurora Belt"}

        monkeypatch.setattr(sw, "_roll_feature", roll)
        out = await sw.survey_planet(9, session_id=scratch_session)
        assert out["features"] == ["Aurora Belt"], out
        bound = [args[0] for sql, args in stub.writes if "SET features" in sql]
        assert bound == ['["Aurora Belt"]'], stub.writes

    async def test_survey_decodes_a_stored_feature_list(self, monkeypatch, scratch_session):
        stub = _PlanetDB(_planet('["Dust"]'))
        monkeypatch.setattr(sw, "Database", stub)
        rolled = []

        async def roll(planet_type):
            rolled.append(planet_type)
            return {"name": "Never"}

        monkeypatch.setattr(sw, "_roll_feature", roll)
        out = await sw.survey_planet(9, session_id=scratch_session)
        assert out["features"] == ["Dust"], out
        assert rolled == []
        assert not [sql for sql, _ in stub.writes if "SET features" in sql]
        source = ["Dust"]
        copy = sw._as_list(source)
        assert copy == source and copy is not source
        for junk in (None, "", "  ", "not json", '{"a": 1}', "7", 7, {"a": 1}):
            assert sw._as_list(junk) == [], junk


class TestOneCallPaysAndTheOtherLoses:
    async def test_two_hunts_pay_once(self, sid, monkeypatch):
        animal = await Database.fetchval(
            "SELECT id FROM maya_rp.space_animals WHERE jsonb_exists(resource_value, 'credits') "
            "ORDER BY id LIMIT 1")
        enc = await Database.fetchval(
            "INSERT INTO maya_rp.animal_encounters (session_id, animal_id, status) "
            "VALUES ($1, $2, 'active') RETURNING id", sid, animal)
        await _fund(sid)
        monkeypatch.setattr(sw.random, "random", lambda: 0.0)
        monkeypatch.setattr(sw.random, "uniform", lambda a, b: 1.0)
        monkeypatch.setattr(sw.EventBus, "emit", _no_emit)
        _slow_credit(monkeypatch)

        results = await asyncio.gather(
            sw.hunt_animal(enc, 10**9, sid), sw.hunt_animal(enc, 10**9, sid))

        wins = [r for r in results if r.get("success")]
        losses = [r for r in results if "error" in r]
        assert await _credits(sid) == wins[0]["loot"]["credits"], results
        assert len(wins) == 1 and len(losses) == 1, results
        status = await Database.fetchval(
            "SELECT status FROM maya_rp.animal_encounters WHERE id=$1", enc)
        assert status == "hunted"

    async def test_two_explores_pay_once(self, sid, monkeypatch):
        anomaly = await Database.fetchval(
            "SELECT id FROM maya_rp.space_anomalies WHERE jsonb_exists(reward_pool, 'credits') "
            "ORDER BY id LIMIT 1")
        disc = await Database.fetchval(
            "INSERT INTO maya_rp.discoveries (session_id, type, target_id, explored) "
            "VALUES ($1, 'anomaly', $2, FALSE) RETURNING id", sid, anomaly)
        await _fund(sid)
        monkeypatch.setattr(sw.random, "random", lambda: 0.0)
        monkeypatch.setattr(sw.random, "uniform", lambda a, b: 1.0)
        monkeypatch.setattr(sw.EventBus, "emit", _no_emit)
        _slow_credit(monkeypatch)

        results = await asyncio.gather(
            sw.explore_anomaly(disc, 10**9, sid), sw.explore_anomaly(disc, 10**9, sid))

        wins = [r for r in results if r.get("outcome") == "success"]
        losses = [r for r in results if "error" in r]
        assert await _credits(sid) == wins[0]["loot"]["credits"], results
        assert len(wins) == 1 and len(losses) == 1, results
        explored = await Database.fetchval(
            "SELECT explored FROM maya_rp.discoveries WHERE id=$1", disc)
        assert explored is True

    async def test_two_tames_resolve_once(self, sid, monkeypatch):
        animal = await Database.fetchval("SELECT id FROM maya_rp.space_animals ORDER BY id LIMIT 1")
        enc = await Database.fetchval(
            "INSERT INTO maya_rp.animal_encounters (session_id, animal_id, status) "
            "VALUES ($1, $2, 'active') RETURNING id", sid, animal)
        monkeypatch.setattr(sw.random, "random", lambda: 0.0)
        monkeypatch.setattr(sw, "Database", delay_after("FROM maya_rp.space_animals"))

        results = await asyncio.gather(
            sw.tame_animal(enc, 100, sid), sw.tame_animal(enc, 100, sid))

        wins = [r for r in results if r.get("success")]
        losses = [r for r in results if "error" in r]
        assert len(wins) == 1 and len(losses) == 1, results
        status = await Database.fetchval(
            "SELECT status FROM maya_rp.animal_encounters WHERE id=$1", enc)
        assert status == "tamed"

    async def test_two_resolves_pay_the_crown_fee_once(self, sid, monkeypatch):
        await _fund(sid)
        pool = await Database.fetchval(
            "INSERT INTO maya_rp.roll_pools (session_id, pool_name, odds, credits_in_pool) "
            "VALUES ($1, 'P', '1:1', 1000) RETURNING id", sid)
        for name, side in (("A", "king"), ("B", "house")):
            await Database.execute(
                "INSERT INTO maya_rp.pool_bets (pool_id, bettor_name, bet_credits, bet_side) "
                "VALUES ($1, $2, 500, $3)", pool, name, side)
        monkeypatch.setattr(rt, "Database", delay_after("status='open'"))

        results = await asyncio.gather(rt.resolve_pool(sid, True), rt.resolve_pool(sid, True))

        assert await _credits(sid) == 50, results
        assert sorted(r["resolved"] for r in results) == [False, True], results
        assert {"resolved": False} in results
        status = await Database.fetchval("SELECT status FROM maya_rp.roll_pools WHERE id=$1", pool)
        assert status == "closed"

    async def test_two_consumes_of_the_last_charge_spend_once(self, sid, monkeypatch):
        await Database.execute(
            "INSERT INTO maya_rp.roll_blessings (session_id, character_name, blessing, effect, charges) "
            "VALUES ($1, 'Fix2', 'Boon', 'luck', 1)", sid)
        monkeypatch.setattr(rt, "Database", delay_after("SELECT id, charges"))

        results = await asyncio.gather(
            rt.consume_blessing(sid, "Boon"), rt.consume_blessing(sid, "Boon"))

        assert sorted(results) == [False, True], results
        charges = await Database.fetchval(
            "SELECT charges FROM maya_rp.roll_blessings WHERE session_id=$1 AND blessing='Boon'", sid)
        assert charges == 0


class TestABlessingKeepsItsRules:
    async def test_a_blessing_keeps_its_rules(self, sid):
        async def add(blessing, charges, last_used):
            await Database.execute(
                "INSERT INTO maya_rp.roll_blessings "
                "(session_id, character_name, blessing, effect, charges, last_used_game_day) "
                "VALUES ($1, 'Fix2', $2, 'luck', $3, $4)", sid, blessing, charges, last_used)

        async def charges_of(blessing):
            return await Database.fetchval(
                "SELECT charges FROM maya_rp.roll_blessings WHERE session_id=$1 AND blessing=$2",
                sid, blessing)

        await add("Full", 2, None)
        await add("Stale", 0, 1)
        await add("Fresh", 0, 30)

        assert await rt.consume_blessing(sid, "Full") is True
        assert await charges_of("Full") == 1

        assert await rt.consume_blessing(sid, "Stale") is True
        assert await charges_of("Stale") == 0
        assert await rt.consume_blessing(sid, "Stale") is False

        assert await rt.consume_blessing(sid, "Fresh") is False
        assert await charges_of("Fresh") == 0
        assert await rt.consume_blessing(sid, "Absent") is False
        assert await charges_of("Absent") is None
