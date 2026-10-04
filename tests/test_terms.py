#!/usr/bin/env python3
"""Terms — the obligations a turn states, quoted rather than interpreted.

Extraction is pure, so most of this needs no database. The record path is checked for idempotency,
because the same turn will be read more than once by the poller.
"""
from __future__ import annotations

import pytest_asyncio

from core.db import Database
from core.terms import extract, open_terms, paragraphs, record, render, speaker_before


# ── extraction, no database ──────────────────────────────────────────────────

def test_a_promise_is_found_and_labelled():
    found = extract("### 1. Surat itu\n\n*Tiga perkara yang aku boleh janjikan:*\n")

    assert [f["kind"] for f in found] == ["janji"]
    assert "aku boleh janjikan" in found[0]["quote"]


def test_perjanjian_is_not_read_as_janji():
    """`perjanjian` contains `janji`. The longer marker is checked first, so the instrument is not
    mislabelled as the promise inside it."""
    found = extract("### 1. Surat itu\n\n*Ini satu perjanjian, bukan satu kurnia.*\n")

    assert [f["kind"] for f in found] == ["perjanjian"]


def test_a_condition_is_found():
    found = extract("### 4. Zulaikha Nadira\n\n*Perkara satu kamu tidak boleh diukur.*\n")

    assert found[0]["kind"] == "syarat"


def test_agreement_is_found():
    found = extract("### 4. Zulaikha Nadira\n\n*Perkara dua kamu: saya bersetuju, dengan satu tambahan.*\n")

    assert found[0]["kind"] == "persetujuan"


def test_a_paragraph_without_a_marker_is_not_a_term():
    assert extract("### 2. Ersya Ardani\n\nDia membaca surat itu tiga kali.\n") == []


def test_the_section_heading_names_the_speaker():
    found = extract("### 4. Zulaikha Nadira\n\n*Perkara satu kamu tidak boleh diukur.*\n")

    assert found[0]["speaker"] == "Zulaikha Nadira"


def test_kata_names_the_speaker_when_no_heading_does():
    found = extract('"Perkara satu kamu tidak boleh diukur," kata Zulaikha.\n')

    assert found[0]["speaker"] == "Zulaikha"


def test_a_speaker_nobody_names_is_none_rather_than_guessed():
    found = extract("*Perkara satu kamu tidak boleh diukur.*\n")

    assert found[0]["speaker"] is None, "an unknown speaker must not become a name"


def test_the_quote_is_verbatim():
    line = "*Perkara dua kamu: saya bersetuju, dengan satu tambahan.*"
    found = extract(f"### 4. Zulaikha Nadira\n\n{line}\n")

    assert found[0]["quote"] == line, "a paraphrase is a second version of the obligation"


def test_paragraphs_split_on_a_blank_line():
    assert [p for _, p in paragraphs("satu\n\ndua\n\ntiga")] == ["satu", "dua", "tiga"]


def test_speaker_before_returns_the_nearest_heading_above():
    text = "### 1. Pertama\n\n### 2. Kedua\n\nteks"

    assert speaker_before(text, len(text)) == "Kedua"


def test_a_long_quote_is_capped_rather_than_dropped():
    found = extract("### 1. X\n\n*Perkara satu " + ("panjang " * 300) + "*\n")

    assert len(found[0]["quote"]) <= 901
    assert found[0]["quote"].endswith("…"), "a cap must be visible, not silent"


# ── storage ──────────────────────────────────────────────────────────────────

async def _ensure_session(session: int, name: str = "Terms") -> None:
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1, $2, 'active')"
        " ON CONFLICT (id) DO NOTHING",
        session, name)


@pytest_asyncio.fixture
async def ledger(scratch_session):
    """A session with Zulaikha on the roster.

    The roster matters: `record` blanks a speaker that is not a character, because run over the real
    turns the nearest heading is often `Harga` or `Mahar` rather than a person. Without her row here
    every term would come back unnamed, which is the correct behaviour and the wrong fixture.
    """
    await Database.init()
    await _ensure_session(scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.characters (session_id, name, status) VALUES ($1, 'Zulaikha Nadira', 'active')",
        scratch_session)
    await Database.execute("DELETE FROM maya_rp.terms WHERE session_id=$1", scratch_session)
    yield scratch_session
    await Database.execute("DELETE FROM maya_rp.terms WHERE session_id=$1", scratch_session)
    await Database.execute("DELETE FROM maya_rp.characters WHERE session_id=$1", scratch_session)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", scratch_session)


async def test_a_heading_that_is_not_a_person_leaves_the_term_unnamed(ledger):
    """`Harga`, `Mahar` and `Tanda` are section headings in the play record, not speakers. A term
    attributed to a price is worse than one attributed to nobody."""
    await record(ledger, turn_id=9, text="### Harga\n\n*Dengan syarat saya yang bertanggungjawab.*\n")

    rows = await open_terms(ledger)

    assert len(rows) == 1
    assert rows[0]["speaker"] is None, "a price is not a person"


async def test_a_table_row_is_not_a_term(ledger):
    """Three of the first seventeen matches were table cells that happened to carry a marker."""
    result = await record(ledger, turn_id=50, text="| Calon | Asas | Harga sanggup bayar |\n")

    assert result["found"] == 0


TURN = ("### 4. Zulaikha Nadira\n\n*Perkara satu kamu tidak boleh diukur.*\n\n"
        "*Perkara dua kamu: saya bersetuju, dengan satu tambahan.*\n")


async def test_recording_a_turn_stores_its_terms(ledger):
    result = await record(ledger, turn_id=75, text=TURN)

    assert result["written"] == 2
    rows = await open_terms(ledger)
    assert [r["kind"] for r in rows] == ["syarat", "persetujuan"]
    assert all(r["speaker"] == "Zulaikha Nadira" for r in rows)


async def test_reading_the_same_turn_twice_writes_once(ledger):
    """The poller will read a turn more than once, so the same passage must be one row."""
    await record(ledger, turn_id=75, text=TURN)

    second = await record(ledger, turn_id=75, text=TURN)

    assert second["written"] == 0
    assert second["already"] == 2
    assert len(await open_terms(ledger)) == 2


async def test_the_same_words_in_a_different_turn_are_a_different_term(ledger):
    await record(ledger, turn_id=75, text=TURN)

    second = await record(ledger, turn_id=76, text=TURN)

    assert second["written"] == 2, "a term restated in a later turn is its own term"


async def test_ordinary_future_tense_is_not_a_term(ledger):
    """`saya akan` and `kamu akan` were markers in the first version. Over the real record they
    produced 110 of 116 matches and almost all were noise: "Saya akan bayar dengan kerja", "Saya
    akan kembali," katanya, "Kamu akan tinggal di sini sampai berapa lama?"."""
    result = await record(ledger, turn_id=4, text='Saya akan bayar dengan kerja. Kamu akan tinggal di sini.')

    assert result["found"] == 0, "future tense is not an obligation"


async def test_a_turn_with_no_terms_records_nothing(ledger):
    result = await record(ledger, turn_id=1, text="Hanya prosa, tiada apa-apa yang diminta.")

    assert result["found"] == 0
    assert await open_terms(ledger) == []


async def test_render_names_the_kind_the_speaker_and_the_turn(ledger):
    await record(ledger, turn_id=75, text=TURN)

    block = await render(ledger)

    assert "TERMA YANG BERDIRI" in block
    assert "Zulaikha Nadira" in block
    assert "giliran 75" in block
    assert "kamu tidak boleh diukur" in block, "the quote itself must reach the GM"


async def test_render_is_empty_when_nothing_stands(ledger):
    """An empty block in the prompt costs tokens and says nothing."""
    assert await render(ledger) == ""


async def test_only_open_terms_are_injected(ledger):
    await record(ledger, turn_id=75, text=TURN)
    await Database.execute(
        "UPDATE maya_rp.terms SET status='resolved' WHERE session_id=$1 AND kind='syarat'", ledger)

    rows = await open_terms(ledger)

    assert [r["kind"] for r in rows] == ["persetujuan"], "a resolved term is not injected"
