#!/usr/bin/env python3
"""Duel — Formal 1v1 ship duel dengan stakes (novel bab 13-17 — "Bald Eagle vs Blizzard Zero").

Doktrin:
- Tier Integrity: win chance = math power_ratio, bukan plot.
- Stakes Integrity: roll boleh kalah; stakes benar-benar dipindah; kapal boleh musnah.
- Spec Clarity: semua angka (hull, power) dari DB, dilaporkan penuh.
"""
from __future__ import annotations
import random
from core.db import Database
from core.log import info


async def challenge(session_id: int, player_ship_id: int, opponent: dict, stakes: dict,
                    venue: str = "Open Space") -> dict:
    """Daftarkan duel formal. opponent: {name, tier, hull, power}. stakes: {type, value}."""
    duel_id = await Database.fetchval(
        """INSERT INTO maya_rp.duels (session_id, player_ship_id, opponent_name, opponent_tier,
                                      opponent_hull, opponent_power, stakes_type, stakes_value, venue, status)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'pending') RETURNING id""",
        session_id, player_ship_id, opponent["name"], opponent["tier"], opponent["hull"],
        opponent["power"], stakes["type"], str(stakes["value"]), venue,
    )
    info("duel", f"Challenge issued: {opponent['name']} (T{opponent['tier']}, power {opponent['power']})")
    return {"duel_id": duel_id, "status": "pending", "message": f"Challenge issued to {opponent['name']}."}


async def resolve(session_id: int, duel_id: int) -> dict:
    """Resolve duel: roll vs win_chance (math power_ratio), stakes transfer, damage applied."""
    d = await Database.fetchrow(
        "SELECT * FROM maya_rp.duels WHERE id=$1 AND session_id=$2 AND status='pending'",
        duel_id, session_id,
    )
    if not d:
        return {"error": "Duel tidak dijumpai atau sudah selesai"}

    ship = await Database.fetchrow(
        "SELECT * FROM maya_rp.ships WHERE id=$1 AND session_id=$2", d["player_ship_id"], session_id,
    )
    if not ship or ship["status"] == "destroyed":
        return {"error": "Kapal pemain tidak aktif atau musnah"}

    # Tier Integrity: math, bukan vibe
    pp = ship["power_rating"]
    ep = d["opponent_power"]
    power_ratio = pp / max(1, ep)
    win_chance = max(5, min(95, 50 + (power_ratio - 1) * 40))
    roll = random.randint(1, 100)
    win = roll <= win_chance

    hull = ship["hull"]
    hull_current = ship["hull_current"] if ship["hull_current"] is not None else hull

    if win:
        if roll <= win_chance * 0.3:
            result = "victory_clean"
            hull_damage = random.randint(0, max(1, int(hull * 0.1)))
        else:
            result = "victory_crippled"
            hull_damage = random.randint(int(hull * 0.3), int(hull * 0.6))
    else:
        if roll >= win_chance + 30:
            result = "defeat_destroyed"
            hull_damage = hull  # kapal musnah
        else:
            result = "defeat_survive"
            hull_damage = random.randint(int(hull * 0.5), int(hull * 0.9))

    # Apply damage ke hull_current (Spec Clarity)
    new_hull = max(0, hull_current - hull_damage)
    if new_hull == 0:
        status = "destroyed"
    elif new_hull < hull * 0.5:
        status = "damaged"
    else:
        status = "active"
    await Database.execute(
        "UPDATE maya_rp.ships SET hull_current=$1, status=$2 WHERE id=$3",
        new_hull, status, ship["id"],
    )

    # Stakes transfer (Stakes Integrity — benar-benar pindah)
    stakes_msg = ""
    if d["stakes_type"] == "credits":
        amount = int(d["stakes_value"] or 0)
        if win:
            await Database.execute(
                "UPDATE maya_rp.resources SET credits=credits+$1 WHERE session_id=$2", amount, session_id)
            stakes_msg = f"Menang {amount:,} credits."
        else:
            await Database.execute(
                "UPDATE maya_rp.resources SET credits=GREATEST(0, credits-$1) WHERE session_id=$2",
                amount, session_id)
            stakes_msg = f"Hilang {amount:,} credits."
    elif d["stakes_type"] == "favor":
        stakes_msg = f"Favor {'menang' if win else 'hilang'} dalam duel."

    await Database.execute(
        "UPDATE maya_rp.duels SET status='resolved', result=$1, resolved_at=NOW() WHERE id=$2",
        result, duel_id,
    )

    # Event + news (spec clarity: nombor penuh)
    desc = (f"{ship['name']} ({ship['sub_class']}, T{ship['tier']}, power {pp:,}) vs "
            f"{d['opponent_name']} (T{d['opponent_tier']}, power {ep:,}). "
            f"{'MENANG' if win else 'KALAH'} — {result.replace('_', ' ').title()}. "
            f"Roll {roll} vs {win_chance:.0f}%. Hull: {new_hull:,}/{hull:,}. {stakes_msg}")
    await Database.execute(
        "INSERT INTO maya_rp.events (session_id, event_type, title, description, importance) "
        "VALUES ($1, 'duel', $2, $3, 4)",
        session_id, f"Duel: {ship['name']} vs {d['opponent_name']}", desc,
    )
    await Database.execute(
        "INSERT INTO maya_rp.news_articles (session_id, tick_number, headline, body, category, faction_bias, importance, read, game_day) "
        "VALUES ($1, 1, $2, $3, 'military', 0, 3, false, (SELECT game_day FROM maya_rp.sessions WHERE id=$1))",
        session_id, f"DUEL: {ship['name']} vs {d['opponent_name']}", desc,
    )

    info("duel", f"Duel {duel_id}: {result} (roll {roll} vs {win_chance:.0f}%)")
    return {"result": result, "hull_remaining": new_hull, "stakes": stakes_msg, "roll": roll, "win_chance": round(win_chance, 1)}


async def cmd(sid: int, action: str, params: dict) -> dict:
    if action == "challenge":
        return await challenge(sid, params["player_ship_id"], params["opponent"],
                               params.get("stakes", {"type": "favor", "value": 0}),
                               params.get("venue", "Open Space"))
    if action == "resolve":
        return await resolve(sid, params["duel_id"])
    if action == "list":
        duels = await Database.fetch(
            "SELECT id, player_ship_id, opponent_name, opponent_tier, stakes_type, status, result, created_at "
            "FROM maya_rp.duels WHERE session_id=$1 ORDER BY created_at DESC LIMIT 10", sid)
        return {"duels": [dict(d) for d in duels]}
    return {"error": f"Unknown action '{action}' (available: challenge, resolve, list)"}


async def run_tick(session_id: int = None) -> dict:
    return {"status": "duel_ready"}
