#!/usr/bin/env python3
"""Market Module — commodity price ticks + price_history (added 2026-08-14).

Seeds the 13-commodity model (5 existed, 8 new) and ticks prices each game
day: supply/demand imbalance drifts price around base, volatility scales the
swing, prices clamp to [0.5×, 2×] base. Every tick writes price_history
(was permanently empty since the Day-19 gap audit).
"""
from __future__ import annotations
import random
from datetime import datetime, timezone
from core.db import Database
from core.config import Config
from core.log import info
from core.utils import calc_game_days

SEED_COMMODITIES = [
    # name, category, base_price, volatility, supply, demand
    ("Medical Supplies", "essentials", 5.0, 0.10, 460160, 350000),
    ("Refined Alloy Ingots", "industrial", 3.0, 0.08, 1800000, 1200000),
    ("He-3 Fuel Cells", "fuel", 2.0, 0.12, 950000, 850000),
    ("Industrial Machinery", "industrial", 8.0, 0.07, 500000, 450000),
    ("Silicon Wafers", "electronics", 1.5, 0.09, 700000, 550000),
    ("Luxury Goods", "consumer", 12.0, 0.15, 120000, 200000),
    ("Agricultural Produce", "essentials", 1.0, 0.10, 2000000, 2400000),
    ("Quantum Components", "electronics", 20.0, 0.18, 60000, 90000),
    ("Exotic Alloys", "industrial", 9.0, 0.14, 80000, 120000),
    ("Water Ice", "essentials", 0.8, 0.06, 3000000, 2600000),
    ("Ship Spare Parts", "industrial", 6.0, 0.08, 400000, 520000),
    ("Consumer Electronics", "consumer", 4.0, 0.11, 900000, 1100000),
    ("Processed Metals", "industrial", 2.5, 0.09, 1500000, 1300000),
]

PRICE_MIN_MULT, PRICE_MAX_MULT = 0.5, 2.0


def market_index(pairs: list) -> float:
    """Pure: mean(current/base) over commodity pairs. 1.0 = prices at base."""
    if not pairs:
        return 1.0
    return sum(cur / base for base, cur in pairs if base) / max(1, len(pairs))


async def get_market_index(session_id: int | None = None) -> float:
    """Live mean price deviation across all commodities."""
    if session_id is None:
        session_id = Config.SESSION_ID
    rows = await Database.fetch(
        "SELECT base_price, current_price FROM maya_rp.commodities WHERE session_id=$1",
        session_id)
    return market_index([(float(r["base_price"]), float(r["current_price"] or r["base_price"]))
                         for r in rows])


def next_price(base: float, current: float, volatility: float,
               supply: float, demand: float, rng=random) -> float:
    """Pure price step: imbalance pulls price, volatility scales, clamps."""
    imbalance = (demand - supply) / max(1, demand + supply)
    drift = current * volatility * (imbalance + rng.uniform(-0.5, 0.5) * 0.4)
    return max(base * PRICE_MIN_MULT, min(base * PRICE_MAX_MULT, current + drift))


async def _seed(session_id: int) -> None:
    for name, cat, base, vol, supply, demand in SEED_COMMODITIES:
        await Database.execute(
            "INSERT INTO maya_rp.commodities (session_id, name, category, base_price, "
            "current_price, volatility, supply, demand, last_tick_at) "
            "VALUES ($1,$2,$3,$4,$4,$5,$6,$7,NOW()) "
            "ON CONFLICT (session_id, name) DO NOTHING",
            session_id, name, cat, base, vol, supply, demand)


async def run_tick(session_id: int | None = None) -> dict:
    if session_id is None:
        session_id = Config.SESSION_ID
    row = await Database.fetchrow(
        "SELECT last_tick_at FROM maya_rp.resources WHERE session_id=$1", session_id)
    if not row or not row.get("last_tick_at"):
        return {"skipped": "no last_tick_at"}
    gd = calc_game_days(row["last_tick_at"])
    if gd < 0.01:
        return {"skipped": "no game day elapsed"}
    await _seed(session_id)
    tick = await Database.fetchval(
        "SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id) or 0
    commodities = await Database.fetch(
        "SELECT id, name, base_price, current_price, volatility, supply, demand "
        "FROM maya_rp.commodities WHERE session_id=$1", session_id)
    ticked = 0
    for c in commodities:
        new_price = next_price(float(c["base_price"]), float(c["current_price"] or c["base_price"]),
                               float(c["volatility"]), float(c["supply"]), float(c["demand"]))
        # supply/demand drift: production fills shortage, consumption drains surplus
        s = int(c["supply"] * (1 + gd * 0.005))
        d = int(c["demand"] * (1 + gd * 0.006))
        await Database.execute(
            "UPDATE maya_rp.commodities SET current_price=$1, supply=$2, demand=$3, "
            "last_tick_at=NOW() WHERE id=$4", round(new_price, 2), s, d, c["id"])
        await Database.execute(
            "INSERT INTO maya_rp.price_history (commodity_id, tick_number, price, volume) "
            "VALUES ($1,$2,$3,$4)",
            c["id"], tick, round(new_price, 2), abs(s - d) // 10 + 1)
        ticked += 1
    info("market", f"Tick: {ticked} commodities priced (game_day {tick})")
    return {"commodities": ticked, "game_day": tick}
