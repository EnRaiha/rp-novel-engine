#!/usr/bin/env python3
"""Faction stance — one deterministic model per faction.

Same row in, same answer out. No random, no sampling, no black box, no LLM.
Every weight is listed in `WEIGHTS` below so the King can audit and move them.

    python3 scripts/faction_stance.py            # compute and store
    python3 scripts/faction_stance.py --show 12  # show the top rows

The engine already runs learned pirate models in `core/decision_models.py` (sklearn
pickles with per-group biases, logged to `ai_decision_log` for retraining). This is
the deterministic half that covers **every** faction, not only pirates: a linear
score over the five axes plus the state columns, then a band.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

# ── the model ────────────────────────────────────────────────────────────
# sign * weight per feature. trust and reputation pull toward friendship;
# aggression and piracy pull away; doctrine and origin nudge.
WEIGHTS = {
    "trust": +0.30,                # 0-100
    "reputation": +0.10,           # 0-100
    "fear_of_player": -0.15,       # 0-100, fear is not friendship
    "trade_aggressiveness": -0.20,  # 0-1
    "pirate_aggressiveness": -0.25,  # 0-1
    "is_pirate": -0.40,            # bool
    "doctrine:science_tech": +0.05,
    "doctrine:magic": 0.00,
    "doctrine:balance": +0.10,
    "doctrine:unaligned": -0.05,
    "origin:natural": +0.10,
    "origin:imposed": +0.05,
    "origin:sponsored": -0.10,
    # standing is the most direct signal in the row; without it a hired pirate
    # that the crown already counts as allied scores hostile.
    "standing:kingdom": +0.35, "standing:friendly": +0.40, "standing:allied": +0.60,
    "standing:neutral": 0.00, "standing:suspicious": -0.20, "standing:hostile": -0.55,
    "standing:unknown": -0.10,
}
BANDS = ((-0.45, "hostile"), (-0.15, "wary"), (0.15, "neutral"), (0.45, "friendly"), (1.01, "allied"))


def _fraction(value) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.5


def _hundredth(value) -> float:
    try:
        return max(0.0, min(1.0, float(value) / 100.0))
    except (TypeError, ValueError):
        return 0.5


def stance(faction: dict) -> dict:
    """Deterministic stance for one faction row.

    @param faction - a mapping with the axis and state columns.
    @returns score in -1..1 and the band it falls in. Pure: no I/O, no RNG.
    """
    score = 0.0
    score += WEIGHTS["trust"] * _hundredth(faction.get("trust"))
    score += WEIGHTS["reputation"] * _hundredth(faction.get("reputation"))
    score += WEIGHTS["fear_of_player"] * _hundredth(faction.get("fear_of_player"))
    score += WEIGHTS["trade_aggressiveness"] * _fraction(faction.get("trade_aggressiveness"))
    score += WEIGHTS["pirate_aggressiveness"] * _fraction(faction.get("pirate_aggressiveness"))
    if faction.get("is_pirate"):
        score += WEIGHTS["is_pirate"]
    score += WEIGHTS.get("doctrine:" + str(faction.get("doctrine") or "unaligned"), 0.0)
    score += WEIGHTS.get("origin:" + str(faction.get("origin") or "imposed"), 0.0)
    score += WEIGHTS.get("standing:" + str(faction.get("standing") or "unknown"), 0.0)
    score = round(max(-1.0, min(1.0, score / 0.75)), 4)
    band = next(name for edge, name in BANDS if score < edge)
    return {"score": score, "band": band}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--show", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    import psycopg2

    env = pathlib.Path.home() / ".env"
    if env.is_file() and not os.environ.get("OC_PG_HOST"):
        for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, _, value = line.partition("=")
                key = key.removeprefix("export ").strip()
                if key.startswith(("OC_PG_", "POSTGRES_")) and key not in os.environ:
                    os.environ[key] = value.strip().strip("'\"")

    conn = psycopg2.connect(
        host=os.environ["OC_PG_HOST"], port=int(os.environ.get("OC_PG_PORT", 5432)),
        user=os.environ["OC_PG_USER"], password=os.environ["OC_PG_PASS"],
        dbname=os.environ.get("OC_PG_DB", "maya_memory"))
    cur = conn.cursor()
    cur.execute("""SELECT id, session_id, name, standing, trust, fear_of_player, reputation,
                          trade_aggressiveness, pirate_aggressiveness, is_pirate, doctrine, origin
                   FROM maya_rp.factions ORDER BY session_id, id""")
    columns = ("id", "session_id", "name", "standing", "trust", "fear_of_player", "reputation",
               "trade_aggressiveness", "pirate_aggressiveness", "is_pirate", "doctrine", "origin")
    rows = [dict(zip(columns, row)) for row in cur.fetchall()]
    results = [(row, stance(row)) for row in rows]

    if args.show:
        for row, verdict in results[: args.show]:
            print(f"{row['name'][:30]:<30} {verdict['band']:<9} {verdict['score']:+.3f}  "
                  f"doc={row['doctrine']} origin={row['origin']}")
    if args.dry_run:
        print(f"computed {len(results)} factions, nothing written")
        return 0

    now = datetime.now(timezone.utc)
    for row, verdict in results:
        cur.execute("""UPDATE maya_rp.factions SET stance=%s, stance_score=%s, stance_at=%s
                       WHERE id=%s""", (verdict["band"], verdict["score"], now, row["id"]))
    conn.commit()
    bands: dict[str, int] = {}
    for _, verdict in results:
        bands[verdict["band"]] = bands.get(verdict["band"], 0) + 1
    print(f"stance written for {len(results)} factions: " + json.dumps(bands))
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
