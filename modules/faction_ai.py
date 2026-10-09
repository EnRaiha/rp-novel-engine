#!/usr/bin/env python3
"""Faction AI — ML-driven decisioning (rewritten 2026-08-14).

Replaces the old random-drift tick with core.decision_models:
  - pirate factions are classified into groups (free|sponsor|hired)
  - each group's policy is predicted by its RandomForest (fallback: rules)
  - fleet/treasury drift now follows group doctrine instead of uniform noise
  - every prediction logged to ai_decision_log (retraining corpus)
"""
from __future__ import annotations
from core.db import Database
from core.session import require_session
from core.log import error, info
from core.decision_models import (detect_pirate_group, predict_pirate_policy,
                                  predict_pirate_survival, log_decision)

# Group doctrine: ((fleet_min, fleet_max), (treasury_min, treasury_max), volatility)
_DOCTRINE = {
    "free":     ((0, 5),   (-15000, 15000), 0.30),   # wild: volatile raids
    "sponsor":  ((0, 2),   (5000, 25000),   0.20),   # wolf packs: patron tolls, stable
    "hired":    ((0, 3),   (15000, 40000),  0.25),   # contract income, disciplined
}


def _doctrine(group: str) -> tuple:
    """Return (fleet_lo, fleet_hi, treasury_lo, treasury_hi, vol) for a group."""
    (f_lo, f_hi), (t_lo, t_hi), vol = _DOCTRINE.get(group, _DOCTRINE["free"])
    return f_lo, f_hi, t_lo, t_hi, vol


async def run_tick(session_id: int | None = None) -> dict:
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    try:
        factions = await Database.fetch(
            "SELECT id, name, is_pirate, pirate_fleet_power, treasury, reputation "
            "FROM maya_rp.factions WHERE session_id=$1", session_id)
        decisions = 0
        for f in factions:
            if not f["is_pirate"]:
                continue
            group = await detect_pirate_group(f["id"], session_id)
            policy = predict_pirate_policy(
                group, src="ai_policy", policy="STANDARD UNIFORMITY",
                cond="clean_crew", act="check_first")
            await log_decision(f["id"], f"pirate_policy", 
                               {"src": "ai_policy", "policy": "STANDARD UNIFORMITY",
                                "cond": "clean_crew", "act": "check_first"},
                               policy["class"], policy.get("probs"), group, session_id)
            fp_lo, fp_hi, t_lo, t_hi, vol = _doctrine(group)
            # Doctrine-shaped drift. Relative writes keep a concurrent update from pirates.py.
            # A credit always applies. A debit applies only when the balance covers it.
            if _chance(vol):
                await Database.execute(
                    "UPDATE maya_rp.factions SET pirate_fleet_power = GREATEST(0, COALESCE(pirate_fleet_power, 0) + $1) "
                    "WHERE id=$2 AND session_id=$3", _randint(fp_lo, fp_hi), f["id"], session_id)
            if _chance(vol):
                await Database.execute(
                    "UPDATE maya_rp.factions SET treasury = COALESCE(treasury, 0) + $1::bigint "
                    "WHERE id=$2 AND session_id=$3 "
                    "AND ($1::bigint >= 0 OR COALESCE(treasury, 0) + $1::bigint >= 0)",
                    _randint(t_lo, t_hi), f["id"], session_id)
            decisions += 1
        info("faction_ai", f"Tick: {decisions} pirate decisions (ML/rules)")
        return {"factions": len(factions), "decisions": decisions}
    except Exception as e:
        error("faction_ai", f"tick failed for session {session_id}: {e}")
        return {"error": str(e)}


def _chance(p: float) -> bool:
    import random
    return random.random() < p


def _randint(a: int, b: int) -> int:
    import random
    return random.randint(a, b)
