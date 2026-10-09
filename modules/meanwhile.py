#!/usr/bin/env python3
"""Meanwhile System — multi-POV cuts. 'Meanwhile, on the other side of the fleet...'"""
from __future__ import annotations
import random
from typing import Any
from core.db import Database
from core.config import Config
from core.session import require_session

async def generate(session_id: int = None) -> dict | None:
    session_id = require_session(session_id)
    from core.ooc import _writes_allowed
    if random.random()>0.15: return None
    from core.pacing import PacingDirector
    pm = await PacingDirector.get_mode(session_id)
    if pm["mode"] in ("intimate","downtime"): return None

    # NOVEL ULTIMATE #3 — DUAL POV INTEL: undetected incoming raids = actionable threat
    # Novel kerap tukar POV ke musuh (Lilith, Marshal, Pirates) untuk dramatic irony.
    raid = await Database.fetchrow(
        "SELECT id, faction_name, target_system, enemy_power, ticks_remaining FROM maya_rp.incoming_raids "
        "WHERE session_id=$1 AND detected=false AND ticks_remaining <= 5 "
        "ORDER BY ticks_remaining ASC LIMIT 1", session_id)
    if raid:
        # Mark the row that was read. Matching on faction and target marked every
        # raid of the same faction at the same system: three live undetected
        # Gale Runner raids at 433-472 collapsed into one POV cut, and the other
        # two could never be reported. A frozen campaign gets the cut and keeps the flag.
        if _writes_allowed(session_id):
            await Database.execute(
                "UPDATE maya_rp.incoming_raids SET detected=true WHERE session_id=$1 AND id=$2",
                session_id, raid["id"])
        # enemy_power and ticks_remaining are nullable columns; `{None:,}` raises.
        power = int(raid["enemy_power"] or 0)
        ticks = int(raid["ticks_remaining"] or 0)
        return {"type":"enemy_pov","location":f"{raid['faction_name']} Command",
                "characters":[f"{raid['faction_name']} admiral"],
                "narrative":f"Meanwhile, in the void... {raid['faction_name']} fleet drops out of FTL. "
                            f"Target: {raid['target_system']}. Power: {power:,}. "
                            f"Impact in {ticks} ticks.",
                "relevance":"Intel revealed. Defensive deployment required."}

    from modules.secrets import get_dramatic_irony
    ironies = await get_dramatic_irony(session_id)
    if ironies:
        s = random.choice(ironies)
        return {"type":"secret","location":"somewhere unseen","characters":[s.get("holder","?")],"narrative":f"Meanwhile, {s.get('holder','someone')} knows something: {s['content']}","relevance":"This will matter soon."}
    fac = await Database.fetchrow("SELECT name FROM maya_rp.factions WHERE session_id=$1 AND standing='hostile' ORDER BY RANDOM() LIMIT 1", session_id)
    if fac:
        return {"type":"enemy","location":f"{fac['name']} territory","characters":[f"{fac['name']} command"],"narrative":f"The {fac['name']} fleet adjusts course. An encrypted message is sent.","relevance":"The enemy is moving."}
    from modules.locations import get_player_location
    loc = await get_player_location(session_id)
    scenes = {"bridge":"The bridge hums. Duty shift changes. Someone left a coffee cup on the navigation console.","mess_hall":"The mess hall is quieter than usual. A group of crew in the corner stop talking as the cook passes.","engine_room":"A technician stares at a readout that doesn't make sense.","cargo_bay":"Someone moved the crates near the emergency exit. No one knows who.","hangar":"A pilot runs her hands over her fighter's hull. Checking for damage that isn't visible."}
    ol = [k for k in scenes if k != loc.get("location")]
    if ol:
        l = random.choice(ol)
        return {"type":"atmosphere","location":l.replace("_"," "),"characters":["unspecified crew"],"narrative":scenes.get(l,"Something is happening here."),"relevance":"The ship is alive even when you're not looking."}
    return None
