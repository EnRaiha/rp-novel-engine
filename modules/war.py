#!/usr/bin/env python3
"""War System — strategic entity with phases, objectives, resolution."""
from __future__ import annotations
import json, random
from typing import Any
from core.db import Database
from core.log import info, error
from core.session import require_session


def _contains(text: str) -> str:
    """LIKE pattern matching `text` as a literal substring (pair with `ESCAPE '\\'`).

    @param text - user text.
    @returns the escaped `%text%` pattern.
    """
    return "%" + str(text).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


WAR_PHASES = ["escalation","mobilization","clash","attrition","turning_point","resolution"]

async def declare(target_faction: str, casus_belli: str, war_goal: str,
                  session_id: int | None = None) -> dict:
    """Open a war against one faction of this campaign.

    The opponent is checked before anything is written: a misspelled name used to
    insert a war row, update no faction, and report success. A second war against
    the same opponent is refused while one is still running.

    The war stores the RESOLVED faction name, not the typed fragment. A fragment such as "setia" was
    stored raw, so `advance` looked up `faction_ships.faction_name = 'setia'`, found no ships and
    fought a phantom of power 1, and a second declare with "Setia Empire" slipped past the running
    check. The faction row is flagged hostile by id and session: the old `LIKE '%fragment%'` UPDATE
    also hit every other faction whose name contained the fragment.

    @param target_faction - literal faction name fragment.
    @param casus_belli - stated reason.
    @param war_goal - stated goal.
    @param session_id - session key; the active session when None.
    @returns {"war_id", "phase", "opponent"} or {"error": ...}.
    @raises FrozenSession when the campaign is frozen reference data.
    """
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    if not str(target_faction or "").strip():
        raise ValueError(f"target_faction must be a non-empty string, got {target_faction!r}")
    opponent = await Database.fetchrow(
        "SELECT id, name FROM maya_rp.factions WHERE session_id=$1 "
        "AND LOWER(name) LIKE LOWER($2) ESCAPE '\\' ORDER BY id LIMIT 1",
        session_id, _contains(target_faction))
    if not opponent:
        return {"error": f"No faction matching '{target_faction}' in session {session_id}"}
    name = opponent["name"]
    running = await Database.fetchval(
        "SELECT 1 FROM maya_rp.wars WHERE session_id=$1 AND LOWER(opponent_faction)=LOWER($2) AND status='active'",
        session_id, name)
    if running:
        return {"error": f"A war with {name} is already running"}
    game_day = await Database.fetchval("SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id)
    async with Database.transaction() as conn:
        wid = await conn.fetchval(
            "INSERT INTO maya_rp.wars (session_id, opponent_faction, casus_belli, war_goal, "
            "phase, started_at_game_day, status) "
            "VALUES ($1,$2,$3,$4,'escalation',$5,'active') RETURNING id",
            session_id, name, casus_belli, war_goal, game_day)
        await conn.execute(
            "UPDATE maya_rp.factions SET standing='hostile' WHERE id=$1 AND session_id=$2",
            opponent["id"], session_id)
    info("war", f"WAR: {name} — {casus_belli}")
    return {"war_id": wid, "phase": "escalation", "opponent": name}

async def advance(war_id: int, session_id: int | None = None) -> dict:
    """Roll one tick of a war: casualties, a possible phase change, and the end once it is due.

    @param war_id - war id in this campaign.
    @param session_id - session key; the active session when None.
    @returns the tick summary or {"error": "War not found"}.
    @raises FrozenSession when the campaign is frozen reference data.
    """
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    war = await Database.fetchrow("SELECT * FROM maya_rp.wars WHERE id=$1 AND session_id=$2", war_id, session_id)
    if not war: return {"error": "War not found"}

    player_power = await Database.fetchval(
        "SELECT COALESCE(SUM(s.power_rating), 0) FROM maya_rp.ships s "
        "WHERE s.session_id=$1 AND s.status='active'", session_id) or 1
    enemy_power = await Database.fetchval(
        "SELECT COALESCE(SUM(fs.power_rating), 0) FROM maya_rp.faction_ships fs "
        "WHERE fs.session_id=$1 AND LOWER(fs.faction_name)=LOWER($2) AND fs.status='active'",
        session_id, war["opponent_faction"]) or 1

    ratio = player_power / max(1, enemy_power)
    if war["phase"] not in WAR_PHASES:
        # An unknown phase restarts the cycle at escalation; say so rather than
        # silently rewinding a war.
        info("war", f"war {war_id} carries unknown phase {war['phase']!r} — treated as escalation")
    current_idx = WAR_PHASES.index(war["phase"]) if war["phase"] in WAR_PHASES else 0
    advance_phase = False
    if current_idx < 4:
        if ratio > 1.5: advance_phase = True
        elif ratio < 0.4: advance_phase = True
        else: advance_phase = random.random() < 0.3

    cas_a = random.randint(0, 50)
    cas_d = random.randint(0, 30)
    await Database.execute(
        "UPDATE maya_rp.wars SET attacker_casualties=attacker_casualties+$1, "
        "defender_casualties=defender_casualties+$2, updated_at=NOW() "
        "WHERE id=$3 AND session_id=$4",
        cas_a, cas_d, war_id, session_id)

    result = {"war_id": war_id, "phase": war["phase"], "power_ratio": round(ratio, 2),
              "attacker_cas": cas_a, "defender_cas": cas_d}

    if advance_phase and current_idx < 5:
        new_phase = WAR_PHASES[current_idx + 1]
        await Database.execute("UPDATE maya_rp.wars SET phase=$1 WHERE id=$2 AND session_id=$3",
                               new_phase, war_id, session_id)
        result["new_phase"] = new_phase
        await Database.execute(
            "INSERT INTO maya_rp.events (session_id, happened_at, event_type, title, description, tags, importance) "
            "VALUES ($1, NOW(), 'war_phase', $2, $3, $4, 5)",
            session_id, f"War Phase: {new_phase.upper()}",
            f"The war with {war['opponent_faction']} enters {new_phase} phase. Power ratio: {ratio:.1f}",
            json.dumps(["war", war["opponent_faction"], new_phase]))

    if current_idx >= 4:
        winner = war["opponent_faction"] if ratio < 0.8 else "Player"
        # Only fire the end-of-war side effects ONCE — this block used to
        # re-emit the importance-10 war_end event on every tick forever.
        if war.get("status") != "ended":
            await Database.execute(
                "UPDATE maya_rp.wars SET status='ended', phase='resolution' WHERE id=$1 AND session_id=$2",
                war_id, session_id)
            await Database.execute(
                "INSERT INTO maya_rp.events (session_id, happened_at, event_type, title, description, tags, importance) "
                "VALUES ($1, NOW(), 'war_end', $2, $3, $4, 10)",
                session_id, f"War Ended: {war['opponent_faction']}",
                f"The war with {war['opponent_faction']} has ended. {winner} emerges victorious.",
                json.dumps(["war", "ended"]))
        result["ended"] = True
        result["winner"] = winner

    return result

async def list_wars(session_id: int | None = None, active_only: bool = False) -> list[dict]:
    """This campaign's wars. `active_only` is what the tick needs: an ended war
    still took casualties every tick because `tick_wars` advanced every row."""
    session_id = require_session(session_id)
    rows = await Database.fetch(
        "SELECT id, opponent_faction, phase, status, casus_belli, attacker_casualties, defender_casualties "
        "FROM maya_rp.wars WHERE session_id=$1 AND ($2 = false OR status = 'active') ORDER BY id",
        session_id, active_only)
    return [dict(r) for r in rows]

async def tick_wars(session_id: int | None = None) -> list[dict]:
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    wars = await list_wars(session_id, active_only=True)
    results = []
    for w in wars:
        r = await advance(w["id"], session_id)
        results.append(r)
    return results

async def run_tick(session_id: int | None = None) -> dict:
    """Advance every active war one tick.

    @returns {"wars_advanced": n}, or {"error": ...} after logging at error level when the tick raises.
    @raises FrozenSession when the campaign is frozen reference data.
    """
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    try:
        results = await tick_wars(session_id)
        info("war", f"Tick: {len(results)} wars advanced")
        return {"wars_advanced": len(results)}
    except Exception as e:
        error("war", f"tick error: {e}")
        return {"error": str(e)}
