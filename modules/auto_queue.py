#!/usr/bin/env python3
"""Auto-Queue & Corporate Tick.

Two duties, one tick:
1. Yard auto-queue — standing orders keep Heaven Yard (and any yard) from
   ever sitting idle. When open builds of a ship_type drop below quota,
   replacement hulls are enqueued automatically.
2. Corporate tick — government corporations serve markets: Setia Pharma
   converts Med Pack stockpiles into Medical Supplies commodity supply
   and books asset income into its treasury.
"""
from __future__ import annotations

from core.db import Database
from core.config import Config
from core.log import info

MEDICAL_SUPPLY_COMMODITY = "Medical Supplies"
MEDICAL_TRANSFER_PER_TICK = 5000  # stockpile → market per pharma corp per tick


async def run_tick(session_id: int | None = None) -> dict:
    if session_id is None:
        session_id = Config.SESSION_ID
    results: dict = {}
    for name, fn in (("yard", _yard_auto_queue), ("pharma", _pharma_tick)):
        try:
            results[name] = await fn(session_id)
        except Exception as e:  # keep the rest of the tick alive
            results[name] = {"error": str(e)}
    info("auto_queue", f"yard={results.get('yard')} pharma={results.get('pharma')}")
    return results


# ─── Yard auto-queue ────────────────────────────────────────────────────

async def _yard_auto_queue(session_id: int) -> dict:
    orders = await Database.fetch(
        "SELECT * FROM maya_rp.auto_queue "
        "WHERE session_id=$1 AND active=TRUE ORDER BY priority",
        session_id,
    )
    enqueued = 0
    for o in orders:
        open_count = await Database.fetchval(
            "SELECT COUNT(*) FROM maya_rp.production_queue "
            "WHERE session_id=$1 AND assigned_yard=$2 AND ship_type=$3 "
            "AND status IN ('planned','building')",
            session_id, o["yard"], o["ship_type"],
        ) or 0
        need = o["quota"] - open_count
        if need <= 0:
            continue
        existing = await Database.fetchval(
            "SELECT COUNT(*) FROM maya_rp.production_queue "
            "WHERE ship_name LIKE $1",
            f"{o['ship_name_prefix']}%",
        ) or 0
        for i in range(1, need + 1):
            n = existing + i
            await Database.execute(
                "INSERT INTO maya_rp.production_queue "
                "(session_id, ship_name, ship_type, hull_class, status, priority, "
                " alloy_cost, fuel_cost, credit_cost, build_time_hours, progress_pct, "
                " assigned_yard, notes) "
                "VALUES ($1,$2,$3,$4,'planned',$5,$6,$7,$8,$9,0,$10,$11)",
                session_id,
                f"{o['ship_name_prefix']}{n:03d}",
                o["ship_type"],
                o["hull_class"],
                o["priority"],
                o["alloy_cost"],
                o["fuel_cost"],
                o["credit_cost"],
                o["build_time_hours"],
                o["yard"],
                "auto-queued",
            )
            enqueued += 1
    return {"orders": len(orders), "enqueued": enqueued}


# ─── Corporate tick: Setia Pharma ───────────────────────────────────────

async def _pharma_tick(session_id: int) -> dict:
    corps = await Database.fetch(
        "SELECT id, name, treasury FROM maya_rp.corporations "
        "WHERE industry='pharmaceutical'",
    )
    if not corps:
        return {"corps": 0, "note": "no pharmaceutical corporations"}

    # Per-corp income: each corp books income from ITS OWN assets only.
    total_income = 0
    for c in corps:
        own_income = await Database.fetchval(
            "SELECT COALESCE(SUM(ca.income_per_day),0) "
            "FROM maya_rp.corporate_assets ca "
            "WHERE ca.corporation_id=$1 AND ca.status='active'",
            c["id"],
        ) or 0
        if own_income:
            await Database.execute(
                "UPDATE maya_rp.corporations SET treasury=treasury+$1 WHERE id=$2",
                own_income, c["id"],
            )
            total_income += own_income

    # Hub throughput is a MARKET-side figure — applied ONCE, not per corp.
    hub_throughput = await Database.fetchval(
        "SELECT COALESCE(SUM(ca.income_per_day),0) "
        "FROM maya_rp.corporate_assets ca "
        "JOIN maya_rp.corporations c ON c.id=ca.corporation_id "
        "WHERE c.industry='pharmaceutical' AND ca.status='active' "
        "AND ca.asset_type='medical_distribution_hub'",
    ) or 0

    supply_moved = 0
    # Stockpile → market transfer once per tick (not per corp).
    avail = await Database.fetchval(
        "SELECT COALESCE(SUM(quantity-reserved),0) "
        "FROM maya_rp.material_stockpiles "
        "WHERE session_id=$1 AND material_name=$2",
        session_id, MEDICAL_SUPPLY_COMMODITY,
    ) or 0
    transfer = min(avail, MEDICAL_TRANSFER_PER_TICK)
    if transfer > 0:
        await Database.execute(
            "UPDATE maya_rp.material_stockpiles SET quantity=quantity-$1 WHERE id=("
            "SELECT id FROM maya_rp.material_stockpiles "
            "WHERE session_id=$2 AND material_name=$3 AND quantity>0 "
            "ORDER BY id LIMIT 1)",
            transfer, session_id, MEDICAL_SUPPLY_COMMODITY,
        )
        await Database.execute(
            "UPDATE maya_rp.commodities SET supply=supply+$1 "
            "WHERE session_id=$2 AND name=$3",
            transfer, session_id, MEDICAL_SUPPLY_COMMODITY,
        )
        supply_moved += transfer

    if hub_throughput > 0:
        await Database.execute(
            "UPDATE maya_rp.commodities SET supply=supply+$1 "
            "WHERE session_id=$2 AND name=$3",
            hub_throughput, session_id, MEDICAL_SUPPLY_COMMODITY,
        )
        supply_moved += hub_throughput

    return {
        "corps": len(corps),
        "treasury_income": total_income,
        "hub_throughput": hub_throughput,
        "medical_supply_added": supply_moved,
    }
