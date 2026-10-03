#!/usr/bin/env python3
"""Fleet Management — Ported from Rust fleet.rs. Create, assign, list, battle."""
from __future__ import annotations
import random, math
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info

FORMATION_MULT = {
    "wall": (0.90, 1.25), "crescent": (1.15, 0.90), "spearhead": (1.30, 0.80),
    "screen": (0.85, 1.05), "arrow": (1.10, 0.95), "scatter": (1.00, 1.15),
}

# The tactics the battle multipliers below name. Anything else fights at the
# balanced rate, which used to happen without a word.
TACTIC_NAMES = frozenset({
    "blitz", "strike", "overwhelm", "speed", "mobility", "flank",
    "defense", "hold", "patrol", "standard", "balanced",
})

async def create_fleet(name: str, formation: str = "spearhead", session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    if formation not in FORMATION_MULT:
        # The schema allows exactly the six in FORMATION_MULT, and the CLI says so.
        # An unknown name used to be stored and then fight at 1.0/1.0 in silence.
        return {"error": f"Unknown formation {formation!r}: use one of "
                         f"{', '.join(sorted(FORMATION_MULT))}"}
    if not (name or "").strip():
        return {"error": "Fleet needs a name."}
    exists = await Database.fetchval(
        "SELECT EXISTS(SELECT 1 FROM maya_rp.fleets WHERE session_id=$1 AND name=$2)", session_id, name)
    if exists: return {"error": f"Fleet '{name}' already exists"}
    await Database.execute(
        "INSERT INTO maya_rp.fleets (session_id, name, formation) VALUES ($1,$2,$3)",
        session_id, name, formation)
    info("fleet", f"Created fleet '{name}' [{formation}]")
    return {"fleet": name, "formation": formation}

async def assign_ship(ship_name: str, fleet_name: str, position: int = 0, session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    sid = await Database.fetchval(
        "SELECT id FROM maya_rp.ships WHERE session_id=$1 AND LOWER(name) LIKE LOWER($2) LIMIT 1",
        session_id, f"%{ship_name}%")
    if not sid: return {"error": f"Ship '{ship_name}' not found"}
    fid = await Database.fetchval(
        "SELECT id FROM maya_rp.fleets WHERE session_id=$1 AND LOWER(name) LIKE LOWER($2) LIMIT 1",
        session_id, f"%{fleet_name}%")
    if not fid: return {"error": f"Fleet '{fleet_name}' not found"}
    await Database.execute(
        "INSERT INTO maya_rp.fleet_members (fleet_id, ship_id, position) VALUES ($1,$2,$3) "
        "ON CONFLICT (fleet_id, ship_id) DO UPDATE SET position=$3", fid, sid, position)
    return {"assigned": True, "ship": ship_name, "fleet": fleet_name, "position": position}

async def list_fleets(session_id: int | None = None) -> list[dict]:
    if session_id is None: session_id = Config.SESSION_ID
    fleets = await Database.fetch(
        "SELECT f.id, f.name, f.formation, f.status, s.name AS flagship "
        "FROM maya_rp.fleets f LEFT JOIN maya_rp.ships s ON f.flagship_id=s.id "
        "WHERE f.session_id=$1 ORDER BY f.name", session_id)
    result = []
    for f in fleets:
        members = await Database.fetch(
            "SELECT s.name FROM maya_rp.fleet_members fm JOIN maya_rp.ships s ON fm.ship_id=s.id "
            "WHERE fm.fleet_id=$1 AND s.session_id=$2 ORDER BY fm.position", f["id"], session_id)
        power = await Database.fetchval(
            "SELECT COALESCE(SUM(s.power_rating),0) FROM maya_rp.fleet_members fm "
            "JOIN maya_rp.ships s ON fm.ship_id=s.id WHERE fm.fleet_id=$1 AND s.session_id=$2",
            f["id"], session_id) or 0
        result.append({"id": f["id"], "name": f["name"], "formation": f["formation"],
                       "status": f["status"], "flagship": f["flagship"],
                       "members": [m["name"] for m in members], "power": power})
    return result

async def fleet_battle(fleet_name: str, tactic: str, threat: str, session_id: int | None = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    fleet = await Database.fetchrow(
        "SELECT id, name, formation FROM maya_rp.fleets WHERE session_id=$1 AND LOWER(name) LIKE LOWER($2) LIMIT 1",
        session_id, f"%{fleet_name}%")
    if not fleet: return {"error": f"Fleet '{fleet_name}' not found"}

    ships = await Database.fetch(
        "SELECT s.id, s.name, s.hull_current, s.hull, s.speed, s.tier, s.power_rating FROM maya_rp.fleet_members fm "
        "JOIN maya_rp.ships s ON fm.ship_id=s.id WHERE fm.fleet_id=$1 AND s.status='active' ORDER BY fm.position",
        fleet["id"])
    if not ships: return {"error": f"No active ships in '{fleet_name}'"}

    f_off, f_def = FORMATION_MULT.get(fleet["formation"], (1.0, 1.0))
    if tactic not in TACTIC_NAMES:
        info("fleet", f"Tactic {tactic!r} is not one of {sorted(TACTIC_NAMES)}; "
                      f"the battle uses the balanced multipliers")
    tactic_off = 1.25 if tactic in ("blitz","strike","overwhelm") else 1.15 if tactic in ("speed","mobility","flank") else 0.90 if tactic in ("defense","hold") else 1.05
    tactic_def = 0.70 if tactic in ("blitz","overwhelm") else 0.85 if tactic in ("patrol","standard") else 0.90

    player_power = sum((s["power_rating"] or s["hull_current"]) * f_off * tactic_off + s["speed"] * 5 * f_def * tactic_def for s in ships)
    enemy_count = random.randint(1, 5)
    enemy_power = sum(400 + random.random() * 600 for _ in range(enemy_count)) * (0.85 + random.random() * 0.3)

    dmg_dealt = (player_power / max(enemy_power, 1)) ** 0.65 * 100
    dmg_taken = (enemy_power / max(player_power, 1)) ** 0.65 * 100

    fuel_cost = round(len(ships) * 10 * (1 + dmg_taken / 200))
    fuel_paid = await Database.fetchrow(
        "UPDATE maya_rp.resources SET fuel = GREATEST(fuel - $1, 0) WHERE session_id = $2 "
        "RETURNING fuel",
        fuel_cost, session_id)
    if fuel_paid is None:
        # A session with no resources row burned no fuel and said nothing. Session 5
        # is that session today.
        info("fleet", f"Battle for {fleet_name}: no resources row for session {session_id}, "
                      f"{fuel_cost} fuel not spent")

    outcomes = [(120, "Decisive Victory"), (80, "Clear Victory"), (50, "Marginal Victory"), (30, "Skirmish"), (0, "Inconclusive")]
    outcome = next(o for t, o in outcomes if dmg_dealt >= t)

    player_lost = 0
    for s in ships:
        dmg = round(dmg_taken / max(len(ships), 1) * (0.5 + random.random() * 0.5))
        new_hull = max(0, s["hull_current"] - dmg)
        if new_hull <= 0: player_lost += 1
        status = "derelict" if new_hull <= 0 else "damaged" if new_hull < s["hull"] / 2 else "active"
        await Database.execute(
            "UPDATE maya_rp.ships SET hull_current=$1, status=$2 WHERE id=$3 AND session_id=$4",
            new_hull, status, s["id"], session_id)

    enemy_lost = round(dmg_dealt / 40 * random.random())
    await Database.execute(
        "INSERT INTO maya_rp.events (session_id, event_type, title, description, tags) VALUES "
        "($1,'battle',$2,$3,'[\"fleet\",\"combat\"]'::jsonb)",
        session_id, f"Fleet Battle: {fleet_name} vs {threat}",
        f"Outcome: {outcome}. Player lost {player_lost}/{len(ships)} ships. Enemy lost {enemy_lost} ships. Fuel: -{fuel_cost}.")

    info("fleet", f"Battle: {fleet_name} vs {threat} -> {outcome}")
    return {"outcome": outcome, "player_lost": player_lost, "total_ships": len(ships),
            "enemy_lost": enemy_lost, "fuel_cost": fuel_cost, "player_power": round(player_power),
            "enemy_power": round(enemy_power)}

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    fleets = await list_fleets(session_id)
    info("fleet", f"Tick: {len(fleets)} fleets")
    return {"fleets": len(fleets)}
