#!/usr/bin/env python3
"""Defense — Ported from Rust defense.rs."""
from __future__ import annotations
from core.db import Database
from core.session import require_session
from core.log import info

VALID = ["orbital_platform","ground_battery","shield_generator","minefield","sensor_array"]
COSTS = {"orbital_platform":3000,"ground_battery":2000,"shield_generator":4000,"minefield":2000,"sensor_array":1500}
RATINGS = {"orbital_platform":500,"ground_battery":300,"shield_generator":200,"minefield":150,"sensor_array":100}
UPKEEP = {"shield_generator":100,"orbital_platform":50,"sensor_array":25,"ground_battery":20,"minefield":20}

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


async def build(colony: str, itype: str, session_id: int | None = None) -> dict:
    """Build one installation, paying alloys in the same transaction.

    The debit is a guarded `UPDATE ... WHERE alloys>=cost`: the old read-then-debit let two
    concurrent builds both pass the check and drive alloys negative.

    @param colony - colony name fragment, matched literally.
    @param itype - one of VALID.
    @param session_id - session; `None` resolves through `require_session`.
    @returns the installation dict, or `{"error": ...}`.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    # An invalid type writes nothing, so it is answered before the freeze check.
    if itype not in VALID: return {"error": f"Invalid type. Valid: {VALID}"}
    session_id = _writable_session(session_id)
    cost = COSTS[itype]
    async with Database.transaction() as conn:
        col = await conn.fetchrow("SELECT id, name FROM maya_rp.colonies WHERE session_id=$1 AND LOWER(name) LIKE LOWER($2) ESCAPE '\\' LIMIT 1", session_id, _contains(colony))
        if not col: return {"error": f"Colony '{colony}' not found"}
        paid = await conn.fetchrow("UPDATE maya_rp.resources SET alloys=alloys-$1 WHERE session_id=$2 AND alloys>=$1 RETURNING alloys", cost, session_id)
        if paid is None: return {"error": f"Need {cost} alloys"}
        await conn.execute("INSERT INTO maya_rp.defense_installations (session_id, colony_id, system_name, installation_type, defense_rating, upkeep_credits) VALUES ($1,$2,$3,$4,$5,$6)", session_id, col["id"], col["name"], itype, RATINGS[itype], UPKEEP[itype])
    info("defense", f"Built {itype} at {col['name']}")
    return {"type": itype, "colony": col["name"], "rating": RATINGS[itype], "cost": cost}

async def upgrade(install_id: int, session_id: int | None = None) -> dict:
    """Upgrade one installation a level, paying alloys in the same transaction.

    The installation row is locked, so two concurrent upgrades cannot both read level N and both
    charge. A NULL `level` reads as 1 and a NULL `defense_rating` as 0: `None >= 5` raised
    TypeError.

    @param install_id - `defense_installations.id` in this session's colonies.
    @param session_id - session; `None` resolves through `require_session`.
    @returns the new level and rating, or `{"error": ...}`.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
    async with Database.transaction() as conn:
        d = await conn.fetchrow("SELECT d.id, d.installation_type, d.level, d.defense_rating FROM maya_rp.defense_installations d JOIN maya_rp.colonies c ON d.colony_id=c.id WHERE d.id=$1 AND c.session_id=$2 FOR UPDATE OF d", install_id, session_id)
        if not d: return {"error": f"Installation {install_id} not found"}
        level = d["level"] if d["level"] is not None else 1
        rating = d["defense_rating"] if d["defense_rating"] is not None else 0
        if level >= 5: return {"error": "Already max level"}
        cost = level * 2000
        paid = await conn.fetchrow("UPDATE maya_rp.resources SET alloys=alloys-$1 WHERE session_id=$2 AND alloys>=$1 RETURNING alloys", cost, session_id)
        if paid is None: return {"error": f"Need {cost} alloys"}
        nl, nr = level + 1, round(rating * 1.4)
        await conn.execute(
            "UPDATE maya_rp.defense_installations SET level=$1, defense_rating=$2 "
            "WHERE id=$3 AND session_id=$4", nl, nr, d["id"], session_id)
    return {"type": d["installation_type"], "level": nl, "rating": nr, "cost": cost}

async def status(session_id: int | None = None) -> list[dict]:
    if session_id is None: session_id = require_session(None)
    rows = await Database.fetch("SELECT d.id, COALESCE(c.name,'Unassigned') as colony, d.installation_type, d.level, d.defense_rating, d.upkeep_credits FROM maya_rp.defense_installations d LEFT JOIN maya_rp.colonies c ON d.colony_id=c.id WHERE d.session_id=$1 ORDER BY d.defense_rating DESC", session_id)
    return [dict(r) for r in rows]

async def run_tick(session_id: int = None) -> dict:
    """Report readiness. Resolves and guards the session like the writers.

    @param session_id - session; `None` resolves through `require_session`.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
    return {"status": "defense_ready"}
