"""Tick-path unit tests — pure logic of economy/market/war/decision layers
(added 2026-08-14 as part of the ML/module review "do all" pass).

DB-free: these exercise the pure helpers the ticks delegate to.
"""
import random

import pytest

from modules.market import next_price, SEED_COMMODITIES
from modules.tactics import formation_bonus, roll_terrain
from core.decision_models import (PIRATE_GROUPS, POLICY_BIAS, SURVIVAL_BIAS,
                                  event_features, predict_pirate_policy,
                                  predict_pirate_survival)


class _RNG:
    """Deterministic rng stub for next_price tests."""
    def __init__(self, value=0.0):
        self.value = value

    def uniform(self, a, b):
        return self.value * (b - a) + a


# ── Market ───────────────────────────────────────────────────────────────

def test_market_seeds_13_commodities():
    assert len(SEED_COMMODITIES) == 13


def test_market_price_clamps_to_bounds():
    rng = _RNG(0.5)  # neutral noise
    p = next_price(base=10.0, current=10.0, volatility=1.0, supply=0, demand=1000000, rng=rng)
    assert p <= 10.0 * 2.0 and p >= 10.0 * 0.5


def test_market_demand_drives_price_up():
    rng = _RNG(0.0)
    p1 = next_price(10.0, 10.0, 0.1, supply=1000, demand=9000, rng=rng)   # shortage
    p2 = next_price(10.0, 10.0, 0.1, supply=9000, demand=1000, rng=rng)   # glut
    assert p1 > p2


# ── Tactics ──────────────────────────────────────────────────────────────

def test_formation_bonus_known_and_unknown():
    assert formation_bonus("wedge") == 1.15
    assert formation_bonus("line") == 1.0
    assert formation_bonus("nonsense") == 1.0


def test_roll_terrain_returns_modifier():
    t = roll_terrain()
    assert "name" in t and "player_mod" in t


# ── Decision models (rule fallback path — no sklearn dependency in tests) ─

def test_pirate_groups_defined():
    assert set(PIRATE_GROUPS) == {"free", "sponsor", "hired"}


def test_policy_rule_fallback_per_group():
    free = predict_pirate_policy("free", "ai_policy", "STANDARD UNIFORMITY", "clean_crew", "check_first")
    sponsor = predict_pirate_policy("sponsor", "ai_policy", "STANDARD UNIFORMITY", "clean_crew", "check_first")
    hired = predict_pirate_policy("hired", "ai_policy", "STANDARD UNIFORMITY", "clean_crew", "check_first")
    assert free["class"] and sponsor["class"] and hired["class"]
    assert free["source"].startswith(("ml:", "rules:"))


def test_survival_rule_fallback_per_group():
    for g in PIRATE_GROUPS:
        r = predict_pirate_survival(g, 0, 0.5, "queen_offers_alliance")
        assert r["class"] in {"den_surrenders", "hostage_trade", "pirate_crew_captured",
                              "pirate_king_captured", "pirate_queen_captured",
                              "queen_offers_alliance", "relic_offer", "tender_of_alliance"}


def test_biases_defined_for_all_groups():
    for g in PIRATE_GROUPS:
        assert POLICY_BIAS[g], f"missing policy bias for {g}"
        assert SURVIVAL_BIAS[g], f"missing survival bias for {g}"


def test_event_features_shape():
    feats = event_features({"event_type": "battle", "tags": ["war", "x"],
                            "happened_at": "2026-08-14T09:00:00+08:00"})
    assert len(feats) == 4
    assert all(isinstance(x, float) for x in feats)
