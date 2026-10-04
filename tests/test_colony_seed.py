#!/usr/bin/env python3
"""Heaven Reach's settlements — sourced, idempotent, and honest about what it does not know.

The seed writes three rows into `maya_rp.colonies` for a session that had none, and six modules
read that table. Two of them return a hard error when a colony is missing, so this is the
difference between `defense.build(colony="Garden")` answering a rating or answering not-found.
"""
from __future__ import annotations

import pytest_asyncio

from core.db import Database
from scripts.seed_heaven_reach_colonies import SETTLEMENTS, seed


async def _ensure_session(session: int, name: str = "Colony seed") -> None:
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1, $2, 'active')"
        " ON CONFLICT (id) DO NOTHING",
        session, name)


@pytest_asyncio.fixture
async def blank(scratch_session):
    """A session with a row and no colonies."""
    await Database.init()
    await _ensure_session(scratch_session)
    await Database.execute("DELETE FROM maya_rp.colonies WHERE session_id=$1", scratch_session)
    yield scratch_session
    await Database.execute("DELETE FROM maya_rp.colonies WHERE session_id=$1", scratch_session)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", scratch_session)


async def test_a_dry_run_writes_nothing(blank):
    result = await seed(blank, write=False)

    assert len(result["created"]) == 3
    assert await Database.fetchval(
        "SELECT count(*) FROM maya_rp.colonies WHERE session_id=$1", blank) == 0


async def test_it_creates_the_three_settlements(blank):
    result = await seed(blank, write=True)

    assert sorted(result["created"]) == ["Bukit Kaca", "Garden", "Pesisir Panjang"]
    names = {r["name"] for r in await Database.fetch(
        "SELECT name FROM maya_rp.colonies WHERE session_id=$1", blank)}
    assert names == {"Garden", "Bukit Kaca", "Pesisir Panjang"}


async def test_the_populations_are_the_ones_the_report_gave(blank):
    """Turn 73: 8,400 in Garden, 3,300 in Bukit Kaca, 3,100 in Pesisir Panjang."""
    await seed(blank, write=True)

    got = {r["name"]: r["population"] for r in await Database.fetch(
        "SELECT name, population FROM maya_rp.colonies WHERE session_id=$1", blank)}

    assert got == {"Garden": 8400, "Bukit Kaca": 3300, "Pesisir Panjang": 3100}


async def test_what_the_source_does_not_give_is_null_and_not_zero(blank):
    """The column defaults to 0, and 0 is a claim: this colony produces nothing.

    Bukit Kaca smelts nine tonnes of iron a day and the column is `alloy_output`, an integer. A
    tonne of iron is not an alloy and not that unit, so the honest value is that nobody has said.
    """
    await seed(blank, write=True)

    rows = await Database.fetch(
        "SELECT name, planet_type, development, alloy_output, fuel_output, credit_output"
        " FROM maya_rp.colonies WHERE session_id=$1", blank)

    assert rows, "the seed created nothing"
    for row in rows:
        assert row["alloy_output"] is None, f"{row['name']} claims an alloy output nobody sourced"
        assert row["fuel_output"] is None, f"{row['name']} claims a fuel output nobody sourced"
        assert row["credit_output"] is None, f"{row['name']} claims a credit output nobody sourced"
        assert row["development"] is None, f"{row['name']} claims a development level nobody sourced"
        assert row["planet_type"] is None, f"{row['name']} claims a planet type nobody sourced"


async def test_running_it_twice_leaves_the_campaign_alone(blank):
    """The story owns this state after the seed. A re-run must not overwrite what it has changed."""
    await seed(blank, write=True)
    await Database.execute(
        "UPDATE maya_rp.colonies SET population=9999, status='abandoned'"
        " WHERE session_id=$1 AND name='Garden'", blank)

    second = await seed(blank, write=True)

    assert second["created"] == [], "a second run created something"
    assert sorted(second["kept"]) == ["Bukit Kaca", "Garden", "Pesisir Panjang"]
    garden = await Database.fetchrow(
        "SELECT population, status FROM maya_rp.colonies WHERE session_id=$1 AND name='Garden'", blank)
    assert garden["population"] == 9999, "the re-run overwrote what the campaign had changed"
    assert garden["status"] == "abandoned"


async def test_it_does_not_touch_another_session(blank):
    neighbour = blank + 1000
    await _ensure_session(neighbour, "Neighbour")
    try:
        await seed(blank, write=True)

        assert await Database.fetchval(
            "SELECT count(*) FROM maya_rp.colonies WHERE session_id=$1", neighbour) == 0
    finally:
        await Database.execute("DELETE FROM maya_rp.colonies WHERE session_id=$1", neighbour)
        await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", neighbour)


def test_every_settlement_carries_its_source():
    """A row without the sentence it came from is a number nobody can check."""
    for name, population, status, source in SETTLEMENTS:
        assert population > 0, f"{name} has no population"
        assert status == "active", f"{name} is seeded as {status}"
        assert len(source) > 60, f"{name} has no usable source sentence"
        # The report writes the names in capitals — GARDEN, BUKIT KACA — and the row does not.
        assert name.lower() in source.lower(), f"{name}'s source sentence does not name it"
