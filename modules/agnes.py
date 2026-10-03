#!/usr/bin/env python3
"""Agnes AI — Ported from Rust agnes.rs. Sapiens gateway integration."""
from __future__ import annotations
from core.db import Database
from core.config import Config
from core.log import info

async def query(prompt: str, session_id: int | None = None) -> dict:
    """Stub gateway: answers that Agnes *would* process the prompt.

    `session_id` is resolved and unused because the stub reads nothing. A
    non-string prompt used to fail on the slice with a TypeError naming no
    argument, so it is refused by name instead. The module is disabled in the
    registry (`"agnes": False`) and has no caller.
    """
    if session_id is None: session_id = Config.SESSION_ID
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError(f"prompt must be a non-empty string, got {prompt!r}")
    info("agnes", f"Query: {prompt[:80]}")
    return {"response": f"Agnes would process: {prompt[:100]}", "prompt": prompt[:100],
            "session_id": session_id}

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    return {"status": "agnes_ready"}
