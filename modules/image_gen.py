#!/usr/bin/env python3
"""Image Generation — Ported from Rust image_gen.rs. Generates AI image prompts from game state."""
from __future__ import annotations
import random
from core.db import Database
from core.config import Config
from core.log import info

async def generate_prompt(session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    ships = await Database.fetchrow("SELECT name, tier, hull FROM maya_rp.ships WHERE session_id=$1 ORDER BY RANDOM() LIMIT 1", session_id)
    chars = await Database.fetchrow("SELECT name, role FROM maya_rp.characters WHERE session_id=$1 ORDER BY RANDOM() LIMIT 1", session_id)
    systems = await Database.fetchrow("SELECT system_name FROM maya_rp.territory WHERE session_id=$1 ORDER BY RANDOM() LIMIT 1", session_id)
    prompt = f"Space scene: "
    if chars: prompt += f"{chars['name']} ({chars['role']}) "
    if ships: prompt += f"onboard T{ships['tier']} vessel in the {systems['system_name'] if systems else 'void'} system. "
    prompt += "Sci-fi cinematic lighting, detailed starship interior, epic scale."
    await Database.execute("INSERT INTO maya_rp.image_prompts (session_id, prompt, tags) VALUES ($1,$2,'[]'::jsonb)", session_id, prompt)
    return {"prompt": prompt}

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    return {"status": "image_gen_ready"}
