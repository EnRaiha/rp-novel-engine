#!/usr/bin/env python3
"""Ship Generation — Ported from Rust ship_gen.rs. Complete stat rolling, weapon/module assignment."""
from __future__ import annotations
import random, math
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info

def tier_mult(tier: int, scale: float = 1.15) -> float:
    return scale ** max(tier - 1, 0)

def roll_stat(base: int, tier: int, scale: float = 1.15, variance: float = 0.10) -> int:
    return round(base * tier_mult(tier, scale) * (1 + random.uniform(-variance, variance)))

def parse_slots(slots_str: str) -> list[tuple[str, int]]:
    """Read a weapon-slot spec like "2XH 2H 4M" into [(size, count), ...].

    A bare size means one mount ("M" -> ("M", 1)).

    A token that is neither is REPORTED rather than dropped: five live classes
    carry specs this parser cannot read ("8", "300", "30", "0", "M"), and they
    silently generated with no weapons at all. Only "0" is a legitimate empty
    spec, so anything unread is named.
    """
    if not slots_str or slots_str.lower() == "none":
        return []
    slots = []
    unread = []
    for tok in slots_str.split():
        if tok in ("WMD", "SH", "XH", "H", "M", "L"):
            slots.append((tok, 1))          # a bare size is one mount
            continue
        for so in ["WMD","SH","XH","H","M","L"]:
            if tok.endswith(so):
                try:
                    c = int(tok[:-len(so)])
                    slots.append((so, c))
                except ValueError:
                    unread.append(tok)
                break
        else:
            unread.append(tok)
    if unread:
        info("ship_generation", f"weapon_slots {slots_str!r}: could not read {unread} — "
                                f"those mounts will be empty")
    return slots

async def get_class(class_name: str) -> dict | None:
    row = await Database.fetchrow(
        "SELECT id, class_name, category, base_mass, base_length, base_crew, base_hull, base_speed, "
        "module_slots, weapon_slots, scale_factor, special_rules FROM maya_rp.ship_classes "
        "WHERE LOWER(class_name) = LOWER($1)", class_name)
    return dict(row) if row else None

async def get_weapons(tier: int) -> list[dict]:
    rows = await Database.fetch(
        "SELECT id, name, kind, slot_size, damage, range_m, tier_min, tier_max, special_rules "
        "FROM maya_rp.weapons WHERE tier_min <= $1 AND tier_max >= $1 ORDER BY slot_size, name", tier)
    return [dict(r) for r in rows]

async def get_modules(tier: int) -> list[dict]:
    rows = await Database.fetch(
        "SELECT id, name, category, effect_type, effect_value, grade, tier_min, tier_max, "
        "cost_alloys, cost_credits, special_rules FROM maya_rp.modules "
        "WHERE tier_min <= $1 AND tier_max >= $1 ORDER BY grade DESC, category", tier)
    return [dict(r) for r in rows]

TYPE_MULTIPLIERS = {"HRO": 1.15, "MYT": 1.50, "CRP": 0.50, "CSM": 1.30, "SPC": 1.10}

async def generate_ship(class_name: str, tier: int, ship_type: str, name: str | None = None,
                         session_id: int | None = None) -> dict[str, Any]:
    if session_id is None: session_id = Config.SESSION_ID
    sc = await get_class(class_name)
    if not sc:
        return {"error": f"Ship class '{class_name}' not found"}
    sf = sc.get("scale_factor") or 1.15

    mass = roll_stat(sc["base_mass"], tier, sf, 0.10)
    speed_mult = tier_mult(tier, sf)
    speed = round(sc["base_speed"] / math.sqrt(speed_mult))
    length = roll_stat(sc["base_length"], tier, sf, 0.08)
    hull = roll_stat(sc["base_hull"], tier, sf, 0.08)
    crew = roll_stat(sc["base_crew"], tier, sf, 0.12)

    type_mult = TYPE_MULTIPLIERS.get(ship_type, 1.0)
    hull = round(hull * type_mult)

    slot_specs = parse_slots(sc["weapon_slots"])
    weapon_pool = await get_weapons(tier)
    armaments = roll_weapons(slot_specs, weapon_pool)

    module_pool = await get_modules(tier)
    modules = roll_modules(sc["module_slots"] or 0, module_pool)

    ship_name = name or sc["class_name"]
    alloy_cost = sum(m.get("cost_alloys", 0) for m in modules) + round(sc["base_mass"] * 0.3 * (tier ** 0.7))
    credit_cost = sum(m.get("cost_credits", 0) for m in modules) + round(sc["base_mass"] * 0.75 * (tier ** 0.7))

    return {
        "name": ship_name, "class_id": sc["id"], "class_name": sc["class_name"],
        "category": sc["category"], "ship_type": ship_type, "tier": tier,
        "mass": mass, "length_m": length, "hull": hull, "speed": speed, "crew": crew,
        "module_slots": sc["module_slots"], "weapon_slots_str": sc["weapon_slots"],
        "total_alloy_cost": alloy_cost, "total_credit_cost": credit_cost,
        "armaments": armaments, "modules": modules,
        # A variant outside TYPE_MULTIPLIERS used to take 1.0 in silence; the
        # caller can see whether the code it named did anything.
        "type_multiplier": type_mult,
        "type_recognised": ship_type in TYPE_MULTIPLIERS,
    }

def roll_weapons(slot_specs: list[tuple[str, int]], weapon_pool: list[dict]) -> list[dict]:
    weapon_list = list(weapon_pool)
    armaments = []
    for size, count in slot_specs:
        pool = [w for w in weapon_list if w.get("slot_size") == size]
        if not pool:
            pool = [w for w in weapon_list if len(w.get("slot_size", "")) <= len(size)]
        if not pool:
            continue
        indices = list(range(len(pool)))
        for i in range(count):
            if not indices:
                indices = list(range(len(pool)))
            idx = random.choice(indices)
            w = pool[idx]
            armaments.append({"slot_index": i, "slot_size": size, "weapon_id": w["id"],
                              "weapon_name": w["name"], "kind": w["kind"],
                              "damage": w["damage"], "range_m": w.get("range_m", 0)})
            indices.remove(idx)
    return armaments

def roll_modules(module_slots: int, module_pool: list[dict]) -> list[dict]:
    if not module_pool:
        return []
    pool = sorted(module_pool, key=lambda m: (-m["grade"], m["name"]))
    picked = []
    cats = set()
    for m in pool:
        if len(picked) >= module_slots: break
        if m["category"] in cats: continue
        picked.append({"module_id": m["id"], "name": m["name"], "category": m["category"],
                       "effect_type": m["effect_type"], "effect_value": m.get("effect_value", 0.0),
                       "grade": m["grade"], "cost_alloys": m.get("cost_alloys", 0),
                       "cost_credits": m.get("cost_credits", 0)})
        cats.add(m["category"])
    if len(picked) < module_slots:
        for m in pool:
            if len(picked) >= module_slots: break
            if m["category"] in cats and random.random() < 1/3: continue
            if m["category"] not in cats: continue
            picked.append({"module_id": m["id"], "name": m["name"], "category": m["category"],
                           "effect_type": m["effect_type"], "effect_value": m.get("effect_value", 0.0),
                           "grade": m["grade"], "cost_alloys": m.get("cost_alloys", 0),
                           "cost_credits": m.get("cost_credits", 0)})
    return picked

async def generate_batch(class_name: str, tier: int, ship_type: str, count: int,
                          prefix: str = "", session_id: int | None = None) -> list[dict]:
    if count < 0:
        raise ValueError(f"count cannot be negative, got {count}")
    ships = []
    for i in range(count):
        name = f"{prefix} {i+1}" if prefix else None
        s = await generate_ship(class_name, tier, ship_type, name, session_id)
        ships.append(s)
    return ships

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    return {"status": "ship_generation_ready"}
