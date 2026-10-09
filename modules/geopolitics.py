#!/usr/bin/env python3
"""Background Geopolitics — factions fight/trade with each other off-screen."""
from __future__ import annotations
import json, random
from typing import Any
from core.db import Database
from core.log import info
from core.session import require_session

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = require_session(None)
    factions = await Database.fetch("SELECT id,name,standing,economic_strength,pirate_fleet_power,reputation FROM maya_rp.factions WHERE session_id=$1 AND name!='Setia Empire' ORDER BY id", session_id)
    events = 0
    for i, fa in enumerate(factions):
        for j, fb in enumerate(factions):
            if i >= j: continue
            if random.random() > 0.1: continue
            # A pair is stored in either order; the row written as (fa, fb) wins over its mirror.
            rel = await Database.fetchrow(
                "SELECT standing FROM maya_rp.faction_relations WHERE session_id=$1 "
                "AND ((faction_a=$2 AND faction_b=$3) OR (faction_a=$3 AND faction_b=$2)) "
                "ORDER BY (faction_a=$2) DESC LIMIT 1",
                session_id, fa["id"], fb["id"])
            stand = rel["standing"] if rel else "neutral"
            desc = ""
            imp = 1
            if stand == "hostile" and random.random() < 0.3:
                winner = fa if random.random() > 0.5 else fb
                losr = fb if winner["id"]==fa["id"] else fa
                desc = f"Intelligence: {winner['name']} forces engaged {losr['name']} in a border skirmish. {winner['name']} claims victory."
                imp = 2
            elif stand == "neutral" and random.random() < 0.4:
                desc = f"Trade convoy spotted between {fa['name']} and {fb['name']} territory."
            elif stand in ("ally", "allied"):
                desc = f"Joint fleet maneuvers detected: {fa['name']} & {fb['name']}."
            if desc:
                await Database.execute("INSERT INTO maya_rp.events(session_id,happened_at,event_type,title,description,tags,importance) VALUES($1,NOW(),'geopolitics',$2,$3,$4,$5)", session_id,desc[:80],desc,'["geopolitics","background"]',imp)
                events += 1

    # NOVEL ULTIMATE #3 — Dual POV Intel: faction power spike → schedule incoming raid
    # Novel: "Meanwhile, the enemy fleet drops out of FTL..." — POV musuh = ancaman nyata.
    for fa in factions:
        power = fa["pirate_fleet_power"] or 0
        if power > 5000 and fa["standing"] == "hostile" and random.random() < 0.3:
            target = await Database.fetchrow(
                "SELECT id, system_name FROM maya_rp.territory WHERE session_id=$1 "
                "AND controlling_faction='Setia Empire' ORDER BY RANDOM() LIMIT 1", session_id)
            if target:
                eta = random.randint(3, 10)
                # One pending raid per faction and target: ticks_remaining > 0 and not responded.
                tag = await Database.execute(
                    "INSERT INTO maya_rp.incoming_raids (session_id, faction_name, target_system, enemy_power, "
                    "ticks_remaining, detected, target_territory_id) "
                    "SELECT $1::int, $2::text, $3::text, $4::int, $5::int, false, $6::int "
                    "WHERE NOT EXISTS (SELECT 1 FROM maya_rp.incoming_raids WHERE session_id=$1::int "
                    "AND faction_name=$2::text AND target_system=$3::text AND ticks_remaining > 0 "
                    "AND COALESCE(player_responded, false) = false)",
                    session_id, fa["name"], target["system_name"],
                    int(power * random.uniform(0.6, 1.0)), eta, target["id"])
                if str(tag).endswith(" 1"):
                    events += 1
    # Escalation engine (2026-08-14): hot relations without an active war
    # occasionally tip into open conflict (border war rows, conservative).
    hot = await Database.fetch(
        "SELECT faction_a, faction_b, military_tension FROM maya_rp.faction_relations "
        "WHERE session_id=$1 AND military_tension >= 0.8", session_id)
    for r in hot:
        existing = await Database.fetchval(
            "SELECT COUNT(*) FROM maya_rp.wars WHERE session_id=$1 AND status='active' "
            "AND (opponent_faction=(SELECT name FROM maya_rp.factions WHERE id=$2 AND session_id=$1) "
            "OR opponent_faction=(SELECT name FROM maya_rp.factions WHERE id=$3 AND session_id=$1))",
            session_id, r["faction_a"], r["faction_b"])
        if not existing and random.random() < 0.02:
            fa = await Database.fetchrow(
                "SELECT name FROM maya_rp.factions WHERE id=$1 AND session_id=$2",
                r["faction_a"], session_id)
            fb = await Database.fetchrow(
                "SELECT name FROM maya_rp.factions WHERE id=$1 AND session_id=$2",
                r["faction_b"], session_id)
            if fa and fb:
                game_day = await Database.fetchval("SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id)
                await Database.execute(
                    "INSERT INTO maya_rp.wars (session_id, opponent_faction, casus_belli, war_goal, phase, status, started_at_game_day) "
                    "VALUES ($1,$2,$3,$4,'escalation','active',$5)",
                    session_id, fb["name"],
                    f"border tension with {fa['name']}",
                    f"contain {fa['name']} border pressure",
                    game_day)
                await Database.execute(
                    "INSERT INTO maya_rp.events (session_id, happened_at, event_type, title, description, tags, importance) "
                    "VALUES ($1, NOW(), 'war', $2, $3, $4, 4)",
                    session_id, f"Border war: {fa['name']} vs {fb['name']}",
                    f"Military tension between {fa['name']} and {fb['name']} has boiled over.",
                    '["geopolitics","war"]')
                events += 1
    return {"events_generated":events}
