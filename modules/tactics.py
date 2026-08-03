#!/usr/bin/env python3
"""Tactics Module — Ported from rpg-tactics skill (combat-system.js, military-ops.js, tactical-positioning.js)"""
from __future__ import annotations
import random, math
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info

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
    ships = await Database.fetch("SELECT tier, hull, hull_current, speed FROM maya_rp.ships WHERE session_id=$1", session_id)
    power = sum(max(1, s["tier"] * 10 + (s["hull_current"] or s["hull"]) // 10) for s in ships) if ships else 0
    return {"fleet_power": power, "ship_count": len(ships)}

async def resolve_exchange(attacker_hull: int, attacker_tier: int, defender_hull: int, defender_tier: int,
                           weapon: str = "kinetic", targeting_system: str | None = None) -> dict:
    dt = DAMAGE_TYPES.get(weapon, DAMAGE_TYPES["kinetic"])
    base_dmg = max(1, attacker_tier * 15)
    dmg = round(base_dmg * dt["mult"])
    return {"damage": dmg, "defender_hull_remaining": max(0, defender_hull - dmg), "weapon": weapon}

async def get_tactical_position(session_id: int, zone: str = "forward", terrain: str = "open_space",
                                 formation: str = "spearhead") -> dict:
    flank_bonus = 1.0 if zone in ("aft","ventral") else 0.8
    terrain_bonus = 1.0 if terrain == "asteroid_field" else 0.9 if terrain == "nebula" else 0.8
    form_bonus = 1.2 if formation == "spearhead" else 1.0 if formation == "wedge" else 0.9
    return {"effective_power": round(flank_bonus * terrain_bonus * form_bonus, 2), "zone": zone, "terrain": terrain, "formation": formation}

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
        info("tactics", f"Error: {e}")
        return {"error": str(e)}
