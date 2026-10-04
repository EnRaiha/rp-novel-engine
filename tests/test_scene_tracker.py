#!/usr/bin/env python3
"""Scene tracker — the output direction.

The engine feeds state in; this reads what the turn declares and checks it back against the
engine. Pure parsing is tested without a database, correction is tested against a scratch
session, and a write is read back rather than assumed.
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from core.db import Database
from core.scene_tracker import FIELDS, TIMES, apply_declaration, consume, parse, render, resolve


async def _ensure_session(session: int, name: str = "Scene tracker") -> None:
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1, $2, 'active')"
        " ON CONFLICT (id) DO NOTHING",
        session, name)


async def _person(session: int, name: str) -> int:
    return await Database.fetchval(
        "INSERT INTO maya_rp.characters (session_id, name, status) VALUES ($1, $2, 'active')"
        " RETURNING id",
        session, name)


@pytest_asyncio.fixture
async def scene(scratch_session):
    """A scratch session with a row, two characters, and a location set."""
    await Database.init()
    await _ensure_session(scratch_session)
    await _person(scratch_session, "Ersya Ardani")
    await _person(scratch_session, "Boyet")
    await Database.execute(
        "INSERT INTO maya_rp.player_context (session_id, location) VALUES ($1, 'rumah_agung')"
        " ON CONFLICT (session_id) DO UPDATE SET location='rumah_agung'",
        scratch_session)
    yield scratch_session
    await Database.execute("DELETE FROM maya_rp.characters WHERE session_id=$1", scratch_session)
    await Database.execute("DELETE FROM maya_rp.player_context WHERE session_id=$1", scratch_session)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", scratch_session)


# ── parsing, no database ──────────────────────────────────────────────────────

def test_a_declaration_is_read_from_a_turn():
    decl = parse("Prose first.\n[SCENE] lokasi=rumah_agung | masuk=Ersya Ardani, Boyet | masa=petang")

    assert decl["lokasi"] == "rumah_agung"
    assert decl["masuk"] == ["Ersya Ardani", "Boyet"]
    assert decl["masa"] == "petang"


def test_a_turn_without_a_declaration_parses_to_nothing():
    assert parse("Just prose, no block.") is None
    assert parse("") is None


def test_the_last_declaration_wins():
    """A turn that declares twice is a GM correcting itself, and the reader takes the second."""
    decl = parse("[SCENE] lokasi=bridge\n[SCENE] lokasi=amanah")

    assert decl["lokasi"] == "amanah"


def test_a_repeated_field_keeps_the_last_value():
    assert parse("[SCENE] lokasi=bridge | lokasi=amanah")["lokasi"] == "amanah"


def test_an_unknown_field_is_captured_not_swallowed():
    decl = parse("[SCENE] lokasi=bridge | lokasii=Boyet")

    assert decl["unknown_fields"] == ["lokasii"]
    assert decl["lokasi"] == "bridge"


def test_names_split_on_commas_and_semicolons_and_drop_empties():
    decl = parse("[SCENE] masuk=A-017, ; A-023 ,")

    assert decl["masuk"] == ["A-017", "A-023"]


def test_render_round_trips_through_parse():
    line = "[SCENE] lokasi=rumah_agung | masuk=Ersya Ardani, Boyet | keluar=Lek | masa=petang"

    assert render(parse(line)) == line


# ── correction, against a scratch session ────────────────────────────────────

async def test_a_misspelled_location_lands_on_the_catalogue_name(scene):
    result = await resolve(scene, parse("[SCENE] lokasi=rumah_agun"))

    assert result["resolved"]["lokasi"] == "rumah_agung"
    assert result["corrections"] == [
        {"field": "lokasi", "said": "rumah_agun", "used": "rumah_agung"}]


async def test_a_misspelled_name_lands_on_the_roster_name(scene):
    result = await resolve(scene, parse("[SCENE] masuk=Ersya Ardan"))

    assert result["resolved"]["masuk"] == ["Ersya Ardani"]
    assert result["corrections"][0]["said"] == "Ersya Ardan"
    assert result["corrections"][0]["used"] == "Ersya Ardani"


async def test_a_name_the_engine_does_not_hold_is_dropped_not_invented(scene):
    """A person must not enter the campaign because of a typo. `Krosh` is real in the prose and
    is not a `characters.name`: he lives inside A-017's description, and the row is known by code."""
    result = await resolve(scene, parse("[SCENE] masuk=Krosh"))

    assert result["resolved"]["masuk"] == []
    assert result["corrections"] == [{"field": "masuk", "said": "Krosh", "used": ""}]


async def test_a_number_the_engine_owns_is_not_a_field(scene):
    """Credits, fuel and population are declared nowhere, so a turn cannot restate them here."""
    decl = parse("[SCENE] lokasi=rumah_agung | kredit=100000000")

    result = await resolve(scene, decl)

    assert result["resolved"]["lokasi"] == "rumah_agung"
    assert [c["field"] for c in result["corrections"]] == ["kredit"]
    assert set(result["resolved"]) == {"masuk", "keluar", "lokasi", "masa"}, "no number reached state"


async def test_a_name_cannot_enter_and_leave_at_once(scene):
    """Entering wins: the scene it just joined is the one the turn is about."""
    result = await resolve(scene, parse("[SCENE] lokasi=rumah_agung | masuk=Boyet | keluar=Boyet"))

    assert result["resolved"]["masuk"] == ["Boyet"]
    assert result["resolved"]["keluar"] == []
    assert any(c.get("kind") == "entered_and_left" for c in result["corrections"])


async def test_a_time_outside_the_set_is_corrected_or_dropped(scene):
    assert (await resolve(scene, parse("[SCENE] masa=petanggg")))["resolved"]["masa"] == "petang"
    assert (await resolve(scene, parse("[SCENE] masa=midnight")))["resolved"]["masa"] is None


# ── writing ──────────────────────────────────────────────────────────────────

async def test_entering_a_scene_moves_the_character_and_the_scene(scene):
    result = await consume(scene, "[SCENE] lokasi=amanah_arkib | masuk=Ersya Ardani")

    stored = await Database.fetchrow(
        "SELECT c.scene_location, p.location AS player FROM maya_rp.characters c"
        " JOIN maya_rp.player_context p ON p.session_id=c.session_id"
        " WHERE c.session_id=$1 AND c.name='Ersya Ardani'", scene)
    assert stored["scene_location"] == "amanah_arkib", result
    assert stored["player"] == "amanah_arkib"


async def test_leaving_a_scene_clears_the_location(scene):
    await Database.execute(
        "UPDATE maya_rp.characters SET scene_location='rumah_agung' WHERE session_id=$1", scene)

    await consume(scene, "[SCENE] lokasi=rumah_agung | keluar=Boyet")

    left = await Database.fetchval(
        "SELECT scene_location FROM maya_rp.characters WHERE session_id=$1 AND name='Boyet'", scene)
    assert left is None, "a character who left is not somewhere else, they are nowhere recorded"


async def test_a_dry_run_writes_nothing(scene):
    before = await Database.fetchval(
        "SELECT location FROM maya_rp.player_context WHERE session_id=$1", scene)
    result = await consume(scene, "[SCENE] lokasi=amanah_arkib | masuk=Ersya Ardani", write=False)
    after = await Database.fetchval(
        "SELECT location FROM maya_rp.player_context WHERE session_id=$1", scene)

    assert after == before == "rumah_agung"
    assert result["moved"] is None
    assert result["resolved"]["lokasi"] == "amanah_arkib", "validated even when not written"


async def test_a_turn_with_no_declaration_changes_nothing(scene):
    before = await Database.fetchval(
        "SELECT location FROM maya_rp.player_context WHERE session_id=$1", scene)
    result = await consume(scene, "Only prose in this turn.")

    assert result["declared"] is None
    assert result["moved"] is None
    assert await Database.fetchval(
        "SELECT location FROM maya_rp.player_context WHERE session_id=$1", scene) == before


def test_the_field_and_time_sets_are_what_the_module_says():
    assert FIELDS == ("lokasi", "masuk", "keluar", "masa")
    assert "petang" in TIMES


async def test_a_declaration_moves_only_the_names_it_names(scene):
    """`controlled_by='gm'` is not the player.

    A first version of `apply_declaration` moved every row with that column set, to keep the player's
    context and the player's character in step. Measured on session 5 the column holds 63 rows, ids
    2931 to 2993, all `supporting` and all `bond 0`: the Arc I supporting cast. The update put all 63
    into town, 52 of which had no recorded location before it, and they had to be restored.

    So this holds the boundary: the scene moves, the named cast moves, and nobody else does.
    """
    bystander = await Database.fetchval(
        "INSERT INTO maya_rp.characters (session_id, name, status, controlled_by, scene_location)"
        " VALUES ($1, 'A Bystander', 'active', 'gm', NULL) RETURNING id",
        scene)
    await Database.execute(
        "UPDATE maya_rp.characters SET controlled_by='gm' WHERE session_id=$1", scene)

    await consume(scene, "[SCENE] lokasi=amanah_arkib | masuk=Ersya Ardani")

    moved = await Database.fetchval(
        "SELECT scene_location FROM maya_rp.characters WHERE id=$1", bystander)
    assert moved is None, "a character the declaration did not name was moved by it"
    named = await Database.fetchval(
        "SELECT scene_location FROM maya_rp.characters WHERE session_id=$1 AND name='Ersya Ardani'",
        scene)
    assert named == "amanah_arkib"


async def test_a_dash_placeholder_is_not_a_person(scene):
    """The first live declaration wrote `keluar=-`, and the reader reported that `-` is not in
    session 5. A placeholder is not a name."""
    result = await consume(scene, "[SCENE] lokasi=rumah_agung | keluar=-")

    assert result["resolved"]["keluar"] == []
    assert not any(c["said"] == "-" for c in result["corrections"]), "a dash was treated as a name"
