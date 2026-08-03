#!/usr/bin/env python3
"""Artifacts — Ported from Rust artifacts.rs."""
from __future__ import annotations
import random
from core.db import Database
from core.config import Config
from core.log import info

ARTIFACT_TYPES = ["weapon","armor","tool","relic","data_core","biological","energy_cell","musical","cultural","unknown"]

async def list_artifacts(session_id: int | None = None) -> list[dict]:
    if session_id is None: session_id = Config.SESSION_ID
    rows = await Database.fetch("SELECT id, name, type, rarity, description, bonus, curse, equipped_to FROM maya_rp.artifacts WHERE session_id=$1 ORDER BY rarity DESC", session_id)
    return [dict(r) for r in rows]

async def discover(session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    name = f"{random.choice(['Echo','Void','Star','Shadow','Bone','Soul','Tide','Ember','Frost','Thorn'])} of {random.choice(['Aethel','Kael','Morn','Veyn','Sylvan','Dorn','Zephyr','Nyx','Orin','Valkor'])}"
    atype = random.choice(ARTIFACT_TYPES)
    rarity = random.choices(["common","uncommon","rare","epic","legendary"], weights=[50,25,15,8,2])[0]
    rarity_mult = {"common": 1, "uncommon": 2, "rare": 4, "epic": 8, "legendary": 15}[rarity]
    bonus = random.randint(1, 10) * rarity_mult
    aid = await Database.fetchval(
        "INSERT INTO maya_rp.artifacts (session_id, name, type, rarity, description, bonus) VALUES ($1,$2,$3,$4,$5,$6) RETURNING id",
        session_id, name, atype, rarity, f"A {rarity} {atype} artifact", bonus)
    return {"id": aid, "name": name, "type": atype, "rarity": rarity, "bonus": bonus}

async def equip(artifact_id: int, target_id: int, session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    art = await Database.fetchrow("SELECT id, name FROM maya_rp.artifacts WHERE id=$1 AND session_id=$2", artifact_id, session_id)
    if not art: return {"error": "Artifact not found"}
    await Database.execute("UPDATE maya_rp.artifacts SET equipped_to=$1 WHERE id=$2", target_id, artifact_id)
    return {"equipped": art["name"], "target_id": target_id}

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    return {"status": "artifacts_ready"}
