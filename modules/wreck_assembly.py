#!/usr/bin/env python3
"""Wreck Assembly — Pasang kapal baru dari serpihan wreck (novel bab 7 — "Blizzard Zero").

Doktrin:
- Spec Clarity: semua nombor dari DB, konsisten, boleh verify.
- Stakes Integrity: roll boleh GAGAL (d100 vs 60 + skill*5). Gagal = modules tak aktif (-50% power).
- Tier Integrity: hasil bergantung pada wreck tier/hull/power sebenar, bukan plot.
"""
from __future__ import annotations
import random
from core.db import Database
from core.log import info

DEFAULT_LOCATION = "Heaven Yard — Assembly Bay"


async def list_wrecks(session_id: int) -> list:
    """Senarai wreck yang masih available."""
    return await Database.fetch(
        "SELECT id, name, tier, hull, power_rating, sub_class FROM maya_rp.wreck_inventory "
        "WHERE session_id=$1 AND status='available' ORDER BY hull DESC",
        session_id,
    )


async def add_wreck(session_id: int, name: str, tier: int, hull: int, power_rating: int,
                    sub_class: str, source_ship_id: int | None = None) -> dict:
    """Tambah wreck ke inventory (dari salvage/debris)."""
    if not (name or "").strip():
        return {"error": "Wreck needs a name."}
    try:
        tier, hull, power_rating = int(tier), int(hull), int(power_rating)
    except (TypeError, ValueError):
        return {"error": f"tier/hull/power must be whole numbers, got {tier}/{hull}/{power_rating}"}
    if tier < 1:
        return {"error": f"Wreck tier must be at least 1, got {tier}"}
    if hull < 0 or power_rating < 0:
        # A negative hull became a ship with negative hull and negative hull_current,
        # because assemble() derives the new hull from the wreck's.
        return {"error": f"Wreck hull and power cannot be negative, got {hull}/{power_rating}"}
    wid = await Database.fetchval(
        """INSERT INTO maya_rp.wreck_inventory (session_id, source_ship_id, name, tier, hull, power_rating, sub_class)
           VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id""",
        session_id, source_ship_id, name, tier, hull, power_rating, sub_class,
    )
    info("wreck_assembly", f"Wreck added: {name} (T{tier}, hull {hull})")
    return {"wreck_id": wid, "name": name}


async def assemble(session_id: int, name: str, wreck_ids: list[int],
                   engineering_skill: int = 5, location: str = DEFAULT_LOCATION) -> dict:
    """Pasang kapal baru dari 2-5 wrecks. Gagal = power -50% (Stakes Integrity)."""
    if not (2 <= len(wreck_ids) <= 5):
        return {"error": "Memerlukan 2-5 wrecks untuk assemble."}
    try:
        engineering_skill = int(engineering_skill)
    except (TypeError, ValueError):
        return {"error": f"engineering skill must be a whole number, got {engineering_skill!r}"}
    if engineering_skill < 0:
        return {"error": f"engineering skill cannot be negative, got {engineering_skill}"}

    wrecks = await Database.fetch(
        "SELECT * FROM maya_rp.wreck_inventory WHERE id = ANY($1::int[]) AND session_id=$2 AND status='available'",
        wreck_ids, session_id,
    )
    if len(wrecks) != len(wreck_ids):
        return {"error": "Sesetengah wrecks tidak dijumpai atau telah digunakan."}

    # Spec Clarity: hull 90% dari wreck terbesar + 10% setiap wreck tambahan
    wrecks_sorted = sorted(wrecks, key=lambda x: x['hull'], reverse=True)
    primary = wrecks_sorted[0]
    base_hull = int(primary['hull'] * 0.9)
    hull_bonus = sum(int(w['hull'] * 0.1) for w in wrecks_sorted[1:])
    final_hull = base_hull + hull_bonus

    # Power inherit dari power_rating tertinggi
    power_wreck = max(wrecks, key=lambda x: x['power_rating'])
    final_power = power_wreck['power_rating']
    sub_class = primary['sub_class']
    tier = primary['tier']

    # Stakes Integrity: roll boleh gagal
    roll = random.randint(1, 100)
    target = 60 + (engineering_skill * 5)
    success = roll <= target

    if not success:
        final_power = int(final_power * 0.5)  # modules tak aktif
        status_msg = f"GAGAL: Modules tidak aktif (roll {roll} vs {target}). Power dikurangkan 50%."
    else:
        status_msg = f"BERJAYA: Semua sistem aktif (roll {roll} vs {target})."

    # PG Before Mouth: insert ke ships
    ship_id = await Database.fetchval(
        """INSERT INTO maya_rp.ships (session_id, name, ship_type, tier, hull, hull_current, power_rating,
                                      sub_class, status, location)
           VALUES ($1, $2, 'Assembled', $3, $4, $4, $5, $6, 'active', $7) RETURNING id""",
        session_id, name, tier, final_hull, final_power, sub_class, location,
    )

    # Tandakan wreck sebagai used
    await Database.execute(
        "UPDATE maya_rp.wreck_inventory SET status='used' WHERE id = ANY($1::int[]) "
        "AND session_id=$2",
        wreck_ids, session_id,
    )

    # Event log (spec clarity: nombor nyata)
    await Database.execute(
        """INSERT INTO maya_rp.events (session_id, event_type, title, description, importance, tags)
           VALUES ($1, 'build', $2, $3, 4, '["assembly", "ship"]'::jsonb)""",
        session_id,
        f"Ship Assembled: {name}",
        f"{status_msg} Hull: {final_hull:,}, Power: {final_power:,}. Dibina dari {len(wrecks)} wrecks "
        f"({', '.join(w['name'] for w in wrecks)}).",
    )

    info("wreck_assembly", f"Assembled {name} (Hull {final_hull}, Power {final_power}, success={success})")
    return {
        "ship_id": ship_id, "name": name, "hull": final_hull, "power": final_power,
        "success": success, "roll": roll, "target": target,
    }


async def cmd(sid: int, action: str, params: dict) -> dict:
    if action == "list":
        return {"wrecks": [dict(w) for w in await list_wrecks(sid)]}
    if action == "add":
        return await add_wreck(sid, params["name"], params.get("tier", 1), params.get("hull", 0),
                               params.get("power", 0), params.get("sub_class", "Wreck"),
                               params.get("source_ship_id"))
    if action == "assemble":
        return await assemble(sid, params.get("name", "Assembled Ship"),
                              params.get("wreck_ids", []), params.get("skill", 5),
                              params.get("location", DEFAULT_LOCATION))
    return {"error": f"Unknown action '{action}' (available: list, add, assemble)"}


async def run_tick(session_id: int = None) -> dict:
    return {"status": "wreck_assembly_ready"}
