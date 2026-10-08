#!/usr/bin/env python3
"""Ship Building — Ported from Rust build.rs. Full build pipeline: resource check, material deduction, insertion."""
from __future__ import annotations
from typing import Any
from core.db import Database
from core.log import info, error
from modules.ship_generation import generate_ship

TIER_MATERIALS = {
    1: [("Alloy Ingot", 0.02)],
    2: [("Alloy Ingot", 0.02), ("Durasteel", 0.01)],
    3: [("Alloy Ingot", 0.02), ("Durasteel", 0.01), ("Refined Fuel", 0.005)],
    4: [("Alloy Ingot", 0.02), ("Durasteel", 0.01), ("Refined Fuel", 0.005), ("Gravitic Core", 0.001)],
    5: [("Alloy Ingot", 0.02), ("Durasteel", 0.01), ("Refined Fuel", 0.005), ("Gravitic Core", 0.002)],
}

def _writable_session(session_id: int | None) -> int:
    """Resolve the session for one call and refuse a frozen campaign.

    Sessions 3 and 5 are reference data. Every writer here resolved `Config.SESSION_ID`, fixed at
    import, and wrote without a freeze check.

    @param session_id - caller's session; `None` resolves through `core.session.require_session`.
    @returns the resolved session id.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    from core.ooc import _refuse_frozen
    from core.session import require_session

    sid = require_session(session_id)
    _refuse_frozen(sid)
    return sid


class _BuildRefused(Exception):
    """Raised inside the build transaction to roll it back; carries the reply for the caller."""

    def __init__(self, reply: dict):
        super().__init__(reply.get("error", ""))
        self.reply = reply


def _units(value) -> int | float:
    """Whole numbers print without the `.0000` that a NUMERIC column adds."""
    return int(value) if value == int(value) else float(value)


async def build_ship(class_name: str, tier: int, ship_type: str, name: str, location: str = "Stasiun TKG",
                      session_id: int | None = None) -> dict[str, Any]:
    """Build one ship: debit alloys, credits and materials, then insert the hull.

    Every write runs in one transaction on one connection. The debits were separate pool
    statements with the ship insert after them, so an insert that raised left the treasury and the
    stockpiles spent for no ship, and two concurrent builds both passed the same balance check.

    @param class_name - `ship_classes.class_name`.
    @param tier - build tier; must be a key of `TIER_MATERIALS`.
    @param ship_type - variant code; see `TYPE_MULTIPLIERS`.
    @param name - ship name.
    @param location - where the hull is docked.
    @param session_id - campaign; `None` resolves through `require_session`.
    @returns `{ship_id, name, class_name, tier, cost_alloys, cost_credits}`, or `{error}` with
        nothing spent.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
    if tier not in TIER_MATERIALS:
        # `.get(tier, TIER_MATERIALS[1])` built a T9 hull out of tier-1 materials
        # and said nothing about it.
        return {"error": f"Unknown tier {tier}: buildable tiers are "
                         f"{', '.join(str(t) for t in sorted(TIER_MATERIALS))}"}

    ship = await generate_ship(class_name, tier, ship_type, name, session_id)
    if "error" in ship:
        return ship

    mats = TIER_MATERIALS[tier]
    needed = {mat_name: max(1, round(ship["mass"] * qty_per_mass)) for mat_name, qty_per_mass in mats}

    try:
        async with Database.transaction() as conn:
            # The treasury row is locked first: a second build waits here instead of reading the
            # same balance.
            res = await conn.fetchrow(
                "SELECT alloys, credits FROM maya_rp.resources WHERE session_id = $1 FOR UPDATE",
                session_id)
            if not res:
                raise _BuildRefused({"error": "No resources found"})
            if res["alloys"] < ship["total_alloy_cost"] or res["credits"] < ship["total_credit_cost"]:
                raise _BuildRefused({"error": f"Not enough resources! Need {ship['total_alloy_cost']}a/"
                                              f"{ship['total_credit_cost']}c, have {res['alloys']}a/{res['credits']}c"})

            # Materials are read and locked before anything is spent.
            takes: list[tuple[str, int, list[tuple[int, object]]]] = []
            for mat_name, qty in needed.items():
                stockpiles = await conn.fetch(
                    "SELECT id, COALESCE(quantity,0) - COALESCE(reserved,0) AS available "
                    "FROM maya_rp.material_stockpiles "
                    "WHERE session_id = $1 AND material_name = $2 AND COALESCE(quantity,0) > COALESCE(reserved,0) "
                    "ORDER BY quantity DESC FOR UPDATE", session_id, mat_name)
                avail = sum(sp["available"] for sp in stockpiles)
                if avail < qty:
                    raise _BuildRefused({"error": f"Not enough {mat_name}! Need {qty}, have {_units(avail)}"})
                plan, remaining = [], qty
                for sp in stockpiles:
                    if remaining <= 0:
                        break
                    take = min(remaining, sp["available"])
                    plan.append((sp["id"], take))
                    remaining -= take
                takes.append((mat_name, qty, plan))

            # Guarded debit: the balance test and the subtraction are one statement.
            debit = await conn.fetchrow(
                "UPDATE maya_rp.resources SET alloys = alloys - $1, credits = credits - $2 "
                "WHERE session_id = $3 AND alloys >= $1 AND credits >= $2 RETURNING session_id",
                ship["total_alloy_cost"], ship["total_credit_cost"], session_id)
            if debit is None:
                raise _BuildRefused({"error": "Not enough resources! The balance changed during the build."})

            for mat_name, qty, plan in takes:
                short = qty
                for sp_id, take in plan:
                    hit = await conn.fetchrow(
                        "UPDATE maya_rp.material_stockpiles SET quantity = quantity - $1 "
                        "WHERE id = $2 AND COALESCE(quantity,0) - COALESCE(reserved,0) >= $1 RETURNING id",
                        take, sp_id)
                    if hit is not None:
                        short -= take
                if short > 0:
                    error("ship_building",
                          f"{mat_name}: {_units(short)} short of {qty} after the locked read; "
                          f"build of {ship['name']} rolled back")
                    raise _BuildRefused({"error": f"{mat_name} short by {_units(short)} of {qty}; "
                                                  f"nothing spent, ship not built"})

            # `sub_class` carries the class name: `ship_modules.install_module` joins
            # `ship_classes.class_name = ships.sub_class`, and a NULL there gave every built ship
            # zero module slots.
            ship_id = await conn.fetchval(
                "INSERT INTO maya_rp.ships (session_id, name, class_id, ship_type, mass, length_m, hull, hull_current, "
                "speed, crew, location, tier, status, sub_class) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$7,$8,$9,$10,$11,'active',$12) RETURNING id",
                session_id, ship["name"], ship["class_id"], ship["ship_type"],
                ship["mass"], ship["length_m"], ship["hull"], ship["speed"], ship["crew"],
                location, ship["tier"], ship["class_name"])

            for arm in ship["armaments"]:
                await conn.execute(
                    "INSERT INTO maya_rp.ship_armaments (ship_id, weapon_id, slot_index, slot_size) VALUES ($1,$2,$3,$4)",
                    ship_id, arm["weapon_id"], arm["slot_index"], arm["slot_size"])

            for i, m in enumerate(ship["modules"]):
                await conn.execute(
                    "INSERT INTO maya_rp.ship_modules (ship_id, module_id, slot_index) VALUES ($1,$2,$3)",
                    ship_id, m["module_id"], i)

            speed_rating = "very_fast" if ship["speed"] > 80 else "fast" if ship["speed"] > 60 else "medium" if ship["speed"] > 40 else "slow" if ship["speed"] > 20 else "very_slow"
            evasion = min(80, max(10, round(ship["speed"] * 0.5)))
            combat_rating = round(ship["hull"] * 0.3 + ship["speed"] * 0.5 + ship["crew"] * 0.2)
            await conn.execute(
                "INSERT INTO maya_rp.combat_stats (ship_id, hull_points, max_hull_points, shield_points, max_shield_points, "
                "speed, evasion, combat_rating) VALUES ($1,$2,$3,$4,$5,$6,$7,$8) ON CONFLICT (ship_id) DO NOTHING",
                ship_id, ship["hull"], ship["hull"], round(ship["hull"] * 0.6), round(ship["hull"] * 0.6),
                speed_rating, evasion, combat_rating)

            await conn.execute(
                "INSERT INTO maya_rp.events (session_id, event_type, title, description, tags) VALUES "
                "($1,'build',$2,$3,'[]'::jsonb)",
                session_id, f"Ship built: {ship['name']}",
                f"{ship['class_name']} ({ship['ship_type']}) built at T{ship['tier']}. "
                f"Mass: {ship['mass']}t, Crew: {ship['crew']}, Hull: {ship['hull']}. "
                f"Cost: {ship['total_alloy_cost']}a/{ship['total_credit_cost']}c.")
    except _BuildRefused as refused:
        return refused.reply

    info("ship_building", f"Built {ship['name']} ({ship['class_name']} T{ship['tier']})")
    return {"ship_id": ship_id, "name": ship["name"], "class_name": ship["class_name"],
            "tier": ship["tier"], "cost_alloys": ship["total_alloy_cost"],
            "cost_credits": ship["total_credit_cost"]}

async def run_tick(session_id: int = None) -> dict:
    """No-op tick. Resolves the session and refuses a frozen campaign.

    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
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
    """Assign crew ke kapal. Deficit = undercrewed state (Stakes Integrity: liability).

    The roster claim, the ship update and the warning event run in one transaction. The crew
    count was read first and claimed later, so two ships assigned together both counted the same
    free crew; the claim now returns the rows it actually took and the deficit follows from that.

    @param session_id - campaign; the ship must belong to it.
    @param ship_id - ship to crew.
    @param required_crew - berths to fill; negative is refused.
    @returns `{warning, crew|deficit, ...}` or `{error}`.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
    if required_crew < 0:
        return {"error": f"required_crew cannot be negative, got {required_crew}"}
    async with Database.transaction() as conn:
        ship = await conn.fetchrow(
            "SELECT id, name, power_rating, hull FROM maya_rp.ships WHERE id=$1 AND session_id=$2 FOR UPDATE",
            ship_id, session_id,
        )
        if not ship:
            return {"error": "Ship not found"}

        # The undercrewed branch used to write crew_current = available and never link a single
        # crew row, so the same people stayed available for the next ship to claim.
        claimed = await conn.fetch(
            """UPDATE maya_rp.crew_roster SET ship_id=$1
               WHERE ship_id IS NULL AND id IN (
                   SELECT id FROM maya_rp.crew_roster
                   WHERE session_id=$2 AND ship_id IS NULL AND status='active'
                   ORDER BY id LIMIT $3 FOR UPDATE SKIP LOCKED)
               RETURNING id""",
            ship_id, session_id, required_crew,
        )
        take = len(claimed)
        deficit = max(0, required_crew - take)
        if deficit > 0:
            # Stakes Integrity: undercrewed ship = liability
            penalty = round(deficit / max(1, required_crew), 3)
            await conn.execute(
                "UPDATE maya_rp.ships SET crew_current=$1, crew_required=$2, undercrewed_penalty=$3, "
                "status='undercrewed' WHERE id=$4 AND session_id=$5",
                take, required_crew, penalty, ship_id, session_id,
            )
            await conn.execute(
                "INSERT INTO maya_rp.events (session_id, event_type, title, description, importance) "
                "VALUES ($1, 'warning', $2, $3, 3)",
                session_id, f"UNDERCREWED: {ship['name']}",
                f"Kapal dilancarkan dengan kekurangan {deficit} crew. Combat efficiency -{penalty*100:.0f}%. "
                f"Novel bab 171: 'Oops! We are short of talent.'",
            )
            return {"warning": True, "deficit": deficit, "penalty": penalty,
                    "status": "undercrewed", "crew_assigned": take}

        await conn.execute(
            "UPDATE maya_rp.ships SET crew_current=$1, crew_required=$2, undercrewed_penalty=0, "
            "status='active' WHERE id=$3 AND session_id=$4",
            required_crew, required_crew, ship_id, session_id,
        )
    return {"warning": False, "crew": required_crew, "status": "active"}


async def crew_shortage_report(session_id: int = None) -> dict:
    """Novel bab 171 arc: talent shortage dashboard.

    `shortage` is counted in crew: berths still empty on active and undercrewed ships (the ship's
    `crew_required`, or its `crew` when no requirement was set), less the unassigned crew who
    could fill them. It subtracted unassigned crew (people) from the number
    of ships, so two free crew "covered" two ships of any size.

    @returns `{crew_total, crew_unassigned, ships_active, undercrewed, berths_unfilled, shortage, status}`.
    """
    from core.session import require_session

    session_id = require_session(session_id)
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
    berths_unfilled = await Database.fetchval(
        "SELECT COALESCE(SUM(GREATEST(COALESCE(NULLIF(crew_required,0), crew, 0) - COALESCE(crew_current,0), 0)), 0) "
        "FROM maya_rp.ships WHERE session_id=$1 AND status IN ('active','undercrewed')",
        session_id) or 0
    shortage = max(0, int(berths_unfilled) - crew_unassigned)
    return {"crew_total": crew_total, "crew_unassigned": crew_unassigned,
            "ships_active": ships_active, "undercrewed": undercrewed,
            "berths_unfilled": int(berths_unfilled), "shortage": shortage,
            "status": "SHORTAGE" if shortage > 0 else "balanced"}
