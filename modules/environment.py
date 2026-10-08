#!/usr/bin/env python3
"""Environmental Storytelling — show state through environment. 'Morale low' → 'Mess hall half-empty. Someone carved HELP into a wall.'"""
from __future__ import annotations
import random
from typing import Any
from core.db import Database
from core.session import require_session
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
    """Pick up to four environmental tells for the session's current state.

    Read-only. The fight window reads `combat_results.created_at`: the table has no `ended_at`,
    and the old query raised UndefinedColumn on every call. A NULL `tension` is skipped; the
    column is nullable and `None >= 7` raised TypeError.

    @param location - key of LOCATION_TELLS; an unknown key adds no location tell.
    @param session_id - session to read; `None` resolves through `require_session`.
    @returns the tells, shuffled.
    """
    if session_id is None: session_id = require_session(None)
    details = []

    morale = await Database.fetchval("SELECT COALESCE(AVG(morale),50) FROM maya_rp.crew_roster WHERE session_id=$1", session_id)
    if morale is None:
        # The COALESCE already answers "no crew rows" with 50. `morale or 50` also answered a crew at
        # zero with 50, so a mutinous ship was described as one that runs like clockwork.
        morale = 50

    for lo, hi, tells in TELLS["morale"]:
        if lo <= morale < hi:
            details.append(random.choice(tells))
            break

    recent = await Database.fetchrow(
        "SELECT COUNT(*) AS fights, COALESCE(SUM(crew_casualties),0) AS casualties"
        " FROM maya_rp.combat_results WHERE session_id=$1 AND created_at > NOW() - INTERVAL '72 hours'",
        session_id)
    if recent and recent["fights"] > 0:
        details.append(random.choice(TELLS["combat"][0][2]))
        # The death tells were written and never reachable: nothing read the casualties a fight left,
        # so "a memorial has appeared" could not appear for a fight that killed anyone.
        if recent["casualties"] > 0:
            details.append(random.choice(TELLS["death"][0][2]))

    pacing = await Database.fetchrow("SELECT tension FROM maya_rp.narrative_pacing WHERE session_id=$1", session_id)
    if pacing and pacing["tension"] is not None and pacing["tension"] >= 7:
        details.append(random.choice(TELLS["tension"][0][2]))

    if location in LOCATION_TELLS:
        details.append(random.choice(LOCATION_TELLS[location]))

    random.shuffle(details)
    return details[:4]

WEATHER = ["clear skies", "ion storm", "meteor shower", "solar wind", "nebula drift", "comet tail", "quiet dark"]
WEATHER_MOD = {"clear skies": 0.0, "ion storm": -0.05, "meteor shower": -0.02,
               "solar wind": 0.03, "nebula drift": -0.03, "comet tail": 0.05,
               "quiet dark": 0.0}

def current_weather(session_id: int = None, game_day: int = None) -> dict:
    """Deterministic weather per game day — voyage difficulty modifier hook."""
    if game_day is None:
        game_day = 1
    idx = game_day % len(WEATHER)
    name = WEATHER[idx]
    return {"weather": name, "voyage_mod": WEATHER_MOD[name], "game_day": game_day}

async def run_tick(session_id: int = None) -> dict:
    """Report the day's weather. Writes nothing, so a frozen campaign needs no refusal.

    @param session_id - session to read; `None` resolves through `require_session`.
    @returns `{"status": "on_demand", weather fields}`.
    """
    if session_id is None: session_id = require_session(None)
    gd = await Database.fetchval("SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id) or 0
    w = current_weather(session_id, gd)
    return {"status": "on_demand", **w}
