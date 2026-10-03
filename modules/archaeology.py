#!/usr/bin/env python3
"""Archaeology — Ported from Rust archaeology.rs. Dig sites, excavation, artifacts."""
from __future__ import annotations
import random
from core.db import Database
from core.config import Config
from core.log import info

SITE_TYPES = ["ruins","crash_site","temple","vault","derelict","monolith"]
PREFIXES = ["Forgotten","Ancient","Lost","Buried","Void-touched","Crystalline","Submerged","Shattered","Veiled","Deep"]
SUFFIXES = ["Wreck","Citadel","Catacombs","Sanctum","Obelisk","Bunker","Archive","Reliquary","Ziggurat","Spire"]

async def seed_sites(session_id: int, count: int = 8) -> list[dict]:
    """Create `count` undiscovered dig sites in this campaign's sectors.

    The sector is read by name. Positional record access (`row[0]`) worked only
    for an asyncpg Record and raised KeyError for any dict-shaped row.
    """
    if count < 0:
        raise ValueError(f"count cannot be negative, got {count}")
    sectors = await Database.fetch("SELECT id, name FROM maya_rp.sectors WHERE session_id=$1", session_id)
    created = []
    for _ in range(count):
        name = f"{random.choice(PREFIXES)}_{random.choice(SUFFIXES)}_{random.randint(100,999)}"
        stype = random.choice(SITE_TYPES)
        diff = random.randint(1, 8)
        yield_amt = random.randint(1, 3)
        sid = await Database.fetchval(
            "INSERT INTO maya_rp.dig_sites (session_id, name, site_type, difficulty, artifact_yield, sector_id, status) "
            "VALUES ($1,$2,$3,$4,$5,$6,'undiscovered') RETURNING id",
            session_id, name, stype, diff, yield_amt,
            random.choice(sectors)["id"] if sectors else None)
        created.append({"id": sid, "name": name, "type": stype, "difficulty": diff})
    return created

async def excavate(site_id: int, session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    # dig_sites has excavation_progress/max_progress — there is no `progress`.
    site = await Database.fetchrow("SELECT id, name, site_type, difficulty, artifact_yield, excavation_progress, max_progress, status FROM maya_rp.dig_sites WHERE id=$1 AND session_id=$2", site_id, session_id)
    if not site: return {"error": "Site not found"}
    if site["status"] == "depleted": return {"error": "Site depleted"}
    # The dig ended at a literal 100 while the row carries its own ceiling: session 3 holds sites whose
    # max_progress runs 300 to 600, and site 251 sat at 450 of 500. One more dig marked it depleted and
    # wrote its progress down to 100, so the site lost 350 points of work and was called complete.
    max_progress = site["max_progress"] if site["max_progress"] is not None else 100
    difficulty = site["difficulty"] if site["difficulty"] is not None else 1
    yield_count = site["artifact_yield"] if site["artifact_yield"] is not None else 1
    gain = random.randint(10, 25) + (10 - difficulty) * 2
    new_progress = (site["excavation_progress"] or 0) + gain
    done = new_progress >= max_progress
    if done:
        await Database.execute(
            "UPDATE maya_rp.dig_sites SET status='depleted', excavation_progress=$1 "
            "WHERE id=$2 AND session_id=$3",
            max_progress, site_id, session_id)
        for _ in range(yield_count):
            # artifacts carries no `source` column; the origin goes in the
            # description and the registered type value is 'relic'.
            await Database.execute(
                "INSERT INTO maya_rp.artifacts (session_id, name, type, description) "
                "VALUES ($1,$2,'relic',$3)",
                session_id, f"{site['name']}_artifact", f"Excavated from {site['name']}")
        return {"completed": True, "artifacts": yield_count}
    else:
        await Database.execute(
            "UPDATE maya_rp.dig_sites SET excavation_progress=$1 WHERE id=$2 AND session_id=$3",
            new_progress, site_id, session_id)
        return {"completed": False, "progress": new_progress}

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    return {"status": "archaeology_ready"}
