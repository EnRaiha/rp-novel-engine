#!/usr/bin/env python3
"""
Corporations Module — Charters companies, assigns CEOs, and automates passive income/events.
Companies operate autonomously during ticks, generating resources or narrative events based on directives.
"""
from __future__ import annotations
import random
from typing import Any
from core.db import Database
from core.log import info, error
from core.session import require_session


def _writable_session(session_id: int | None) -> int:
    """Resolve the session for one call and refuse a frozen campaign.

    Sessions 3 and 5 are reference data; a writer that skipped this check mutated them.

    @param session_id - caller's session; `None` resolves through `core.session.require_session`.
    @returns the resolved session id.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    from core.ooc import _refuse_frozen

    sid = require_session(session_id)
    _refuse_frozen(sid)
    return sid


class _Abort(Exception):
    """Roll the open transaction back and hand `payload` to the caller as the answer."""

    def __init__(self, payload: dict):
        super().__init__(payload.get("error", "aborted"))
        self.payload = payload

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
    """Found a new company. Deducts founding cost from player treasury.

    The debit is a guarded UPDATE (`credits >= cost`) in the same transaction as the company insert.

    @param session_id - campaign; `None` resolves through `require_session`.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
    if not name:
        return {"error": "Company name required."}
    if industry not in INDUSTRIES:
        return {"error": f"Invalid industry. Valid: {list(INDUSTRIES.keys())}"}

    cost = INDUSTRIES[industry]["cost"]

    # Transaction: deduct credits AND insert company atomically.
    async with Database.transaction() as conn:
        debited = await conn.fetchrow(
            "UPDATE maya_rp.resources SET credits = credits - $1 "
            "WHERE session_id = $2 AND credits >= $1 RETURNING credits",
            cost, session_id)
        if debited is None:
            return {"error": f"Insufficient funds. Need {cost:,}C"}

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
    """Issue a directive (contract) to a company.

    @param session_id - campaign; `None` resolves through `require_session`.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
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
    """Corporation tick: process active contracts, generate yields, trigger events.

    A completion claims the contract (`active` to `completed`) first, then pays, in one transaction.
    The payout and the status used to be two statements, so an error between them paid the contract
    again on the next tick. A NULL payout column reads as 0: `credits + NULL` is NULL and wiped the
    treasury.

    @param session_id - campaign; `None` resolves through `require_session`.
    @returns tick counters, or `{error}` when a query raises.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)

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
        unknown_industries: set[str] = set()

        for con in contracts:
            days_left = con["days_remaining"] - 1
            payout_c = con["payout_credits"] or 0
            payout_a = con["payout_alloys"] or 0
            if days_left <= 0:
                # Contract complete — claim it, then pay out to player, in one transaction.
                async with Database.transaction() as conn:
                    claimed = await conn.fetchval(
                        "UPDATE maya_rp.corporate_contracts SET status = 'completed' "
                        "WHERE id = $1 AND status = 'active' RETURNING id", con["id"])
                    if claimed is None:
                        continue
                    paid = await conn.fetchval(
                        "UPDATE maya_rp.resources SET credits = credits + $1, "
                        "alloys = alloys + $2 WHERE session_id = $3 RETURNING credits",
                        payout_c, payout_a, session_id)
                    # Success boosts standing + efficiency.
                    await conn.execute(
                        "UPDATE maya_rp.corporations SET "
                        "standing = LEAST(100, standing + 2), "
                        "efficiency = LEAST(100, efficiency + 1) WHERE id = $1",
                        con["corp_id"])
                completed += 1
                if paid is None:
                    info("corporations",
                         f"Contract {con['id']} completed but session {session_id} has no resources row; "
                         f"{payout_c:,}C not paid")
                    events.append(f"{con['corp_name']} completed a {con['contract_type']} contract. "
                                  f"No treasury row: payout not deposited.")
                    continue
                credits_gained += payout_c
                alloys_gained += payout_a
                events.append(
                    f"{con['corp_name']} completed a {con['contract_type']} contract. "
                    f"+{payout_c:,}C deposited.")
            else:
                await Database.execute(
                    "UPDATE maya_rp.corporate_contracts SET days_remaining = $1 "
                    "WHERE id = $2", days_left, con["id"])

                # Random corporate event.
                industry = con["industry"]
                spec = INDUSTRIES.get(industry)
                if spec is None:
                    # Fifteen of the twenty industries on live rows are not in this
                    # table (smuggling, banking, insurance, ...), so the default risk
                    # silently covered almost every corporation. Said once per tick.
                    if industry not in unknown_industries:
                        unknown_industries.add(industry)
                        info("corporations",
                             f"Industry {industry!r} is not in INDUSTRIES; event risk reads 0.1")
                    spec = {}
                risk = spec.get("risk", 0.1)
                if random.random() < risk:
                    event_type = random.choice(["labor_dispute", "breakthrough", "market_shift"])
                    if event_type == "labor_dispute":
                        await Database.execute(
                            "UPDATE maya_rp.corporations SET "
                            "efficiency = GREATEST(10, efficiency - 5) WHERE id = $1",
                            con["corp_id"])
                        events.append(f"Labor dispute at {con['corp_name']}. Efficiency dropped.")
                    elif event_type == "breakthrough":
                        bonus = int(payout_c * 0.1)
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


# ═══════════════════════════════════════════════════════════════
# NOVEL ADAPTATION — BLUEPRINT MARKET (novel bab 22-23, 171)
# Jual tech yang dah unlocked → modal. Data redacted = buyer kena R&D sendiri.
# ═══════════════════════════════════════════════════════════════

async def list_saleable_blueprints(session_id: int | None = None) -> list[dict]:
    """The blueprints on the market.

    `maya_rp.research_projects` carries no session_id, so the catalogue is
    galaxy-wide and the session argument is interface parity, not a filter.
    """
    rows = await Database.fetch(
        "SELECT id, name, field, effect_type, effect_value, blueprint_price FROM maya_rp.research_projects "
        "WHERE unlocked=true AND saleable=true ORDER BY blueprint_price DESC")
    return [dict(r) for r in rows]


async def sell_blueprint(session_id: int | None, project_id: int, buyer: str = "Iron Concord",
                         markdown_pct: float = 20) -> dict:
    """Jual blueprint (80% data, redacted) ke faction. Buyer bayar; kita simpan tech.
    Redacted = buyer dapat tech, tapi perlu R&D sendiri untuk full spec (novel bab 23).

    `markdown_pct` is a PERCENTAGE, 0..100, which is what `cli.py craft sell` passes
    and what its usage line calls it. The body used to multiply `1 - markdown_pct`,
    so the documented `20` became `1 - 20 = -19`: the sale paid the buyer 19 times
    the blueprint's price and drained the player treasury by the same amount.

    The buyer is charged first with a guarded UPDATE (`treasury >= price`); no row means the faction
    does not exist in this session or cannot pay, and the sale aborts. The player was credited the
    full price in every case, so an unknown buyer minted money and a poor buyer paid only what it
    had. The charge, the credit, the ledger contract and the event share one transaction.

    @param session_id - campaign; `None` resolves through `require_session`.
    @param project_id - `research_projects.id`.
    @param buyer - faction name in this session.
    @param markdown_pct - discount for the redacted data, 0..100.
    @returns the sale record, or `{error}` for a bad markdown, blueprint, buyer or treasury.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
    if not 0 <= markdown_pct <= 100:
        return {"error": f"markdown_pct is a percentage 0..100, got {markdown_pct}"}
    proj = await Database.fetchrow(
        "SELECT id, name, blueprint_price, saleable, unlocked FROM maya_rp.research_projects "
        "WHERE id=$1", project_id)
    if not proj or not proj["unlocked"] or not proj["saleable"]:
        return {"error": "Blueprint tak saleable / belum unlocked"}
    if proj["blueprint_price"] is None:
        return {"error": f"Blueprint {proj['name']} has no price on the row"}

    price = int(proj["blueprint_price"] * (1 - markdown_pct / 100.0))  # redacted discount

    try:
        async with Database.transaction() as conn:
            charged = await conn.fetchrow(
                "UPDATE maya_rp.factions SET treasury=treasury-$1 "
                "WHERE session_id=$2 AND name=$3 AND treasury >= $1 RETURNING treasury",
                price, session_id, buyer)
            if charged is None:
                info("corporations",
                     f"Blueprint sale: buyer {buyer!r} is not a faction in session {session_id} "
                     f"or holds less than {price:,}C; nothing moved")
                raise _Abort({"error": f"Buyer {buyer!r} not found in session {session_id} "
                                       f"or cannot pay {price:,}C"})
            credited = await conn.fetchrow(
                "UPDATE maya_rp.resources SET credits=credits+$1 WHERE session_id=$2 RETURNING credits",
                price, session_id)
            if credited is None:
                info("corporations",
                     f"Blueprint sale: no resources row for session {session_id}, {price:,}C not banked")
                raise _Abort({"error": f"No treasury row for session {session_id}"})

            # Ledger contract. The row is written with the BHI corporation when one exists;
            # no session has ever chartered one, so the row arrives invisible to the tick
            # join and the sale stays a record rather than a second payout.
            ledger_corp = await conn.fetchval(
                "SELECT id FROM maya_rp.corporations WHERE session_id=$1 AND name='BHI' LIMIT 1",
                session_id)
            cid = await conn.fetchval(
                """INSERT INTO maya_rp.corporate_contracts (session_id, corp_id, contract_type, target_system,
                   payout_credits, duration_days, days_remaining, status)
                   VALUES ($1, $2, 'blueprint_sale', $3, $4, 30, 30, 'active') RETURNING id""",
                session_id, ledger_corp, buyer, price)
            if ledger_corp is None:
                info("corporations",
                     f"Blueprint sale {proj['name']}: no BHI corporation in session {session_id}, "
                     f"contract {cid} is a ledger row the tick cannot see")
            await conn.execute(
                "INSERT INTO maya_rp.events (session_id, event_type, title, description, importance, tags) "
                "VALUES ($1, 'trade', $2, $3, 3, '[\"blueprint\",\"trade\"]'::jsonb)",
                session_id, f"Blueprint Sold: {proj['name']}",
                f"80% data redacted blueprint {proj['name']} dijual ke {buyer} untuk {price:,}C. "
                f"Buyer perlu R&D sendiri untuk full spec.")
    except _Abort as stop:
        return stop.payload
    return {"sold": proj["name"], "buyer": buyer, "price": price, "contract_id": cid,
            "markdown_pct": markdown_pct, "banked": True, "charged_buyer": True}
