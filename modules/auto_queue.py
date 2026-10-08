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
from core.log import error, info
from core.session import require_session

MEDICAL_SUPPLY_COMMODITY = "Medical Supplies"
MEDICAL_TRANSFER_PER_TICK = 5000  # stockpile → market per pharma corp per tick


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


def _like_escape(text: str) -> str:
    """Escape `\\`, `%` and `_` so a ship-name prefix matches as literal text under `ESCAPE '\\'`.

    @param text - ship name prefix from an `auto_queue` row.
    @returns the text with LIKE wildcards neutralised.
    """
    return str(text).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def run_tick(session_id: int | None = None) -> dict:
    """Run the yard auto-queue and the pharma tick for this campaign.

    @param session_id - campaign; `None` resolves through `require_session`.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
    results: dict = {}
    for name, fn in (("yard", _yard_auto_queue), ("pharma", _pharma_tick)):
        try:
            results[name] = await fn(session_id)
        except Exception as e:  # keep the rest of the tick alive
            # The answer says what broke, and the log now says it too: a tick that half-ran used to
            # be visible only to whoever read the returned dict.
            error("auto_queue", f"{name} failed for session {session_id}: {e}")
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
        # Count and insert under one per-session lock. Two ticks counted the same open builds, and each
        # enqueued the full shortfall, doubling the quota.
        async with Database.transaction() as conn:
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext('auto_queue'), $1)", session_id)
            open_count = await conn.fetchval(
                "SELECT COUNT(*) FROM maya_rp.production_queue "
                "WHERE session_id=$1 AND assigned_yard=$2 AND ship_type=$3 "
                "AND status IN ('planned','building')",
                session_id, o["yard"], o["ship_type"],
            ) or 0
            need = o["quota"] - open_count
            if need <= 0:
                continue
            existing = await conn.fetchval(
                # The name count ran with no session filter, so it counted every campaign's hulls with
                # this prefix and one campaign's standing orders numbered themselves against another's.
                # `%` and `_` in the prefix match literally.
                "SELECT COUNT(*) FROM maya_rp.production_queue "
                "WHERE session_id=$1 AND ship_name LIKE $2 ESCAPE '\\'",
                session_id, f"{_like_escape(o['ship_name_prefix'])}%",
            ) or 0
            for i in range(1, need + 1):
                n = existing + i
                await conn.execute(
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
    # `corporations` carries a session_id and this read had no filter on it, so every campaign's
    # pharmaceutical corps booked income during another campaign's tick.
    corps = await Database.fetch(
        "SELECT id, name, treasury FROM maya_rp.corporations "
        "WHERE industry='pharmaceutical' AND session_id=$1",
        session_id,
    )
    if not corps:
        # Same keys as the full answer: a caller that reads `treasury_income` got a KeyError on
        # exactly the session that has no corporations, which is the one most likely to be asked why
        # nothing moved.
        return {"corps": 0, "treasury_income": 0, "hub_throughput": 0,
                "medical_supply_added": 0, "note": "no pharmaceutical corporations"}

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
        "WHERE c.industry='pharmaceutical' AND c.session_id=$1 AND ca.status='active' "
        "AND ca.asset_type='medical_distribution_hub'",
        session_id,
    ) or 0

    supply_moved = 0
    # Stockpile → market transfer once per tick (not per corp).
    # The old body moved `min(SUM(quantity - reserved), 5000)` out of the single lowest-id row, so a
    # pile of 100 with a 5000 budget went to -4900 and the market was credited 5000. The budget is
    # spent across the session's piles instead, and a pile is never asked for more than it holds.
    piles = await Database.fetch(
        "SELECT id, quantity, COALESCE(reserved, 0) AS reserved FROM maya_rp.material_stockpiles "
        "WHERE session_id=$1 AND material_name=$2 AND quantity > COALESCE(reserved, 0) "
        "ORDER BY id",
        session_id, MEDICAL_SUPPLY_COMMODITY,
    )
    budget = MEDICAL_TRANSFER_PER_TICK
    transfer = 0
    # The pile decrements and the market credit share one transaction, and each decrement is guarded by
    # the unreserved stock, so a concurrent consumer cannot drive a pile negative and an error cannot
    # remove stock without crediting the market.
    async with Database.transaction() as conn:
        for pile in piles:
            if budget <= 0:
                break
            take = min(budget, pile["quantity"] - pile["reserved"])
            if take <= 0:
                continue
            moved = await conn.fetchval(
                "UPDATE maya_rp.material_stockpiles SET quantity = quantity - $1 "
                "WHERE id = $2 AND quantity - COALESCE(reserved, 0) >= $1 RETURNING id",
                take, pile["id"],
            )
            if moved is None:
                continue
            budget -= take
            transfer += take
        if transfer > 0:
            await conn.execute(
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
