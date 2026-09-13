#!/usr/bin/env python3
"""Guardrails — Ported from Rust guardrail.rs. Content safety checks, moral boundaries."""
from __future__ import annotations
from core.db import Database
from core.config import Config
from core.log import info

async def check_action(action: str, context: dict | None = None) -> dict:
    blocked_words = ["mind_control","permanent_harm","irreversible_damage","slavery_of_children"]
    lower = action.lower()
    for w in blocked_words:
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
    if session_id is None: session_id = Config.SESSION_ID
    return {"status": "guardrails_ready"}
