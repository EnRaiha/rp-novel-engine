#!/usr/bin/env python3
"""Espionage — Ported from Rust espionage.rs."""
from __future__ import annotations
import json, random
from core.db import Database
from core.session import require_session
from core.log import info, error

def _contains(text: str) -> str:
    """LIKE pattern matching `text` as a literal substring (pair with `ESCAPE '\\'`).

    @param text - user text.
    @returns the escaped `%text%` pattern.
    """
    return "%" + str(text).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _writable_session(session_id: int | None) -> int:
    """Resolve the session for one call and refuse a frozen campaign.

    @param session_id - caller's session; `None` resolves through `core.session.require_session`.
    @returns the resolved session id.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    from core.ooc import _refuse_frozen

    sid = session_id if session_id is not None else require_session(None)
    _refuse_frozen(sid)
    return sid


async def run_espionage(faction: str, mission_type: str, agent: str, session_id: int | None = None) -> dict:
    """Run one mission and RECORD it.

    Nothing wrote to `espionage_missions` before this: `list_espionage_log`
    could only ever show rows that predate the code, and the tick could only
    resolve rows nothing created. The mission row is written after the roll, so
    the log states what happened.

    The roll ladder tests success first, then a critical failure in the TOP tail of the failing
    rolls. The old ladder tested `roll <= success // 5` first, so the lowest rolls, the ones that
    should succeed, were reported as captured agents.

    @param faction - faction name fragment, matched literally.
    @param mission_type - key of the base-chance table.
    @param agent - agent name for the log.
    @param session_id - session; `None` resolves through `require_session`.
    @returns the outcome dict, or `{"error": ...}`.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
    fac = await Database.fetchrow(
        "SELECT id, name, reputation FROM maya_rp.factions WHERE session_id=$1 "
        "AND LOWER(name) LIKE LOWER($2) ESCAPE '\\' ORDER BY (LOWER(name)=LOWER($3)) DESC, id LIMIT 1",
        session_id, _contains(faction), faction)
    if not fac: return {"error": f"Faction '{faction}' not found"}

    base = {"steal_tech": 40, "sabotage": 35, "steal_resources": 55, "assassinate": 20, "plant_rumor": 60, "scout_fleet": 70}
    chance = base.get(mission_type)
    if chance is None: return {"error": f"Unknown mission: {mission_type}"}

    # `reputation` is a nullable column; `None // 10` raised TypeError.
    rep_mod = max(-10, int(fac["reputation"] or 0) // 10)
    success = max(5, min(95, chance + rep_mod + random.randint(-15, 15)))
    roll = random.randint(1, 100)
    if roll <= success:
        outcome = "success"
    elif roll > 100 - success // 5:
        outcome = "critical_failure"
    elif roll <= success + 20:
        outcome = "detected"
    else:
        outcome = "failure"

    loot_a, loot_c, rep_delta, narrative = 0, 0, 0, ""
    if outcome == "success":
        loot_a, loot_c = random.randint(500, 2000), random.randint(200, 1000)
        narrative = f"{agent} successfully completed {mission_type} against {fac['name']}."
    elif outcome == "critical_failure":
        rep_delta = -15
        narrative = f"{agent} was CAPTURED during {mission_type} against {fac['name']}!"
    elif outcome == "detected":
        rep_delta = -5
        narrative = f"{agent} was detected during {mission_type}. {fac['name']} is not amused."
    else:
        rep_delta = -3
        narrative = f"{agent} failed the {mission_type} mission against {fac['name']}."

    if loot_a or loot_c:
        tag = await Database.execute(
            "UPDATE maya_rp.resources SET alloys=alloys+$1, credits=credits+$2 WHERE session_id=$3",
            loot_a, loot_c, session_id)
        if isinstance(tag, str) and tag.split()[-1:] == ["0"]:
            # A session with no resources row (session 5 has none) used to be
            # told it looted; the mission row would then lie as well.
            info("espionage", f"session {session_id} has no resources row — "
                              f"{loot_a} alloys / {loot_c}C NOT banked")
            loot_a, loot_c = 0, 0
    await Database.execute("UPDATE maya_rp.factions SET reputation=GREATEST(reputation+$1, -100) WHERE id=$2", rep_delta, fac["id"])
    await Database.execute(
        "INSERT INTO maya_rp.espionage_missions "
        "(session_id, faction_id, mission_type, agent_name, success_chance, outcome, "
        " loot_json, reputation_delta, narrative, launched_at, resolved_at) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,NOW(),NOW())",
        session_id, fac["id"], mission_type, agent, success, outcome,
        json.dumps({"alloys": loot_a, "credits": loot_c}), rep_delta, narrative)
    info("espionage", f"{agent} → {fac['name']} ({mission_type}): {outcome}")
    return {"outcome": outcome, "agent": agent, "mission": mission_type, "faction": fac["name"], "loot_alloys": loot_a, "loot_credits": loot_c, "rep_delta": rep_delta, "narrative": narrative}

async def list_espionage_log(session_id: int | None = None) -> list[dict]:
    if session_id is None: session_id = require_session(None)
    rows = await Database.fetch("SELECT em.mission_type, em.agent_name, em.outcome, em.narrative FROM maya_rp.espionage_missions em WHERE em.session_id=$1 ORDER BY em.created_at DESC LIMIT 15", session_id)
    return [dict(r) for r in rows]

async def run_tick(session_id: int = None) -> dict:
    """Mission phase progression (added 2026-08-14): unresolved missions age
    and resolve with delay — planted rumors fade, scouts go dark.

    @param session_id - session to tick; `None` resolves through `require_session`.
    @returns `{"resolved_stale": n}`, or `{"error": ...}` on a database error.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
    try:
        stale = await Database.fetch(
            "SELECT id, mission_type, agent_name FROM maya_rp.espionage_missions "
            "WHERE session_id=$1 AND resolved_at IS NULL AND launched_at < NOW() - INTERVAL '10 days'",
            session_id)
        resolved = 0
        for m in stale:
            outcome = "went_dark" if m["mission_type"] in ("scout_fleet", "plant_rumor") else "compromised"
            await Database.execute(
                "UPDATE maya_rp.espionage_missions SET outcome=$1, resolved_at=NOW() "
                "WHERE id=$2 AND session_id=$3",
                outcome, m["id"], session_id)
            resolved += 1
        info("espionage", f"Tick: {resolved} stale missions resolved")
        return {"resolved_stale": resolved}
    except Exception as e:
        error("espionage", f"tick error: {e}")
        return {"error": str(e)}
