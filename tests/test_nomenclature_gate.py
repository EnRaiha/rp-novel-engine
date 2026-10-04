#!/usr/bin/env python3
"""Nomenclature at the import gate.

The import path matches a character on the whole name, exactly. A name one letter
away from an existing one therefore inserts a second character and nothing says
so, and a stock name from the common card packs is accepted like any other. These
tests hold the report that now runs before the match.
"""
from __future__ import annotations

import pytest
import pytest_asyncio

from core.db import Database
from scripts.import_character_card import GENERIC_NAMES, name_report


async def _ensure_session(session: int, name: str = "Nomenclature gate") -> None:
    """`characters.session_id` is a foreign key, so a row must exist first.

    The `scratch_session` fixture sweeps every table carrying a `session_id`
    column. `sessions` carries `id`, so it is not swept, and this file owns both
    the row it writes and the removal of it.
    """
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
async def roster(scratch_session):
    """A scratch session that exists, and is removed with its characters after."""
    await Database.init()
    await _ensure_session(scratch_session)
    yield scratch_session
    await Database.execute("DELETE FROM maya_rp.characters WHERE session_id=$1", scratch_session)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", scratch_session)


async def test_exact_name_is_reported_as_the_same_person(roster):
    mine = await _person(roster, "Ersya Ardani")

    report = await name_report(roster, "Ersya Ardani")

    assert [row["id"] for row in report["exact"]] == [mine]
    assert report["near"] == [], "an exact match is not also a near neighbour"


async def test_a_name_one_letter_away_is_reported(roster):
    mine = await _person(roster, "Zulaikha Nadira")

    report = await name_report(roster, "Zulaikha Nadirs")

    assert report["exact"] == [], "one letter apart is not the same person"
    assert [row["id"] for row in report["near"]] == [mine]


async def test_a_contained_name_is_reported_even_when_it_is_long(roster):
    mine = await _person(roster, "Ersya Ardani binti Harun")

    report = await name_report(roster, "Ersya Ardani")

    assert [row["id"] for row in report["near"]] == [mine]


async def test_a_stock_name_is_flagged(roster):
    report = await name_report(roster, "Kael")

    assert report["generic"] is True


async def test_a_rooted_name_is_not_flagged_and_has_no_neighbours(roster):
    await _person(roster, "Ersya Ardani")

    report = await name_report(roster, "Bowo Sim")

    assert report["generic"] is False
    assert report["exact"] == []
    assert report["near"] == [], "an unrelated name must not be dragged in by its length alone"


async def test_the_report_reads_only_its_own_session(roster):
    other = roster + 1000
    await _ensure_session(other, "Another campaign")
    try:
        elsewhere = await _person(other, "Suri Okonjo")

        report = await name_report(roster, "Suri Okonjo")

        assert report["exact"] == [], "another campaign's roster is not this campaign's"
        assert elsewhere > 0
    finally:
        await Database.execute("DELETE FROM maya_rp.characters WHERE session_id=$1", other)
        await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", other)


async def test_a_designation_is_not_a_neighbour_of_anybody(roster):
    """`A-011` normalises to a single `a`, and a lone `a` sits inside most names.

    Without a floor on the containment branch these were reported as neighbours of
    everyone, and the five slots were spent on them. Found by running the report
    against the live 440-name roster, not by a unit test.
    """
    await _person(roster, "A-011")
    await _person(roster, "A-017")

    report = await name_report(roster, "Kael")

    assert report["near"] == [], "a one-letter designation is not a neighbour of anybody"


async def test_the_generic_list_is_what_it_says():
    assert "kael" in GENERIC_NAMES
    assert "bowo" not in GENERIC_NAMES


@pytest.mark.parametrize("name", ["Zulaikha Nadira", "zulaikha nadira", "ZulaikhaNadira", "ZULAIKHA  NADIRA"])
async def test_case_and_spacing_do_not_hide_a_collision(roster, name):
    """Normalisation drops case and everything that is not a letter, so all four
    spellings are one person rather than four neighbours."""
    mine = await _person(roster, "Zulaikha Nadira")

    report = await name_report(roster, name)

    assert [row["id"] for row in report["exact"]] == [mine]
    assert report["near"] == [], "a spelling variant of one name is not a neighbour"
