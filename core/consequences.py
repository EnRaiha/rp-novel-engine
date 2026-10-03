#!/usr/bin/env python3
"""Consequence chains — delayed cascading effects. Actions at tick N → effects at N+delay."""
from __future__ import annotations
import json
from typing import Any
from core.db import Database
from core.log import error, info
from core.session import resolve_session, unset

#: Effect types `_fire` knows how to land. Anything else is reported, not dropped in silence.
EFFECT_TYPES = ("event", "stat", "faction_reaction")

#: The columns a `stat` effect may name. Whitelisted because the column is interpolated.
STAT_COLUMNS = frozenset({
    "aggregate_morale", "credits", "alloys", "fuel", "population",
    "tech_score", "influence", "fear",
})


def _session(session_id: int | None) -> int:
    """The session to act on: the one named, else the one the engine resolves now.

    Reading `Config.SESSION_ID` here would take the value this process resolved at
    import, which is the drift `core.session.stale_process_default` describes: a
    tick process that started while the arc was session 3 keeps writing to the
    frozen campaign after the arc moves. A caller that names no session gets the
    arc as it stands now. `0`, `''` and `None` all mean "no session named", which
    is the same rule the resolver uses.
    """
    if not unset(session_id):
        return int(session_id)
    resolved = resolve_session()
    if resolved is None:
        # Maintenance mode: the operator names the session, the engine will not guess.
        raise ValueError("no session named and the engine is in maintenance mode")
    return int(resolved)


def _affected(status: str) -> int:
    """Rows an asyncpg command status reports: 'UPDATE 1' -> 1, 'UPDATE 0' -> 0."""
    try:
        return int(str(status).split()[-1])
    except (ValueError, IndexError):
        return 0


def _normalise_effects(effects: Any) -> list[dict]:
    """Give every effect the delay it will be counted against.

    An effect that names no delay is due now, and an explicit `delay_ticks: 0`
    already meant exactly that. The old default was 999, so a seed planted
    without one waited 999 ticks and no tick ever reached it: the ripple was
    stored and never landed. Deciding it here means every stored effect carries
    its own delay, and `process_due` never has to guess for a row written later.
    """
    if not isinstance(effects, list) or not effects:
        raise ValueError("effects must be a non-empty list")
    normalised = []
    for index, effect in enumerate(effects):
        if not isinstance(effect, dict):
            raise ValueError(f"effects[{index}] must be an object, got {type(effect).__name__}")
        if not effect.get("type"):
            raise ValueError(f"effects[{index}] has no type")
        raw_delay = effect.get("delay_ticks", 0)
        try:
            delay = int(raw_delay)
        except (TypeError, ValueError):
            raise ValueError(f"effects[{index}].delay_ticks is not a number: {raw_delay!r}") from None
        if delay < 0:
            raise ValueError(f"effects[{index}].delay_ticks is negative: {delay}")
        normalised.append({**effect, "delay_ticks": delay})
    return normalised


async def _current_tick(session_id: int) -> int:
    """Get the current session game day as tick number."""
    row = await Database.fetchrow("SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id)
    if row is None:
        raise ValueError(f"no session {session_id}: maya_rp.sessions has no such row")
    return row["game_day"] or 1


async def plant(seed: dict) -> int:
    """Plant a consequence seed and return its id.

    seed = {"trigger":"...", "session_id":3, "cause_description":"...",
            "effects": [{"delay_ticks":2, "type":"event", "template":"ambush", "severity":"high", "description":"..."}],
            "can_be_prevented":True, "prevention_action":"..."}

    An effect that names no `delay_ticks` is due on the next tick. The returned id
    is what `prevent` takes; before, nothing could name the seed it had just made.
    """
    if not isinstance(seed, dict):
        raise ValueError("seed must be an object")
    for key in ("trigger", "cause_description"):
        if not seed.get(key):
            raise ValueError(f"seed has no {key}")
    effects = _normalise_effects(seed.get("effects"))
    sid = _session(seed.get("session_id"))
    tick = await _current_tick(sid)
    row = await Database.fetchrow(
        "INSERT INTO maya_rp.consequence_seeds (session_id, trigger_type, cause_description, "
        "effects_jsonb, planted_at_tick, can_be_prevented, prevention_action, status) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,'planted') RETURNING id",
        sid, seed["trigger"], seed["cause_description"],
        json.dumps(effects), tick,
        seed.get("can_be_prevented", False), seed.get("prevention_action"))
    seed_id = int(row["id"])
    soonest = min(effect["delay_ticks"] for effect in effects)
    info("consequences", f"Planted {seed_id}: {seed['trigger']} ({len(effects)} effects, first due in {soonest})")
    return seed_id


async def process_due(session_id: int = None) -> list[dict]:
    """Process all due consequences for this tick.

    @returns one record per effect that landed, each naming the cause behind it.
    """
    sid = _session(session_id)
    current = await _current_tick(sid)

    seeds = await Database.fetch(
        "SELECT id, trigger_type, cause_description, effects_jsonb, planted_at_tick, "
        "can_be_prevented, prevention_action "
        "FROM maya_rp.consequence_seeds WHERE session_id=$1 AND status='planted'",
        sid)

    fired = []
    for seed in seeds:
        effects = seed["effects_jsonb"]
        if isinstance(effects, str):
            effects = json.loads(effects)
        remaining = []
        for eff in effects:
            ticks_since = current - seed["planted_at_tick"]
            # 0 is the default for a row written before the delay was made explicit.
            if ticks_since >= eff.get("delay_ticks", 0):
                if await _fire(eff, seed, sid):
                    fired.append({"effect": eff, "cause": seed["cause_description"]})
                else:
                    error("consequences", f"seed {seed['id']} effect '{eff.get('type')}' landed nothing; dropped")
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


async def _fire(effect: dict, seed: dict, session_id: int) -> bool:
    """Fire a single effect.

    @returns True when the effect changed something. False means the effect asked
    for a type, a column or a faction that does not exist, and the caller drops it
    with a log line rather than counting it as a consequence that happened.
    """
    kind = effect.get("type")

    if kind == "event":
        # `trigger` is the key `plant` takes; the column is `trigger_type`, and
        # this read used the wrong one, so every event effect raised KeyError out
        # of the whole tick. The event path had never landed one.
        await Database.execute(
            "INSERT INTO maya_rp.events (session_id, happened_at, event_type, title, description, tags, importance) "
            "VALUES ($1, NOW(), 'consequence', $2, $3, $4, $5)",
            session_id,
            f"[{seed['trigger_type']}] {effect.get('template','consequence')}",
            effect.get("description", ""),
            json.dumps(["consequence", seed["trigger_type"], effect.get("severity", "medium")]),
            3 if effect.get("severity") == "high" else 1,
        )
        return True

    if kind == "stat":
        # `morale` is NOT a column of maya_rp.resources (live columns: credits,
        # alloys, fuel, population, tech_score, influence, fear,
        # aggregate_morale, …) — the old default raised UndefinedColumnError
        # into a bare `except: pass`, so every stat consequence silently did
        # nothing.
        col = effect.get("target") or "aggregate_morale"
        if col not in STAT_COLUMNS:
            error("consequences", f"stat effect names '{col}', which is not a resources column; using aggregate_morale")
            col = "aggregate_morale"
        delta = effect.get("delta", 0)
        try:
            status = await Database.execute(
                f"UPDATE maya_rp.resources SET {col} = GREATEST(0, COALESCE({col},0) + $1) "
                f"WHERE session_id=$2",
                delta, session_id)
        except Exception as e:
            error("consequences", f"stat consequence {col} failed: {e}")
            return False
        if _affected(status) == 0:
            # The update matching nothing is how a session pays a cost it never had:
            # no resources row, no deduction, and no word about it.
            error("consequences", f"stat effect on '{col}' changed nothing: session {session_id} has no maya_rp.resources row")
            return False
        return True

    if kind == "faction_reaction":
        faction = effect.get("faction", "")
        action = effect.get("action", "")
        delta = effect.get("delta", 0)
        if action != "increase_aggression":
            error("consequences", f"faction_reaction '{action}' is not implemented; effect dropped")
            return False
        status = await Database.execute(
            "UPDATE maya_rp.factions SET pirate_fleet_power = COALESCE(pirate_fleet_power,0) + $1, "
            "pirate_aggressiveness = LEAST(1.0, COALESCE(pirate_aggressiveness,0) + 0.1) "
            "WHERE session_id=$2 AND LOWER(name) LIKE LOWER($3)",
            delta, session_id, f"%{faction}%")
        if _affected(status) == 0:
            error("consequences", f"faction_reaction found no faction matching '{faction}' in session {session_id}")
            return False
        return True

    error("consequences", f"unknown effect type '{kind}'; known types are {', '.join(EFFECT_TYPES)}")
    return False


async def prevent(seed_id: int, method: str, session_id: int = None) -> bool:
    """Player prevented a consequence.

    @returns True when a planted seed was actually marked prevented. False means
    the id named no planted seed in this session, which the caller should hear
    about rather than assume the prevention worked.
    """
    sid = _session(session_id)
    status = await Database.execute(
        "UPDATE maya_rp.consequence_seeds SET status='prevented', prevention_method=$1 "
        "WHERE id=$2 AND session_id=$3 AND status='planted'",
        method, seed_id, sid)
    if _affected(status) == 0:
        error("consequences", f"seed {seed_id} is not a planted seed of session {sid}; nothing was prevented")
        return False
    info("consequences", f"Prevented seed {seed_id} via {method}")
    return True


async def run_tick(session_id: int = None) -> dict:
    """Consequence tick: process due effects."""
    sid = _session(session_id)
    try:
        fired = await process_due(sid)
        return {"fired": len(fired)}
    except Exception as e:
        # The orchestrator reads a dict with "error" as a module failure, so this
        # is a report rather than a swallow, and it belongs at error level.
        error("consequences", f"tick failed for session {sid}: {e}")
        return {"error": str(e)}
