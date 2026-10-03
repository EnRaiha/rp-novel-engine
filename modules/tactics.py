#!/usr/bin/env python3
"""Tactics Module — Ported from rpg-tactics skill (combat-system.js, military-ops.js, tactical-positioning.js)"""
from __future__ import annotations
import random, math
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info, error

DAMAGE_TYPES = {
    "kinetic":   {"strong_vs": ["hull","armor"], "weak_vs": ["shield"], "mult": 1.0},
    "energy":    {"strong_vs": ["shield","system"], "weak_vs": ["armored_hull"], "mult": 1.0},
    "explosive": {"strong_vs": ["hull","station"], "weak_vs": ["fast_target"], "mult": 1.3},
    "void":      {"strong_vs": ["all"], "weak_vs": [], "mult": 2.0},
}
SYSTEM_TARGETS = ["shields","engines","weapons","sensors","life_support","comms"]
ZONES = ["forward","port","starboard","aft","dorsal","ventral"]
TERRAINS = ["open_space","asteroid_field","nebula","debris_field","atmosphere","planetary_ring"]
FORMATIONS = ["line","wedge","sphere","screen","spearhead","scatter"]

async def calculate_fleet_power(session_id: int, fleet_name: str | None = None) -> dict:
    """Combat power of a campaign's ships, or of one named fleet inside it.

    `fleet_name` was accepted and never read, so asking for one fleet answered with the whole
    campaign's order of battle (44,269 hulls for session 3 against 9 for the fleet that was named).
    The name now resolves through `fleets`, scoped to the session, and its `fleet_members`; a name the
    session does not hold raises instead of answering with everything.

    A hull at zero is a wreck, not a full-strength ship: `hull_current or hull` read the real zero as
    missing and counted a destroyed hull at its original hull value.
    """
    if fleet_name is None:
        ships = await Database.fetch(
            "SELECT tier, hull, hull_current, speed FROM maya_rp.ships WHERE session_id=$1", session_id)
    else:
        fleet = await Database.fetchrow(
            "SELECT id FROM maya_rp.fleets WHERE session_id=$1 AND name=$2", session_id, fleet_name)
        if fleet is None:
            raise ValueError(f"Unknown fleet {fleet_name!r} in session {session_id}")
        ships = await Database.fetch(
            "SELECT s.tier, s.hull, s.hull_current, s.speed FROM maya_rp.ships s"
            " JOIN maya_rp.fleet_members fm ON fm.ship_id=s.id WHERE fm.fleet_id=$1", fleet["id"])
    power = 0
    for s in ships:
        tier = s["tier"] if s["tier"] is not None else 1
        hull_now = s["hull_current"] if s["hull_current"] is not None else s["hull"]
        if hull_now is None: hull_now = 0
        power += max(1, tier * 10 + hull_now // 10)
    return {"fleet_power": power, "ship_count": len(ships)}

async def resolve_exchange(attacker_hull: int, attacker_tier: int, defender_hull: int, defender_tier: int,
                           weapon: str = "kinetic", targeting_system: str | None = None) -> dict:
    """Damage from one exchange.

    An unknown weapon name used to resolve as kinetic, so a typo fought at kinetic odds with nothing
    said about it. It raises now, the way `BattleEngine._tactic_mult` refuses an unknown tactic.
    `None` stays the caller's "not specified" and means kinetic, which the CLI and the exchange test
    both pass.

    `targeting_system` is checked against the module's own SYSTEM_TARGETS and echoed back, because the
    resolver has no defender subsystem state to aim at: only the attacker's tier and the weapon's
    multiplier move the damage today.
    """
    if weapon is None:
        weapon = "kinetic"
    dt = DAMAGE_TYPES.get(weapon)
    if dt is None:
        raise ValueError(f"Unknown damage type {weapon!r}. Known types: {', '.join(sorted(DAMAGE_TYPES))}")
    if targeting_system is not None and targeting_system not in SYSTEM_TARGETS:
        raise ValueError(f"Unknown targeting system {targeting_system!r}. Known: {', '.join(SYSTEM_TARGETS)}")
    base_dmg = max(1, attacker_tier * 15)
    dmg = round(base_dmg * dt["mult"])
    return {"damage": dmg, "defender_hull_remaining": max(0, defender_hull - dmg), "weapon": weapon,
            "targeting_system": targeting_system}

async def get_tactical_position(session_id: int, zone: str = "forward", terrain: str = "open_space",
                                 formation: str = "spearhead") -> dict:
    """Position multipliers, naming every input the module does not recognise.

    An unknown zone, terrain or formation took a default multiplier in silence: the same answer for a
    typo as for a real zone, which is how the CLI's `war position flank` reported the unflanked 0.8
    with nothing said. The unrecognised values are listed in `warnings` now. `None` stays the caller's
    "not specified": the CLI passes None for terrain and formation, and the module's own defaults are
    the ones that apply.
    """
    # One case rule for both the checks and the multipliers. Formation was the
    # only one checked case-insensitively while all three multiplied
    # case-sensitively, so "WEDGE" passed validation and still took the 0.9
    # fallback, and "AFT" was warned about and then treated as forward.
    zone_l = zone.lower() if isinstance(zone, str) else zone
    terrain_l = terrain.lower() if isinstance(terrain, str) else terrain
    form_l = formation.lower() if isinstance(formation, str) else formation
    warnings = []
    if zone_l not in ZONES:
        warnings.append(f"unknown zone {zone!r}. Known zones: {', '.join(ZONES)}")
    if terrain_l is not None and terrain_l not in TERRAINS:
        warnings.append(f"unknown terrain {terrain!r}. Known terrains: {', '.join(TERRAINS)}")
    if form_l is not None and form_l not in FORMATIONS:
        warnings.append(f"unknown formation {formation!r}. Known formations: {', '.join(FORMATIONS)}")
    flank_bonus = 1.0 if zone_l in ("aft","ventral") else 0.8
    terrain_bonus = 1.0 if terrain_l == "asteroid_field" else 0.9 if terrain_l == "nebula" else 0.8
    form_bonus = 1.2 if form_l == "spearhead" else 1.0 if form_l == "wedge" else 0.9
    out = {"effective_power": round(flank_bonus * terrain_bonus * form_bonus, 2), "zone": zone,
           "terrain": terrain, "formation": formation}
    if warnings:
        out["warnings"] = warnings
    return out

MILITARY_OPS = {
    "blitz": {"desc": "Fast overwhelming assault", "difficulty": 6, "duration": 3},
    "siege": {"desc": "Systematic reduction", "difficulty": 7, "duration": 5},
    "ambush": {"desc": "Surprise attack from hidden position", "difficulty": 5, "duration": 2},
    "recon": {"desc": "Stealth information gathering", "difficulty": 4, "duration": 2},
    "convoy": {"desc": "Protected supply run", "difficulty": 5, "duration": 4},
    "patrol": {"desc": "Standard area security", "difficulty": 3, "duration": 2},
    "blockade": {"desc": "Starve out enemy positions", "difficulty": 6, "duration": 6},
}

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    try:
        fp = await calculate_fleet_power(session_id)
        info("tactics", f"Tick: fleet_power={fp['fleet_power']}, ships={fp['ship_count']}")
        return fp
    except Exception as e:
        error("tactics", f"tick error: {e}")
        return {"error": str(e)}


# ─── Formation & terrain helpers (battle campaign tick, 2026-08-14) ─────

_FORMATIONS = {"wedge": 1.15, "wall": 1.10, "pincer": 1.05, "screen": 0.95, "line": 1.0}
_TERRAINS = [
    {"name": "open space", "player_mod": 0.0},
    {"name": "asteroid field", "player_mod": 0.05},
    {"name": "nebula interference", "player_mod": -0.05},
    {"name": "gravity well", "player_mod": -0.03},
    {"name": "debris chokepoint", "player_mod": 0.08},
]


def formation_bonus(formation: str) -> float:
    """Multiplier for fleet power by formation. Unknown → 1.0."""
    return _FORMATIONS.get(str(formation).lower(), 1.0)


def roll_terrain() -> dict:
    """Random battlefield terrain with a player modifier."""
    import random
    return dict(random.choice(_TERRAINS))
