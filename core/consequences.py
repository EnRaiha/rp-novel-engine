#!/usr/bin/env python3
"""Consequence chains — delayed cascading effects. Actions at tick N → effects at N+delay."""
from __future__ import annotations
import json
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info

async def _current_tick(session_id: int) -> int:
    """Get the current session game day as tick number."""
    row = await Database.fetchrow("SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id)
    return row["game_day"] or 1

async def plant(seed: dict):
    """Plant a consequence seed.
    seed = {"trigger":"...", "session_id":3, "cause_description":"...",
            "effects": [{"delay_ticks":2, "type":"event", "template":"ambush", "severity":"high", "description":"..."}],
            "can_be_prevented":True, "prevention_action":"..."}
    """
    sid = seed.get("session_id", Config.SESSION_ID)
    tick = await _current_tick(sid)
    await Database.execute(
        "INSERT INTO maya_rp.consequence_seeds (session_id, trigger_type, cause_description, "
        "effects_jsonb, planted_at_tick, can_be_prevented, prevention_action, status) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,'planted')",
        sid, seed["trigger"], seed["cause_description"],
        json.dumps(seed["effects"]), tick,
        seed.get("can_be_prevented", False), seed.get("prevention_action"))
    info("consequences", f"Planted: {seed['trigger']} ({len(seed['effects'])} effects)")


async def process_due(session_id: int = None) -> list[dict]:
    """Process all due consequences for this tick."""
    if session_id is None:
        session_id = Config.SESSION_ID
    current = await _current_tick(session_id)

    seeds = await Database.fetch(
        "SELECT id, trigger_type, cause_description, effects_jsonb, planted_at_tick, "
        "can_be_prevented, prevention_action "
        "FROM maya_rp.consequence_seeds WHERE session_id=$1 AND status='planted'",
        session_id)

    fired = []
    for seed in seeds:
        effects = seed["effects_jsonb"]
        if isinstance(effects, str):
            effects = json.loads(effects)
        remaining = []
        for eff in effects:
            ticks_since = current - seed["planted_at_tick"]
            if ticks_since >= eff.get("delay_ticks", 999):
                await _fire(eff, seed, session_id)
                fired.append({"effect": eff, "cause": seed["cause_description"]})
            else:
                remaining.append(eff)

        if not remaining:
            await Database.execute(
                "UPDATE maya_rp.consequence_seeds SET status='exhausted' WHERE id=$1",
                seed["id"])
        else:
            await Database.execute(
                "UPDATE maya_rp.consequence_seeds SET effects_jsonb=$1 WHERE id=$2",
                json.dumps(remaining), seed["id"])

    if fired:
        info("consequences", f"Fired {len(fired)} consequence(s)")
    return fired


async def _fire(effect: dict, seed: dict, session_id: int):
    """Fire a single effect."""
    if effect["type"] == "event":
        await Database.execute(
            "INSERT INTO maya_rp.events (session_id, happened_at, event_type, title, description, tags, importance) "
            "VALUES ($1, NOW(), 'consequence', $2, $3, $4, $5)",
            session_id,
            f"[{seed['trigger']}] {effect.get('template','consequence')}",
            effect.get("description", ""),
            json.dumps(["consequence", seed["trigger"], effect.get("severity", "medium")]),
            3 if effect.get("severity") == "high" else 1,
        )

    elif effect["type"] == "stat":
        col = effect.get("target", "morale")
        # Whitelist allowed columns to prevent SQL injection via effect templates
        _ALLOWED_COLS = {"morale", "credits", "alloys", "fuel", "population",
                          "tech_score", "influence", "fear", "aggregate_morale"}
        if col not in _ALLOWED_COLS:
            col = "morale"  # safe default
        delta = effect.get("delta", 0)
        try:
            await Database.execute(
                f"UPDATE maya_rp.resources SET {col} = GREATEST(0, COALESCE({col},0) + $1) "
                f"WHERE session_id=$2",
                delta, session_id)
        except Exception:
            pass

    elif effect["type"] == "faction_reaction":
        faction = effect.get("faction", "")
        action = effect.get("action", "")
        delta = effect.get("delta", 0)
        if action == "increase_aggression":
            await Database.execute(
                "UPDATE maya_rp.factions SET pirate_fleet_power = COALESCE(pirate_fleet_power,0) + $1, "
                "pirate_aggressiveness = LEAST(1.0, COALESCE(pirate_aggressiveness,0) + 0.1) "
                "WHERE session_id=$2 AND LOWER(name) LIKE LOWER($3)",
                delta, session_id, f"%{faction}%")


async def prevent(seed_id: int, method: str, session_id: int = None):
    """Player prevented a consequence."""
    if session_id is None:
        session_id = Config.SESSION_ID
    await Database.execute(
        "UPDATE maya_rp.consequence_seeds SET status='prevented', prevention_method=$1 "
        "WHERE id=$2 AND session_id=$3",
        method, seed_id, session_id)
    info("consequences", f"Prevented seed {seed_id} via {method}")


async def run_tick(session_id: int = None) -> dict:
    """Consequence tick: process due effects."""
    if session_id is None:
        session_id = Config.SESSION_ID
    try:
        fired = await process_due(session_id)
        return {"fired": len(fired)}
    except Exception as e:
        info("consequences", f"Error: {e}")
        return {"error": str(e)}
