#!/usr/bin/env python3
"""Decision Models — ML-powered faction/pirate decisioning (QA/ML review 2026-08-14).

Loads the trained sklearn ensembles from models/ and exposes typed predictors.
Pirate decisions are split into THREE groups per King's directive:

  Group 1 "free"     — wild & free pirates (independent, aggressive)
  Group 2 "sponsor"  — sponsored pirates (patron-backed: tolls, trade ties)
  Group 3 "hired"    — hired/contract pirates (mission-focused privateers)

Model slot resolution per group:
  models/pirate_policy_{group}.pkl   → fallback models/pirate_policy.pkl   → rules
  models/pirate_survival_{group}.pkl → fallback models/pirate_survival.pkl → rules
Shared: models/event_importance_tree.pkl, models/pirate_events_tree.pkl.

Per-group deterministic biases (logit multipliers) sit on top of predictions
until per-group models are trained (train_models.py writes them once
ai_decision_log accumulates a `pirate_group` corpus). Every prediction is
logged to ai_decision_log for that retraining loop.

Degrades gracefully: sklearn missing / pickle corrupt / low-confidence →
rule-based fallback. Never raises into the tick.
"""
from __future__ import annotations
import os, pickle, random, json
from datetime import datetime, timezone
from core.db import Database
from core.config import Config
from core.log import info, error

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models")

PIRATE_GROUPS = ("free", "sponsor", "hired")
DEFAULT_GROUP = "free"

# ── Per-group behavior biases (logit multipliers on predicted probs) ─────
# These encode doctrine until dedicated per-group models are trained.
POLICY_BIAS = {
    # act labels from pirate_policy_tree.act_map
    "free":     {"bullet": 1.6, "clear_all": 1.4, "bullet_or_ransom": 1.2},
    "sponsor":  {"check_first": 1.7, "confirm_first": 1.5, "debt_bound": 1.3,
                 "convert": 1.2, "bullet": 0.5},
    "hired":    {"confirm_first": 1.5, "bullet_or_ransom": 1.4, "level": 1.3,
                 "clear_all": 0.7, "bullet": 0.8},
}
SURVIVAL_BIAS = {
    # action labels from pirate_survival_tree.action_map
    "free":     {"pirate_crew_captured": 1.3, "pirate_king_captured": 1.2,
                 "hostage_trade": 0.8},
    "sponsor":  {"tender_of_alliance": 1.7, "queen_offers_alliance": 1.4,
                 "relic_offer": 1.3, "den_surrenders": 1.2},
    "hired":    {"hostage_trade": 1.6, "pirate_crew_captured": 1.2,
                 "den_surrenders": 0.8, "tender_of_alliance": 0.7},
}


def _log(module: str, msg: str):
    try:
        info(module, msg)
    except Exception:  # deliberate: logging must never raise into its caller
        pass


# ── Loading ──────────────────────────────────────────────────────────────

_cache: dict = {}

def _load(name: str) -> dict | None:
    """Load a pickle by basename; return None on any failure."""
    if name in _cache:
        return _cache[name]
    paths = []
    if "{" not in name:
        paths.append(os.path.join(MODEL_DIR, name))
    _cache[name] = None
    for p in paths:
        if not os.path.exists(p):
            continue
        try:
            with open(p, "rb") as f:
                obj = pickle.load(f)
            if isinstance(obj, dict) and any(k in obj for k in ("tree", "clf", "rf")):
                _cache[name] = obj
                _log("decision_models", f"Loaded {name}")
                return obj
        except Exception as e:
            _log("decision_models", f"Failed to load {name}: {e}")
            return None
    return None


def _model_for(group: str, kind: str) -> dict | None:
    """kind ∈ {policy, survival}. Group-specific model → base model → None."""
    group = group if group in PIRATE_GROUPS else DEFAULT_GROUP
    base = {"policy": "pirate_policy_tree.pkl", "survival": "pirate_survival_tree.pkl"}[kind]
    specific = f"pirate_{kind}_{group}.pkl"
    m = _load(specific) or _load(base)
    if m is None and specific != base:
        _log("decision_models", f"No model for {kind}/{group} — rule fallback")
    return m


def _has_sklearn() -> bool:
    try:
        import sklearn  # noqa: F401
        return True
    except ImportError:
        return False


# ── Feature construction ─────────────────────────────────────────────────

def event_features(event: dict) -> list:
    """['day','hour','type_idx','n_tags'] for event_importance_tree."""
    et = event.get("event_type") or event.get("title") or ""
    type_map = (_load("event_importance_tree.pkl") or {}).get("type_map", {})
    type_idx = type_map.get(et.lower(), len(type_map))
    tags = event.get("tags") or []
    n_tags = len(tags) if isinstance(tags, (list, tuple)) else 0
    ts = event.get("happened_at") or datetime.now(timezone.utc)
    if hasattr(ts, "day"):
        day, hour = ts.day, ts.hour
    elif isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            day, hour = dt.day, dt.hour
        except Exception:
            day, hour = 1, 0
    else:
        day, hour = 1, 0
    return [float(day), float(hour), float(type_idx), float(n_tags)]


def pirate_event_features(pirate: dict) -> list:
    """['day','tier','dist','has_royalty','sub_idx'] for pirate_events_tree."""
    sub_map = (_load("pirate_events_tree.pkl") or {}).get("sub_map", {})
    sub = (pirate.get("subtype") or pirate.get("event_subtype") or "")
    return [
        float(pirate.get("day") or 0),
        float(pirate.get("tier") or 0),
        float(pirate.get("dist") or 0),
        float(1 if pirate.get("has_royalty") else 0),
        float(sub_map.get(sub.lower(), len(sub_map))),
    ]


def policy_features(src: str, policy: str, cond: str, act: str) -> list:
    """['src_idx','pol_idx','cond_idx','act_idx'] for pirate_policy_tree."""
    m = _load("pirate_policy.pkl") or {}
    sm = m.get("src_map", {}); pm = m.get("pol_map", {})
    cm = m.get("cond_map", {}); am = m.get("act_map", {})
    return [float(sm.get(src, len(sm))), float(pm.get(policy, len(pm))),
            float(cm.get(cond, len(cm))), float(am.get(act, len(am)))]


def survival_features(virgin: int, live_chance: float, action: str) -> list:
    """['virgin','live_chance','action_idx'] for pirate_survival_tree."""
    m = _load("pirate_survival.pkl") or {}
    am = m.get("action_map", {})
    return [float(virgin), float(live_chance), float(am.get(action, len(am)))]


# ── Predictors ───────────────────────────────────────────────────────────

def predict_event_importance(event: dict) -> float:
    """0-10 importance score; falls back to rule heuristic."""
    m = _load("event_importance_tree.pkl")
    if m and _has_sklearn():
        try:
            rf = m.get("rf") or m.get("tree")
            return float(rf.predict([event_features(event)])[0])
        except Exception as e:
            _log("decision_models", f"importance predict failed: {e}")
    tags = event.get("tags") or []
    return 7.0 if "war" in tags or "battle" in tags else 3.0


def predict_pirate_policy(group: str, src: str, policy: str, cond: str, act: str) -> dict:
    """Predict pirate policy decision {class, probs, source}."""
    m = _model_for(group, "policy")
    if m and _has_sklearn():
        try:
            clf = m.get("clf")
            feats = [policy_features(src, policy, cond, act)]
            probs = clf.predict_proba(feats)[0]
            bias = POLICY_BIAS.get(group, {})
            if bias:
                labels = list(clf.classes_)
                am = {v: k for k, v in m.get("act_map", {}).items()}
                for label, mult in bias.items():
                    idx = am.get(label)
                    if idx is not None and idx < len(probs):
                        probs[idx] *= mult
                probs = probs / probs.sum()
            pred = int(probs.argmax())
            am_inv = {v: k for k, v in m.get("act_map", {}).items()}
            return {"class": am_inv.get(pred, str(pred)), "probs": probs.tolist(),
                    "source": f"ml:{group}"}
        except Exception as e:
            _log("decision_models", f"policy predict failed: {e}")
    # rule fallback per group
    if group == "sponsor":
        out = "check_first" if cond != "den_destroyed" else "level"
    elif group == "hired":
        out = "confirm_first"
    else:
        out = "bullet_or_ransom" if cond in ("captive", "boarding") else "bullet"
    return {"class": out, "probs": [], "source": f"rules:{group}"}


def predict_pirate_survival(group: str, virgin: int, live_chance: float, action: str) -> dict:
    """Predict pirate survival-action outcome {class, probs, source}."""
    m = _model_for(group, "survival")
    if m and _has_sklearn():
        try:
            clf = m.get("clf")
            probs = clf.predict_proba([survival_features(virgin, live_chance, action)])[0]
            bias = SURVIVAL_BIAS.get(group, {})
            if bias:
                am = {v: k for k, v in m.get("action_map", {}).items()}
                for label, mult in bias.items():
                    idx = am.get(label)
                    if idx is not None and idx < len(probs):
                        probs[idx] *= mult
                probs = probs / probs.sum()
            pred = int(probs.argmax())
            am_inv = {v: k for k, v in m.get("action_map", {}).items()}
            return {"class": am_inv.get(pred, str(pred)), "probs": probs.tolist(),
                    "source": f"ml:{group}"}
        except Exception as e:
            _log("decision_models", f"survival predict failed: {e}")
    # rule fallback per group
    if group == "sponsor":
        out = "tender_of_alliance"
    elif group == "hired":
        out = "hostage_trade"
    else:
        out = "pirate_crew_captured"
    return {"class": out, "probs": [], "source": f"rules:{group}"}


# ── Group detection ──────────────────────────────────────────────────────

async def detect_pirate_group(faction_id: int, session_id: int | None = None) -> str:
    """Classify a pirate faction into free|sponsor|hired.

    1. explicit override column (factions.pirate_group, set by King)
    2. sponsor: any non-hostile relation with trade_volume > 0 (tolls/patronage)
    3. hired: exactly one high-tension relation (>=0.6) and no trade ties
    4. default: free
    Persists the detected group back to factions.pirate_group.
    """
    sid = session_id or Config.SESSION_ID
    try:
        row = await Database.fetchrow(
            "SELECT pirate_group FROM maya_rp.factions WHERE id=$1 AND session_id=$2",
            faction_id, sid)
        if not row:
            return DEFAULT_GROUP
        if row["pirate_group"]:
            return row["pirate_group"]
        rels = await Database.fetch(
            "SELECT standing, trade_volume, military_tension FROM maya_rp.faction_relations "
            "WHERE session_id=$1 AND faction_a=$2", sid, faction_id)
        trade = any((r["trade_volume"] or 0) > 0 for r in rels)
        high_tension = [r for r in rels if (r["military_tension"] or 0) >= 0.6]
        if trade and any(r["standing"] in ("friendly", "neutral") for r in rels):
            group = "sponsor"
        elif len(high_tension) == 1 and not trade:
            group = "hired"
        else:
            group = "free"
        await Database.execute(
            "UPDATE maya_rp.factions SET pirate_group=$1 WHERE id=$2", group, faction_id)
        return group
    except Exception as e:
        _log("decision_models", f"group detect failed for {faction_id}: {e}")
        return DEFAULT_GROUP


async def log_decision(faction_id: int, model_name: str, inputs: dict,
                       predicted: str, probs: list | None = None,
                       group: str | None = None, session_id: int | None = None) -> None:
    """Append a row to ai_decision_log (retraining corpus). Never raises."""
    sid = session_id or Config.SESSION_ID
    try:
        name = await Database.fetchval(
            "SELECT name FROM maya_rp.factions WHERE id=$1", faction_id) or "unknown"
        tick = await Database.fetchval(
            "SELECT game_day FROM maya_rp.sessions WHERE id=$1", sid) or 0
        await Database.execute(
            "INSERT INTO maya_rp.ai_decision_log "
            "(session_id, faction_name, tick_number, decision_type, faction_id, model_name, inputs, predicted, probs, pirate_group, decided_at) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8,$9::jsonb,$10,NOW())",
            sid, name, tick, model_name, faction_id, model_name,
            json.dumps(inputs, ensure_ascii=False, default=str),
            predicted, json.dumps(probs or []), group)
    except Exception as e:
        _log("decision_models", f"log_decision failed: {e}")
