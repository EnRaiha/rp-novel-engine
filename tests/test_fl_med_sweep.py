"""Medium sweep over fleet, geopolitics, local_gen and fleet_economy (T4).

Fleet and geopolitics tests write a scratch session (900-999). Template tests write one
`stream_templates` catalogue row under a unique tag and delete it. Sessions 3 and 5 are not touched:
every call passes the scratch id and `Config.SESSION_ID` is patched to it.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

from core.config import Config  # noqa: E402
from core.db import Database  # noqa: E402
from modules import fleet, fleet_economy, geopolitics, local_gen  # noqa: E402

#: `trigger_tag_embed` is `vector(768)`.
DIM = 768


def _vec(fill: float = 0.1) -> str:
    return "[" + ",".join([str(fill)] * DIM) + "]"


async def _wipe(session_id):
    await Database.execute(
        "DELETE FROM maya_rp.fleet_members WHERE fleet_id IN "
        "(SELECT id FROM maya_rp.fleets WHERE session_id=$1)", session_id)
    for table in ("fleets", "ships", "events", "faction_relations", "factions"):
        await Database.execute(f"DELETE FROM maya_rp.{table} WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", session_id)


@pytest_asyncio.fixture
async def sid(scratch_session, monkeypatch):
    """A scratch session on game day 10. `Config.SESSION_ID` and `RP_SESSION` point at it."""
    monkeypatch.setattr(Config, "SESSION_ID", scratch_session)
    monkeypatch.setenv("RP_SESSION", str(scratch_session))
    await Database.init()
    await _wipe(scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status, game_day) "
        "VALUES ($1, 'sweep scratch', 'active', 10)", scratch_session)
    try:
        yield scratch_session
    finally:
        await _wipe(scratch_session)
        await Database.close()


async def _ship(session_id, name):
    return await Database.fetchval(
        "INSERT INTO maya_rp.ships (session_id, name, status) VALUES ($1,$2,'active') RETURNING id",
        session_id, name)


async def _members(session_id, fleet_name):
    rows = await Database.fetch(
        "SELECT s.name FROM maya_rp.fleet_members fm "
        "JOIN maya_rp.fleets f ON f.id=fm.fleet_id JOIN maya_rp.ships s ON s.id=fm.ship_id "
        "WHERE f.session_id=$1 AND f.name=$2 ORDER BY fm.position", session_id, fleet_name)
    return [r["name"] for r in rows]


async def _member_rows(session_id):
    return await Database.fetchval(
        "SELECT count(*) FROM maya_rp.fleet_members WHERE fleet_id IN "
        "(SELECT id FROM maya_rp.fleets WHERE session_id=$1)", session_id)


class TestFleetNamesResolveExactFirstAndEscaped:
    async def test_an_exact_fleet_name_beats_a_longer_one(self, sid):
        await fleet.create_fleet("Rex Prime", "wall", sid)
        await fleet.create_fleet("Rex", "wall", sid)
        await _ship(sid, "T4 Ship")
        out = await fleet.assign_ship("T4 Ship", "Rex", position=1, session_id=sid)
        assert out.get("assigned"), out
        assert await _members(sid, "Rex") == ["T4 Ship"]
        assert await _members(sid, "Rex Prime") == []

    async def test_a_partial_fleet_name_with_two_matches_is_refused(self, sid):
        await fleet.create_fleet("Rex One", "wall", sid)
        await fleet.create_fleet("Rex Two", "wall", sid)
        await _ship(sid, "T4 Ship")
        out = await fleet.assign_ship("T4 Ship", "Rex", position=1, session_id=sid)
        assert "ambiguous" in out["error"], out
        assert "Rex One" in out["error"] and "Rex Two" in out["error"], out
        assert await _member_rows(sid) == 0

    async def test_a_unique_partial_name_still_matches(self, sid):
        await fleet.create_fleet("Legion Vanguard", "wall", sid)
        await _ship(sid, "T4 Ship")
        out = await fleet.assign_ship("T4 Ship", "vanguard", position=1, session_id=sid)
        assert out["assigned"], out
        assert await _members(sid, "Legion Vanguard") == ["T4 Ship"]

    @pytest.mark.parametrize("wildcard", ["%", "_"])
    async def test_wildcards_match_nothing(self, sid, wildcard):
        await fleet.create_fleet("Alpha", "wall", sid)
        await _ship(sid, "T4 Ship")
        out = await fleet.assign_ship("T4 Ship", wildcard, position=1, session_id=sid)
        assert "not found" in out["error"], out
        assert await _member_rows(sid) == 0

    async def test_ship_names_resolve_the_same_way(self, sid):
        await fleet.create_fleet("Alpha", "wall", sid)
        await _ship(sid, "Maw One")
        await _ship(sid, "Maw Two")
        out = await fleet.assign_ship("Maw", "Alpha", position=1, session_id=sid)
        assert "ambiguous" in out["error"], out
        assert "Maw One" in out["error"] and "Maw Two" in out["error"], out
        assert await _member_rows(sid) == 0

    async def test_a_battle_refuses_an_ambiguous_fleet(self, sid):
        await fleet.create_fleet("Rex One", "wall", sid)
        await fleet.create_fleet("Rex Two", "wall", sid)
        out = await fleet.fleet_battle("Rex", "blitz", 100, sid)
        assert "ambiguous" in out["error"], out


async def _two_factions(session_id):
    a = await Database.fetchval(
        "INSERT INTO maya_rp.factions (session_id, name) VALUES ($1,$2) RETURNING id",
        session_id, f"T4 A {session_id}")
    b = await Database.fetchval(
        "INSERT INTO maya_rp.factions (session_id, name) VALUES ($1,$2) RETURNING id",
        session_id, f"T4 B {session_id}")
    return a, b


async def _relate(session_id, faction_a, faction_b, standing):
    await Database.execute(
        "INSERT INTO maya_rp.faction_relations (session_id, faction_a, faction_b, standing) "
        "VALUES ($1,$2,$3,$4)", session_id, faction_a, faction_b, standing)


async def _geopolitics_events(session_id):
    rows = await Database.fetch(
        "SELECT description FROM maya_rp.events WHERE session_id=$1 AND event_type='geopolitics'",
        session_id)
    return [r["description"] for r in rows]


class TestGeopoliticsReadsRelationsBothWays:
    async def test_a_relation_stored_the_other_way_is_found(self, sid, monkeypatch):
        a, b = await _two_factions(sid)
        await _relate(sid, b, a, "hostile")
        monkeypatch.setattr(geopolitics.random, "random", lambda: 0.0)
        await geopolitics.run_tick(sid)
        events = await _geopolitics_events(sid)
        assert len(events) == 1, events
        assert "border skirmish" in events[0], events

    async def test_allied_relations_report_joint_maneuvers(self, sid, monkeypatch):
        a, b = await _two_factions(sid)
        await _relate(sid, a, b, "allied")
        monkeypatch.setattr(geopolitics.random, "random", lambda: 0.0)
        await geopolitics.run_tick(sid)
        events = await _geopolitics_events(sid)
        assert len(events) == 1, events
        assert "Joint fleet maneuvers" in events[0], events


@pytest_asyncio.fixture
async def tag():
    """A unique catalogue tag. The row is removed whether or not the test created it."""
    await Database.init()
    value = f"[T4 SWEEP {os.getpid()}]"
    await Database.execute("DELETE FROM maya_rp.stream_templates WHERE trigger_tag=$1", value)
    try:
        yield value
    finally:
        await Database.execute("DELETE FROM maya_rp.stream_templates WHERE trigger_tag=$1", value)
        await Database.close()


async def _row(tag_value):
    row = await Database.fetchrow(
        "SELECT expanded_text, readable_hint, required_context, trigger_tag_embed IS NOT NULL AS embedded "
        "FROM maya_rp.stream_templates WHERE trigger_tag=$1", tag_value)
    return {**row, "required_context": json.loads(row["required_context"])}


class TestUpsertKeepsStoredHintAndContext:
    async def _seed(self, tag):
        await Database.execute(
            "INSERT INTO maya_rp.stream_templates "
            "(trigger_tag, expanded_text, category, readable_hint, required_context, trigger_tag_embed) "
            "VALUES ($1, 'first text', 'review', 'a readable hint', $2::jsonb, $3::vector)",
            tag, json.dumps(["place"]), _vec())

    async def test_an_upsert_without_a_hint_keeps_the_stored_hint_and_context(self, tag):
        await self._seed(tag)
        await local_gen.upsert_template(tag, "second text")
        row = await _row(tag)
        assert row["expanded_text"] == "second text", row
        assert row["readable_hint"] == "a readable hint", row
        assert row["required_context"] == ["place"], row
        assert row["embedded"], row

    async def test_an_upsert_with_context_replaces_it(self, tag):
        await self._seed(tag)
        await local_gen.upsert_template(tag, "second text", required_context=["a", "b"])
        row = await _row(tag)
        assert row["required_context"] == ["a", "b"], row

    async def test_an_empty_list_clears_the_context(self, tag):
        await self._seed(tag)
        await local_gen.upsert_template(tag, "second text", required_context=[])
        row = await _row(tag)
        assert row["required_context"] == [], row

    async def test_a_new_row_without_hint_or_context(self, tag):
        await local_gen.upsert_template(tag, "fresh text")
        row = await _row(tag)
        assert row["expanded_text"] == "fresh text", row
        assert row["readable_hint"] == "", row
        assert row["required_context"] == [], row
        assert not row["embedded"], row


def test_fleet_economy_never_reads_config_for_a_session():
    source = pathlib.Path(fleet_economy.__file__).read_text()
    assert "Config.SESSION_ID" not in source, [
        line for line in source.splitlines() if "Config.SESSION_ID" in line]
