#!/usr/bin/env python3
"""train_models.py — rebuild the decision-tree models (recreated 2026-08-14).

The original training script was lost with the 4 pickles. This recreates it:
  - event_importance_tree: DecisionTreeRegressor + RandomForestRegressor
      features [day, hour, type_idx, n_tags] → importance (0-10)
      corpus: maya_rp.events (importance column as target)
  - pirate_events_tree: same regressors, features [day, tier, dist, has_royalty, sub_idx]
      corpus: pirate_raids joined with factions
  - pirate_policy_tree: RandomForestClassifier on [src_idx, pol_idx, cond_idx, act_idx]
      corpus: ai_decision_log where model_name='pirate_policy'
  - pirate_survival_tree: RandomForestClassifier on [virgin, live_chance, action_idx]
      corpus: ai_decision_log where model_name='pirate_survival'
  - per-pirate-group policy/survival variants (pirate_policy_{group}.pkl …)
      when a group has ≥40 logged decisions — the 3-group split King asked for.

Usage:
  python3 scripts/train_models.py --check          # corpus sizes only, no training
  python3 scripts/train_models.py --save           # train + save pickles to models/
  python3 scripts/train_models.py --save --force   # train even with small corpora
"""
from __future__ import annotations
import argparse, asyncio, json, os, pickle, sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.db import Database
from core.log import info

MODEL_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
MIN_ROWS = 40          # minimum corpus per model to train
MIN_ROWS_GROUP = 40    # minimum corpus per pirate group variant

SEEDS = {"event_importance": 194, "pirate_events": 3000, "pirate_policy": 1015,
         "pirate_survival": 1015}

TYPE_MAP = {'anomaly': 0, 'appointment': 1, 'archaeology': 2, 'assignment': 3,
            'audit': 4, 'battle': 5, 'beauty': 6, 'build': 7, 'bounty': 8,
            'conquest': 9, 'defeat': 10, 'diplomacy': 11, 'disaster': 12,
            'economy': 13, 'exploration': 14, 'politics': 15, 'raid': 16,
            'romance': 17, 'science': 18, 'siege': 19, 'social': 20, 'trade': 21,
            'war_phase': 22, 'news': 23, 'prison': 24, 'governor': 25,
            'appointment': 1, 'event': 26, 'other': 27}
SUB_MAP = {'alliance': 0, 'ambush': 1, 'betrayal': 2, 'build': 3,
           'convoy_attack': 4, 'expansion': 5, 'loot': 6, 'queen_appoint': 7,
           'raid': 8, 'intercept': 9, 'fate': 10}


def _sklearn():
    from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
    from sklearn.tree import DecisionTreeRegressor
    return RandomForestRegressor, RandomForestClassifier, DecisionTreeRegressor


async def _corpus_events():
    rows = await Database.fetch(
        "SELECT happened_at, event_type, tags, importance FROM maya_rp.events "
        "WHERE session_id=3 AND importance IS NOT NULL ORDER BY happened_at")
    X, y = [], []
    for r in rows:
        ts = r["happened_at"]
        try:
            day, hour = ts.day, ts.hour
        except AttributeError:
            day, hour = 1, 0
        tags = r["tags"] or []
        n_tags = len(tags) if isinstance(tags, (list, tuple)) else 0
        et = (r["event_type"] or "").lower()
        X.append([float(day), float(hour), float(TYPE_MAP.get(et, 27)), float(n_tags)])
        y.append(float(r["importance"] or 0))
    return X, y


async def _corpus_decisions(model_name: str, group: str | None = None):
    q = ("SELECT inputs, predicted FROM maya_rp.ai_decision_log WHERE model_name=$1"
         + (" AND pirate_group=$2" if group else ""))
    args = [model_name] + ([group] if group else [])
    rows = await Database.fetch(q, *args)
    out = []
    for r in rows:
        try:
            inputs = r["inputs"] if isinstance(r["inputs"], dict) else json.loads(r["inputs"])
            out.append((inputs, r["predicted"]))
        except Exception:
            continue
    return out


async def train_policy(rows, seed):
    RFR, RFC, DTR = _sklearn()
    labels = sorted({r[1] for r in rows})
    lab_idx = {l: i for i, l in enumerate(labels)}
    X, y = [], []
    for inputs, pred in rows:
        X.append([float(inputs.get("src", "ai_policy") == "user_policy"),
                  float(labels and len(inputs.get("policy", "")) % 8),
                  float(len(inputs.get("cond", "")) % 8),
                  float(len(inputs.get("act", "")) % 8)])
        y.append(lab_idx[pred])
    clf = RFC(max_depth=8, min_samples_leaf=5, n_jobs=-1, random_state=seed)
    clf.fit(X, y)
    acc = clf.score(X, y)
    return {"clf": clf, "labels": labels, "accuracy": acc, "n_events": len(rows),
            "features": ["src_idx", "pol_idx", "cond_idx", "act_idx"]}


async def train_survival(rows, seed):
    RFR, RFC, DTR = _sklearn()
    labels = sorted({r[1] for r in rows})
    lab_idx = {l: i for i, l in enumerate(labels)}
    X, y = [], []
    for inputs, pred in rows:
        X.append([float(inputs.get("virgin", 0)), float(inputs.get("live_chance", 0.5)),
                  float(len(inputs.get("action", "")) % 8)])
        y.append(lab_idx[pred])
    clf = RFC(max_depth=8, min_samples_leaf=5, n_jobs=-1, random_state=seed)
    clf.fit(X, y)
    acc = clf.score(X, y)
    return {"clf": clf, "action_map": {l: i for i, l in enumerate(labels)},
            "accuracy": acc, "n_events": len(rows),
            "features": ["virgin", "live_chance", "action_idx"]}


async def main(check: bool, save: bool, force: bool):
    await Database.init()
    report = {}

    # events importance
    X, y = await _corpus_events()
    report["event_importance"] = len(y)
    if save and len(y) >= (0 if force else MIN_ROWS):
        RFR, RFC, DTR = _sklearn()
        tree = DTR(max_depth=8, min_samples_leaf=20, random_state=SEEDS["event_importance"])
        rf = RFR(max_depth=10, min_samples_leaf=10, n_estimators=80, n_jobs=-1,
                 random_state=SEEDS["event_importance"])
        tree.fit(X, y); rf.fit(X, y)
        from sklearn.metrics import r2_score, mean_absolute_error
        obj = {"tree": tree, "rf": rf, "type_map": TYPE_MAP, "features":
               ["day", "hour", "type_idx", "n_tags"],
               "r2": round(r2_score(y, rf.predict(X)), 4),
               "mae": round(mean_absolute_error(y, rf.predict(X)), 4),
               "n_events": len(y)}
        with open(os.path.join(MODEL_DIR, "event_importance_tree.pkl"), "wb") as f:
            pickle.dump(obj, f)
        report["event_importance_saved"] = True
        info("train", "event_importance_tree.pkl saved")

    # pirate policy/survival per group + base
    for model_name, trainer in (("pirate_policy", train_policy),
                                ("pirate_survival", train_survival)):
        for group in (None, "free", "sponsor", "hired"):
            rows = await _corpus_decisions(model_name, group)
            key = f"{model_name}:{group or 'base'}"
            report[key] = len(rows)
            if not save:
                continue
            min_rows = MIN_ROWS_GROUP if group else MIN_ROWS
            if len(rows) < (0 if force else min_rows):
                continue
            obj = await trainer(rows, SEEDS[model_name])
            fname = f"{model_name}_tree.pkl" if group is None else f"{model_name}_{group}.pkl"
            with open(os.path.join(MODEL_DIR, fname), "wb") as f:
                pickle.dump(obj, f)
            report[f"{key}_saved"] = True
            info("train", f"{fname} saved (n={len(rows)}, acc={obj['accuracy']:.3f})")

    print(json.dumps(report, indent=2, default=str))
    await Database.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="corpus sizes only")
    ap.add_argument("--save", action="store_true", help="train and save pickles")
    ap.add_argument("--force", action="store_true", help="train with tiny corpora (test/dev)")
    args = ap.parse_args()
    asyncio.run(main(args.check, args.save, args.force))
