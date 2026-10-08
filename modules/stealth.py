#!/usr/bin/env python3
"""Stealth/Spy — Ported from Rust stealth.rs."""
from __future__ import annotations
import random
from core.db import Database
from core.log import info


def _writable_session(session_id: int | None) -> int:
    """Resolve the session for one call and refuse a frozen campaign.

    Sessions 3 and 5 are reference data. Every writer here resolved `Config.SESSION_ID`, fixed at
    import, and wrote without a freeze check.

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
    """Escape LIKE wildcards. Pair with `ESCAPE '\\'`: a `_` or `%` in a name matched other rows."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def build_spy(unit_type: str, name: str, session_id: int | None = None) -> dict:
    """Pay for and register one stealth unit.

    The debit is a guarded statement in the same transaction as the insert. It was a balance read,
    then a debit, then the insert as three pool statements: an insert that raised kept the alloys,
    and two builds together spent the same balance.

    @param unit_type - substring of `stealth_unit_types.name`; wildcards are escaped.
    @param name - the new unit's name.
    @param session_id - campaign; `None` resolves through `require_session`.
    @returns `{name, type, cloak, lanes}` or `{error}` with nothing spent.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
    # 'probe' matches both Shadow Probe and Pool Observation Probe on live rows,
    # and fetchrow took whichever the plan returned first. Refuse the ambiguity.
    pattern = f"%{_like(unit_type)}%"
    matches = await Database.fetchval(
        "SELECT count(*) FROM maya_rp.stealth_unit_types WHERE LOWER(name) LIKE LOWER($1) ESCAPE '\\'",
        pattern) or 0
    if matches > 1:
        kinds = await Database.fetch(
            "SELECT name FROM maya_rp.stealth_unit_types WHERE LOWER(name) LIKE LOWER($1) ESCAPE '\\' ORDER BY id",
            pattern)
        return {"error": f"{unit_type!r} matches {matches} unit types: "
                         + ", ".join(r["name"] for r in kinds)}
    ut = await Database.fetchrow("SELECT id, name, base_cost_alloys, cloak_level, max_lanes FROM maya_rp.stealth_unit_types WHERE LOWER(name) LIKE LOWER($1) ESCAPE '\\' ORDER BY id LIMIT 1", pattern)
    if not ut: return {"error": f"Unknown unit type: {unit_type}"}
    async with Database.transaction() as conn:
        res = await conn.fetchrow("SELECT alloys FROM maya_rp.resources WHERE session_id=$1 FOR UPDATE", session_id)
        if not res or res["alloys"] < ut["base_cost_alloys"]:
            return {"error": f"Need {ut['base_cost_alloys']} alloys"}
        paid = await conn.fetchrow("UPDATE maya_rp.resources SET alloys=alloys-$1 WHERE session_id=$2 AND alloys>=$1 RETURNING alloys", ut["base_cost_alloys"], session_id)
        if paid is None:
            return {"error": f"Need {ut['base_cost_alloys']} alloys"}
        await conn.execute("INSERT INTO maya_rp.stealth_units (session_id, unit_type_id, name) VALUES ($1,$2,$3)", session_id, ut["id"], name)
    info("stealth", f"Built spy: {name}")
    return {"name": name, "type": ut["name"], "cloak": ut["cloak_level"], "lanes": ut["max_lanes"]}

async def deploy_spy(name: str, lane: str, session_id: int | None = None) -> dict:
    """Station an active spy on a lane.

    @param name - the unit's name; an exact match wins over a substring match, wildcards are escaped.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
    su = await Database.fetchrow("SELECT id FROM maya_rp.stealth_units WHERE session_id=$1 AND LOWER(name) LIKE LOWER($2) ESCAPE '\\' AND status='active' ORDER BY (LOWER(name)=LOWER($3)) DESC, id LIMIT 1", session_id, f"%{_like(name)}%", name)
    if not su: return {"error": f"Spy '{name}' not found"}
    await Database.execute("UPDATE maya_rp.stealth_units SET assigned_lane=$1 WHERE id=$2 AND session_id=$3", lane, su["id"], session_id)
    return {"deployed": name, "lane": lane}

async def hack(name: str, operation: str, target: str, session_id: int | None = None) -> dict:
    """Run one hack with a spy and bank the intel on the target lane.

    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
    su = await Database.fetchrow("SELECT su.id, su.name FROM maya_rp.stealth_units su WHERE su.session_id=$1 AND LOWER(su.name) LIKE LOWER($2) ESCAPE '\\' ORDER BY (LOWER(su.name)=LOWER($3)) DESC, su.id LIMIT 1", session_id, f"%{_like(name)}%", name)
    if not su: return {"error": f"Spy '{name}' not found"}
    chance = 40 + random.randint(-10, 20)
    roll = random.randint(1, 100)
    outcome = "success" if roll <= chance else "detected" if roll <= chance + 20 else "failure"
    intel = random.randint(20, 80) if outcome == "success" else random.randint(0, 10)
    lanes_touched = 0
    if intel > 0:
        row = await Database.fetchrow(
            "UPDATE maya_rp.space_lanes SET intel_level=LEAST(COALESCE(intel_level,0)+$1,100) "
            "WHERE session_id=$2 AND (origin=$3 OR destination=$3) RETURNING id",
            intel, session_id, target)
        lanes_touched = 1 if row else 0
        if not lanes_touched:
            # A target name that matches no lane used to report the intel anyway.
            info("stealth", f"Hack on {target!r}: no lane in session {session_id} carries that name, "
                            f"{intel} intel not banked")
    return {"spy": su["name"], "operation": operation, "target": target, "outcome": outcome,
            "intel_gained": intel, "lanes_touched": lanes_touched}

async def build_anticloak(system: str, level: int = 1, session_id: int | None = None) -> dict:
    """Pay for and register an anti-cloak grid on a system.

    One active grid per system: a second build is refused. `ON CONFLICT DO NOTHING` named no
    conflict target and the table has no unique key, so it never fired; every call charged the
    cost and added another grid.

    @param system - system name; matched case-insensitively against existing grids.
    @param level - clamped to 1..5.
    @param session_id - campaign; `None` resolves through `require_session`.
    @returns `{system, level, detection, range, cost}` or `{error}` with nothing spent.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
    lev = max(1, min(5, level))
    cost = [0, 10000, 25000, 60000, 150000, 500000][lev]
    detect = [0, 15, 30, 50, 75, 95][lev]
    rng = [0, 3, 6, 10, 15, 25][lev]
    upk = [0, 200, 500, 1500, 4000, 15000][lev]
    async with Database.transaction() as conn:
        # The treasury row is the lock: two builds for one system queue here.
        res = await conn.fetchrow("SELECT alloys FROM maya_rp.resources WHERE session_id=$1 FOR UPDATE", session_id)
        if not res or res["alloys"] < cost: return {"error": f"Need {cost} alloys"}
        existing = await conn.fetchval("SELECT id FROM maya_rp.anti_cloak_grids WHERE session_id=$1 AND LOWER(system_name)=LOWER($2) AND status='active' LIMIT 1", session_id, system)
        if existing:
            return {"error": f"{system} already has an active anti-cloak grid (id {existing})"}
        paid = await conn.fetchrow("UPDATE maya_rp.resources SET alloys=alloys-$1 WHERE session_id=$2 AND alloys>=$1 RETURNING alloys", cost, session_id)
        if paid is None: return {"error": f"Need {cost} alloys"}
        await conn.execute("INSERT INTO maya_rp.anti_cloak_grids (session_id, system_name, level, detection_pct, range_ly, upkeep_credits) VALUES ($1,$2,$3,$4,$5,$6)", session_id, system, lev, detect, rng, upk)
    return {"system": system, "level": lev, "detection": detect, "range": rng, "cost": cost}

async def list_anticloak(session_id: int | None = None) -> list[dict]:
    from core.session import require_session
    session_id = require_session(session_id)
    rows = await Database.fetch("SELECT system_name, level, detection_pct, range_ly, upkeep_credits FROM maya_rp.anti_cloak_grids WHERE session_id=$1 AND status='active' ORDER BY level DESC", session_id)
    return [dict(r) for r in rows]

async def run_tick(session_id: int = None) -> dict:
    """@raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed."""
    session_id = _writable_session(session_id)
    return {"status": "stealth_ready"}
