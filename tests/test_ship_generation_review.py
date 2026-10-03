"""Module review tests for modules/ship_generation.py.

Defects covered:

1. `parse_slots` dropped a token it could not read, in silence. Five live ship
   classes carry specs it cannot parse — "8" (Artillery Cruiser), "300"
   (Starforged), "30" (Portal Ship), "0" (EDEN), "M" (Phantom EW Cruiser) — so
   four of them generated with NO WEAPONS AT ALL and nothing said so. Unread
   tokens are named now.
2. A bare size with no count is one mount: "M" gave nothing before, and there is
   no other reading of that token in a format where every other token is
   "<count><size>".
3. `roll_modules(sc["module_slots"], …)` raised TypeError on a NULL slot count.
   The column has no NULL today, so the guard is defensive.
4. `TYPE_MULTIPLIERS.get(ship_type, 1.0)` gave an unrecognised variant a silent
   1.0. The result reports whether the named code did anything.
5. `generate_batch` accepted a negative count.

Checked and found correct: the catalogue reads (ship_classes, weapons, modules)
are global tables with no session of their own; a weapon pool that matches no
slot falls back to the shorter sizes before giving up; sampling inside a size
group draws without replacement and refills only when exhausted; modules are
picked one per category at the highest grade first; and the cost is built from
the modules plus a mass- and tier-scaled hull charge.

No database: every test drives a fake Database or a pure helper.
"""
from __future__ import annotations

import pytest

import modules.ship_generation as gen


class FakeDB:
    def __init__(self, rows=None):
        self.row_map = rows or {}
        self.calls = []

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", " ".join(sql.split()), args))
        for marker, value in self.row_map.items():
            if marker in sql:
                return value
        return None

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", " ".join(sql.split()), args))
        for marker, value in self.row_map.items():
            if marker in sql:
                return value
        return []


def _install(monkeypatch, fake):
    for name in ("fetchrow", "fetch"):
        monkeypatch.setattr("modules.ship_generation.Database." + name, getattr(fake, name))
    return fake


SHIP_CLASS = {"id": 16, "class_name": "Artillery Cruiser", "category": "military",
              "base_mass": 900_000, "base_length": 800, "base_crew": 300,
              "base_hull": 50_000, "base_speed": 40, "module_slots": 2,
              "weapon_slots": "2XH 2H 4M", "scale_factor": 1.15, "special_rules": None}


# ── 1 + 2. The slot parser ──────────────────────────────────────────────

def test_a_normal_spec_parses_into_size_and_count():
    assert gen.parse_slots("2XH 2H 4M") == [("XH", 2), ("H", 2), ("M", 4)]


def test_a_bare_size_is_one_mount():
    assert gen.parse_slots("M") == [("M", 1)]
    assert gen.parse_slots("2XH H") == [("XH", 2), ("H", 1)]


def test_an_empty_or_none_spec_has_no_slots():
    assert gen.parse_slots("") == []
    assert gen.parse_slots(None) == []
    assert gen.parse_slots("none") == []


def test_a_zero_count_is_read_as_zero_mounts():
    assert gen.parse_slots("0H") == [("H", 0)]


@pytest.mark.parametrize("spec,unread", [
    ("8", "8"),
    ("300", "300"),
    ("30 2H", "30"),
])
def test_an_unreadable_token_is_named_not_dropped(monkeypatch, spec, unread):
    seen = []
    monkeypatch.setattr("modules.ship_generation.info", lambda mod, msg: seen.append(msg))

    slots = gen.parse_slots(spec)

    assert any(unread in m for m in seen), seen
    assert all(size in ("WMD", "SH", "XH", "H", "M", "L") for size, _ in slots), slots


def test_the_live_unreadable_specs_are_exactly_the_ones_we_know(monkeypatch):
    seen = []
    monkeypatch.setattr("modules.ship_generation.info", lambda mod, msg: seen.append(msg))

    for spec in ("8", "300", "30", "0", "M"):
        gen.parse_slots(spec)

    # "M" is readable now (one mount); the four that are not are named
    assert len(seen) == 4, seen
    assert sum("M" in m for m in seen) == 0, seen


# ── 3. A NULL slot count cannot crash the roll ──────────────────────────

def test_a_null_module_slot_count_yields_no_modules():
    assert gen.roll_modules(None or 0, [{"id": 1, "name": "A", "category": "c", "grade": 1,
                                         "effect_type": "e", "effect_value": 1.0,
                                         "cost_alloys": 0, "cost_credits": 0}]) == []


async def test_generate_ship_survives_a_null_slot_count(monkeypatch):
    sc = dict(SHIP_CLASS, module_slots=None)
    # The pool must be non-empty: an empty one returns before the slot count is
    # ever compared, which is what hid this on the first pass.
    pool = [{"id": 1, "name": "A", "category": "shield", "grade": 1, "effect_type": "e",
             "effect_value": 1.0, "cost_alloys": 0, "cost_credits": 0}]
    _install(monkeypatch, FakeDB(rows={"ship_classes": sc, "weapons": [], "modules": pool}))

    out = await gen.generate_ship("Artillery Cruiser", 3, "HRO", "Test", 5)

    assert out["modules"] == []


# ── 4. The variant code is reported ─────────────────────────────────────

async def test_a_known_variant_applies_its_multiplier(monkeypatch):
    _install(monkeypatch, FakeDB(rows={"ship_classes": SHIP_CLASS, "weapons": [], "modules": []}))

    out = await gen.generate_ship("Artillery Cruiser", 3, "MYT", "Test", 5)

    assert out["type_recognised"] is True
    assert out["type_multiplier"] == gen.TYPE_MULTIPLIERS["MYT"] == 1.5


async def test_an_unknown_variant_is_flagged(monkeypatch):
    _install(monkeypatch, FakeDB(rows={"ship_classes": SHIP_CLASS, "weapons": [], "modules": []}))

    out = await gen.generate_ship("Artillery Cruiser", 3, "frigate", "Test", 5)

    assert out["type_recognised"] is False
    assert out["type_multiplier"] == 1.0


async def test_an_unknown_class_is_answered_not_crashed(monkeypatch):
    _install(monkeypatch, FakeDB(rows={}))

    out = await gen.generate_ship("No Such Hull", 3, "HRO", "Test", 5)

    assert "not found" in out["error"]


# ── 5. The batch ────────────────────────────────────────────────────────

async def test_a_negative_batch_count_is_refused(monkeypatch):
    fake = _install(monkeypatch, FakeDB(rows={}))

    with pytest.raises(ValueError, match="count cannot be negative"):
        await gen.generate_batch("Artillery Cruiser", 3, "HRO", -2)

    assert not fake.calls


async def test_a_batch_names_its_ships_when_it_is_given_a_prefix(monkeypatch):
    fake = _install(monkeypatch, FakeDB(rows={"ship_classes": SHIP_CLASS, "weapons": [], "modules": []}))

    out = await gen.generate_batch("Artillery Cruiser", 3, "HRO", 2, prefix="Lance", session_id=5)

    assert [s["name"] for s in out] == ["Lance 1", "Lance 2"]


# ── Contract the module claims ──────────────────────────────────────────

def test_contract_the_tier_multiplier_compounds_with_tier():
    assert gen.tier_mult(1) == 1.0
    assert gen.tier_mult(2) == pytest.approx(1.15)
    assert gen.tier_mult(3) == pytest.approx(1.15 ** 2)
    assert gen.tier_mult(0) == 1.0          # below tier 1 there is nothing to scale


def test_contract_a_roll_stays_inside_its_variance_band():
    for _ in range(50):
        value = gen.roll_stat(1000, 3, 1.15, 0.10)
        assert 1000 * 1.15 ** 2 * 0.9 <= value <= 1000 * 1.15 ** 2 * 1.1


def test_contract_weapons_fill_every_mount_they_can(monkeypatch):
    pool = [{"id": i, "name": f"W{i}", "kind": "kinetic", "slot_size": "M",
             "damage": 10, "range_m": 100} for i in range(4)]
    armaments = gen.roll_weapons([("M", 4)], pool)

    assert len(armaments) == 4
    assert {a["weapon_id"] for a in armaments} == {0, 1, 2, 3}


def test_contract_a_mount_with_no_weapon_is_skipped_not_invented(monkeypatch):
    armaments = gen.roll_weapons([("WMD", 2)], [])

    assert armaments == []


def test_contract_modules_are_one_per_category_at_the_highest_grade():
    pool = [{"id": 1, "name": "A", "category": "shield", "grade": 3, "effect_type": "e",
             "effect_value": 1.0, "cost_alloys": 0, "cost_credits": 0},
            {"id": 2, "name": "B", "category": "shield", "grade": 1, "effect_type": "e",
             "effect_value": 1.0, "cost_alloys": 0, "cost_credits": 0},
            {"id": 3, "name": "C", "category": "engine", "grade": 2, "effect_type": "e",
             "effect_value": 1.0, "cost_alloys": 0, "cost_credits": 0}]

    picked = gen.roll_modules(2, pool)

    assert [m["module_id"] for m in picked] == [1, 3]
    assert [m["category"] for m in picked] == ["shield", "engine"]
