#!/usr/bin/env python3
"""Defense — Ported from Rust defense.rs."""
from __future__ import annotations
from core.db import Database
from core.config import Config
from core.log import info

VALID = ["orbital_platform","ground_battery","shield_generator","minefield","sensor_array"]
COSTS = {"orbital_platform":3000,"ground_battery":2000,"shield_generator":4000,"minefield":2000,"sensor_array":1500}
RATINGS = {"orbital_platform":500,"ground_battery":300,"shield_generator":200,"minefield":150,"sensor_array":100}
UPKEEP = {"shield_generator":100,"orbital_platform":50,"sensor_array":25,"ground_battery":20,"minefield":20}

async def build(colony: str, itype: str, session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    if itype not in VALID: return {"error": f"Invalid type. Valid: {VALID}"}
    col = await Database.fetchrow("SELECT id, name FROM maya_rp.colonies WHERE session_id=$1 AND LOWER(name) LIKE LOWER($2) LIMIT 1", session_id, f"%{colony}%")
    if not col: return {"error": f"Colony '{colony}' not found"}
    cost = COSTS[itype]
    res = await Database.fetchrow("SELECT alloys FROM maya_rp.resources WHERE session_id=$1", session_id)
    if not res or res["alloys"] < cost: return {"error": f"Need {cost} alloys"}
    await Database.execute("UPDATE maya_rp.resources SET alloys=alloys-$1 WHERE session_id=$2", cost, session_id)
    await Database.execute("INSERT INTO maya_rp.defense_installations (session_id, colony_id, system_name, installation_type, defense_rating, upkeep_credits) VALUES ($1,$2,$3,$4,$5,$6)", session_id, col["id"], col["name"], itype, RATINGS[itype], UPKEEP[itype])
    info("defense", f"Built {itype} at {col['name']}")
    return {"type": itype, "colony": col["name"], "rating": RATINGS[itype], "cost": cost}

async def upgrade(install_id: int, session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    d = await Database.fetchrow("SELECT d.id, d.installation_type, d.level, d.defense_rating FROM maya_rp.defense_installations d JOIN maya_rp.colonies c ON d.colony_id=c.id WHERE d.id=$1 AND c.session_id=$2", install_id, session_id)
    if not d: return {"error": f"Installation {install_id} not found"}
    if d["level"] >= 5: return {"error": "Already max level"}
    cost = d["level"] * 2000
    res = await Database.fetchrow("SELECT alloys FROM maya_rp.resources WHERE session_id=$1", session_id)
    if not res or res["alloys"] < cost: return {"error": f"Need {cost} alloys"}
    await Database.execute("UPDATE maya_rp.resources SET alloys=alloys-$1 WHERE session_id=$2", cost, session_id)
    nl, nr = d["level"] + 1, round(d["defense_rating"] * 1.4)
    await Database.execute("UPDATE maya_rp.defense_installations SET level=$1, defense_rating=$2 WHERE id=$3", nl, nr, d["id"])
    return {"type": d["installation_type"], "level": nl, "rating": nr, "cost": cost}

async def status(session_id: int | None = None) -> list[dict]:
    if session_id is None: session_id = Config.SESSION_ID
    rows = await Database.fetch("SELECT d.id, COALESCE(c.name,'Unassigned') as colony, d.installation_type, d.level, d.defense_rating, d.upkeep_credits FROM maya_rp.defense_installations d LEFT JOIN maya_rp.colonies c ON d.colony_id=c.id WHERE d.session_id=$1 ORDER BY d.defense_rating DESC", session_id)
    return [dict(r) for r in rows]

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    return {"status": "defense_ready"}
