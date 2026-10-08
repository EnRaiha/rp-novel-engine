"""Module review tests for modules/guardrails.py.

Defects covered:

1. The blocked terms are snake_case keys and the guard compared them literally,
   so an action written "mind control the captain" — the exact concept the guard
   exists to stop — was allowed. The haystack is closed up before matching now.
2. `blocked_words` was built inside the function on every call while the sibling
   list was a module constant, so the action list could not be asserted or read
   without calling the function. It is `BLOCKED_WORDS` now.
3. `check_action(None)` raised AttributeError on `.lower()`, which is a crash
   rather than a refusal.

`check_generation` is deliberately NOT normalized, and a test pins that choice:
its list is written in natural spelling, and closing the gaps there would block
innocent prose like "a minor in engineering" with no retry on the caller side.

No database: both entry points are pure functions.
"""
from __future__ import annotations

import pytest

import modules.guardrails as guardrails


# ── 1. The action guard sees through spelling ────────────────────────────

@pytest.mark.parametrize("action", [
    "mind_control the captain",
    "use mind control on the captain",
    "apply mind-control",
    "cause permanent_harm",
    "cause permanent harm to the crew",
    "irreversible damage to the moon",
    "slavery_of_children",
    "slavery of children",
])
async def test_the_action_guard_blocks_the_concept_however_it_is_spelled(action):
    out = await guardrails.check_action(action)

    assert out["allowed"] is False, out
    assert out["reason"].startswith("Blocked by guardrail:")


@pytest.mark.parametrize("action", [
    "walk to the dock",
    "mind the gap",
    "harmless banter with the dockmaster",
    "control the helm",
])
async def test_ordinary_actions_still_pass(action):
    out = await guardrails.check_action(action)

    assert out["allowed"] is True, out


async def test_the_blocked_terms_are_one_module_constant():
    assert isinstance(guardrails.BLOCKED_WORDS, tuple)
    assert "mind_control" in guardrails.BLOCKED_WORDS
    # the reason names the term that matched
    out = await guardrails.check_action("permanent harm")
    assert out["reason"].endswith("permanent_harm")


# ── 3. A missing action is a pass, not a crash ───────────────────────────

@pytest.mark.parametrize("action", [None, "", "   "])
async def test_a_missing_action_does_not_crash_the_guard(action):
    out = await guardrails.check_action(action)

    assert out["allowed"] is True, out


async def test_the_context_argument_is_accepted_and_unused():
    # the CLI passes {"session_id": sid}; the check is stateless
    with_ctx = await guardrails.check_action("walk to the dock", {"session_id": 5})
    without = await guardrails.check_action("walk to the dock")

    assert with_ctx == without


# ── check_generation keeps natural spelling ──────────────────────────────

@pytest.mark.parametrize("text", [
    "underage crew",
    "non-consensual scene",
    "child abuse",
    "a minor_in_ the ledger",
])
def test_the_generation_gate_blocks_its_list(text):
    assert guardrails.check_generation(text)["allowed"] is False


def test_the_generation_gate_is_not_closed_up_into_false_positives():
    out = guardrails.check_generation("She took a minor in engineering at the academy.")

    assert out["allowed"] is True, "closing the gaps would block innocent prose here"


def test_the_generation_gate_tolerates_empty_text():
    assert guardrails.check_generation(None)["allowed"] is True
    assert guardrails.check_generation("")["allowed"] is True


# ── Module contract ──────────────────────────────────────────────────────

async def test_contract_run_tick_answers_ready_for_the_engine_session(monkeypatch):
    monkeypatch.setenv("RP_SESSION", "77")

    assert await guardrails.run_tick() == {"status": "guardrails_ready"}


def test_contract_both_gates_return_the_same_shape():
    for result in (guardrails.check_generation("hello"),):
        assert set(result) == {"allowed", "reason"}
