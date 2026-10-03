"""Encounters and narrative_seeds review: what reading both files in full turned up.

Nothing here writes to session 3, and every row this file creates in session 5 is removed by the id it
was given.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from core.db import Database  # noqa: E402
from modules import encounters, narrative_seeds  # noqa: E402

SESSION = 5


async def _seed(session_id=SESSION, status="planted", days=30):
    return await Database.fetchval(
        "INSERT INTO maya_rp.narrative_seeds "
        "(session_id, seed_type, content, planted_at_game_day, status, payoff_game_day) "
        "VALUES ($1, 'review', 'a review seed', 1, $2, $3) RETURNING id",
        session_id, status, days)


async def _drop(seed_id):
    await Database.execute("DELETE FROM maya_rp.narrative_seeds WHERE id = $1", seed_id)


class TestTheEncounterCategory:
    async def test_an_unknown_category_is_reported_not_hidden(self):
        """It still answers with a space phenomenon; the answer now says which word it could not use."""
        out = await encounters.generate_event(SESSION, "hazard", 5)
        assert out["category"] == "space_phenomena", out
        assert out["requested_category"] == "hazard", out
        assert out["available"] == sorted(encounters.ENCOUNTER_CATEGORIES)
        assert "requested_category" not in await encounters.generate_event(SESSION, "combat", 5)

    async def test_a_known_category_rolls_from_its_own_table(self):
        out = await encounters.generate_event(SESSION, "disaster", 5)
        assert out["event_type"] in encounters.ENCOUNTER_CATEGORIES["disaster"], out
        assert out["tier"] in ("standard", "elite", "boss"), out


class TestTheEncountersTick:
    async def test_a_failing_tick_is_logged_as_a_fault(self, monkeypatch):
        seen = []

        async def boom(*args, **kwargs):
            raise RuntimeError("events query died")

        monkeypatch.setattr(encounters.Database, "fetch", boom)
        monkeypatch.setattr(encounters, "error", lambda module, message: seen.append(message))
        out = await encounters.run_tick(SESSION)
        assert "events query died" in out["error"], out
        assert seen, "a failing tick returned a dict and said nothing at fault level"


class TestTheSeedBelongsToItsCampaign:
    async def test_another_campaigns_seed_cannot_be_foreshadowed(self):
        """The lookup ran by seed id alone and never read the session it was handed."""
        await Database.init()
        seed = await _seed(session_id=3)
        try:
            out = await narrative_seeds.mark_foreshadowed(seed, SESSION)
            assert out["marked"] is False, out
            count = await Database.fetchval(
                "SELECT COALESCE(foreshadow_count, 0) FROM maya_rp.narrative_seeds WHERE id = $1",
                seed)
            assert count == 0, "another campaign's seed was marked hinted"
        finally:
            await _drop(seed)
            await Database.close()

    async def test_its_own_seed_advances_and_then_pays_off(self):
        await Database.init()
        seed = await _seed()
        try:
            first = await narrative_seeds.mark_foreshadowed(seed, SESSION)
            assert first == {"seed_id": seed, "marked": True, "status": "foreshadowed"}, first
            status = await Database.fetchval(
                "SELECT status FROM maya_rp.narrative_seeds WHERE id = $1", seed)
            assert status == "foreshadowed", status
        finally:
            await _drop(seed)
            await Database.close()

    async def test_another_campaigns_seed_cannot_be_paid_off(self):
        await Database.init()
        seed = await _seed(session_id=3)
        try:
            out = await narrative_seeds.pay_off(seed, SESSION)
            assert "not found in session 5" in out.get("error", ""), out
            status = await Database.fetchval(
                "SELECT status FROM maya_rp.narrative_seeds WHERE id = $1", seed)
            assert status == "planted", "another campaign's seed was paid off"
        finally:
            await _drop(seed)
            await Database.close()

    async def test_its_own_seed_pays_off_and_logs_the_event(self):
        await Database.init()
        seed = await _seed()
        try:
            out = await narrative_seeds.pay_off(seed, SESSION)
            assert out["paid_off"] is True, out
            status = await Database.fetchval(
                "SELECT status FROM maya_rp.narrative_seeds WHERE id = $1", seed)
            assert status == "paid_off", status
        finally:
            await Database.execute(
                "DELETE FROM maya_rp.events WHERE session_id = $1 AND event_type = 'payoff' "
                "AND description = 'a review seed'", SESSION)
            await _drop(seed)
            await Database.close()


class TestTheSeedTick:
    async def test_the_tick_pays_off_only_what_is_due_in_its_campaign(self):
        await Database.init()
        mine = await _seed(days=-1)
        theirs = await _seed(session_id=3, days=-1)
        try:
            out = await narrative_seeds.run_tick(SESSION)
            assert out == {"auto_payoffs": 1}, out
            assert await Database.fetchval(
                "SELECT status FROM maya_rp.narrative_seeds WHERE id = $1", mine) == "paid_off"
            assert await Database.fetchval(
                "SELECT status FROM maya_rp.narrative_seeds WHERE id = $1", theirs) == "planted"
        finally:
            await Database.execute(
                "DELETE FROM maya_rp.events WHERE session_id = $1 AND event_type = 'payoff'", SESSION)
            await _drop(mine)
            await _drop(theirs)
            await Database.close()

    async def test_a_failing_tick_is_logged_as_a_fault(self, monkeypatch):
        seen = []

        async def boom(*args, **kwargs):
            raise RuntimeError("seed query died")

        monkeypatch.setattr(narrative_seeds.Database, "fetchval", boom)
        monkeypatch.setattr(narrative_seeds, "error", lambda module, message: seen.append(message))
        out = await narrative_seeds.run_tick(SESSION)
        assert "seed query died" in out["error"], out
        assert seen, "a failing tick returned a dict and said nothing at fault level"

    async def test_the_foreshadow_plan_is_scoped_and_ordered(self):
        await Database.init()
        mine = await _seed()
        theirs = await _seed(session_id=3)
        try:
            plan = await narrative_seeds.get_foreshadow_ops(SESSION)
            assert [p["id"] for p in plan] == [mine], plan
        finally:
            await _drop(mine)
            await _drop(theirs)
            await Database.close()
