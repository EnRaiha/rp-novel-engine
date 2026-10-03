"""Module review: core/intent.py.

THREE DEFECTS.

The combat call passed its arguments in the wrong order. `battle.resolve_intent` is
`(session_id, action, target, fleet_name="")`, and this module called `(session_id, intent.target,
intent.item_used)`, so the target landed in `action`, which the resolver ignores, and the item
landed in `target`, which is the string the narrative and the defeat branch name. The resolver's
own docstring records the disagreement with the other caller, `scripts/kilo_bridge.py`. The call now
passes the action, the target and the fleet name, and agrees with the bridge.

That call sat inside `except Exception` with no line anywhere: a bug in the resolver came back to
the player as `Combat resolver error: ...` with nothing in the log to find it by.

For nine of the fourteen actions the dispatch claims to route, it answered `success: True`, `event:
<action>_queued`, and a note about a workflow, while it imported and called nothing. `scripts/cli.py`
prints that event straight to the player. The registry is a map of names rather than of callables
(`modules.fleet_expansion (workflow script)`, `narrative-only (no CPU state change)`), so the honest
answer is a refusal that names the resolver the action is registered to.

Reported, not changed: the amount guardrail compares every action's number against credits, while
the schema calls it "Numeric parameter (credits, ships, days)", so deploying five ships is refused
or allowed by the treasury; `resolve_creative` rolls `random()` in SQL and its comment called that
check deterministic; and `asyncio`, `json` and `Config` are imported and never used.

The tests here run with no database where the code path allows it, and the two that need state use a
scratch session removed in the fixture's finally.
"""
from __future__ import annotations

import os
import pathlib
import sys

import pytest
from pydantic import ValidationError

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import intent as intent_mod  # noqa: E402
from core.db import Database  # noqa: E402

SCRATCH_SESSION = 200 + (os.getpid() % 100)
TARGET = "Review Pirate Den"


@pytest.fixture()
async def scratch_session():
    """A session with one faction and no resources row, removed afterwards."""
    await Database.init()
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status)"
        " VALUES ($1,'Intent review session','active') ON CONFLICT (id) DO NOTHING",
        SCRATCH_SESSION,
    )
    await Database.execute(
        "INSERT INTO maya_rp.factions (session_id, name) VALUES ($1,$2)", SCRATCH_SESSION, TARGET)
    try:
        yield SCRATCH_SESSION
    finally:
        for statement in ("DELETE FROM maya_rp.factions WHERE session_id=$1",
                          "DELETE FROM maya_rp.sessions WHERE id=$1"):
            await Database.execute(statement, SCRATCH_SESSION)
        await Database.close()


class TestTheCombatCall:
    """`resolve_intent(session_id, action, target, fleet_name="")` took three arguments wrong."""

    @staticmethod
    async def _ok(*_args, **_kwargs):
        return True, "ok", {"resolver": "modules.battle.resolve_intent"}

    async def test_the_target_reaches_the_target_parameter(self, monkeypatch):
        seen: list[tuple] = []

        async def recorder(session_id, action, target, fleet_name=""):
            seen.append((session_id, action, target, fleet_name))
            return {"winner": "TKG"}

        monkeypatch.setattr(intent_mod, "validate_intent", self._ok)
        monkeypatch.setattr("modules.battle.resolve_intent", recorder)
        result = await intent_mod.resolve_intent_dispatch(
            SCRATCH_SESSION,
            intent_mod.PlayerIntent(action_type="attack", target=TARGET, item_used="Ironclad"),
        )
        assert seen == [(SCRATCH_SESSION, "attack", TARGET, "Ironclad")], seen
        assert result["success"] is True and result["event"] == "combat_resolved"

    async def test_a_resolver_that_fails_is_logged_before_it_is_reported(self, monkeypatch):
        said: list[str] = []

        async def broken(*_args, **_kwargs):
            raise RuntimeError("resolver blew up")

        monkeypatch.setattr(intent_mod, "validate_intent", self._ok)
        monkeypatch.setattr("modules.battle.resolve_intent", broken)
        monkeypatch.setattr("core.log.error", lambda module, message: said.append((module, message)))
        result = await intent_mod.resolve_intent_dispatch(
            SCRATCH_SESSION, intent_mod.PlayerIntent(action_type="attack", target=TARGET))
        assert result["success"] is False
        assert "resolver blew up" in result["error"]
        assert said and said[0][0] == "intent" and "resolver blew up" in said[0][1], said


class TestWhatTheDispatchActuallyDispatches:
    """Nine actions answered success without anything running."""

    @staticmethod
    async def _ok(*_args, **_kwargs):
        return True, "ok", {"resolver": "modules.movement.move_fleet"}

    async def test_an_action_nothing_invokes_is_not_reported_as_queued(self, monkeypatch):
        monkeypatch.setattr(intent_mod, "validate_intent", self._ok)
        result = await intent_mod.resolve_intent_dispatch(
            SCRATCH_SESSION,
            intent_mod.PlayerIntent(action_type="move", target="Rigel", amount=3),
        )
        assert result["success"] is False, "nothing ran, so nothing succeeded"
        assert result["event"] == "move_not_dispatched"
        assert result["resolver"] == "modules.movement.move_fleet", (
            "the refusal names the resolver the action is registered to")

    async def test_a_roll_is_still_acknowledged(self):
        result = await intent_mod.resolve_intent_dispatch(
            SCRATCH_SESSION, intent_mod.PlayerIntent(action_type="roll", target="2d6+1"))
        assert result == {"success": True, "event": "roll_requested", "expr": "2d6+1"}

    async def test_a_narrative_only_action_needs_no_dispatch(self):
        result = await intent_mod.resolve_intent_dispatch(
            SCRATCH_SESSION, intent_mod.PlayerIntent(action_type="look", dialogue="I look around"))
        assert result["success"] is True and result["narrative_only"] is True


class TestTheSchemaAndTheGuardrail:
    """The module's stated job: the LLM emits JSON, the CPU refuses what it cannot mean."""

    def test_an_unknown_action_is_refused(self):
        with pytest.raises(ValidationError):
            intent_mod.PlayerIntent(action_type="teleport")

    def test_a_hallucinated_key_is_refused(self):
        with pytest.raises(ValidationError):
            intent_mod.PlayerIntent(action_type="look", fleet_count=9000)

    def test_a_blank_field_is_read_as_absent(self):
        parsed = intent_mod.PlayerIntent(action_type="attack", target="   ", item_used="")
        assert parsed.target is None and parsed.item_used is None

    def test_a_negative_amount_is_refused(self):
        with pytest.raises(ValidationError):
            intent_mod.PlayerIntent(action_type="build", amount=-1)

    def test_every_action_in_the_schema_has_a_registry_entry(self):
        """`ctx["resolver"]` comes from this map, and the map is what the refusal names."""
        schema_actions = intent_mod.PlayerIntent.model_fields["action_type"].annotation
        assert set(intent_mod.RESOLVERS) == set(schema_actions.__args__)

    async def test_an_item_the_session_does_not_have_is_refused(self, scratch_session):
        ok, error, _ctx = await intent_mod.validate_intent(
            scratch_session, intent_mod.PlayerIntent(action_type="use_item", item_used="Ghost Ship"))
        assert ok is False and "Ghost Ship" in error

    async def test_a_target_that_is_not_in_the_sector_is_refused(self, scratch_session):
        ok, error, _ctx = await intent_mod.validate_intent(
            scratch_session, intent_mod.PlayerIntent(action_type="attack", target="Nowhere At All"))
        assert ok is False and "Nowhere At All" in error

    async def test_a_target_that_exists_passes_with_its_resolver(self, scratch_session):
        ok, error, ctx = await intent_mod.validate_intent(
            scratch_session, intent_mod.PlayerIntent(action_type="attack", target=TARGET))
        assert ok is True and error == "ok"
        assert ctx["resolver"] == "modules.battle.resolve_intent"
