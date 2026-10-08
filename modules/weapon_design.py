#!/usr/bin/env python3
"""Weapon Design — Ported from Rust weapon_design.rs. Blueprints, produce, upgrades."""
from __future__ import annotations
from typing import Any
from core.db import Database
from core.log import info
from core.session import require_session


class _Refuse(Exception):
    """Carries an error answer out of a transaction so every write in it rolls back."""

    def __init__(self, out: dict):
        super().__init__(out.get("error", ""))
        self.out = out


def _tag_count(tag) -> int:
    """Row count of an asyncpg command tag such as `UPDATE 1`; 0 when unreadable."""
    try:
        return int(str(tag).split()[-1])
    except (ValueError, IndexError):
        return 0


def _positive_int(value) -> bool:
    """True for a real int above zero; a bool, a float and a numeric string all fail."""
    return isinstance(value, int) and not isinstance(value, bool) and value > 0

async def list_weapons() -> list[dict]:
    rows = await Database.fetch(
        "SELECT id, name, kind, slot_size, damage, range_m, tier_min, tier_max, special_rules "
        "FROM maya_rp.weapons ORDER BY kind, slot_size, name")
    return [dict(r) for r in rows]

async def list_blueprints() -> list[dict]:
    rows = await Database.fetch(
        "SELECT id, name, category, base_damage, base_range, slot_size, tier_required, tech_prereq, "
        "alloy_cost, credit_cost, research_cost, special_rules "
        "FROM maya_rp.weapon_blueprints ORDER BY category, tier_required, name")
    return [dict(r) for r in rows]

async def design_blueprint(name: str, category: str, damage: int, range_m: int, slot: str, tier: int,
                            session_id: int | None = None) -> dict:
    """Design a blueprint for credits; the charge and the insert commit together.

    Damage, range and tier must be positive ints. The cost is linear in them, so a negative damage
    produced a negative price and the "charge" refunded the treasury.

    The `weapon_blueprints` table is a shared armoury with no session_id: a blueprint outlives the
    campaign that paid for it. Izzat decides whether that stays.

    @param name - blueprint name, unique across the armoury.
    @param category - weapon kind.
    @param damage - positive int.
    @param range_m - positive int.
    @param slot - slot size.
    @param tier - positive int.
    @param session_id - session whose treasury pays; the active session when None.
    @returns the blueprint summary or {"error": ...}.
    @raises FrozenSession when the campaign is frozen reference data.
    """
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    for label, value in (("damage", damage), ("range_m", range_m), ("tier", tier)):
        if not _positive_int(value):
            return {"error": f"{label} must be a positive integer, got {value!r}"}
    if not str(name or "").strip():
        return {"error": "name must be a non-empty string"}
    # No session filter here on purpose: `weapon_blueprints` is a shared armoury with no session_id
    # column, so a blueprint name is global. Adding the filter raised UndefinedColumnError, which the
    # test caught within a minute of the mistake.
    exists = await Database.fetchval(
        "SELECT id FROM maya_rp.weapon_blueprints WHERE LOWER(name)=LOWER($1)", name)
    if exists: return {"error": f"Blueprint '{name}' already exists"}

    cost_credits = damage * 200 + range_m * 50 + tier * 500
    cost_research = damage * 100 + range_m * 25 + tier * 300

    try:
        async with Database.transaction() as conn:
            charged = await conn.execute(
                "UPDATE maya_rp.resources SET credits=credits-$1 WHERE session_id=$2 AND credits>=$1",
                cost_credits, session_id)
            if _tag_count(charged) == 0:
                raise _Refuse({"error": f"Need {cost_credits} credits"})
            made = await conn.fetchval(
                "INSERT INTO maya_rp.weapon_blueprints (name, category, base_damage, base_range, slot_size, tier_required, credit_cost, research_cost) "
                "SELECT $1::text,$2::text,$3::int,$4::int,$5::text,$6::int,$7::int,$8::int "
                "WHERE NOT EXISTS (SELECT 1 FROM maya_rp.weapon_blueprints WHERE LOWER(name)=LOWER($1)) "
                "RETURNING id",
                name, category, damage, range_m, slot, tier, cost_credits, cost_research)
            if made is None:
                raise _Refuse({"error": f"Blueprint '{name}' already exists"})
    except _Refuse as refused:
        return refused.out

    info("weapon_design", f"Designed blueprint: {name} (T{tier}, {slot})")
    return {"name": name, "category": category, "tier": tier, "slot": slot, "cost_credits": cost_credits}

async def produce_weapons(blueprint: str, qty: int = 1, session_id: int | None = None) -> dict:
    """Pay for `qty` weapons of a blueprint and make sure the catalogue lists the type.

    DESIGN DECISION FOR IZZAT. `weapons` is a GLOBAL catalogue (no session_id, no quantity column).
    The old code inserted `qty` identical rows into it per call, so one campaign's order grew every
    campaign's catalogue and repeated orders piled up duplicates. This version charges the treasury for
    `qty` and inserts at most ONE catalogue row per weapon name, skipping the insert when the name is
    already listed. No per-session stock is recorded, because the schema has nowhere to put it.

    @param blueprint - blueprint name, exact match ignoring case.
    @param qty - positive int.
    @param session_id - session whose treasury pays; the active session when None.
    @returns {"produced", "weapon", "cost_alloys", "cost_credits"} or {"error": ...}.
    @raises FrozenSession when the campaign is frozen reference data.
    """
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    if not _positive_int(qty):
        return {"error": f"qty must be a positive integer, got {qty!r}"}
    bp = await Database.fetchrow(
        "SELECT id, name, category, base_damage, base_range, slot_size, tier_required, "
        "alloy_cost, credit_cost, research_cost FROM maya_rp.weapon_blueprints"
        " WHERE LOWER(name)=LOWER($1)",
        blueprint)
    if not bp: return {"error": f"Blueprint '{blueprint}' not found"}

    alloy_cost = (bp["alloy_cost"] or 0) * qty
    credit_cost = (bp["credit_cost"] or 0) * qty
    res = await Database.fetchrow("SELECT alloys, credits FROM maya_rp.resources WHERE session_id=$1", session_id)
    # The sibling paths already refuse this case; this one raised TypeError on a
    # session with no resources row, which is every session that has not been seeded.
    if res is None:
        return {"error": f"no resources row for session {session_id}"}
    if (res["alloys"] or 0) < alloy_cost or (res["credits"] or 0) < credit_cost:
        return {"error": f"Need {alloy_cost}a/{credit_cost}c"}

    tier = bp["tier_required"] or 1
    try:
        async with Database.transaction() as conn:
            charged = await conn.execute(
                "UPDATE maya_rp.resources SET alloys=alloys-$1, credits=credits-$2 "
                "WHERE session_id=$3 AND alloys>=$1 AND credits>=$2", alloy_cost, credit_cost, session_id)
            if _tag_count(charged) == 0:
                raise _Refuse({"error": f"Need {alloy_cost}a/{credit_cost}c"})
            await conn.execute(
                "INSERT INTO maya_rp.weapons (name, kind, slot_size, damage, range_m, tier_min, tier_max) "
                "SELECT $1::text,$2::text,$3::text,$4::int,$5::int,$6::int,$7::int "
                "WHERE NOT EXISTS (SELECT 1 FROM maya_rp.weapons WHERE LOWER(name)=LOWER($1))",
                bp["name"], bp["category"], bp["slot_size"] or "L",
                bp["base_damage"] or 0, bp["base_range"] or 0, tier, tier + 2)
    except _Refuse as refused:
        return refused.out

    info("weapon_design", f"Produced {qty}x {bp['name']}")
    return {"produced": qty, "weapon": bp["name"], "cost_alloys": alloy_cost, "cost_credits": credit_cost}

async def list_upgrades(weapon_id: int) -> list[dict]:
    rows = await Database.fetch(
        "SELECT id, upgrade_name, effect_type, effect_value, tier_required, cost "
        "FROM maya_rp.weapon_upgrades WHERE weapon_id=$1 ORDER BY tier_required, upgrade_name", weapon_id)
    return [dict(r) for r in rows]

async def apply_upgrade(weapon_id: int, upgrade_name: str, ship_id: int | None = None,
                        session_id: int | None = None) -> dict:
    """Buy and fit one upgrade.

    Reviewed 2026-10-03 before wiring, and three things were wrong. The row carried no record that it
    had been applied, so a second call charged the treasury again for the same fitting. `effect_type`
    and `effect_value` were read and then ignored, so the upgrade cost money and changed nothing. And
    an unknown effect type fell through silently. All three are fixed here; the catalogue itself is
    empty, which is a separate and open question.

    The claim (`applied_at IS NULL`), the charge and the effect commit in one transaction. The claim
    runs first and guarded, so two concurrent calls cannot both pay. The special-rule write bound an
    untyped `$2` inside `jsonb_build_object`, which PostgreSQL cannot infer; it is `$2::text` now. A NULL
    `effect_value` nulled the `damage` column; it counts as 0.

    DESIGN DECISION FOR IZZAT. `weapons` and `weapon_upgrades.applied_at` are GLOBAL: an upgrade fitted
    by one campaign is fitted for all, and paid by one. The code keeps that and does not redesign it.

    @param weapon_id - catalogue weapon id.
    @param upgrade_name - upgrade name, exact match ignoring case.
    @param ship_id - unused.
    @param session_id - session whose treasury pays; the active session when None.
    @returns {"applied", "weapon_id", "cost", "effect"} or {"error": ...}.
    @raises FrozenSession when the campaign is frozen reference data.
    """
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    upg = await Database.fetchrow(
        "SELECT id, upgrade_name, effect_type, effect_value, tier_required, cost, applied_at"
        " FROM maya_rp.weapon_upgrades WHERE weapon_id=$1 AND LOWER(upgrade_name)=LOWER($2)",
        weapon_id, upgrade_name)
    if not upg:
        return {"error": f"Upgrade '{upgrade_name}' not found for weapon #{weapon_id}"}
    if upg["applied_at"] is not None:
        return {"error": f"'{upgrade_name}' is already fitted to weapon #{weapon_id}"}

    effect_type = (upg["effect_type"] or "").strip().lower()
    value = upg["effect_value"] if upg["effect_value"] is not None else 0
    column = {"damage": "damage", "range": "range_m", "range_m": "range_m"}.get(effect_type)
    if column is None and effect_type not in ("special", "special_rules"):
        # Fail loudly rather than charge for an effect this engine cannot apply.
        return {"error": f"Upgrade '{upgrade_name}' has effect_type '{upg['effect_type']}',"
                         f" which this engine cannot apply"}

    cost = upg["cost"] or 0
    if cost < 0:
        return {"error": f"Upgrade '{upgrade_name}' has a negative cost ({cost}); refused"}
    res = await Database.fetchrow("SELECT credits FROM maya_rp.resources WHERE session_id=$1", session_id)
    if res is None:
        return {"error": f"no resources row for session {session_id}"}
    if (res["credits"] or 0) < cost:
        return {"error": f"Need {cost} credits"}

    try:
        async with Database.transaction() as conn:
            claimed = await conn.execute(
                "UPDATE maya_rp.weapon_upgrades SET applied_at=now() WHERE id=$1 AND applied_at IS NULL",
                upg["id"])
            if _tag_count(claimed) == 0:
                raise _Refuse({"error": f"'{upgrade_name}' is already fitted to weapon #{weapon_id}"})
            charged = await conn.execute(
                "UPDATE maya_rp.resources SET credits=credits-$1 WHERE session_id=$2 AND credits>=$1",
                cost, session_id)
            if _tag_count(charged) == 0:
                raise _Refuse({"error": f"Need {cost} credits"})
            if column:
                # damage and range_m are integer columns; asyncpg rejects a float bind.
                await conn.execute(
                    f"UPDATE maya_rp.weapons SET {column} = COALESCE({column},0) + $1 WHERE id=$2",
                    int(round(value)), weapon_id)
            else:
                await conn.execute(
                    "UPDATE maya_rp.weapons SET special_rules="
                    " COALESCE(special_rules,'{}'::jsonb) || jsonb_build_object($1::text, $2::text) WHERE id=$3",
                    upgrade_name, str(value), weapon_id)
    except _Refuse as refused:
        return refused.out
    info("weapon_design", f"Fitted '{upgrade_name}' to weapon #{weapon_id} for {cost}")
    return {"applied": upgrade_name, "weapon_id": weapon_id, "cost": cost,
            "effect": {"type": effect_type, "value": value}}


async def run_tick(session_id: int | None = None) -> dict:
    """Report readiness; weapon design has no per-tick work.

    @raises FrozenSession when the campaign is frozen reference data.
    """
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    return {"status": "weapon_design_ready"}
