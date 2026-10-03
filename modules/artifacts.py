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
    await Database.execute(
        "UPDATE maya_rp.artifacts SET equipped_to=$1 WHERE id=$2 AND session_id=$3",
        target_id, artifact_id, session_id)
    return {"equipped": art["name"], "target_id": target_id}

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    return {"status": "artifacts_ready"}


# ═══════════════════════════════════════════════════════════════
# NOVEL ADAPTATION — MEDALS & HONOR (novel bab 211, 601, 692)
# "This is the medal I earned with my love's life."
# Medal tiers: merit → sacrifice → resurrection. Setiap medal bawa backstory.
# ═══════════════════════════════════════════════════════════════

MEDAL_TIERS = {
    "merit": {"label": "Medal of Merit", "bonus": 5, "desc": "Untuk perkhidmatan cemerlang"},
    "sacrifice": {"label": "Medal of Sacrifice", "bonus": 10, "desc": "Untuk pengorbanan — dibayar dengan nyawa cinta"},
    "resurrection": {"label": "Resurrection Medal", "bonus": 15, "desc": "Untuk yang bangkit semula dari kegagalan"},
}


async def award_medal(session_id: int | None, recipient: str, tier: str = "merit",
                      backstory: str = "") -> dict:
    """Anugerah medal — dengan sacrifice backstory (novel: medal = cerita korban)."""
    if session_id is None: session_id = Config.SESSION_ID
    if tier not in MEDAL_TIERS:
        return {"error": f"Tier mesti: {list(MEDAL_TIERS.keys())}"}
    if not (recipient or "").strip():
        # Without a recipient the medal is named "Medal of Merit — " and the event
        # reads " menerima Medal of Merit".
        return {"error": "Medal needs a recipient."}
    conf = MEDAL_TIERS[tier]
    name = f"{conf['label']} — {recipient}"
    desc = conf["desc"] if not backstory else backstory
    aid = await Database.fetchval(
        """INSERT INTO maya_rp.artifacts (session_id, name, type, rarity, description, bonus, sacrifice_backstory, award_recipient)
           VALUES ($1, $2, 'medal', $3, $4, $5, $6, $7) RETURNING id""",
        session_id, name, tier, desc, conf["bonus"], backstory or None, recipient)
    await Database.execute(
        "INSERT INTO maya_rp.events (session_id, event_type, title, description, importance) "
        "VALUES ($1, 'honor', $2, $3, 4)",
        session_id, f"MEDAL AWARDED: {conf['label']}",
        f"{recipient} menerima {conf['label']}. {desc}")
    return {"medal_id": aid, "name": name, "tier": tier, "bonus": conf["bonus"]}


async def list_medals(session_id: int | None = None) -> list[dict]:
    if session_id is None: session_id = Config.SESSION_ID
    rows = await Database.fetch(
        "SELECT id, name, rarity, bonus, sacrifice_backstory, award_recipient FROM maya_rp.artifacts "
        "WHERE session_id=$1 AND type='medal' ORDER BY bonus DESC", session_id)
    return [dict(r) for r in rows]
