#!/usr/bin/env python3
"""Exoscience — Ported from Rust exoscience.rs. Science missions, anomalies, theories."""
from __future__ import annotations
import random
from core.db import Database
from core.config import Config
from core.log import info

ANOMALY_TYPES = ["gravity_well","temporal_rift","bio_signal","energy_surge","precursor_signal","void_echo"]
ANOMALY_PREFIXES = ["Anomalous","Deep","Void","Phantom","Resonant","Shifting","Silent","Ancient","Pulsing","Crimson"]
ANOMALY_SUFFIXES = ["Distortion","Echo","Signature","Well","Rift","Surge","Pulse","Anomaly","Field","Nexus"]

async def run_tick(session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    try:
        # Progress active science missions
        missions = await Database.fetch("SELECT id, mission_type, progress, target_progress, research_reward FROM maya_rp.science_missions WHERE session_id=$1 AND status='active'", session_id)
        completed = 0
        for m in missions:
            gain = random.randint(5, 15)
            new_progress = min(m["target_progress"], m["progress"] + gain)
            is_done = new_progress >= m["target_progress"]
            await Database.execute("UPDATE maya_rp.science_missions SET progress=$1, status=$2 WHERE id=$3", new_progress, "completed" if is_done else "active", m["id"])
            if is_done:
                await Database.execute("UPDATE maya_rp.resources SET credits=credits+$1 WHERE session_id=$2", m["research_reward"], session_id)
                completed += 1

        # Collect data from anomalies
        anomalies = await Database.fetch("SELECT id, name, data_collected, data_threshold FROM maya_rp.anomalies_catalog WHERE session_id=$1 AND studied=false", session_id)
        studied = 0
        for a in anomalies:
            collected = a["data_collected"] + random.randint(5, 15)
            if collected >= a["data_threshold"]:
                await Database.execute("UPDATE maya_rp.anomalies_catalog SET studied=true, data_collected=$1 WHERE id=$2", collected, a["id"])
                studied += 1
            else:
                await Database.execute("UPDATE maya_rp.anomalies_catalog SET data_collected=$1 WHERE id=$2", collected, a["id"])

        info("exoscience", f"Tick: {completed} missions, {studied} anomalies studied")
        return {"missions_completed": completed, "anomalies_studied": studied}
    except Exception as e:
        info("exoscience", f"Error: {e}")
        return {"error": str(e)}

async def start_mission(mission_type: str, session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    target = random.randint(50, 200)
    reward = target * 5
    mid = await Database.fetchval(
        "INSERT INTO maya_rp.science_missions (session_id, mission_type, target_progress, research_reward, status) VALUES ($1,$2,$3,$4,'active') RETURNING id",
        session_id, mission_type, target, reward)
    return {"mission_id": mid, "type": mission_type, "target": target, "reward": reward}

async def generate_anomaly(location: str, session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    name = f"{random.choice(ANOMALY_PREFIXES)} {random.choice(ANOMALY_SUFFIXES)}"
    atype = random.choice(ANOMALY_TYPES)
    threshold = random.randint(30, 100)
    # anomalies_catalog keys its site by sector_id (there is no `location`
    # column): resolve the location name to a sector and keep the raw text in
    # the description so nothing is lost when the name is not a sector.
    sector_id = await Database.fetchval(
        "SELECT id FROM maya_rp.sectors WHERE session_id=$1 AND LOWER(name) LIKE LOWER($2) LIMIT 1",
        session_id, f"%{location}%")
    aid = await Database.fetchval(
        "INSERT INTO maya_rp.anomalies_catalog (session_id, name, anomaly_type, sector_id, data_threshold, studied, description) "
        "VALUES ($1,$2,$3,$4,$5,false,$6) RETURNING id",
        session_id, name, atype, sector_id, threshold, f"Location: {location}")
    return {"anomaly_id": aid, "name": name, "type": atype, "location": location, "sector_id": sector_id}
