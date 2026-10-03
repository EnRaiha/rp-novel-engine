"""Module review: consequences.py.

The ripple system was written, wired into the tick, and could not land an effect
that did not carry its own delay. `process_due` read a missing `delay_ticks` as
999 ticks, so a seed planted without one waited 999 game days: stored, counted as
pending, and never reached. No module passed one. A teammate worked around it at
the single call site in roll_theater; the default is fixed here instead, so the
next caller does not have to know.

Four more defects sat behind it, all of the same family: an effect that could not
land was still reported as landed. `_fire` returned nothing, so a stat update
matching no resources row, a faction name matching no faction, and an effect type
that does not exist at all were each counted in `fired` and then deleted from the
seed. The session fallback also read `Config.SESSION_ID`, resolved once at import,
which is the drift `core.session.stale_process_default` describes.

The scratch session is derived from the process id, the pattern tests/test_ooc.py
uses, so concurrent runs do not delete each other's rows. Every write this file
makes is removed in the fixture's finally.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import consequences  # noqa: E402
from core.db import Database  # noqa: E402

SCRATCH_SESSION = 800 + (os.getpid() % 100)

#: Rows this file owns. Removed before and after every test.
CLEANUP = (
    "DELETE FROM maya_rp.consequence_seeds WHERE session_id=$1",
    "DELETE FROM maya_rp.events WHERE session_id=$1",
)


async def _clear(session_id: int) -> None:
    for statement in CLEANUP:
        await Database.execute(statement, session_id)


@pytest.fixture()
async def scratch_session():
    """A disposable campaign with no resources row, removed afterwards."""
    await Database.init()
    await _clear(SCRATCH_SESSION)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status, game_day) VALUES ($1,'Consequence scratch','active',10)"
        " ON CONFLICT (id) DO UPDATE SET game_day=10",
        SCRATCH_SESSION,
    )
    try:
        yield SCRATCH_SESSION
    finally:
        await _clear(SCRATCH_SESSION)
        await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", SCRATCH_SESSION)
        await Database.close()


async def _plant(session_id: int, effects: list[dict], **extra):
    """Plant one seed and return its id."""
    seed = {
        "session_id": session_id,
        "trigger": "review_trigger",
        "cause_description": "a partial roll",
        "effects": effects,
        **extra,
    }
    return await consequences.plant(seed)


async def _stored_effects(seed_id: int) -> list[dict]:
    row = await Database.fetchrow(
        "SELECT effects_jsonb, status FROM maya_rp.consequence_seeds WHERE id=$1", seed_id)
    effects = row["effects_jsonb"]
    return json.loads(effects) if isinstance(effects, str) else effects


class TestTheDelayDefault:
    """The defect the Lead named: a seed without a delay never landed."""

    async def test_an_effect_with_no_delay_lands_on_the_next_tick(self, scratch_session):
        """Before the fix this returned fired=[] and left the seed planted for good."""
        seed_id = await _plant(scratch_session, [{"type": "event", "template": "ambush"}])
        fired = await consequences.process_due(scratch_session)
        assert len(fired) == 1, fired
        assert fired[0]["effect"]["template"] == "ambush"

    async def test_the_stored_effect_carries_the_delay_it_was_counted_against(self, scratch_session):
        seed_id = await _plant(scratch_session, [{"type": "event", "template": "ambush"}])
        effects = await _stored_effects(seed_id)
        assert effects[0]["delay_ticks"] == 0, effects

    async def test_an_explicit_delay_still_waits(self, scratch_session):
        seed_id = await _plant(
            scratch_session, [{"type": "event", "template": "later", "delay_ticks": 5}])
        fired = await consequences.process_due(scratch_session)
        assert fired == [], fired
        # Still planted, and still holding the effect that has not come due.
        assert len(await _stored_effects(seed_id)) == 1

    async def test_a_zero_delay_is_read_as_now_and_not_as_absent(self, scratch_session):
        """`or` would turn a real zero into the old 999; the fix reads the key."""
        seed_id = await _plant(
            scratch_session, [{"type": "event", "template": "now", "delay_ticks": 0}])
        fired = await consequences.process_due(scratch_session)
        assert len(fired) == 1, fired


class TestAnEffectThatCannotLand:
    """`_fire` returned None, so nothing could tell a landed effect from a lost one."""

    async def test_an_unknown_effect_type_is_not_counted_as_fired(self, scratch_session):
        seed_id = await _plant(scratch_session, [{"type": "nonsense"}])
        fired = await consequences.process_due(scratch_session)
        assert fired == [], fired

    async def test_a_stat_effect_with_no_resources_row_is_not_counted_as_fired(self, scratch_session):
        """A session with no resources row paid nothing, and the seed said it paid."""
        has_row = await Database.fetchval(
            "SELECT 1 FROM maya_rp.resources WHERE session_id=$1", scratch_session)
        assert has_row is None, "this test needs a session with no resources row"
        seed_id = await _plant(
            scratch_session, [{"type": "stat", "target": "aggregate_morale", "delta": -5}])
        fired = await consequences.process_due(scratch_session)
        assert fired == [], fired

    async def test_a_faction_reaction_that_matches_nothing_is_not_counted(self, scratch_session):
        seed_id = await _plant(scratch_session, [{
            "type": "faction_reaction", "faction": "no such faction", "action": "increase_aggression"}])
        fired = await consequences.process_due(scratch_session)
        assert fired == [], fired

    async def test_a_code_path_that_did_not_land_still_exhausts_the_seed(self, scratch_session):
        """Dropping it is right; retrying a type that does not exist would loop forever."""
        seed_id = await _plant(scratch_session, [{"type": "nonsense"}])
        await consequences.process_due(scratch_session)
        row = await Database.fetchrow(
            "SELECT status FROM maya_rp.consequence_seeds WHERE id=$1", seed_id)
        assert row["status"] == "exhausted", row


class TestTheSessionItActsOn:
    """A fallback that reads Config.SESSION_ID reads the session this process started with."""

    async def test_a_session_that_does_not_exist_is_refused_by_name(self):
        await Database.init()
        with pytest.raises(ValueError, match="no session 999999"):
            await consequences.process_due(999999)
        await Database.close()

    async def test_zero_means_no_session_named_rather_than_session_zero(self):
        """The engine rule: 0 and blank are unset. Before, 0 queried session 0 and matched nothing."""
        from core.session import resolve_session

        resolved = resolve_session()
        assert consequences._session(None) == resolved
        assert consequences._session(0) == resolved
        assert consequences._session("") == resolved


class TestPrevent:
    """`prevent` had no caller and no way to reach it: plant returned nothing."""

    async def test_plant_returns_the_id_prevent_takes(self, scratch_session):
        seed_id = await _plant(
            scratch_session, [{"type": "event", "template": "ambush"}], can_be_prevented=True)
        assert isinstance(seed_id, int) and seed_id > 0

    async def test_preventing_a_planted_seed_reports_that_it_worked(self, scratch_session):
        seed_id = await _plant(scratch_session, [{"type": "event", "template": "ambush"}])
        assert await consequences.prevent(seed_id, "counter-intel", scratch_session) is True
        row = await Database.fetchrow(
            "SELECT status, prevention_method FROM maya_rp.consequence_seeds WHERE id=$1", seed_id)
        assert row["status"] == "prevented" and row["prevention_method"] == "counter-intel"

    async def test_preventing_nothing_reports_that_it_failed(self, scratch_session):
        assert await consequences.prevent(999999, "counter-intel", scratch_session) is False

    async def test_a_prevented_seed_does_not_fire(self, scratch_session):
        seed_id = await _plant(scratch_session, [{"type": "event", "template": "ambush"}])
        await consequences.prevent(seed_id, "counter-intel", scratch_session)
        assert await consequences.process_due(scratch_session) == []


class TestPlantValidation:
    """A seed is a contract. A missing field used to be a KeyError three frames deep."""

    async def test_a_seed_with_no_trigger_is_refused(self, scratch_session):
        with pytest.raises(ValueError, match="trigger"):
            await consequences.plant(
                {"session_id": scratch_session, "cause_description": "x",
                 "effects": [{"type": "event"}]})

    async def test_effects_must_be_a_non_empty_list(self, scratch_session):
        with pytest.raises(ValueError, match="non-empty list"):
            await consequences.plant(
                {"session_id": scratch_session, "trigger": "t", "cause_description": "x", "effects": []})

    async def test_an_effect_with_no_type_is_refused(self, scratch_session):
        with pytest.raises(ValueError, match="has no type"):
            await consequences.plant(
                {"session_id": scratch_session, "trigger": "t", "cause_description": "x",
                 "effects": [{"delay_ticks": 1}]})

    async def test_a_negative_delay_is_refused(self, scratch_session):
        with pytest.raises(ValueError, match="negative"):
            await consequences.plant(
                {"session_id": scratch_session, "trigger": "t", "cause_description": "x",
                 "effects": [{"type": "event", "delay_ticks": -1}]})

    async def test_a_delay_that_is_not_a_number_is_refused(self, scratch_session):
        with pytest.raises(ValueError, match="not a number"):
            await consequences.plant(
                {"session_id": scratch_session, "trigger": "t", "cause_description": "x",
                 "effects": [{"type": "event", "delay_ticks": "soon"}]})


class TestRunTick:
    async def test_run_tick_reports_the_count_it_fired(self, scratch_session):
        await _plant(scratch_session, [{"type": "event", "template": "ambush"}])
        out = await consequences.run_tick(scratch_session)
        assert out == {"fired": 1}, out

    async def test_run_tick_reports_a_bad_session_as_an_error_dict(self):
        """The orchestrator reads a dict with 'error' as a module failure."""
        await Database.init()
        out = await consequences.run_tick(999999)
        assert "error" in out, out
        await Database.close()
