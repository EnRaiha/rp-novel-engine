#!/usr/bin/env python3
"""Environmental Storytelling — show state through environment. 'Morale low' → 'Mess hall half-empty. Someone carved HELP into a wall.'"""
from __future__ import annotations
import random
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info

TELLS = {
    "morale": [
        (80,101,["Laughter echoes from the mess hall. Someone's playing music.","The corridors buzz with energy. Crew nod as you pass — genuine respect.","A banner hangs: 'SETIA STANDS.' Someone painted it by hand."]),
        (50,80,["Routine. The ship runs like clockwork.","A crewman nods — polite, not warm.","The mess hall is full but quiet."]),
        (25,50,["The mess hall is half-empty. Conversations die when you approach.","Someone scratched tally marks into a corridor wall.","The garden is overgrown. Nobody's been tending it."]),
        (0,25,["A crewman spits on the deck as you pass.","'MUTINY' is scratched into the lift door.","The mess hall is dark. Crew eat alone in their quarters."]),
    ],
    "combat": [(1,999,["Scorch marks on the corridor walls. Fresh paint over plasma burns.","The air still smells of ozone.","A memorial has appeared. Fresh flowers."])],
    "death": [(1,999,["An empty seat at the command console. No one's reassigned it.","A uniform jacket draped over a chair. Unclaimed for days."])],
    "tension": [(7,10,["Security patrols have doubled.","Whispered conversations stop when you enter.","The armory has been restocked."])],
    "prosperity": [(1,999,["New mattresses in crew quarters. Actual comfort.","The food has improved. Real protein.","Someone runs a small market in the cargo bay."])],
}
LOCATION_TELLS = {
    "bridge":["The starfield fills the main viewport.","Consoles hum. The ship breathes through its systems."],
    "garden":["Bioluminescent plants cast soft blue light.","The air smells of rain and green.","A bench near the waterfall. Someone's been sitting here."],
    "quarters":["Personal effects pinned to walls. Photos. A child's toy.","The bed is narrow but clean. A small viewport shows stars."],
    "brig":["The cells are empty. For now.","Harsh lighting. No soft edges here."],
    "hangar":["Fighters in neat rows. Sparks fly from a maintenance crew.","The air smells of lubricant and ambition."],
    "pelabuhan_port":["Docking horns echo across the bay.","Crates stacked everywhere. Trade never sleeps."],
    "pelabuhan_square":["Evening sun through clouds. Street musicians. The smell of grilled food."],
}

async def generate_details(location: str = "bridge", session_id: int = None) -> list[str]:
    if session_id is None: session_id = Config.SESSION_ID
    details = []

    morale = await Database.fetchval("SELECT COALESCE(AVG(morale),50) FROM maya_rp.crew_roster WHERE session_id=$1", session_id) or 50

    for lo, hi, tells in TELLS["morale"]:
        if lo <= morale < hi:
            details.append(random.choice(tells))
            break

    recent = await Database.fetchval("SELECT COUNT(*) FROM maya_rp.combat_results WHERE session_id=$1 AND ended_at > NOW() - INTERVAL '72 hours'", session_id)
    if recent and recent > 0:
        details.append(random.choice(TELLS["combat"][0][2]))

    pacing = await Database.fetchrow("SELECT tension FROM maya_rp.narrative_pacing WHERE session_id=$1", session_id)
    if pacing and pacing["tension"] >= 7:
        details.append(random.choice(TELLS["tension"][0][2]))

    if location in LOCATION_TELLS:
        details.append(random.choice(LOCATION_TELLS[location]))

    random.shuffle(details)
    return details[:4]

async def run_tick(session_id: int = None) -> dict:
    return {"status": "on_demand"}
