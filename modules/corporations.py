#!/usr/bin/env python3
"""
Corporations Module — Charters companies, assigns CEOs, and automates passive income/events.
Companies operate autonomously during ticks, generating resources or narrative events based on directives.
"""
from __future__ import annotations
import random
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info, error

INDUSTRIES = {
    "mining": {"yields": "alloys", "cost": 100000, "risk": 0.1},
    "manufacturing": {"yields": "credits", "cost": 150000, "risk": 0.05},
    "trade": {"yields": "credits", "cost": 200000, "risk": 0.15},
    "pmc": {"yields": "fleet", "cost": 250000, "risk": 0.2},
    "research": {"yields": "tech", "cost": 300000, "risk": 0.08},
}

VALID_CONTRACT_TYPES = ("resource_extraction", "production_boost", "privateering")


async def charter_company(name: str, industry: str, ceo_id: int = None,
                          session_id: int = None) -> dict:
    """Found a new company. Deducts founding cost from player treasury."""
    if session_id is None:
        session_id = Config.SESSION_ID
    if not name:
        return {"error": "Company name required."}
    if industry not in INDUSTRIES:
        return {"error": f"Invalid industry. Valid: {list(INDUSTRIES.keys())}"}

    cost = INDUSTRIES[industry]["cost"]

    # Transaction: deduct credits AND insert company atomically.
    async with Database.transaction() as conn:
        res = await conn.fetchrow(
            "SELECT credits FROM maya_rp.resources WHERE session_id=$1 FOR UPDATE",
            session_id)
        if not res or (res["credits"] or 0) < cost:
            return {"error": f"Insufficient funds. Need {cost:,}C"}

        await conn.execute(
            "UPDATE maya_rp.resources SET credits = credits - $1 WHERE session_id = $2",
            cost, session_id)

        gd = await conn.fetchval(
            "SELECT COALESCE(game_day, 1) FROM maya_rp.sessions WHERE id=$1",
            session_id) or 1

        corp_id = await conn.fetchval(
            """INSERT INTO maya_rp.corporations
               (session_id, name, industry, faction_id, ceo_character_id, tier,
                treasury, efficiency, standing, created_at_game_day)
               VALUES ($1, $2, $3, 1, $4, 1, 50000, 50, 50, $5) RETURNING id""",
            session_id, name, industry, ceo_id, gd)

    info("corporations", f"Chartered company: {name} ({industry})")
    return {"corp_id": corp_id, "name": name, "industry": industry, "cost": cost}


async def issue_directive(corp_id: int, contract_type: str, target_system: str = None,
                          duration_days: int = 30, session_id: int = None) -> dict:
    """Issue a directive (contract) to a company."""
    if session_id is None:
        session_id = Config.SESSION_ID
    if contract_type not in VALID_CONTRACT_TYPES:
        return {"error": f"Invalid contract type. Valid: {list(VALID_CONTRACT_TYPES)}"}
    duration_days = max(1, int(duration_days or 30))

    corp = await Database.fetchrow(
        "SELECT id, name, industry, efficiency FROM maya_rp.corporations "
        "WHERE id=$1 AND session_id=$2 AND status='active'",
        corp_id, session_id)
    if not corp:
        return {"error": "Company not found or inactive"}

    # Payout scales with efficiency (50 = baseline).
    eff_mult = (corp["efficiency"] or 50) / 50.0
    payout_c = int(random.randint(50000, 100000) * eff_mult)
    payout_a = int(random.randint(1000, 5000) * eff_mult) if corp["industry"] == "mining" else 0

    cid = await Database.fetchval(
        """INSERT INTO maya_rp.corporate_contracts
           (session_id, corp_id, contract_type, target_system,
            payout_credits, payout_alloys, duration_days, days_remaining, status)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $7, 'active') RETURNING id""",
        session_id, corp_id, contract_type, target_system,
        payout_c, payout_a, duration_days)

    info("corporations", f"Directive: {corp['name']} → {contract_type} ({duration_days}d)")
    return {"contract_id": cid, "corp": corp["name"],
            "expected_payout": {"credits": payout_c, "alloys": payout_a},
            "duration_days": duration_days}


async def run_tick(session_id: int | None = None) -> dict[str, Any]:
    """Corporation tick: process active contracts, generate yields, trigger events."""
    if session_id is None:
        session_id = Config.SESSION_ID

    try:
        contracts = await Database.fetch(
            """SELECT cc.id, cc.corp_id, cc.contract_type, cc.target_system,
                      cc.payout_credits, cc.payout_alloys, cc.days_remaining,
                      c.name AS corp_name, c.industry, c.efficiency, c.standing
               FROM maya_rp.corporate_contracts cc
               JOIN maya_rp.corporations c ON cc.corp_id = c.id
               WHERE cc.session_id = $1 AND cc.status = 'active'""",
            session_id)

        completed = 0
        credits_gained = 0
        alloys_gained = 0
        events = []

        for con in contracts:
            days_left = con["days_remaining"] - 1
            if days_left <= 0:
                # Contract complete — pay out to player.
                await Database.execute(
                    "UPDATE maya_rp.resources SET credits = credits + $1, "
                    "alloys = alloys + $2 WHERE session_id = $3",
                    con["payout_credits"], con["payout_alloys"], session_id)
                await Database.execute(
                    "UPDATE maya_rp.corporate_contracts SET status = 'completed' "
                    "WHERE id = $1", con["id"])
                completed += 1
                credits_gained += con["payout_credits"]
                alloys_gained += con["payout_alloys"]

                # Success boosts standing + efficiency.
                await Database.execute(
                    "UPDATE maya_rp.corporations SET "
                    "standing = LEAST(100, standing + 2), "
                    "efficiency = LEAST(100, efficiency + 1) WHERE id = $1",
                    con["corp_id"])
                events.append(
                    f"{con['corp_name']} completed a {con['contract_type']} contract. "
                    f"+{con['payout_credits']:,}C deposited.")
            else:
                await Database.execute(
                    "UPDATE maya_rp.corporate_contracts SET days_remaining = $1 "
                    "WHERE id = $2", days_left, con["id"])

                # Random corporate event.
                risk = INDUSTRIES.get(con["industry"], {}).get("risk", 0.1)
                if random.random() < risk:
                    event_type = random.choice(["labor_dispute", "breakthrough", "market_shift"])
                    if event_type == "labor_dispute":
                        await Database.execute(
                            "UPDATE maya_rp.corporations SET "
                            "efficiency = GREATEST(10, efficiency - 5) WHERE id = $1",
                            con["corp_id"])
                        events.append(f"Labor dispute at {con['corp_name']}. Efficiency dropped.")
                    elif event_type == "breakthrough":
                        bonus = int(con["payout_credits"] * 0.1)
                        await Database.execute(
                            "UPDATE maya_rp.resources SET credits = credits + $1 "
                            "WHERE session_id = $2", bonus, session_id)
                        events.append(
                            f"{con['corp_name']} reported a breakthrough! "
                            f"Bonus {bonus:,}C injected.")

        # Log aggregate corporate dispatch.
        if events:
            summary = " | ".join(events[:3])
            await Database.execute(
                """INSERT INTO maya_rp.events (session_id, happened_at, event_type, title, description, importance, tags)
                   VALUES ($1, NOW(), 'corporate', 'Corporate Dispatch', $2, 2, '["corporation","economy"]'::jsonb)""",
                session_id, summary)

        info("corporations",
             f"Tick: {len(contracts)} active, {completed} completed. "
             f"Gained {credits_gained:,}C/{alloys_gained:,}A")
        return {"active_contracts": len(contracts), "completed": completed,
                "credits_gained": credits_gained, "alloys_gained": alloys_gained}

    except Exception as e:
        error("corporations", f"Tick error: {e}")
        return {"error": str(e)}
