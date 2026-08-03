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

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    return {"status": "guardrails_ready"}
