"""Roll Theater tests — outcome tiers, telegram dice, pool odds (2026-08-14)."""
from modules.roll_theater import (tier_of, parse_telegram_dice, pool_odds,
                                  flavor, memorial_name, DEFAULT_FLAVOR)


def test_tier_boundaries():
    assert tier_of(1, 70) == "fumble"          # absolute fumble ≤5
    assert tier_of(30, 70) == "fumble"         # dc-40 boundary inclusive
    assert tier_of(31, 70) == "fail"
    assert tier_of(50, 70) == "partial"        # dc-20 ≤ x < dc
    assert tier_of(69, 70) == "partial"
    assert tier_of(70, 70) == "success"
    assert tier_of(100, 70) == "crit"          # absolute crit ≥96
    assert tier_of(80, 50) == "crit"           # +30 over DC (80 ≥ 50+30)
    assert tier_of(75, 50) == "success"        # +25 over DC — not crit
    assert tier_of(5, 70) == "fumble"          # ≤5 wins over partial math


def test_telegram_dice_bands():
    assert 1 <= parse_telegram_dice(1) <= 5
    assert 96 <= parse_telegram_dice(6) <= 100
    assert 6 <= parse_telegram_dice(2) <= 40
    # out-of-range clamps
    assert 96 <= parse_telegram_dice(99) <= 100


def test_pool_odds_direction():
    assert "against" in pool_odds(0.20)   # hot king → house fades him
    assert "on the King" in pool_odds(0.01)
    assert "1:1" in pool_odds(0.08)


def test_flavor_deterministic_per_domain():
    for domain in ("battle", "craft", "romance", "diplomacy", "travel",
                   "social", "mystery", "pirate", "economy"):
        a = flavor(domain, "crit", 7)
        b = flavor(domain, "crit", 7)
        assert a == b and a != ""


def test_flavor_fallback_for_unknown_domain():
    f = flavor("unknown_domain", "crit", 3)
    assert f in DEFAULT_FLAVOR["crit"]


def test_memorial_names_include_domain_word():
    name = memorial_name("craft", 100)
    assert "Forge" in name
    name2 = memorial_name("craft", 1)
    assert "Forge" in name2
