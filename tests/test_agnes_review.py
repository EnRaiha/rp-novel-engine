"""Module review tests for modules/agnes.py.

Findings:

1. `query(None)` (or any non-string prompt) failed on the slice with a TypeError
   that named no argument, which is a crash rather than a refusal. It is refused
   by name now.
2. `session_id` is resolved and unused because the gateway is a stub that reads
   nothing; the response now echoes the session so the caller can see which
   campaign it answered for.
3. The module is disabled in the registry (`"agnes": False`) and `query` has no
   caller in the repo. That is reported, not wired: the stub needs a Sapiens
   gateway first.

No database: the module never reads one.
"""
from __future__ import annotations

import pytest

import modules.agnes as agnes


async def test_a_prompt_is_answered_and_logged(monkeypatch):
    seen = []
    monkeypatch.setattr("modules.agnes.info", lambda mod, msg: seen.append(msg))

    out = await agnes.query("hail the Sapiens gateway")

    assert out["response"] == "Agnes would process: hail the Sapiens gateway"
    assert out["prompt"] == "hail the Sapiens gateway"
    assert seen and "hail the Sapiens" in seen[0]


@pytest.mark.parametrize("prompt", [None, "", "   ", 42, {"a": 1}])
async def test_a_bad_prompt_is_refused_by_name(prompt):
    with pytest.raises(ValueError, match="prompt must be a non-empty string"):
        await agnes.query(prompt)


async def test_the_session_defaults_to_the_resolved_session(monkeypatch):
    """The default comes from `require_session` (RP_SESSION), not from the import-time `Config.SESSION_ID`."""
    monkeypatch.setenv("RP_SESSION", "77")

    out = await agnes.query("status")

    assert out["session_id"] == 77


async def test_an_explicit_session_is_carried_back(monkeypatch):
    out = await agnes.query("status", session_id=9)

    assert out["session_id"] == 9


def test_the_prompt_is_echoed_to_the_declared_length():
    import asyncio

    long_prompt = "x" * 200
    out = asyncio.run(agnes.query(long_prompt))

    assert len(out["prompt"]) == 100
    assert out["response"].endswith(out["prompt"])


async def test_contract_run_tick_reports_ready_without_touching_the_world(monkeypatch):
    monkeypatch.setenv("RP_SESSION", "77")

    assert await agnes.run_tick() == {"status": "agnes_ready"}
