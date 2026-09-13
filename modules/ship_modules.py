#!/usr/bin/env python3
"""Ship module system — install & query modules on ships (2026-08-15).

"Crossing the void" = traveling BETWEEN nebulas (z-planes) without a gate.
A ship needs a VOID DRIVE installed to cross the void on its own power;
Nebular Ward cuts the void risk; Void Anchor resists wormhole/gate collapse.

Ships carry module_slots (from ship_classes) — installing checks tier range
(tier_min/max), slot availability, and duplicates.

Key API:
  install_module(ship_id, module_name)  — fit a module into a free slot
  list_modules(ship_id)                 — what's fitted, with effects
  fleet_void_capable(fleet_tag)         — does any fleet ship have a Void Drive?
  void_crossing_cost(z1, z2, fleet_tag) — travel plan for a void crossing
"""
from __future__ import annotations

from core.db import Database
from core.config import Config
from core.log import info

VOID_HOURS_PER_UNIT = 12.0          # void crossing is FAST: 12h/u vs 24h/u standard
VOID_BASE_RISK_PCT = 20             # d100 <= 20 base void hazard per crossing
VOID_WARD_REDUCTION = 20            # Nebular Ward grade-scaled reduction (pct points)


async def install_module(ship_id: int, module_name: str,
                         session_id: int | None = None) -> dict:
    """Fit a module into a free slot on a ship. Validates tier range + slots."""
    if session_id is None:
        session_id = Config.SESSION_ID
    ship = await Database.fetchrow(
        """SELECT s.id, s.name, s.tier, s.sub_class,
                  COALESCE(sc.module_slots, 0) AS module_slots
           FROM maya_rp.ships s
           LEFT JOIN maya_rp.ship_classes sc ON sc.class_name = s.sub_class
           WHERE s.id=$1 AND s.session_id=$2""",
        ship_id, session_id)
    if not ship:
        raise ValueError(f"No ship id={ship_id}")
    mod = await Database.fetchrow(
        """SELECT * FROM maya_rp.modules WHERE name ILIKE $1""", f"%{module_name}%")
    if not mod:
        raise ValueError(f"No module named {module_name!r}")
    tier = ship["tier"] or 0
    if tier < mod["tier_min"] or (mod["tier_max"] and tier > mod["tier_max"]):
        raise ValueError(
            f"Module {mod['name']} needs tier {mod['tier_min']}–{mod['tier_max']}, "
            f"ship {ship['name']} is tier {tier}")
    used = await Database.fetchval(
        "SELECT count(*) FROM maya_rp.ship_modules WHERE ship_id=$1", ship_id)
    if used >= (ship["module_slots"] or 0):
        raise ValueError(
            f"Ship {ship['name']} has no free module slots "
            f"({used}/{ship['module_slots'] or 0} used)")
    dup = await Database.fetchrow(
        """SELECT sm.id FROM maya_rp.ship_modules sm
           JOIN maya_rp.modules m ON m.id = sm.module_id
           WHERE sm.ship_id=$1 AND m.name ILIKE $2""",
        ship_id, f"%{mod['name']}%")
    if dup:
        raise ValueError(f"{mod['name']} is already fitted on {ship['name']}")
    mid = await Database.fetchval(
        """INSERT INTO maya_rp.ship_modules (ship_id, module_id, slot_index)
           VALUES ($1, $2, $3) RETURNING id""",
        ship_id, mod["id"], used + 1)
    info("ship_modules", f"Installed {mod['name']} on {ship['name']} "
                         f"(slot {used + 1}/{ship['module_slots'] or 0})")
    return {"id": mid, "ship": ship["name"], "module": mod["name"],
            "category": mod["category"], "slot": used + 1}


async def list_modules(ship_id: int) -> list[dict]:
    """List fitted modules with effects + special rules."""
    return await Database.fetch(
        """SELECT m.name, m.category, m.effect_type, m.effect_value, m.grade,
                  m.special_rules, sm.slot_index
           FROM maya_rp.ship_modules sm
           JOIN maya_rp.modules m ON m.id = sm.module_id
           WHERE sm.ship_id=$1 ORDER BY sm.slot_index""",
        ship_id)


async def fleet_void_capable(fleet_name: str | None,
                             session_id: int | None = None) -> dict:
    """Does any ship in the fleet carry a Void Drive?

    fleet_name matches maya_rp.fleets.name (e.g. 'SEF-3 Silent Maw',
    'Legion Vanguard'). Returns {capable, ships, drive_ships} — drive_ships
    are the ones that can personally cross the void.
    """
    if not fleet_name:
        return {"capable": False, "ships": 0, "drive_ships": 0, "drive_names": []}
    if session_id is None:
        session_id = Config.SESSION_ID
    rows = await Database.fetch(
        """SELECT s.id, s.name, s.sub_class, s.tier,
                  (EXISTS (SELECT 1 FROM maya_rp.ship_modules sm
                           JOIN maya_rp.modules m ON m.id=sm.module_id
                           WHERE sm.ship_id=s.id AND m.effect_type='void_cross')) AS has_drive
           FROM maya_rp.fleets f
           JOIN maya_rp.fleet_members fm ON fm.fleet_id = f.id
           JOIN maya_rp.ships s ON s.id = fm.ship_id
           WHERE f.session_id=$1 AND f.name ILIKE $2
           ORDER BY s.id""",
        session_id, f"%{fleet_name}%")
    drive_ships = [r for r in rows if r["has_drive"]]
    return {"capable": bool(drive_ships), "ships": len(rows),
            "drive_ships": len(drive_ships),
            "drive_names": [r["name"] for r in drive_ships]}


async def void_crossing_cost(z1, z2, fleet_name: str | None,
                             session_id: int | None = None) -> dict:
    """Cost + risk of crossing the void between z-planes with a fleet.

    Requires at least one Void Drive in the fleet. Travel is FAST (12h/u)
    but risky: base 20% hazard per crossing, reduced by Nebular Ward on any
    drive ship (each grade adds reduction). Returns the plan; the caller
    rolls the actual crossing in advance().
    """
    if session_id is None:
        session_id = Config.SESSION_ID
    cap = await fleet_void_capable(fleet_name, session_id)
    if not cap["capable"]:
        raise ValueError(
            "No Void Drive in fleet — the void cannot be crossed without one. "
            "Install a Void Drive first (ship module install).")
    # ward reduction from any ship in the fleet that has Nebular Ward
    ward_rows = await Database.fetch(
        """SELECT m.effect_value, m.grade
           FROM maya_rp.ship_modules sm
           JOIN maya_rp.modules m ON m.id=sm.module_id
           JOIN maya_rp.ships s ON s.id=sm.ship_id
           JOIN maya_rp.fleet_members fm ON fm.ship_id=s.id
           JOIN maya_rp.fleets f ON f.id=fm.fleet_id
           WHERE f.session_id=$1 AND f.name ILIKE $2 AND m.effect_type='void_resist'""",
        session_id, f"%{fleet_name}%")
    ward = sum(int(r["effect_value"] or 0) for r in ward_rows)
    risk = max(5, VOID_BASE_RISK_PCT - ward)
    return {"capable": True, "z1": z1, "z2": z2,
            "hours_per_unit": VOID_HOURS_PER_UNIT,
            "risk_pct": risk, "ward": ward,
            "drive_ships": cap["drive_names"]}


async def list_void_modules() -> list[dict]:
    """Catalog of void-category modules."""
    return await Database.fetch(
        """SELECT id, name, effect_type, effect_value, grade, tier_min, tier_max,
                  cost_alloys, cost_credits
           FROM maya_rp.modules WHERE category='void' ORDER BY id""")
