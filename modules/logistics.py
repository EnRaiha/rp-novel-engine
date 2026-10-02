#!/usr/bin/env python3
"""Physical Logistics — cargo exists in space. Blockades work. Transport missions."""
from __future__ import annotations
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info

async def create_cargo(item: str, qty: float, loc_type: str, loc_id: int, session_id: int = None) -> dict:
    """Put goods somewhere.

    Reviewed 2026-10-03 before wiring. Two things were missing rather than wrong. A negative or zero
    quantity was accepted, which makes cargo that weighs less than nothing, and an empty location type
    was accepted, which makes cargo that is nowhere. Nothing created cargo before this, so no caller
    ever had the chance to notice.

    @returns the new row's id, or an error dict naming what was refused.
    """
    if session_id is None: session_id = Config.SESSION_ID
    if qty is None or qty <= 0:
        return {"error": f"quantity must be greater than zero, got {qty!r}"}
    if not (loc_type or "").strip():
        return {"error": "location_type is required: cargo that is nowhere cannot be moved"}
    if loc_id is None:
        return {"error": "location_id is required"}
    cargo_id = await Database.fetchval(
        "INSERT INTO maya_rp.cargo(session_id,item_type,quantity,location_type,location_id)"
        " VALUES($1,$2,$3,$4,$5) RETURNING id",
        session_id, item, qty, loc_type.strip(), loc_id)
    return {"cargo_id": cargo_id, "item": item, "qty": qty, "at": f"{loc_type}:{loc_id}"}

async def transport(cargo_id: int, dest_type: str, dest_id: int, ship_id: int, session_id: int = None) -> dict:
    """Ship one cargo row toward a destination, arriving three game days later.

    Also reviewed before wiring, and it had no caller either: `run_tick` delivered missions nothing
    could create. The guards here mirror `create_cargo`, and the mission refuses cargo that does not
    exist rather than tracking a phantom.
    """
    if session_id is None: session_id = Config.SESSION_ID
    if not dest_type or dest_id is None:
        return {"error": "a destination needs both a type and an id"}
    held = await Database.fetchval(
        "SELECT 1 FROM maya_rp.cargo WHERE id=$1 AND session_id=$2", cargo_id, session_id)
    if held is None:
        return {"error": f"cargo {cargo_id} does not exist in session {session_id}"}
    if ship_id is None:
        return {"error": "a transport ship is required"}
    gd = await Database.fetchval("SELECT COALESCE(game_day,1) FROM maya_rp.sessions WHERE id=$1", session_id)
    mid = await Database.fetchval("INSERT INTO maya_rp.transport_missions(session_id,cargo_id,transport_ship_id,dest_type,dest_id,status,depart_day,arrive_day) VALUES($1,$2,$3,$4,$5,'in_transit',$6,$6+3) RETURNING id", session_id,cargo_id,ship_id,dest_type,dest_id,gd)
    return {"mission_id":mid,"arrives_in":"3 game days","risk":"Interceptable by pirates"}

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    gd = await Database.fetchval("SELECT COALESCE(game_day,1) FROM maya_rp.sessions WHERE id=$1", session_id)
    arrived = await Database.fetch("UPDATE maya_rp.transport_missions SET status='delivered' WHERE session_id=$1 AND status='in_transit' AND arrive_day<=$2 RETURNING id,cargo_id,dest_type,dest_id", session_id,gd)
    for a in arrived:
        await Database.execute("UPDATE maya_rp.cargo SET location_type=$1,location_id=$2 WHERE id=$3", a["dest_type"],a["dest_id"],a["cargo_id"])
    return {"deliveries":len(arrived)}
