#!/usr/bin/env python3
"""Ship Building — Ported from Rust build.rs. Full build pipeline: resource check, material deduction, insertion."""
from __future__ import annotations
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info, error
from modules.ship_generation import generate_ship

TIER_MATERIALS = {
    1: [("Alloy Ingot", 0.02)],
    2: [("Alloy Ingot", 0.02), ("Durasteel", 0.01)],
    3: [("Alloy Ingot", 0.02), ("Durasteel", 0.01), ("Refined Fuel", 0.005)],
    4: [("Alloy Ingot", 0.02), ("Durasteel", 0.01), ("Refined Fuel", 0.005), ("Gravitic Core", 0.001)],
    5: [("Alloy Ingot", 0.02), ("Durasteel", 0.01), ("Refined Fuel", 0.005), ("Gravitic Core", 0.002)],
}

async def build_ship(class_name: str, tier: int, ship_type: str, name: str, location: str = "Stasiun TKG",
                      session_id: int | None = None) -> dict[str, Any]:
    if session_id is None: session_id = Config.SESSION_ID
    if tier not in TIER_MATERIALS:
        # `.get(tier, TIER_MATERIALS[1])` built a T9 hull out of tier-1 materials
        # and said nothing about it.
        return {"error": f"Unknown tier {tier}: buildable tiers are "
                         f"{', '.join(str(t) for t in sorted(TIER_MATERIALS))}"}

    ship = await generate_ship(class_name, tier, ship_type, name, session_id)
    if "error" in ship:
        return ship

    # Check resources
    res = await Database.fetchrow(
        "SELECT alloys, credits FROM maya_rp.resources WHERE session_id = $1", session_id)
    if not res:
        return {"error": "No resources found"}
    if res["alloys"] < ship["total_alloy_cost"] or res["credits"] < ship["total_credit_cost"]:
        return {"error": f"Not enough resources! Need {ship['total_alloy_cost']}a/{ship['total_credit_cost']}c, "
                f"have {res['alloys']}a/{res['credits']}c"}

    # Validate materials BEFORE spending anything: the old order deducted
    # alloys/credits first, so a build that then failed on a missing material
    # burned the resources and produced nothing.
    mats = TIER_MATERIALS.get(tier, TIER_MATERIALS[1])
    needed = {mat_name: max(1, round(ship["mass"] * qty_per_mass)) for mat_name, qty_per_mass in mats}
    for mat_name, qty in needed.items():
        avail = await Database.fetchval(
            "SELECT COALESCE(SUM(quantity - reserved), 0) FROM maya_rp.material_stockpiles "
            "WHERE session_id = $1 AND material_name = $2", session_id, mat_name) or 0
        if avail < qty:
            return {"error": f"Not enough {mat_name}! Need {qty}, have {avail}"}

    # Deduct alloys + credits (resources has no updated_at column)
    await Database.execute(
        "UPDATE maya_rp.resources SET alloys = alloys - $1, credits = credits - $2 WHERE session_id = $3",
        ship["total_alloy_cost"], ship["total_credit_cost"], session_id)

    # Consume materials
    for mat_name, qty in needed.items():
        stockpiles = await Database.fetch(
            "SELECT id, quantity - reserved AS available FROM maya_rp.material_stockpiles "
            "WHERE session_id = $1 AND material_name = $2 AND quantity > reserved ORDER BY quantity DESC",
            session_id, mat_name)
        remaining = qty
        for sp in stockpiles:
            if remaining <= 0: break
            take = min(remaining, sp["available"])
            await Database.execute("UPDATE maya_rp.material_stockpiles SET quantity = quantity - $1 WHERE id = $2",
                                   take, sp["id"])
            remaining -= take
        if remaining > 0:
            # The stockpile check above this loop and the take inside it read the
            # same rows twice. Anything that moved in between leaves the build
            # short, and the shortfall used to be swallowed by the loop.
            error("ship_building",
                  f"{mat_name}: {remaining} short of {qty} after consumption; "
                  f"alloys and credits for {ship['name']} are already spent")
            return {"error": f"{mat_name} short by {remaining} after deduction; "
                             f"alloys and credits are spent, ship not built"}

    # Insert ship
    ship_id = await Database.fetchval(
        "INSERT INTO maya_rp.ships (session_id, name, class_id, ship_type, mass, length_m, hull, hull_current, "
        "speed, crew, location, tier, status) VALUES ($1,$2,$3,$4,$5,$6,$7,$7,$8,$9,$10,$11,'active') RETURNING id",
        session_id, ship["name"], ship["class_id"], ship["ship_type"],
        ship["mass"], ship["length_m"], ship["hull"], ship["speed"], ship["crew"],
        location, ship["tier"])

    # Armaments
    for arm in ship["armaments"]:
        await Database.execute(
            "INSERT INTO maya_rp.ship_armaments (ship_id, weapon_id, slot_index, slot_size) VALUES ($1,$2,$3,$4)",
            ship_id, arm["weapon_id"], arm["slot_index"], arm["slot_size"])

    # Modules
    for i, m in enumerate(ship["modules"]):
        await Database.execute(
            "INSERT INTO maya_rp.ship_modules (ship_id, module_id, slot_index) VALUES ($1,$2,$3)",
            ship_id, m["module_id"], i)

    # Combat stats
    speed_rating = "very_fast" if ship["speed"] > 80 else "fast" if ship["speed"] > 60 else "medium" if ship["speed"] > 40 else "slow" if ship["speed"] > 20 else "very_slow"
    evasion = min(80, max(10, round(ship["speed"] * 0.5)))
    combat_rating = round(ship["hull"] * 0.3 + ship["speed"] * 0.5 + ship["crew"] * 0.2)
    await Database.execute(
        "INSERT INTO maya_rp.combat_stats (ship_id, hull_points, max_hull_points, shield_points, max_shield_points, "
        "speed, evasion, combat_rating) VALUES ($1,$2,$3,$4,$5,$6,$7,$8) ON CONFLICT (ship_id) DO NOTHING",
        ship_id, ship["hull"], ship["hull"], round(ship["hull"] * 0.6), round(ship["hull"] * 0.6),
        speed_rating, evasion, combat_rating)

    # Event
    await Database.execute(
        "INSERT INTO maya_rp.events (session_id, event_type, title, description, tags) VALUES "
        "($1,'build',$2,$3,'[]'::jsonb)",
        session_id, f"Ship built: {ship['name']}",
        f"{ship['class_name']} ({ship['ship_type']}) built at T{ship['tier']}. "
        f"Mass: {ship['mass']}t, Crew: {ship['crew']}, Hull: {ship['hull']}. "
        f"Cost: {ship['total_alloy_cost']}a/{ship['total_credit_cost']}c.")

    info("ship_building", f"Built {ship['name']} ({ship['class_name']} T{ship['tier']})")
    return {"ship_id": ship_id, "name": ship["name"], "class_name": ship["class_name"],
            "tier": ship["tier"], "cost_alloys": ship["total_alloy_cost"],
            "cost_credits": ship["total_credit_cost"]}

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    return {"status": "ship_building_ready"}


# ═══════════════════════════════════════════════════════════════
# NOVEL ULTIMATE #1 — TALENT SHORTAGE (Bottleneck Logik)
# Novel: masalah utama bukan kapal, tapi CREW. "Oops! We are short of talent."
# Kapal undercrewed = liability (power drop + status undercrewed).
# ═══════════════════════════════════════════════════════════════

async def check_crew_capacity(session_id: int, required_crew: int) -> bool:
    """Betulkan: ada cukup crew unassigned untuk kapal baru?"""
    available = await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.crew_roster WHERE session_id=$1 AND ship_id IS NULL AND status='active'",
        session_id,
    ) or 0
    return available >= required_crew


async def assign_crew_to_ship(session_id: int, ship_id: int, required_crew: int) -> dict:
    """Assign crew ke kapal. Deficit = undercrewed state (Stakes Integrity: liability)."""
    # Semak spec kapal dulu
    ship = await Database.fetchrow(
        "SELECT id, name, power_rating, hull FROM maya_rp.ships WHERE id=$1 AND session_id=$2",
        ship_id, session_id,
    )
    if not ship:
        return {"error": "Ship not found"}

    available = await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.crew_roster WHERE session_id=$1 AND ship_id IS NULL AND status='active'",
        session_id,
    ) or 0

    deficit = max(0, required_crew - available)
    # The crew that does exist goes aboard in both branches. The undercrewed branch
    # used to write crew_current = available and never link a single crew row, so
    # the same people stayed available for the next ship to claim.
    take = available if deficit > 0 else required_crew
    if take > 0:
        await Database.execute(
            """UPDATE maya_rp.crew_roster SET ship_id=$1
               WHERE id IN (SELECT id FROM maya_rp.crew_roster
                            WHERE session_id=$2 AND ship_id IS NULL AND status='active'
                            ORDER BY id LIMIT $3)""",
            ship_id, session_id, take,
        )
    if deficit > 0:
        # Stakes Integrity: undercrewed ship = liability
        penalty = round(deficit / max(1, required_crew), 3)
        await Database.execute(
            "UPDATE maya_rp.ships SET crew_current=$1, crew_required=$2, undercrewed_penalty=$3, "
            "status='undercrewed' WHERE id=$4 AND session_id=$5",
            available, required_crew, penalty, ship_id, session_id,
        )
        await Database.execute(
            "INSERT INTO maya_rp.events (session_id, event_type, title, description, importance) "
            "VALUES ($1, 'warning', $2, $3, 3)",
            session_id, f"UNDERCREWED: {ship['name']}",
            f"Kapal dilancarkan dengan kekurangan {deficit} crew. Combat efficiency -{penalty*100:.0f}%. "
            f"Novel bab 171: 'Oops! We are short of talent.'",
        )
        return {"warning": True, "deficit": deficit, "penalty": penalty,
                "status": "undercrewed", "crew_assigned": take}

    # Crew cukup — assign (already done above, with the ship's session in the subquery)
    await Database.execute(
        "UPDATE maya_rp.ships SET crew_current=$1, crew_required=$2, undercrewed_penalty=0, "
        "status='active' WHERE id=$3 AND session_id=$4",
        required_crew, required_crew, ship_id, session_id,
    )
    return {"warning": False, "crew": required_crew, "status": "active"}


async def crew_shortage_report(session_id: int = None) -> dict:
    """Novel bab 171 arc: talent shortage dashboard."""
    if session_id is None:
        session_id = Config.SESSION_ID
    crew_total = await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.crew_roster WHERE session_id=$1 AND status='active'", session_id) or 0
    crew_unassigned = await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.crew_roster WHERE session_id=$1 AND ship_id IS NULL AND status='active'",
        session_id) or 0
    ships_active = await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.ships WHERE session_id=$1 AND status IN ('active','undercrewed')",
        session_id) or 0
    undercrewed = await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.ships WHERE session_id=$1 AND status='undercrewed'", session_id) or 0
    shortage = max(0, ships_active - crew_unassigned)
    return {"crew_total": crew_total, "crew_unassigned": crew_unassigned,
            "ships_active": ships_active, "undercrewed": undercrewed,
            "shortage": shortage,
            "status": "SHORTAGE" if shortage > 0 else "balanced"}
