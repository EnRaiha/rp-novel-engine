#!/usr/bin/env python3
"""Physical Logistics — cargo exists in space. Blockades work. Transport missions."""
from __future__ import annotations
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info

async def create_cargo(item: str, qty: float, loc_type: str, loc_id: int, session_id: int = None):
    if session_id is None: session_id = Config.SESSION_ID
    await Database.execute("INSERT INTO maya_rp.cargo(session_id,item_type,quantity,location_type,location_id) VALUES($1,$2,$3,$4,$5)", session_id,item,qty,loc_type,loc_id)

async def transport(cargo_id: int, dest_type: str, dest_id: int, ship_id: int, session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
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
