#!/usr/bin/env python3
"""
resource_modifiers.py — Apply hybrid resource modifiers to planets (Day 1383, Izzat).

Hybrid = planet_types_catalog base (canon, by type) + deterministic ±15% jitter
(seeded by planet id). Bounded: jitter never flips a planet's type logic.
Only touches planets with empty '{}' modifiers; surveyed planets untouched.
"""
from __future__ import annotations
import os
import asyncio, hashlib, json, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import Config
from core.db import Database

SID = Config.SESSION_ID

# Canon base per type (from planet_types_catalog) — food/fuel/alloys/research
BASE = {
    "Terran":         {"food": 1.5, "alloys": 1.0, "research": 1.2},
    "Continental":    {"food": 1.6, "alloys": 1.1, "research": 1.1},
    "Gaia":           {"food": 2.5, "fuel": 1.5, "alloys": 1.5, "research": 1.5},
    "Ocean":          {"food": 2.0, "fuel": 0.5, "alloys": 0.6},
    "Desert":         {"food": 0.3, "fuel": 1.3, "alloys": 1.1},
    "Arid":           {"food": 0.8, "fuel": 1.1, "alloys": 1.2},
    "Tundra":         {"food": 0.4, "alloys": 1.2, "research": 1.3},
    "Ice World":      {"food": 0.3, "fuel": 1.4, "alloys": 1.0, "research": 1.3},
    "Frozen":         {"food": 0.0, "fuel": 1.2, "alloys": 0.8, "research": 1.1},
    "Barren":         {"food": 0.0, "fuel": 0.5, "alloys": 1.5},
    "Rocky":          {"food": 0.0, "fuel": 0.6, "alloys": 1.6},
    "Molten":         {"food": 0.0, "fuel": 1.8, "alloys": 2.2},
    "Volcanic":       {"food": 0.0, "fuel": 1.5, "alloys": 2.0},
    "Toxic":          {"food": 0.0, "fuel": 1.6, "alloys": 0.8, "research": 1.2},
    "Gas Giant":      {"fuel": 3.0, "research": 1.5},
    "Ringed Gas Giant": {"fuel": 3.5, "research": 1.7},
    "Ice Giant":      {"fuel": 2.5, "research": 1.4},
    "Dwarf Planet":   {"food": 0.0, "fuel": 0.4, "alloys": 1.0},
    "Asteroid Field": {"fuel": 0.8, "alloys": 2.0},
    "Carbon World":   {"fuel": 1.2, "alloys": 2.4, "research": 1.0},
    "Crystal World":  {"fuel": 0.5, "alloys": 1.8, "research": 1.6},
    "Habitat Station": {"food": 1.0, "fuel": 0.5, "alloys": 0.8, "research": 1.2},
    "Star":           {},
    "Tomb":           {"food": 0.0, "alloys": 0.5, "research": 2.0},
    "Ringworld":      {"food": 1.5, "fuel": 2.0, "alloys": 2.0, "research": 3.0},
}

JITTER = 0.15  # ±15%


def jitter_for(planet_id: int, base: dict) -> dict:
    """Deterministic ±15% jitter seeded by planet id. Never below 0."""
    seed = int(hashlib.md5(f"resmod-{planet_id}".encode()).hexdigest(), 16) % (2**32)
    out = {}
    for k, v in base.items():
        delta = (seed % 1000) / 1000.0 * 2 - 1  # -1..+1
        nv = round(v * (1 + delta * JITTER), 2)
        out[k] = max(0.0, nv)
    return out


async def main() -> None:
    await Database.init()
    planets = await Database.fetch(
        """SELECT id, name, planet_type, resource_modifiers FROM maya_rp.planets
           WHERE session_id=$1 AND (resource_modifiers IS NULL OR resource_modifiers = '{}'::jsonb)""",
        SID)
    updated = 0
    for p in planets:
        base = BASE.get(p["planet_type"], {})
        if not base:
            continue
        mods = jitter_for(p["id"], base)
        await Database.execute(
            "UPDATE maya_rp.planets SET resource_modifiers=$2 WHERE id=$1",
            p["id"], json.dumps(mods))
        updated += 1
    print(f"HYBRID RESOURCE MODIFIERS — {updated} planets updated (type base + ±15% seed jitter)")
    await Database.close()


if __name__ == "__main__":
    asyncio.run(main())