"""Module review tests for modules/space_wonders.py (2026-10-03).

The database-backed tests create their own sectors and discoveries in `scratch_session` and
delete them in a finally. The tests that stub `sw.Database` also stub `EventBus.emit`, which
writes `events` through the real pool.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.space_wonders as sw  # noqa: E402
from core.config import Config  # noqa: E402
from core.db import Database  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


async def _no_emit(event_type, data):
    """Stands in for `EventBus.emit`, whose `events` insert goes through the real pool."""


class _StubDB:
    """Answers space_wonders' statements and records every SQL string it saw."""

    def __init__(self, answers=None, resources_row=None):
        self.answers = answers or []   # (substring, value), first match wins
        self.resources_row = resources_row
        self.reads = []                # (sql, args)
        self.writes = []               # (sql, args)
        self.credits = []              # args of the resources UPDATE

    def _match(self, sql, default):
        for key, value in self.answers:
            if key in sql:
                return value
        return default

    async def fetchrow(self, sql, *args):
        self.reads.append((sql, args))
        if "UPDATE maya_rp.resources" in sql:
            self.credits.append(args)
            return self.resources_row
        return self._match(sql, None)

    async def fetch(self, sql, *args):
        self.reads.append((sql, args))
        return self._match(sql, []) or []

    async def fetchval(self, sql, *args):
        self.reads.append((sql, args))
        return self._match(sql, None)

    async def execute(self, sql, *args):
        self.writes.append((sql, args))
        return "OK"

    def sql_containing(self, needle):
        return [sql for sql, _ in self.reads + self.writes if needle in sql]


# ── The session default used to raise NameError ─────────────────────────


def test_session_defaults_resolve_without_a_name(monkeypatch):
    """Config was never imported, so every default path raised NameError."""
    stub = _StubDB()
    monkeypatch.setattr(sw, "Database", stub)
    overview = _run(sw.get_wonders_overview())
    assert isinstance(overview, dict) and "planets" in overview
    refused = _run(sw.explore_anomaly(1))
    assert refused == {"error": refused["error"]}
    assert "Discovery 1 not found" in refused["error"]


def test_story_log_uses_the_callers_session(monkeypatch):
    stub = _StubDB()
    monkeypatch.setattr(sw, "Database", stub)
    _run(sw._log(5, "exploration", "title", "content"))
    _run(sw._log(None, "exploration", "title", "content"))
    assert stub.writes[0][1][0] == 5
    assert stub.writes[1][1][0] == Config.SESSION_ID
    assert stub.writes[1][1][0] is not None


# ── Loot is paid, and what cannot be paid is named ──────────────────────


def test_credit_pays_the_columns_and_reports_the_rest(monkeypatch):
    stub = _StubDB(resources_row={"credits": 1})
    monkeypatch.setattr(sw, "Database", stub)
    report = _run(sw._credit_resources(5, {
        "credits": 10, "research": 5, "artifact": True, "food": 7,
    }))
    assert report["applied"] == {"credits": 10, "research_points": 5}
    assert report["skipped"] == {"artifact": True, "food": 7}
    assert report["credited"] is True
    sql = stub.sql_containing("UPDATE maya_rp.resources")[0]
    assert "research_points" in sql and "food" not in sql
    assert stub.credits[0] == (5, 10, 5)


def test_credit_says_when_the_session_has_no_resources_row(monkeypatch):
    stub = _StubDB(resources_row=None)
    monkeypatch.setattr(sw, "Database", stub)
    logged = []
    monkeypatch.setattr(sw, "info", lambda *a: logged.append(a))
    report = _run(sw._credit_resources(5, {"credits": 10}))
    assert report["credited"] is False
    assert report["applied"] == {"credits": 10}
    assert any("No resources row for session 5" in line[-1] for line in logged)


def test_hunt_pays_the_loot_it_reports(monkeypatch, scratch_session):
    stub = _StubDB(
        answers=[
            ("FROM maya_rp.animal_encounters", {"id": 7, "animal_id": 3}),
            # jsonb arrives as text from asyncpg; hunt_animal called .items() on it.
            ("FROM maya_rp.space_animals", {
                "id": 3, "name": "Void Skimmer", "species": "skimmer",
                "aggression": 2, "taming_difficulty": 3, "rarity": "common",
                "resource_value": '{"credits": 500, "alloys": 40}',
                "special_ability": "",
            }),
        ],
        resources_row={"credits": 100},
    )
    monkeypatch.setattr(sw, "Database", stub)
    monkeypatch.setattr(sw.random, "random", lambda: 0.0)  # force the hit
    monkeypatch.setattr(sw.EventBus, "emit", _no_emit)

    out = _run(sw.hunt_animal(7, 100, session_id=scratch_session))

    assert out["success"] is True
    # The loot rolls 0.8-1.2x, so the contract is that the paid amount equals
    # the reported amount, not a literal.
    paid = out["resources"]["applied"]
    for key, value in out["loot"].items():
        if key in sw._LOOT_COLUMNS:
            assert paid[sw._LOOT_COLUMNS[key]] == value, (key, value, paid)
    assert paid["credits"] == out["loot"]["credits"]
    assert out["resources"]["credited"] is True
    assert stub.credits, "the hunt reported loot and paid none"


def test_survey_applies_the_planet_type_modifiers(monkeypatch):
    """`resource_modifiers` is jsonb text, so the multipliers never applied."""
    stub = _StubDB(answers=[
        ("FROM maya_rp.planets", {
            "id": 9, "session_id": 5, "name": "Review World", "planet_type": "Carbon World",
            "habitability": 1, "features": ["Dust"], "resource_modifiers": '{"alloys": 2.5}',
        }),
    ])
    monkeypatch.setattr(sw, "Database", stub)
    monkeypatch.setattr(sw.random, "randint", lambda a, b: 100)

    out = _run(sw.survey_planet(9, session_id=5))

    assert out["yield"]["alloys"] == 250
    assert out["yield"]["fuel"] == 100


def test_explore_decodes_the_anomaly_reward_pool(monkeypatch, scratch_session):
    stub = _StubDB(answers=[
        ("FROM maya_rp.discoveries", {"id": 4, "target_id": 2}),
        ("FROM maya_rp.space_anomalies", {
            "id": 2, "name": "The Quiet Gate", "type": "gate", "reward_pool":
            '{"credits": 400, "exploration": "new_system"}', "danger_level": 1,
        }),
    ], resources_row={"credits": 100})
    monkeypatch.setattr(sw, "Database", stub)
    monkeypatch.setattr(sw.random, "random", lambda: 0.0)  # force the success branch
    monkeypatch.setattr(sw.EventBus, "emit", _no_emit)

    out = _run(sw.explore_anomaly(4, 100, session_id=scratch_session))

    assert out["outcome"] == "success"
    assert out["resources"]["applied"]["credits"] == out["loot"]["credits"]
    assert out["loot"]["new_system_discovered"] is True


def test_hunt_and_explore_refuse_a_nonpositive_fleet_power(monkeypatch):
    stub = _StubDB()
    monkeypatch.setattr(sw, "Database", stub)
    for out in (_run(sw.hunt_animal(1, 0, session_id=5)),
                _run(sw.hunt_animal(1, -5, session_id=5)),
                _run(sw.explore_anomaly(1, 0, session_id=5))):
        assert "fleet_power must be positive" in out["error"]
    assert stub.reads == [], "a refused call still queried the database"


# ── Session scope at the database boundary ──────────────────────────────


def _read(row, key):
    return row[key] if row else None


class TestSessionScope:
    def test_survey_refuses_another_sessions_planet(self, scratch_session):
        """The survey borrows a real row and never creates one.

        `tests/test_dry_run_safety.py` fingerprints maya_rp.planets, so this test
        inserts nothing: it takes an existing unsurveyed session-3 planet and asserts
        the call from the scratch session is refused. The finally writes the original
        value back only when the planet changed, which means the survey broke.
        """

        async def scenario():
            await Database.init()
            row = await Database.fetchrow(
                "SELECT id, surveyed FROM maya_rp.planets "
                "WHERE session_id = 3 AND surveyed = FALSE ORDER BY id LIMIT 1")
            try:
                assert row, "no unsurveyed session-3 planet to borrow"
                out = await sw.survey_planet(row["id"], session_id=scratch_session)
                after = await Database.fetchval(
                    "SELECT surveyed FROM maya_rp.planets WHERE id=$1", row["id"])
                return out, after
            finally:
                if row:
                    current = await Database.fetchval(
                        "SELECT surveyed FROM maya_rp.planets WHERE id=$1", row["id"])
                    if current != row["surveyed"]:
                        await Database.execute(
                            "UPDATE maya_rp.planets SET surveyed=$1 WHERE id=$2",
                            row["surveyed"], row["id"])
                await Database.close()

        out, after = _run(scenario())
        assert f"not found in session {scratch_session}" in out.get("error", ""), out
        assert after is False, "the refused survey marked another campaign's planet surveyed"

    def test_a_discovery_lands_in_the_named_session(self, scratch_session):
        """`sectors.session_id` has an FK to `sessions` with no cascade: the test seeds the scratch
        session row and removes the sector before it removes the row."""

        async def scenario():
            await Database.init()
            await Database.execute(
                "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1, 'wonders review', 'active')"
                " ON CONFLICT (id) DO NOTHING", scratch_session)
            try:
                sector = await Database.fetchval(
                    "INSERT INTO maya_rp.sectors (session_id, name, x_coord, y_coord) "
                    "VALUES ($1, 'review-temp-sector', 0, 0) RETURNING id", scratch_session)
                out = await sw.discover_anomaly(sector, session_id=scratch_session)
                owner = await Database.fetchval(
                    "SELECT session_id FROM maya_rp.discoveries WHERE id=$1", out.get("discovery_id"))
                return out, owner
            finally:
                # `discoveries` and `story_log` cascade from the session row.
                await Database.execute("DELETE FROM maya_rp.sectors WHERE session_id = $1", scratch_session)
                await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", scratch_session)
                await Database.close()

        out, owner = _run(scenario())
        assert out.get("discovery_id"), out
        assert owner == scratch_session, "the discovery was written into another session"


def test_the_tick_reads_inside_its_own_session(monkeypatch):
    stub = _StubDB(answers=[
        ("FROM maya_rp.sectors", [{"id": 11}]),
        ("FROM maya_rp.planets", {"id": 12}),
        ("FROM maya_rp.space_animals", {
            "id": 3, "name": "Void Skimmer", "species": "skimmer", "aggression": 2,
            "taming_difficulty": 3, "rarity": "common",
            "resource_value": {}, "special_ability": "",
        }),
    ])
    monkeypatch.setattr(sw, "Database", stub)
    monkeypatch.setattr(sw.random, "random", lambda: 0.0)  # open all three gates

    _run(sw.run_tick(session_id=5))

    scoped = [sql for sql in stub.sql_containing("FROM maya_rp.sectors")
              + stub.sql_containing("FROM maya_rp.planets")]
    assert scoped, "the tick read nothing"
    for sql in scoped:
        assert "session_id" in sql, sql
    for sql, args in stub.reads:
        if "FROM maya_rp.sectors" in sql or "FROM maya_rp.planets" in sql:
            assert 5 in args, (sql, args)


# ── The module's own contract ───────────────────────────────────────────


def test_every_loot_key_in_the_catalogue_is_paid_or_named():
    """Loot vocabulary comes from the live tables: any key must be mapped or skipped."""

    async def keys():
        await Database.init()
        try:
            animals = await Database.fetch(
                "SELECT DISTINCT jsonb_object_keys(resource_value) AS k "
                "FROM maya_rp.space_animals WHERE resource_value IS NOT NULL")
            anomalies = await Database.fetch(
                "SELECT DISTINCT jsonb_object_keys(reward_pool) AS k "
                "FROM maya_rp.space_anomalies WHERE reward_pool IS NOT NULL")
            cols = await Database.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='maya_rp' AND table_name='resources'")
            return ({r["k"] for r in animals} | {r["k"] for r in anomalies},
                    {r["column_name"] for r in cols})
        finally:
            await Database.close()

    loot_keys, columns = _run(keys())
    assert loot_keys, "the catalogues carry no loot keys"
    for key in loot_keys:
        assert key in sw._LOOT_COLUMNS or key in sw._NON_RESOURCE_KEYS, (
            f"loot key {key} is neither mapped nor declared a non-resource")
    assert sw._LOOT_COLUMNS.keys().isdisjoint(sw._NON_RESOURCE_KEYS)
    for column in sw._LOOT_COLUMNS.values():
        assert column in columns, f"_LOOT_COLUMNS names {column}, not a resources column"
