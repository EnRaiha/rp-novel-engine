#!/usr/bin/env python3
"""Image Generation — Ported from Rust image_gen.rs. Generates AI image prompts from game state."""
from __future__ import annotations
import random
from core.db import Database
from core.log import info
from core.session import require_session

async def generate_prompt(session_id: int | None = None) -> dict:
    if session_id is None: session_id = require_session(None)
    # `hull` was selected here and never used: it is a numeric hull value, not a
    # class name, so it could not go into a prompt.
    ships = await Database.fetchrow("SELECT name, tier FROM maya_rp.ships WHERE session_id=$1 ORDER BY RANDOM() LIMIT 1", session_id)
    chars = await Database.fetchrow("SELECT name, role FROM maya_rp.characters WHERE session_id=$1 ORDER BY RANDOM() LIMIT 1", session_id)
    systems = await Database.fetchrow("SELECT system_name FROM maya_rp.territory WHERE session_id=$1 ORDER BY RANDOM() LIMIT 1", session_id)
    prompt = "Space scene: "
    if chars: prompt += f"{chars['name']} ({chars['role']}) "
    if ships: prompt += f"onboard T{ships['tier']} vessel in the {systems['system_name'] if systems else 'void'} system. "
    prompt += "Sci-fi cinematic lighting, detailed starship interior, epic scale."
    # image_prompts keys on (scene_type, prompt_full) — there is no `prompt`
    # column and no `tags` column. scene_type is enum-checked, so pick a legal
    # value for what the prompt actually describes.
    scene_type = "character-portrait" if chars else "planet-landscape"
    await Database.execute(
        "INSERT INTO maya_rp.image_prompts (session_id, scene_type, subject_name, prompt_full) "
        "VALUES ($1,$2,$3,$4)",
        session_id, scene_type, (chars["name"] if chars else None), prompt)
    return {"prompt": prompt, "scene_type": scene_type}

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = require_session(None)
    return {"status": "image_gen_ready"}
