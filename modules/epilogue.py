#!/usr/bin/env python3
"""Epilogue — Ported from Rust epilogue.rs. End-game narrative and victory wrap-up."""
from __future__ import annotations
from core.db import Database
from core.log import info
from core.session import require_session


def _writable_session(session_id: int | None) -> int:
    """Resolve the session for one call and refuse a frozen campaign.

    Sessions 3 and 5 are reference data; a writer that skipped this check mutated them.

    @param session_id - caller's session; `None` resolves through `core.session.require_session`.
    @returns the resolved session id.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    from core.ooc import _refuse_frozen

    sid = require_session(session_id)
    _refuse_frozen(sid)
    return sid

async def generate(session_id: int | None = None) -> dict:
    """Summarise a campaign. Read-only, so a frozen campaign may call it.

    @param session_id - campaign; `None` resolves through `require_session`.
    """
    session_id = require_session(session_id)
    chars = await Database.fetchval("SELECT COUNT(*) FROM maya_rp.characters WHERE session_id=$1", session_id) or 0
    ships = await Database.fetchval("SELECT COUNT(*) FROM maya_rp.ships WHERE session_id=$1", session_id) or 0
    events = await Database.fetchval("SELECT COUNT(*) FROM maya_rp.events WHERE session_id=$1", session_id) or 0
    # victory_tracking is faction-scoped (faction_id) — there is no session_id,
    # so reach the session through factions.
    victories = await Database.fetch(
        "SELECT vt.victory_type, vt.progress FROM maya_rp.victory_tracking vt "
        "JOIN maya_rp.factions f ON f.id = vt.faction_id WHERE f.session_id = $1", session_id)
    v_data = {r["victory_type"]: r["progress"] for r in victories} if victories else {}
    return {
        "characters": chars, "ships": ships, "events": events,
        "victory_data": v_data,
        "summary": f"Campaign concluded. {chars} characters, {ships} ships, {events} events across the journey.",
    }

async def run_tick(session_id: int | None = None) -> dict:
    """No-op tick. @raises core.ooc.FrozenSession - the campaign is frozen."""
    _writable_session(session_id)
    return {"status": "epilogue_ready"}
