#!/usr/bin/env python3
"""Guardrails — Ported from Rust guardrail.rs. Content safety checks, moral boundaries."""
from __future__ import annotations
import re
from core.db import Database
from core.config import Config
from core.session import require_session
from core.log import info

# The blocked terms are snake_case keys, so the haystack is closed up before the
# match: an action written "mind control" walked straight past a literal "_"
# compare and was allowed. Same list, one definition, not rebuilt per call.
BLOCKED_WORDS = ("mind_control", "permanent_harm", "irreversible_damage",
                 "slavery_of_children")

_ACTION_GAP_RE = re.compile(r"[\s\-]+")


def _normalize_action(action) -> str:
    """Lowercase and close the gaps: spaces and hyphens become underscores.

    `check_generation` is NOT normalized. Its list is written in natural
    spelling already ("underage", "non-consensual", "child abuse"), and closing
    the gaps there would block innocent prose like "a minor in engineering"
    with no retry on the caller's side.
    """
    return _ACTION_GAP_RE.sub("_", str(action if action is not None else "").lower())


async def check_action(action: str, context: dict | None = None) -> dict:
    """Gate one proposed action.

    `context` is accepted and unused: the check is stateless, so there is no
    session to scope. The CLI passes {"session_id": sid} for a future rule.
    """
    lower = _normalize_action(action)
    for w in BLOCKED_WORDS:
        if w in lower:
            return {"allowed": False, "reason": f"Blocked by guardrail: {w}"}
    return {"allowed": True, "reason": "Passes all guardrails"}

GEN_BLOCKED = ["underage", "minor_in_", "non-consensual", "child abuse"]

def check_generation(text: str) -> dict:
    """Gate local-model prose before it reaches the GM (qwen-abliterated
    has no built-in guardrails). Returns {allowed, reason}."""
    low = (text or "").lower()
    for w in GEN_BLOCKED:
        if w in low:
            return {"allowed": False, "reason": f"Blocked by generation guardrail: {w}"}
    return {"allowed": True, "reason": "Passes generation guardrails"}

async def run_tick(session_id: int = None) -> dict:
    session_id = require_session(session_id)
    return {"status": "guardrails_ready"}
