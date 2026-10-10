"""The tables migration 138 binds: manufacturing, tech_tree and roll_theater name their campaign.

`production_lines`, `research_labs` and `pool_bets` carry `session_id`, so a read is scoped by it and a
write names it. Each module is driven through its own entry point, and the row that proves the binding
is a row whose marker disagrees with the table it hangs off: a line whose colony sits in one campaign
while the line names another, a lab on this campaign's colony that names another, a bet on this
campaign's pool that names another.

Every row lives in a scratch campaign (900-999). `scratch_session` hands this file one id and the
fixture adds a second, `OTHER`, both cleared before the file ends. Sessions 3 and 5 are never written.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest_asyncio  # noqa: E402

from core.db import Database  # noqa: E402
from modules import manufacturing as mf, roll_theater as rt, tech_tree  # noqa: E402
from tests.conftest import _clear_session_rows, scratch_id  # noqa: E402

#: The fixture's own slot, and a neighbour half a cycle away, so the two never collide.
OWN = scratch_id(__name__)
OTHER = 900 + (OWN - 900 + 50) % 100

#: Recipe 9, Alloy Ingot Smelting: Raw Ore 5 + Power Cell 1 -> Alloy Ingot 3.
RECIPE = 9

#: What one tick of a line with no lab and no tech score advances: base 1, so `10 + 1`.
GAIN_WITHOUT_LABS = 11


@pytest_asyncio.fixture
async def pair(scratch_session):
    """Two scratch campaigns, and both rows removed after the test."""
    assert scratch_session == OWN, (scratch_session, OWN)
    await Database.init()
    for session_id in (scratch_session, OTHER):
        await _clear_session_rows(session_id)
        await Database.execute(
            "INSERT INTO maya_rp.sessions (id, name, status, game_day)"
            " VALUES ($1, 'state tables scratch', 'active', 40)"
            " ON CONFLICT (id) DO NOTHING", session_id)
    try:
        yield scratch_session, OTHER
    finally:
        # `scratch_session` owns its own slot; this clears the neighbour this fixture made.
        await _clear_session_rows(OTHER)
        try:
            await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", OTHER)
        except Exception as exc:  # noqa: BLE001 - a child row left behind must not hide the result
            print(f"pair: could not remove the sessions row {OTHER}: {exc!r}")
        await Database.close()


# ── rows the tests plant ────────────────────────────────────────────────────────────────────────

async def _colony(session_id: int, name: str) -> int:
    return await Database.fetchval(
        "INSERT INTO maya_rp.colonies (session_id, name) VALUES ($1, $2) RETURNING id",
        session_id, name)


async def _resources(session_id: int, credits: int = 0, alloys: int = 0, tech_score: int = 0) -> None:
    await Database.execute("DELETE FROM maya_rp.resources WHERE session_id = $1", session_id)
    await Database.execute(
        "INSERT INTO maya_rp.resources (session_id, credits, alloys, tech_score)"
        " VALUES ($1, $2, $3, $4)", session_id, credits, alloys, tech_score)


async def _stock(session_id: int, colony: int, material: str, quantity: int) -> None:
    await Database.execute(
        "INSERT INTO maya_rp.material_stockpiles (session_id, colony_id, material_name, quantity)"
        " VALUES ($1, $2, $3, $4)", session_id, colony, material, quantity)


async def _stock_of(session_id: int, material: str) -> int:
    return int(await Database.fetchval(
        "SELECT COALESCE(SUM(quantity), 0) FROM maya_rp.material_stockpiles"
        " WHERE session_id = $1 AND material_name = $2", session_id, material) or 0)


async def _line(session_id: int, colony: int, status: str = "running") -> int:
    """A running line. `production_lines.session_id` decides which campaign ticks it."""
    return await Database.fetchval(
        "INSERT INTO maya_rp.production_lines (session_id, colony_id, recipe_id, status, efficiency)"
        " VALUES ($1, $2, $3, $4, 1.0) RETURNING id", session_id, colony, RECIPE, status)


async def _lab(session_id: int, colony: int, name: str, rate: int = 1) -> int:
    return await Database.fetchval(
        "INSERT INTO maya_rp.research_labs"
        " (session_id, colony_id, name, level, research_field, research_rate)"
        " VALUES ($1, $2, $3, 1, 'physics', $4::int) RETURNING id", session_id, colony, name, rate)


async def _scientist(session_id: int, name: str) -> int:
    return await Database.fetchval(
        "INSERT INTO maya_rp.characters (session_id, name, status) VALUES ($1, $2, 'active')"
        " RETURNING id", session_id, name)


# ── manufacturing ───────────────────────────────────────────────────────────────────────────────

async def test_a_line_marked_for_another_campaign_is_not_ticked(pair):
    """The colony is this campaign's; the line names the other one, so the tick leaves it alone."""
    own, other = pair
    colony = await _colony(own, "binding colony")
    await _stock(own, colony, "Raw Ore", 5)
    await _stock(own, colony, "Power Cell", 1)
    await _line(other, colony)

    out = await mf.run_tick(own)

    assert out == {"lines": 0, "blocked": 0, "unblocked": 0}, out
    assert await _stock_of(own, "Raw Ore") == 5, "a foreign line consumed this campaign's stock"
    assert await _stock_of(own, "Alloy Ingot") == 0, "a foreign line produced into this campaign"


async def test_a_line_that_names_its_campaign_is_ticked(pair):
    """The filter must not starve the campaign that owns the line."""
    own, _ = pair
    colony = await _colony(own, "binding colony")
    await _stock(own, colony, "Raw Ore", 5)
    await _stock(own, colony, "Power Cell", 1)
    await _line(own, colony)

    out = await mf.run_tick(own)

    assert out == {"lines": 1, "blocked": 0, "unblocked": 0}, out
    assert await _stock_of(own, "Alloy Ingot") == 3, await _stock_of(own, "Alloy Ingot")


# ── tech_tree ───────────────────────────────────────────────────────────────────────────────────

async def test_a_built_lab_carries_its_campaign(pair):
    """The insert names the session, so the column default never decides."""
    own, _ = pair
    await _resources(own, credits=5000)
    await _colony(own, "binding colony")
    lab = None
    try:
        out = await tech_tree.build_lab("binding colony", "binding lab", "physics", own)
        assert "error" not in out, out
        lab = out["lab_id"]
        marker = await Database.fetchval(
            "SELECT session_id FROM maya_rp.research_labs WHERE id = $1", lab)
        assert marker == own, f"the lab landed in session {marker}"
    finally:
        # The row is removed by id: a lab the default marked for another campaign is not this
        # fixture's to leave behind.
        if lab is not None:
            await Database.execute("DELETE FROM maya_rp.research_labs WHERE id = $1", lab)


async def test_list_labs_skips_a_lab_marked_for_another_campaign(pair):
    own, other = pair
    colony = await _colony(own, "binding colony")
    await _lab(other, colony, "foreign lab")

    assert await tech_tree.list_labs(own) == []


async def test_a_lab_marked_for_another_campaign_takes_no_scientist(pair):
    own, other = pair
    colony = await _colony(own, "binding colony")
    lab = await _lab(other, colony, "foreign lab")
    await _scientist(own, "binding scientist")
    try:
        out = await tech_tree.assign_scientist("binding scientist", lab, "physics", own)

        assert f"not found in session {own}" in out.get("error", ""), out
        assigned = await Database.fetchval(
            "SELECT COUNT(*) FROM maya_rp.scientist_assignments WHERE lab_id = $1", lab)
        assert assigned == 0, "a scientist joined another campaign's lab"
    finally:
        # `scientist_assignments` carries no session of its own, so the fixture cannot see this row.
        await Database.execute(
            "DELETE FROM maya_rp.scientist_assignments WHERE lab_id = $1", lab)


async def test_the_tick_counts_only_its_own_labs(pair):
    """A foreign lab used to raise this campaign's research rate through its colony."""
    own, other = pair
    colony = await _colony(own, "binding colony")
    await _lab(other, colony, "foreign lab", rate=20)
    await _resources(own, alloys=10_000, credits=10_000)
    technology = await Database.fetchval(
        "INSERT INTO maya_rp.technologies"
        " (session_id, name, field, tier, researched, research_progress)"
        " VALUES ($1, 'binding probe', 'physics', 1, false, 5) RETURNING id", own)

    out = await tech_tree.run_tick(own)

    assert out == {"active": 1, "completed": 0}, out
    progress = await Database.fetchval(
        "SELECT research_progress FROM maya_rp.technologies WHERE id = $1", technology)
    assert progress == 5 + GAIN_WITHOUT_LABS, f"a foreign lab raised the rate: {progress}"


# ── roll_theater ────────────────────────────────────────────────────────────────────────────────

async def test_a_pool_writes_its_campaign_on_every_bet(pair):
    own, _ = pair
    await Database.execute(
        "INSERT INTO maya_rp.crew_roster (session_id, name, status)"
        " VALUES ($1, 'binding crew', 'active')", own)
    pool = None
    try:
        pool = await rt.open_pool(own, "Binding Pool", 50)

        bets = await Database.fetch(
            "SELECT session_id, bet_credits FROM maya_rp.pool_bets WHERE pool_id = $1",
            pool["pool_id"])
        assert bets, "the pool opened with no bettor"
        assert {row["session_id"] for row in bets} == {own}, [dict(row) for row in bets]
        assert pool["credits_in_pool"] == sum(row["bet_credits"] for row in bets), pool
    finally:
        # The pool is this test's, so its book is removed by pool id: a bet the column default
        # marked for another campaign is not this fixture's to leave behind.
        if pool is not None:
            await Database.execute(
                "DELETE FROM maya_rp.pool_bets WHERE pool_id = $1", pool["pool_id"])
            await Database.execute("DELETE FROM maya_rp.roll_pools WHERE id = $1", pool["pool_id"])


async def test_a_pool_pays_only_its_own_campaign_bets(pair):
    """Two bets share one pool id. Only this campaign's bet is read, so only it can win."""
    own, other = pair
    await _resources(own, credits=1000)
    pool = await Database.fetchval(
        "INSERT INTO maya_rp.roll_pools (session_id, pool_name, odds, credits_in_pool, status)"
        " VALUES ($1, 'Binding Pool', '1:1', 1000, 'open') RETURNING id", own)
    mine = await Database.fetchval(
        "INSERT INTO maya_rp.pool_bets"
        " (session_id, pool_id, bettor_name, bet_credits, bet_side)"
        " VALUES ($1, $2, 'Binding Mine', 500, 'house') RETURNING id", own, pool)
    foreign = await Database.fetchval(
        "INSERT INTO maya_rp.pool_bets"
        " (session_id, pool_id, bettor_name, bet_credits, bet_side)"
        " VALUES ($1, $2, 'Binding Foreign', 500, 'king') RETURNING id", other, pool)

    out = await rt.resolve_pool(own, king_won=True)

    assert out["resolved"] is True, out
    assert out["paid"] == 0, "a bet from another campaign was paid"
    assert out["crown_fee"] == 500, out
    paid_foreign = await Database.fetchval(
        "SELECT payout FROM maya_rp.pool_bets WHERE id = $1", foreign)
    assert paid_foreign == 0, "the foreign bet holds the winning side and was paid"
    paid_mine = await Database.fetchval("SELECT payout FROM maya_rp.pool_bets WHERE id = $1", mine)
    assert paid_mine == 0, "a losing bet was paid"
