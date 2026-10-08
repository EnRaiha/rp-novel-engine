"""Voyage hidden-thread risk v2 tests — Izzat's act-driven model (2026-08-15).

Model: base danger 10-20%; run +30-50%; no guide +20%; prep/equip/knowledge
each -5%; cargo heat +5%. POSITIVE SIDE: clean arrivals pay cargo_value ×
margin to the treasury. The act determines both risk and reward.

DB-free: pure helpers only (danger, margin, outcome resolution).
"""
import math
import os
import random
from contextlib import asynccontextmanager

import pytest

from modules.voyage import (HIDDEN_THREAD_BASE_MIN, HIDDEN_THREAD_BASE_MAX,
                            HIDDEN_THREAD_NO_GUIDE_PCT, GRID_HOURS_PER_UNIT,
                            hidden_thread_danger, hidden_thread_margin,
                            hidden_thread_outcome, parse_coord, euclidean,
                            compute_travel)


# ── Danger model ─────────────────────────────────────────────────────────

def test_danger_base_band():
    rng = random.Random(1)
    for _ in range(200):
        d = hidden_thread_danger(rng=rng)
        assert HIDDEN_THREAD_BASE_MIN <= d <= HIDDEN_THREAD_BASE_MAX


def test_run_adds_30_to_50():
    rng = random.Random(2)
    base = hidden_thread_danger(rng=rng)
    rng = random.Random(2)
    run = hidden_thread_danger(act="run", rng=rng)
    assert 30 <= run - base <= 50


def test_no_guide_adds_20():
    rng = random.Random(3)
    with_g = hidden_thread_danger(has_guide=True, rng=rng)
    rng = random.Random(3)
    without = hidden_thread_danger(has_guide=False, rng=rng)
    assert without - with_g == HIDDEN_THREAD_NO_GUIDE_PCT


def test_prep_equip_knowledge_reduce_danger():
    rng = random.Random(4)
    naked = hidden_thread_danger(prep_level=0, equip_level=0, knowledge_level=0, rng=rng)
    rng = random.Random(4)
    geared = hidden_thread_danger(prep_level=3, equip_level=3, knowledge_level=3, rng=rng)
    assert geared < naked            # 9 levels × 5% → strictly lower
    assert geared >= 5               # clamp floor holds


def test_heat_increases_danger():
    rng = random.Random(5)
    cool = hidden_thread_danger(cargo_heat=0, rng=rng)
    rng = random.Random(5)
    hot = hidden_thread_danger(cargo_heat=3, rng=rng)
    assert hot >= cool + 10


def test_danger_clamps():
    rng = random.Random(6)
    assert hidden_thread_danger(act="run", has_guide=False, prep_level=0,
                                equip_level=0, knowledge_level=0, cargo_heat=3,
                                rng=rng) <= 95
    rng = random.Random(6)
    assert hidden_thread_danger(prep_level=3, equip_level=3, knowledge_level=3,
                                has_guide=True, rng=rng) >= 5


def test_danger_deterministic_with_seed():
    a = hidden_thread_danger(act="run", has_guide=False, rng=random.Random(7))
    b = hidden_thread_danger(act="run", has_guide=False, rng=random.Random(7))
    assert a == b


# ── Margin model (positive side) ─────────────────────────────────────────

def test_margin_base_band():
    rng = random.Random(8)
    # default (act='sneak' +0.10, has_guide +0.05) → 0.40-0.55 raw band
    for _ in range(200):
        m = hidden_thread_margin(rng=rng)
        assert 0.40 <= m <= 0.55


def test_margin_act_ordering():
    rng = random.Random(9)
    sneak = hidden_thread_margin(act="sneak", rng=rng)
    rng = random.Random(9)
    run = hidden_thread_margin(act="run", rng=rng)
    assert sneak > run  # sneak premium vs run discount


def test_margin_guide_and_gear_boost():
    rng = random.Random(10)
    bare = hidden_thread_margin(has_guide=False, prep_level=0, equip_level=0,
                                knowledge_level=0, rng=rng)
    rng = random.Random(10)
    full = hidden_thread_margin(has_guide=True, prep_level=3, equip_level=3,
                                knowledge_level=3, rng=rng)
    assert full > bare


def test_margin_heat_premium():
    rng = random.Random(11)
    cool = hidden_thread_margin(cargo_heat=0, rng=rng)
    rng = random.Random(11)
    hot = hidden_thread_margin(cargo_heat=3, rng=rng)
    assert hot > cool  # hotter cargo = bigger black-market premium


def test_margin_clamps():
    assert hidden_thread_margin(act="sneak", cargo_heat=3, prep_level=3,
                                equip_level=3, knowledge_level=3,
                                has_guide=True, rng=random.Random(12)) <= 0.95
    assert hidden_thread_margin(act="run", rng=random.Random(13)) >= 0.05


# ── Outcome resolution ───────────────────────────────────────────────────

def test_sneak_with_gear_slips_away():
    rng = random.Random(14)
    res = hidden_thread_outcome("sneak", True, 2, 2, 2, 100, rng)
    assert res["outcome"] == "slipped_away"
    assert res["chased"] is False
    assert 0 <= res["loss"] <= 5


def test_sneak_without_gear_caught():
    rng = random.Random(15)
    res = hidden_thread_outcome("sneak", False, 0, 0, 0, 100, rng)
    assert res["outcome"] == "caught"
    assert res["chased"] is True
    assert 10 <= res["loss"] <= 30


def test_run_chased_30_to_50():
    rng = random.Random(16)
    res = hidden_thread_outcome("run", True, 0, 0, 0, 100, rng)
    assert res["outcome"] == "chased_down"
    assert res["chased"] is True
    assert 30 <= res["loss"] <= 50


def test_bribe_buys_out():
    rng = random.Random(17)
    res = hidden_thread_outcome("bribe", True, 0, 0, 0, 100, rng)
    assert res["outcome"] == "bought_out"
    assert res["chased"] is False
    assert res["loss"] <= 5


def test_guard_fights():
    rng = random.Random(18)
    res = hidden_thread_outcome("guard", True, 0, 0, 0, 100, rng)
    assert res["outcome"] == "engaged"
    assert res["chased"] is True
    assert 10 <= res["loss"] <= 30


def test_zero_ships_min_loss():
    rng = random.Random(19)
    res = hidden_thread_outcome("run", False, 0, 0, 0, 0, rng)
    assert res["loss"] >= 1  # min 1 even on empty run


def test_parse_coord_z_aware():
    assert parse_coord("20,250,3") == (20.0, 250.0, 3.0)
    assert parse_coord("450-450-1") == (450.0, 450.0, 1.0)
    assert parse_coord("433-433") == (433.0, 433.0)


# ── XYZ coordinate system (2026-08-15) ───────────────────────────────────
# z planes: 2 = current map (mid), 1 = bottom veil, 3 = top veil.
# Gates are the ONLY legal z-crossings; hidden_thread lanes flag 'hidden'.

def test_parse_coord_3d_all_separators():
    assert parse_coord("10,20,3") == (10.0, 20.0, 3.0)          # comma
    assert parse_coord("10-20-1") == (10.0, 20.0, 1.0)          # dash
    assert parse_coord("10 x 20 x 2") == (10.0, 20.0, 2.0)      # x separator
    assert parse_coord("10, 20 , 3") == (10.0, 20.0, 3.0)       # spaces
    assert parse_coord("  -5.5, 12.25 , 1 ") == (-5.5, 12.25, 1.0)  # negatives+floats


def test_parse_coord_2d_vs_3d_shapes():
    two = parse_coord("433-433")
    three = parse_coord("433-433-2")
    assert two is not None and len(two) == 2
    assert three is not None and len(three) == 3
    assert two[0] == three[0] == two[1] == three[1] == 433.0
    assert three[2] == 2.0  # default z when given explicitly = mid plane


def test_parse_coord_2d_mixed_separators():
    assert parse_coord("10,20") == (10.0, 20.0)
    assert parse_coord("10-20") == (10.0, 20.0)
    assert parse_coord("10 x 20") == (10.0, 20.0)
    assert parse_coord("10, 20 ") == (10.0, 20.0)


def test_parse_coord_invalid():
    assert parse_coord(None) is None
    assert parse_coord("") is None
    assert parse_coord("  ") is None
    assert parse_coord("abc") is None
    assert parse_coord("10") is None            # single number
    assert parse_coord("10,20,30,40") is None   # too many dims
    assert parse_coord("a,b,c") is None
    assert parse_coord("10,,20") is None


def test_euclidean_uses_xy_only():
    # z must NOT affect planar distance — z is a separate layer axis
    assert euclidean((0, 0), (3, 4)) == 5.0
    assert euclidean((0, 0, 1), (3, 4, 3)) == 5.0   # same xy, z differs → same dist
    assert euclidean((1, 1), (1, 1)) == 0.0


async def _fake_gate_crossing_hidden(z1, z2, session_id=None):
    return {"name": "Ghost Thread ↔ Murk Thread", "distance": 12.0,
            "travel_time_hours": 30.0, "hidden": True, "lane_type": "hidden_thread",
            "toll_credits": 0, "pirate_density": 0.65}


async def _fake_gate_crossing_public(z1, z2, session_id=None):
    return {"name": "Aether Gate ↔ Upper Gate Anchor", "distance": 8.0,
            "travel_time_hours": 20.0, "hidden": False, "lane_type": "gate",
            "toll_credits": 25000, "pirate_density": 0.05}


async def test_compute_travel_same_z_no_gate(monkeypatch):
    # same z (2→2): plain euclidean, mode 'coord', NO gate_crossing call
    called = {"n": 0}
    async def boom(*a, **k):
        called["n"] += 1
        raise AssertionError("gate_crossing must not be called for same-z travel")
    monkeypatch.setattr("modules.voyage.gate_crossing", boom)
    r = await compute_travel(origin="0,0,2", destination="3,4,2")
    assert r["mode"] == "coord"
    assert r["distance_units"] == 5.0
    assert r["travel_days"] == 5.0 * GRID_HOURS_PER_UNIT / 24.0
    assert called["n"] == 0


async def test_compute_travel_z_crossing_routes_via_gate(monkeypatch):
    # z differs (2→3): gate_crossing called, travel time added, mode 'gate'
    monkeypatch.setattr("modules.voyage.gate_crossing", _fake_gate_crossing_public)
    r = await compute_travel(origin="20,250,3", destination="25,12,2")
    assert r["mode"] == "gate"
    assert r["via_gate"] == "Aether Gate ↔ Upper Gate Anchor"
    assert r["hidden"] is False
    planar = math.hypot(20 - 25, 250 - 12)          # √(5² + 238²)
    assert r["distance_units"] == pytest.approx(planar + 8.0)   # + gate distance
    assert r["travel_hours"] == pytest.approx(planar * GRID_HOURS_PER_UNIT + 20.0)


async def test_compute_travel_hidden_thread_flag(monkeypatch):
    # hidden_thread lane surfaces hidden=True → register() stores via_hidden
    monkeypatch.setattr("modules.voyage.gate_crossing", _fake_gate_crossing_hidden)
    r = await compute_travel(origin="450,450,3", destination="450,450,1")
    assert r["mode"] == "gate"
    assert r["hidden"] is True
    assert r["via_gate"] == "Ghost Thread ↔ Murk Thread"


async def test_compute_travel_mixed_2d_3d_no_gate(monkeypatch):
    # one side has z, other doesn't → can't cross-verify → plain coord mode
    called = {"n": 0}
    async def boom(*a, **k):
        called["n"] += 1
        raise AssertionError("gate_crossing must not fire when z missing")
    monkeypatch.setattr("modules.voyage.gate_crossing", boom)
    r = await compute_travel(origin="433-433", destination="433-433-2")
    assert r["mode"] == "coord"
    assert called["n"] == 0


async def test_compute_travel_ly_units_precedence(monkeypatch):
    # explicit ly/units beat coordinates entirely
    called = {"n": 0}
    async def boom(*a, **k):
        called["n"] += 1
        raise AssertionError("gate_crossing must not fire with explicit ly/units")
    monkeypatch.setattr("modules.voyage.gate_crossing", boom)
    r = await compute_travel(origin="0,0,3", destination="10,10,1", distance_ly=28400)
    assert r["mode"] == "ly"
    assert r["travel_days"] == 40.0           # canon anchor 28,400 ly / 710
    assert called["n"] == 0


# ── Gate tolls + pirate density (2026-08-15 Izzat canon) ─────────────────
# "The mainstream path by gate at Setia is the most used because it only has
# appropriate fair, less pirate, low risk." → gates: fair toll 25K, pirates 5%.
# Open lanes: standard 15%, hazardous 30%, unstable 45%; hidden 65%.

def test_gate_is_fair_highway():
    # gate: toll + low density; hidden: no toll + high density
    g = {"lane_type": "gate", "toll_credits": 25000, "pirate_density": 0.05}
    h = {"lane_type": "hidden_thread", "toll_credits": 0, "pirate_density": 0.65}
    assert g["toll_credits"] > h["toll_credits"]          # gate charges a fair toll
    assert g["pirate_density"] < h["pirate_density"]       # gate is safer
    assert g["pirate_density"] <= 0.10                      # "less pirate" = garrisoned


async def test_compute_travel_gate_carries_toll_and_density(monkeypatch):
    monkeypatch.setattr("modules.voyage.gate_crossing", _fake_gate_crossing_public)
    r = await compute_travel(origin="20,250,3", destination="25,12,2")
    assert r["lane_type"] == "gate"
    assert r["toll_credits"] == 25000
    assert r["pirate_density"] == 0.05


async def test_compute_travel_hidden_carries_no_toll_high_density(monkeypatch):
    monkeypatch.setattr("modules.voyage.gate_crossing", _fake_gate_crossing_hidden)
    r = await compute_travel(origin="450,450,3", destination="450,450,1")
    assert r["lane_type"] == "hidden_thread"
    assert r["toll_credits"] == 0
    assert r["pirate_density"] == 0.65


async def test_register_gate_setia_fleet_at_internal_cost(monkeypatch):
    """Izzat canon: Setia fleet uses gates FREE, AT INTERNAL COST — the cost
    is SMALLER than the public price (20% = 5,000C); the public price stays
    standardized at 25,000C via economy.gate_toll_income()."""
    import modules.voyage as voyage
    charged = []
    inserted = []

    class FakeConn:
        async def fetchval(self, sql, *args):
            if "UPDATE maya_rp.resources" in sql and "COALESCE(credits, 0) - $1" in sql:
                charged.append(args)
                return 1_000_000      # RETURNING credits: the debit found a row with funds
            if "INSERT INTO maya_rp.voyages" in sql:
                inserted.append(args)
                return 42
            return None

        async def execute(self, sql, *args):
            return "OK"

        async def fetch(self, sql, *args):
            return []

        async def fetchrow(self, sql, *args):
            return None

    @asynccontextmanager
    async def transaction():
        yield FakeConn()

    async def fetchval(sql, *args):
        return 100 if "game_day" in sql else None
    async def fetchrow(sql, *args):
        return None   # compute_travel path: coords only
    monkeypatch.setattr(voyage.Database, "fetchval", fetchval)
    monkeypatch.setattr(voyage.Database, "fetchrow", fetchrow)
    monkeypatch.setattr(voyage.Database, "transaction", transaction)
    monkeypatch.setattr(voyage, "gate_crossing", _fake_gate_crossing_public)
    r = await voyage.register("Free Gate Test", "20,250,3", "25,12,2",
                              ship_count=10, fleet_tag="TEST", session_id=900 + os.getpid() % 100)
    assert r["lane_type"] == "gate"
    # internal cost is SMALLER than the public price
    assert r["toll_paid"] == 25000 * 0.20           # 5,000C internal share
    assert r["toll_paid"] < 25000
    # treasury cost is booked (Setia fleet free to use, treasury pays smaller)
    assert r["toll_charged"] is True, r
    assert [a[0] for a in charged] == [5000], f"the treasury debit was not the internal share: {charged}"
    assert len(inserted) == 1, "the voyage row was not inserted in the same transaction"
