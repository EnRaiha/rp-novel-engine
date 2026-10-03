#!/usr/bin/env python3
"""
The Collapse Matrix — when core stats hit critical zero, the game transforms.
Defeat is not an end state. It is a portal to a new type of story.

Each collapse state creates a new forced story arc with a genre shift,
recovery conditions, and GM instructions for Deepseek.

Call `check_for_collapse()` at the end of every tick or time skip.
"""
from __future__ import annotations
import json
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info


COLLAPSE_STATES: dict[str, dict] = {
    "fuel_zero": {
        "trigger": "fuel <= 0",
        "new_arc_theme": "stranded",
        "title": "Dead in the Water",
        "effects": [
            "All ships halted. FTL disabled.",
            "Fleet becomes a sitting duck for pirates and rival factions.",
            "Desperation mechanics activate — can strip ships for parts, send distress signals.",
        ],
        "recovery": "Mine local resources for 100,000 fuel units, OR send a desperate distress signal and negotiate rescue.",
        "gm_instruction": (
            "The fleet is drifting. Silence. No engines. The universe feels infinitely large and empty. "
            "Focus on survival, rationing, and internal conflict. No battles — only desperate choices."
        ),
    },
    "morale_collapse": {
        "trigger": "aggregate_morale <= 15",
        "new_arc_theme": "mutiny",
        "title": "The Breaking Point",
        "effects": [
            "Random crew members become hostile or desert.",
            "Cabinet authority is challenged publicly.",
            "Player must choose: crush the mutiny (brutality ++) or negotiate (lose face).",
        ],
        "recovery": "Resolve the mutiny arc through confrontation or concession. Victory restores morale to 35.",
        "gm_instruction": (
            "The crew has broken. Eyes that used to hold respect now hold contempt. "
            "Weapons might be turned inward. This is a political and personal crisis, not a military one."
        ),
    },
    "credits_zero": {
        "trigger": "credits <= 0",
        "new_arc_theme": "scavengers",
        "title": "Bankrupt",
        "effects": [
            "Cannot pay crew salaries. Loyalty decays fast.",
            "Must resort to piracy, smuggling, or selling artifacts.",
            "Factions sense weakness and demand tribute.",
        ],
        "recovery": "Accumulate 5,000,000 credits through any means necessary — trade, piracy, contracts.",
        "gm_instruction": (
            "The treasury is empty. The fleet is starving for resources. "
            "The player must make morally compromising choices to survive. Honor has a price tag."
        ),
    },
    "hull_critical": {
        "trigger": "flagship_hull <= 10%",
        "new_arc_theme": "disaster",
        "title": "Falling Apart",
        "effects": [
            "Flagship systems failing randomly — gravity, life support, comms.",
            "Evacuation protocols may be needed.",
            "Desperate repairs required using scavenged materials.",
        ],
        "recovery": "Restore flagship hull to 50% through repairs in a friendly shipyard.",
        "gm_instruction": (
            "Sparks fly from conduits. Bulkheads groan. The ship is dying around them. "
            "Focus on the visceral horror of a failing vessel in deep space."
        ),
    },
    "population_zero": {
        "trigger": "population <= 0",
        "new_arc_theme": "exodus",
        "title": "The Empty Worlds",
        "effects": [
            "No taxable population remains in TKG territory.",
            "Automated systems still function but cannot be crewed.",
            "Must recruit from outside or turn to automation/robotics.",
        ],
        "recovery": "Establish a recruitment or cloning program to bring population above 100,000.",
        "gm_instruction": (
            "The worlds are silent. Cities stand empty. What happened to the people?"
        ),
    },
}


async def check_for_collapse(session_id: int = None) -> dict | None:
    """
    Check all collapse conditions. Returns the first triggered collapse,
    or None if the system is stable.

    Call this at the end of every tick and after every time skip.
    """
    if session_id is None:
        session_id = Config.SESSION_ID

    r = await Database.fetchrow(
        """SELECT credits, fuel, alloys, population, aggregate_morale
           FROM maya_rp.resources WHERE session_id=$1""",
        session_id,
    )
    if not r:
        return None

    # 1. Fuel zero
    if r["fuel"] is not None and r["fuel"] <= 0:
        return await _trigger_collapse("fuel_zero", session_id)

    # 2. Morale collapse
    if r["aggregate_morale"] is not None and r["aggregate_morale"] <= 15:
        return await _trigger_collapse("morale_collapse", session_id)

    # 3. Credits zero
    if r["credits"] is not None and r["credits"] <= 0:
        return await _trigger_collapse("credits_zero", session_id)

    # 4. Population zero
    if r["population"] is not None and r["population"] <= 0:
        return await _trigger_collapse("population_zero", session_id)

    # 5. Flagship hull critical
    flagship = await Database.fetchrow(
        """SELECT name, hull_current, hull FROM maya_rp.ships
           WHERE session_id=$1 AND status='active'
           ORDER BY hull DESC LIMIT 1""",
        session_id,
    )
    # Both columns are nullable, and `hull_current <=` raises TypeError on a NULL rather than
    # answering. NULL is skipped, not read as critical: the schema permits it and no value in it
    # says the ship is dying. `hull > 0` also keeps the division meaningful.
    if (
        flagship
        and flagship["hull"] is not None
        and flagship["hull"] > 0
        and flagship["hull_current"] is not None
        and flagship["hull_current"] <= (flagship["hull"] * 0.1)
    ):
        return await _trigger_collapse("hull_critical", session_id)

    return None


async def _trigger_collapse(collapse_type: str, session_id: int) -> dict:
    """Execute a collapse: create a new story arc, log the event, return instructions."""
    config = COLLAPSE_STATES.get(collapse_type)
    if not config:
        return {"collapsed": False, "error": f"Unknown collapse type: {collapse_type}"}

    info("collapse", f"⚠️ COLLAPSE: {config['title']} ({config['new_arc_theme']})")

    # 1. End any active non-collapse arc
    await Database.execute(
        """UPDATE maya_rp.story_arcs
           SET status='completed', ended_at=NOW()
           WHERE session_id=$1 AND status='active' AND collapse_type IS NULL""",
        session_id,
    )

    # 2. Start a new collapse arc
    existing_collapse = await Database.fetchval(
        """SELECT id FROM maya_rp.story_arcs
           WHERE session_id=$1 AND status='active' AND collapse_type=$2 LIMIT 1""",
        session_id, collapse_type,
    )
    if not existing_collapse:
        await Database.execute(
            """INSERT INTO maya_rp.story_arcs
               (session_id, title, theme, central_conflict, stakes_description,
                phase, sessions_in_phase, total_sessions, status, collapse_type, collapse_recovery)
               VALUES ($1, $2, $3, $4, $5, 'setup', 0, 4, 'active', $6, $7)""",
            session_id,
            config["title"],
            config["new_arc_theme"],
            " | ".join(config["effects"]),
            f"Recovery: {config['recovery']}",
            collapse_type,
            config["recovery"],
        )

        # 3. Log the collapse event, once, when the arc is created. The condition that starts a
        # collapse is a state, not an incident: it stays true on every following tick, and the
        # caller runs on every tick, so logging outside this branch wrote one `importance 5`
        # event per tick for as long as the treasury stayed empty.
        await Database.execute(
            """INSERT INTO maya_rp.events
               (session_id, happened_at, event_type, title, description, tags, importance)
               VALUES ($1, NOW(), 'collapse', $2, $3, $4, 5)""",
            session_id,
            config["title"],
            f"CRITICAL: {config['trigger']}. {config['effects'][0]}",
            json.dumps(["collapse", collapse_type, config["new_arc_theme"]]),
        )

    return {
        "collapsed": True,
        "type": collapse_type,
        "title": config["title"],
        "new_arc": config["new_arc_theme"],
        "effects": config["effects"],
        "recovery": config["recovery"],
        "gm_instruction": config["gm_instruction"],
    }


async def run_tick(session_id: int = None) -> dict:
    """
    Called at the end of every engine tick.
    Returns collapse info if triggered, or {'status': 'stable'}.
    """
    if session_id is None:
        session_id = Config.SESSION_ID

    collapse = await check_for_collapse(session_id)
    if collapse:
        return collapse

    return {"status": "stable"}
