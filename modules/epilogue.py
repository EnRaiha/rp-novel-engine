#!/usr/bin/env python3
"""Epilogue — Ported from Rust epilogue.rs. End-game narrative and victory wrap-up."""
from __future__ import annotations
from core.db import Database
from core.config import Config
from core.log import info

async def generate(session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
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

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    return {"status": "epilogue_ready"}
