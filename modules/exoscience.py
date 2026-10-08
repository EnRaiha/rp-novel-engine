#!/usr/bin/env python3
"""Exoscience — Ported from Rust exoscience.rs. Science missions, anomalies, theories."""
from __future__ import annotations
import hashlib
import random
from core.db import Database
from core.log import info, warn, error
from core.session import require_session


def _writable_session(session_id: int | None) -> int:
    """Resolve the session for one call and refuse a frozen campaign.

    Sessions 3 and 5 are reference data; a writer that skipped this check mutated them.

    @param session_id - caller's session; `None` resolves through `core.session.require_session`.
    @returns the resolved session id.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    from core.ooc import _refuse_frozen

    sid = require_session(session_id)
    _refuse_frozen(sid)
    return sid


def _like_escape(text: str) -> str:
    """Escape `\\`, `%` and `_` so a location matches as literal text under `ESCAPE '\\'`.

    @param text - user-supplied location.
    @returns the text with LIKE wildcards neutralised.
    """
    return str(text).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _pace(*parts: object) -> int:
    """A stable 5..15 pace for one row, derived from the row's own state.

    The tick used `random.randint(5, 15)`, so running it twice on the same state gave two different
    campaigns. A digest of the row's identity and its progress keeps the variety without losing
    reproducibility: the same state always advances the same way.
    """
    seed = hashlib.blake2s("|".join(str(part) for part in parts).encode(), digest_size=4).digest()
    return 5 + (int.from_bytes(seed, "big") % 11)


ANOMALY_TYPES = ["gravity_well","temporal_rift","bio_signal","energy_surge","precursor_signal","void_echo"]
ANOMALY_PREFIXES = ["Anomalous","Deep","Void","Phantom","Resonant","Shifting","Silent","Ancient","Pulsing","Crimson"]
ANOMALY_SUFFIXES = ["Distortion","Echo","Signature","Well","Rift","Surge","Pulse","Anomaly","Field","Nexus"]

async def run_tick(session_id: int | None = None) -> dict:
    """Progress active missions and anomalies for this campaign.

    A mission's progress write and its reward credit share one transaction, and the write is guarded
    by `status='active'`, so a second concurrent tick neither pays the reward twice nor re-completes
    the mission. A NULL `research_reward` reads as 0: `credits + NULL` is NULL and wiped the treasury.

    @param session_id - campaign; `None` resolves through `require_session`.
    @returns `{missions_completed, anomalies_studied}` plus `rewards_unpaid` when a completion had no treasury row.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
    try:
        # Progress active science missions
        missions = await Database.fetch("SELECT id, mission_type, progress, target_progress, research_reward FROM maya_rp.science_missions WHERE session_id=$1 AND status='active'", session_id)
        completed = 0
        unpaid = 0
        for m in missions:
            # `progress` and `target_progress` are nullable columns. A row written without them made
            # `None + gain` raise inside the tick's single try, so one malformed row stopped every
            # mission in the session instead of being read as the zero progress it holds.
            progress = m["progress"] if m["progress"] is not None else 0
            target = m["target_progress"] if m["target_progress"] is not None else 100
            gain = _pace(session_id, m["id"], progress)
            new_progress = min(target, progress + gain)
            is_done = new_progress >= target
            reward = m["research_reward"] if m["research_reward"] is not None else 0
            async with Database.transaction() as conn:
                claimed = await conn.fetchval(
                    "UPDATE maya_rp.science_missions SET progress=$1, status=$2 "
                    "WHERE id=$3 AND session_id=$4 AND status='active' RETURNING id",
                    new_progress, "completed" if is_done else "active", m["id"], session_id)
                if claimed is None:
                    continue
                if is_done:
                    # A session with no resources row takes the reward and loses it silently: the UPDATE
                    # matches nothing and reports no error. Session 5 is in exactly that state, so the
                    # tick says what it could not pay instead of counting it as paid.
                    paid = await conn.fetchval(
                        "UPDATE maya_rp.resources SET credits=credits+$1 WHERE session_id=$2"
                        " RETURNING credits", reward, session_id)
            if is_done:
                if paid is None:
                    unpaid += 1
                    warn("exoscience",
                         f"mission {m['id']} completed but session {session_id} has no resources row;"
                         f" {reward} credits were not paid")
                completed += 1

        # Collect data from anomalies
        anomalies = await Database.fetch("SELECT id, name, data_collected, data_threshold FROM maya_rp.anomalies_catalog WHERE session_id=$1 AND studied=false", session_id)
        studied = 0
        for a in anomalies:
            # Same nullable-column read as the mission loop: `data_collected` and `data_threshold`
            # can both be absent, and one such anomaly row killed the whole tick.
            before = a["data_collected"] if a["data_collected"] is not None else 0
            threshold = a["data_threshold"] if a["data_threshold"] is not None else 100
            collected = before + _pace(session_id, a["id"], before)
            if collected >= threshold:
                await Database.execute(
                    "UPDATE maya_rp.anomalies_catalog SET studied=true, data_collected=$1 "
                    "WHERE id=$2 AND session_id=$3",
                    collected, a["id"], session_id)
                studied += 1
            else:
                await Database.execute(
                    "UPDATE maya_rp.anomalies_catalog SET data_collected=$1 "
                    "WHERE id=$2 AND session_id=$3",
                    collected, a["id"], session_id)

        info("exoscience", f"Tick: {completed} missions, {studied} anomalies studied")
        out = {"missions_completed": completed, "anomalies_studied": studied}
        if unpaid:
            out["rewards_unpaid"] = unpaid
        return out
    except Exception as e:
        error("exoscience", f"Error: {e}")
        return {"error": str(e)}

async def start_mission(mission_type: str, session_id: int | None = None) -> dict:
    """Start one science mission. @raises core.ooc.FrozenSession - the campaign is frozen."""
    session_id = _writable_session(session_id)
    if not (mission_type or "").strip():
        return {"error": "mission_type is required: a mission with no type cannot be progressed"}
    mission_type = mission_type.strip()
    target = random.randint(50, 200)
    reward = target * 5
    mid = await Database.fetchval(
        "INSERT INTO maya_rp.science_missions (session_id, mission_type, target_progress, research_reward, status) VALUES ($1,$2,$3,$4,'active') RETURNING id",
        session_id, mission_type, target, reward)
    return {"mission_id": mid, "type": mission_type, "target": target, "reward": reward}

async def generate_anomaly(location: str, session_id: int | None = None) -> dict:
    """Create one anomaly at the sector whose name contains `location` (literal match).

    @raises core.ooc.FrozenSession - the campaign is frozen.
    """
    session_id = _writable_session(session_id)
    if not (location or "").strip():
        # An empty location made the LIKE pattern `%%`, which matched the session's first sector, so
        # an anomaly with no site was silently tied to whichever sector the scan happened to return.
        return {"error": "location is required: an anomaly with no site cannot be placed"}
    location = location.strip()
    name = f"{random.choice(ANOMALY_PREFIXES)} {random.choice(ANOMALY_SUFFIXES)}"
    atype = random.choice(ANOMALY_TYPES)
    threshold = random.randint(30, 100)
    # anomalies_catalog keys its site by sector_id (there is no `location`
    # column): resolve the location name to a sector and keep the raw text in
    # the description so nothing is lost when the name is not a sector.
    sector_id = await Database.fetchval(
        "SELECT id FROM maya_rp.sectors WHERE session_id=$1 AND LOWER(name) LIKE LOWER($2) ESCAPE '\\' "
        "ORDER BY id LIMIT 1",
        session_id, f"%{_like_escape(location)}%")
    aid = await Database.fetchval(
        "INSERT INTO maya_rp.anomalies_catalog (session_id, name, anomaly_type, sector_id, data_threshold, studied, description) "
        "VALUES ($1,$2,$3,$4,$5,false,$6) RETURNING id",
        session_id, name, atype, sector_id, threshold, f"Location: {location}")
    return {"anomaly_id": aid, "name": name, "type": atype, "location": location, "sector_id": sector_id}
