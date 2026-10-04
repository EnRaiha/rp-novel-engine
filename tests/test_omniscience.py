#!/usr/bin/env python3
"""Omniscience — who speaks in a scene they are recorded as not being in.

Extraction is pure, so most of this needs no database. `check` reads the roster and the scene
location, and writes nothing.
"""
from __future__ import annotations

import pytest_asyncio

from core.db import Database
from core.omniscience import check, resolve, speakers


# ── extraction, no database ──────────────────────────────────────────────────

def test_kata_names_the_speaker():
    assert speakers('"ini tidak masuk," kata Ngozi.') == ["Ngozi"]


def test_a_two_word_name_is_taken_whole():
    assert speakers('"tinggal di sini," kata Doyo Kwarta.') == ["Doyo Kwarta"]


def test_a_name_before_berkata_is_taken():
    assert speakers("Wulan berkata dengan lantang di dalam") == ["Wulan"]


def test_both_forms_of_one_speaker_are_reported_once():
    """The prose uses `kata Doyo` and `Doyo berkata` in the same scene, and one person is speaking."""
    text = '"Ya," kata Doyo. Doyo berkata sekali lagi.'

    assert speakers(text) == ["Doyo"]


def test_katanya_is_not_a_speaker():
    """`katanya` attributes to whoever spoke last and names nobody, so it must not be read as a
    name beginning with a lowercase letter."""
    assert speakers('"Tidak," katanya.') == []


def test_a_title_is_not_a_speaker():
    """`kata Cikgu Izzat` names the person addressed as often as the one speaking."""
    assert speakers('"Kamu mahu tahu," kata Cikgu Izzat.') == []


def test_speakers_come_back_in_the_order_they_appear():
    assert speakers('"A," kata Zulaikha. "B," kata Ersya.') == ["Zulaikha", "Ersya"]


def test_prose_without_speech_reports_nobody():
    assert speakers("Kapal itu berlepas tanpa sesiapa berkata apa-apa.") == []


def test_an_empty_turn_is_handled():
    assert speakers("") == []


# ── resolving a spoken name to a roster name ─────────────────────────────────

def test_an_exact_name_resolves_to_itself():
    assert resolve("Wulan", ["Wulan", "Lek"]) == "Wulan"


def test_a_short_form_finds_the_full_roster_name():
    """Measured on the novel: `Doyo` three times as often as `Doyo Kwarta`."""
    assert resolve("Doyo", ["Doyo Kwarta", "Wulan"]) == "Doyo Kwarta"


def test_a_surname_finds_the_full_name():
    assert resolve("Bregg", ["Marlon Bregg", "Wulan"]) == "Marlon Bregg"


def test_a_short_form_two_people_answer_to_resolves_to_nothing():
    """Choosing one would place a person because two share a name."""
    assert resolve("Doyo", ["Doyo Kwarta", "Doyo Sim"]) is None


def test_a_name_nobody_answers_to_resolves_to_nothing():
    assert resolve("Krosh", ["Ersya Ardani", "Wulan"]) is None


def test_a_misspelling_still_resolves():
    assert resolve("Zulaikha Nadirs", ["Zulaikha Nadira", "Wulan"]) == "Zulaikha Nadira"


# ── the check, against a scratch session ─────────────────────────────────────

async def _ensure_session(session: int, name: str = "Omniscience") -> None:
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1, $2, 'active')"
        " ON CONFLICT (id) DO NOTHING",
        session, name)


@pytest_asyncio.fixture
async def scene(scratch_session):
    await Database.init()
    await _ensure_session(scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.player_context (session_id, location) VALUES ($1, 'rumah_agung')"
        " ON CONFLICT (session_id) DO UPDATE SET location='rumah_agung'",
        scratch_session)
    for name, at in (("Wulan", "rumah_agung"),
                     ("Ersya Ardani", "rumah_agung_sayap_timur"),
                     ("Zulaikha Nadira", "amanah_arkib"),
                     ("Sumayyah Harun", "garden_city_klinik")):
        await Database.execute(
            "INSERT INTO maya_rp.characters (session_id, name, status, scene_location)"
            " VALUES ($1, $2, 'active', $3)", scratch_session, name, at)
    yield scratch_session
    await Database.execute("DELETE FROM maya_rp.characters WHERE session_id=$1", scratch_session)
    await Database.execute("DELETE FROM maya_rp.player_context WHERE session_id=$1", scratch_session)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", scratch_session)


async def test_a_speaker_in_the_scene_is_not_a_finding(scene):
    result = await check(scene, '"Letak di sini," kata Wulan.')

    assert result["speakers"] == ["Wulan"]
    assert result["findings"] == [], "Wulan is at rumah_agung and the scene is there"


async def test_a_speaker_elsewhere_is_a_finding(scene):
    """Zulaikha is in the archive aboard AMANAH in orbit. She cannot speak in the house."""
    result = await check(scene, '"Saya sudah catat," kata Zulaikha.')

    assert result["findings"] == [{"character": "Zulaikha Nadira", "kind": "speaks_elsewhere",
                                   "said": "Zulaikha", "recorded_at": "amanah_arkib",
                                   "scene": "rumah_agung"}]


async def test_a_name_the_roster_does_not_hold_is_a_separate_kind(scene):
    """`Krosh` is real in the prose and lives inside A-017's description. That is the import
    gate's question, not an omniscience finding, and it is reported as its own kind."""
    result = await check(scene, '"Saya dengar," kata Krosh.')

    assert [f["kind"] for f in result["findings"]] == ["not_in_roster"]
    assert result["findings"][0]["said"] == "Krosh"


async def test_it_writes_nothing(scene):
    """The correction is the GM's declaration and the scene tracker's write. A heuristic here
    would move a person into a room because of a sentence about the past."""
    before = await Database.fetch(
        "SELECT name, scene_location FROM maya_rp.characters WHERE session_id=$1 ORDER BY name", scene)

    await check(scene, '"Saya sudah catat," kata Zulaikha. "Letak di situ," kata Ersya.')

    after = await Database.fetch(
        "SELECT name, scene_location FROM maya_rp.characters WHERE session_id=$1 ORDER BY name", scene)
    assert [dict(r) for r in before] == [dict(r) for r in after]


async def test_the_report_says_where_the_correction_lives(scene):
    result = await check(scene, "Nothing spoken.")

    assert "scene tracker" in result["note"]
    assert result["scene"] == "rumah_agung"
    assert result["checked"] == 4
