"""Void-crossing module tests — inter-nebular travel (2026-08-15).

"Crossing the void" = traveling BETWEEN nebulas (z-planes) without a gate.
A ship needs a VOID DRIVE; Nebular Ward cuts the risk; travel is fast
(12h/u vs 24h/u standard) but hazard is base 20%.

DB-free: pure math + monkeypatched Database for the async resolvers.
"""
import pytest

from modules.ship_modules import (VOID_HOURS_PER_UNIT, VOID_BASE_RISK_PCT,
                                  install_module, list_modules,
                                  fleet_void_capable, void_crossing_cost)


def test_void_hours_faster_than_standard():
    assert VOID_HOURS_PER_UNIT < 24.0        # void is the fast lane
    assert VOID_HOURS_PER_UNIT == 12.0


def test_void_base_risk_sane():
    assert 10 <= VOID_BASE_RISK_PCT <= 35    # risky but not suicide


async def test_fleet_void_capable_no_fleet(monkeypatch):
    async def fetch(sql, *args):
        return []
    monkeypatch.setattr("modules.ship_modules.Database.fetch", fetch)
    r = await fleet_void_capable(None)
    assert r == {"capable": False, "ships": 0, "drive_ships": 0,
                 "drive_names": []}


async def test_fleet_void_capable_detects_drive(monkeypatch):
    rows = [
        {"id": 1, "name": "Maw-1", "sub_class": "Dreadnought", "tier": 10, "has_drive": True},
        {"id": 2, "name": "Maw-2", "sub_class": "Dreadnought", "tier": 10, "has_drive": False},
    ]
    async def fetch(sql, *args):
        return rows
    monkeypatch.setattr("modules.ship_modules.Database.fetch", fetch)
    r = await fleet_void_capable("SEF-3 Silent Maw")
    assert r["capable"] is True
    assert r["ships"] == 2
    assert r["drive_ships"] == 1
    assert r["drive_names"] == ["Maw-1"]


async def test_install_module_tier_gate(monkeypatch):
    async def fetchrow(sql, *args):
        if "ship_classes" in sql:
            return {"id": 1, "name": "Corvette-1", "tier": 1,
                    "sub_class": "Corvette", "module_slots": 2}
        return {"id": 45, "name": "Void Drive", "category": "void",
                "tier_min": 4, "tier_max": 8, "effect_value": 1}
    monkeypatch.setattr("modules.ship_modules.Database.fetchrow", fetchrow)
    with pytest.raises(ValueError, match="tier"):
        await install_module(1, "Void Drive")   # tier 1 corvette can't fit T4 module


async def test_install_module_no_slots(monkeypatch):
    async def fetchrow(sql, *args):
        if "ship_classes" in sql:
            return {"id": 2, "name": "Big Ship", "tier": 6,
                    "sub_class": "Cruiser", "module_slots": 0}
        return {"id": 46, "name": "Nebular Ward", "category": "void",
                "tier_min": 3, "tier_max": 8, "effect_value": 20}
    async def fetchval(sql, *args):
        return 0
    monkeypatch.setattr("modules.ship_modules.Database.fetchrow", fetchrow)
    monkeypatch.setattr("modules.ship_modules.Database.fetchval", fetchval)
    with pytest.raises(ValueError, match="no free module slots"):
        await install_module(2, "Nebular Ward")


async def test_install_module_duplicate_blocked(monkeypatch):
    # ship lookup → module lookup → duplicate check returns a row
    calls = {"n": 0}
    async def fetchrow(sql, *args):
        calls["n"] += 1
        if calls["n"] == 1:   # ship
            return {"id": 3, "name": "Warship", "tier": 6,
                    "sub_class": "Cruiser", "module_slots": 4}
        if calls["n"] == 2:   # module
            return {"id": 45, "name": "Void Drive", "category": "void",
                    "tier_min": 4, "tier_max": 8, "effect_value": 1}
        return {"id": 7}      # duplicate exists
    async def fetchval(sql, *args):
        return 1             # 1 slot used
    monkeypatch.setattr("modules.ship_modules.Database.fetchrow", fetchrow)
    monkeypatch.setattr("modules.ship_modules.Database.fetchval", fetchval)
    with pytest.raises(ValueError, match="already fitted"):
        await install_module(3, "Void Drive")


async def test_install_module_success(monkeypatch):
    calls = {"n": 0, "val": []}
    async def fetchrow(sql, *args):
        calls["n"] += 1
        if calls["n"] == 1:   # ship
            return {"id": 4, "name": "Maw-1", "tier": 10,
                    "sub_class": "Dreadnought", "module_slots": 4}
        if calls["n"] == 2:   # module
            return {"id": 45, "name": "Void Drive", "category": "void",
                    "tier_min": 4, "tier_max": 12, "effect_value": 1}
        return None           # no duplicate
    async def fetchval(sql, *args):
        calls["val"].append(sql)
        if "count" in sql:
            return 1          # 1 slot used
        return 10             # insert RETURNING id
    monkeypatch.setattr("modules.ship_modules.Database.fetchrow", fetchrow)
    monkeypatch.setattr("modules.ship_modules.Database.fetchval", fetchval)
    r = await install_module(4, "Void Drive")
    assert r["module"] == "Void Drive"
    assert r["ship"] == "Maw-1"
    assert r["slot"] == 2


async def test_void_crossing_requires_drive(monkeypatch):
    async def fetch(sql, *args):
        if "effect_type='void_resist'" in sql:
            return []
        return []
    monkeypatch.setattr("modules.ship_modules.Database.fetch", fetch)
    with pytest.raises(ValueError, match="No Void Drive"):
        await void_crossing_cost(3, 1, "Legion Vanguard")


async def test_void_crossing_risk_with_ward(monkeypatch):
    async def fetch(sql, *args):
        if "effect_type='void_resist'" in sql:
            return [{"effect_value": 20, "grade": 2}]
        return [
            {"id": 1, "name": "Maw-1", "sub_class": "Dreadnought",
             "tier": 10, "has_drive": True},
        ]
    monkeypatch.setattr("modules.ship_modules.Database.fetch", fetch)
    r = await void_crossing_cost(3, 1, "SEF-3 Silent Maw")
    assert r["capable"] is True
    assert r["risk_pct"] == max(5, VOID_BASE_RISK_PCT - 20)   # ward cuts risk
    assert r["hours_per_unit"] == VOID_HOURS_PER_UNIT
    assert r["z1"] == 3 and r["z2"] == 1


async def test_list_modules_returns_fitted(monkeypatch):
    async def fetch(sql, *args):
        return [{"name": "Void Drive", "category": "void",
                 "effect_type": "void_cross", "effect_value": 1,
                 "grade": 3, "special_rules": None, "slot_index": 1}]
    monkeypatch.setattr("modules.ship_modules.Database.fetch", fetch)
    r = await list_modules(4)
    assert r[0]["name"] == "Void Drive"
    assert r[0]["slot_index"] == 1
