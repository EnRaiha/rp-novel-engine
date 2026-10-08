#!/usr/bin/env python3
"""Siege — Ported from Rust siege.rs."""
from __future__ import annotations
import random
import json
from core.db import Database
from core.log import error, info

# The attacker is the player's faction. `sieges` has no attacker column and nothing else in the
# schema names the player's faction per session, so the name is one constant instead of a literal
# in the capture statement. Same name `victory.py`, `state.py` and `narrative.py` use.
ATTACKER_FACTION = "Setia Empire"

# sieges.phase carries CHECK (phase >= 1 AND phase <= 5).
DB_PHASE_CAP = 5


def _writable_session(session_id: int | None) -> int:
    """Resolve the session for one call and refuse a frozen campaign.

    @param session_id - caller's session; `None` resolves through `core.session.require_session`.
    @returns the resolved session id.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    from core.ooc import _refuse_frozen
    from core.session import require_session

    sid = require_session(session_id)
    _refuse_frozen(sid)
    return sid


def _like(text: str) -> str:
    """Escape LIKE wildcards. Pair with `ESCAPE '\\'`: a `_` or `%` in a system name matched other systems."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def start_siege(system: str, session_id: int | None = None) -> dict:
    """Open a siege against a territory of this campaign.

    The system resolves to one territory: an exact (case-insensitive) name wins, otherwise a single
    substring match. Two substring matches are refused as ambiguous, where `LIMIT 1` picked one at
    random. The siege stores the territory's own name, so the capture in `advance_siege` finds it
    even when the caller typed a fragment. One active siege per territory: a second start is refused.

    @param system - territory name or fragment.
    @param session_id - campaign; `None` resolves through `require_session`.
    @returns `{siege_id, system, faction, attacker_power, defender_power}` or `{error}`.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
    found = await Database.fetch(
        "SELECT id, system_name, controlling_faction, status FROM maya_rp.territory "
        "WHERE session_id=$1 AND LOWER(system_name) LIKE LOWER($2) ESCAPE '\\' "
        "ORDER BY (LOWER(system_name)=LOWER($3)) DESC, id LIMIT 2",
        session_id, f"%{_like(system)}%", system)
    if not found: return {"error": f"System '{system}' not found"}
    t = found[0]
    if len(found) > 1 and t["system_name"].lower() != system.lower():
        return {"error": f"System '{system}' is ambiguous: {found[0]['system_name']}, {found[1]['system_name']}"}
    atk = await Database.fetchval("SELECT COALESCE(SUM(tier)*1000 + SUM(hull_current/10), 0) FROM maya_rp.ships WHERE session_id=$1 AND status='active'", session_id) or 0
    # factions has no fleet_strength column: the registered scalar for a
    # faction's fleet is pirate_fleet_power (maintained by pirates.py /
    # faction_ai.py). The * 800 scale below was calibrated for that magnitude,
    # so keep the module's own default when the faction has no rating yet.
    def_power = await Database.fetchval(
        "SELECT NULLIF(pirate_fleet_power, 0) FROM maya_rp.factions WHERE name=$1 AND session_id=$2",
        t["controlling_faction"], session_id) or 30
    defender = def_power * 800 + random.randint(200, 2000)
    async with Database.transaction() as conn:
        # The territory row is the lock: two starts for one system queue here, and the second
        # sees the first's siege.
        await conn.fetchrow("SELECT id FROM maya_rp.territory WHERE id=$1 FOR UPDATE", t["id"])
        running = await conn.fetchval(
            "SELECT id FROM maya_rp.sieges WHERE session_id=$1 AND territory_id=$2 AND status='active' LIMIT 1",
            session_id, t["id"])
        if running is not None:
            return {"error": f"{t['system_name']} is already under siege (siege {running})"}
        sid = await conn.fetchval("INSERT INTO maya_rp.sieges (session_id, territory_id, target_system, target_faction, attacker_power, defender_power) VALUES ($1,$2,$3,$4,$5,$6) RETURNING id", session_id, t["id"], t["system_name"], t["controlling_faction"], atk, defender)
    info("siege", f"Siege started: {t['system_name']} vs {t['controlling_faction']}")
    return {"siege_id": sid, "system": t["system_name"], "faction": t["controlling_faction"], "attacker_power": atk, "defender_power": defender}

async def advance_siege(siege_id: int, session_id: int | None = None) -> dict:
    """Play one phase of an active siege and apply its result.

    The phase write, the capture, the loot and the experience commit together. The status test is
    in the UPDATE itself, so a siege resolved by a concurrent tick is not resolved twice (it paid
    the loot twice). The stored phase is capped at `min(max_phases, DB_PHASE_CAP)`: the CHECK on
    `sieges.phase` rejected phase 6, so a siege on its last phase raised on every tick and never
    ended. Routed is decided before stalemate: a force that lost 3000 men on the last phase was
    reported as a stalemate.

    @param siege_id - siege to advance; must belong to `session_id` and be active.
    @param session_id - campaign; `None` resolves through `require_session`.
    @returns the phase result, or `{error}` when the siege is missing, foreign or resolved.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
    async with Database.transaction() as conn:
        s = await conn.fetchrow("SELECT id, target_system, target_faction, attacker_power, defender_power, phase, max_phases, damage_dealt, casualties_taken FROM maya_rp.sieges WHERE id=$1 AND session_id=$2 AND status='active' FOR UPDATE", siege_id, session_id)
        if not s: return {"error": f"Siege {siege_id} not found or resolved"}
        atk_roll = s["attacker_power"] + random.randint(0, s["attacker_power"] // 4) - s["defender_power"] // 4
        def_roll = s["defender_power"] + random.randint(0, s["defender_power"] // 3) - s["attacker_power"] // 5
        dmg, cas = s["damage_dealt"] or 0, s["casualties_taken"] or 0

        if atk_roll > def_roll * 2: dmg += s["defender_power"] // 2; cas += random.randint(10, 100); desc = "Major Victory"
        elif atk_roll > def_roll: dmg += s["defender_power"] // 3; cas += random.randint(20, 200); desc = "Advantage"
        elif atk_roll > def_roll // 2: cas += random.randint(50, 300); desc = "Stalemate"
        else: cas += random.randint(100, 500); desc = "Defender Advantage"

        phase_cap = min(s["max_phases"], DB_PHASE_CAP)
        new_phase = s["phase"] + 1
        status = "victory" if dmg >= s["defender_power"] * 2 else "routed" if cas > 3000 else "stalemate" if new_phase > phase_cap else "active"
        stored_phase = min(new_phase, phase_cap)
        done = await conn.fetchval("UPDATE maya_rp.sieges SET phase=$1, damage_dealt=$2, casualties_taken=$3, status=$4 WHERE id=$5 AND session_id=$6 AND status='active' RETURNING id", stored_phase, dmg, cas, status, siege_id, session_id)
        if done is None:
            return {"error": f"Siege {siege_id} not found or resolved"}

        result = {"siege_id": siege_id, "system": s["target_system"], "phase": stored_phase, "max_phases": s["max_phases"], "status": status, "description": desc, "damage_dealt": dmg, "casualties": cas}

        if status == "victory":
            # The capture was written by system name alone, so a victory here flipped the same-named
            # territory in every campaign that has one.
            await conn.execute(
                "UPDATE maya_rp.territory SET controlling_faction=$3, status='controlled' "
                "WHERE session_id=$1 AND system_name=$2", session_id, s["target_system"], ATTACKER_FACTION)
            loot = random.randint(1000, 5000)
            await conn.execute("UPDATE maya_rp.resources SET alloys=alloys+$1 WHERE session_id=$2", loot, session_id)
            await conn.execute("UPDATE maya_rp.ships SET experience=COALESCE(experience,0)+100 WHERE session_id=$1", session_id)
            result["loot"] = loot
    if status == "victory":
        info("siege", f"VICTORY: {s['target_system']} captured!")

    return result

async def list_sieges(session_id: int | None = None) -> list[dict]:
    from core.session import require_session
    session_id = require_session(session_id)
    rows = await Database.fetch("SELECT id, target_system, target_faction, status, phase, max_phases, casualties_taken FROM maya_rp.sieges WHERE session_id=$1 ORDER BY status, created_at DESC", session_id)
    return [dict(r) for r in rows]

async def run_tick(session_id: int = None) -> dict:
    """Auto-advance all active sieges (attrition loop, added 2026-08-14).

    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
    rows = await Database.fetch(
        "SELECT id FROM maya_rp.sieges WHERE session_id=$1 AND status='active'", session_id)
    advanced = 0
    for r in rows:
        try:
            res = await advance_siege(r["id"], session_id)
            if "error" in res:
                # Resolved by another tick between the list and the advance: nothing happened here.
                continue
            if res.get("status") != "active":
                await Database.execute(
                    "INSERT INTO maya_rp.events (session_id, happened_at, event_type, title, description, tags, importance) "
                    "VALUES ($1, NOW(), 'siege', $2, $3, $4::jsonb, 6)",
                    session_id, f"Siege {res.get('status')}: {res.get('system')}",
                    f"Siege of {res.get('system')} {res.get('status')}: {res.get('description')}",
                    json.dumps(["siege", res.get("system", ""), res.get("status", "")]))
            advanced += 1
        except Exception as e:
            error("siege", f"advance failed for siege {r['id']}: {e}")
    info("siege", f"Tick: {advanced} sieges advanced")
    return {"sieges_advanced": advanced}
