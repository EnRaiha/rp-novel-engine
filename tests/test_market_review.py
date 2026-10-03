"""Module review tests for modules/market.py (2026-10-03).

The price step is pure and the tick is stubbed, so no commodity is repriced.
"""
from __future__ import annotations

import asyncio
import random
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.market as market  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


class _SeededRng:
    def uniform(self, a, b):
        return 0.0


class _StubDB:
    def __init__(self, resources=None, game_day=2253, commodities=()):
        self.resources = resources
        self.game_day = game_day
        self.commodities = list(commodities)
        self.reads = []
        self.writes = []

    async def fetchrow(self, sql, *args):
        self.reads.append((sql, args))
        if "FROM maya_rp.resources" in sql:
            return self.resources
        return None

    async def fetchval(self, sql, *args):
        self.reads.append((sql, args))
        if "game_day" in sql:
            return self.game_day
        return 0

    async def fetch(self, sql, *args):
        self.reads.append((sql, args))
        if "FROM maya_rp.commodities" in sql:
            return self.commodities
        return []

    async def execute(self, sql, *args):
        self.writes.append((sql, args))
        return "OK"


COMMODITY = {"id": 3, "name": "Water Ice", "base_price": 0.8, "current_price": 0.8,
             "volatility": 0.06, "supply": 3000000, "demand": 2600000}


# ── The index over the pairs it can divide ──────────────────────────────


def test_the_index_averages_over_the_pairs_it_used():
    """The count used to include a zero-base pair the sum had skipped."""
    assert market.market_index([]) == 1.0
    assert market.market_index([(0.0, 5.0)]) == 1.0
    assert market.market_index([(2.0, 4.0), (0.0, 9.0)]) == 2.0


def test_the_index_at_base_is_one():
    pairs = [(c[2], c[2]) for c in market.SEED_COMMODITIES]
    assert market.market_index(pairs) == 1.0


def test_the_seed_table_is_the_thirteen_commodities_the_header_claims():
    assert len(market.SEED_COMMODITIES) == 13
    for name, category, base, vol, supply, demand in market.SEED_COMMODITIES:
        assert name and category and base > 0
        assert 0 < vol < 0.5 and supply > 0 and demand > 0


# ── The price step keeps its documented bounds ──────────────────────────


def test_the_price_step_clamps_to_the_declared_band():
    # A drift far past either bound has to come back to it: with volatility 5.0 the
    # unclamped step is 10 - 50 at the floor and 10 + 50 at the ceiling.
    assert market.next_price(10.0, 10.0, 5.0, 10**9, 0, rng=_SeededRng()) == 5.0
    assert market.next_price(10.0, 10.0, 5.0, 0, 10**9, rng=_SeededRng()) == 20.0
    for _ in range(200):
        price = market.next_price(10.0, 9.0, 0.9, 100, 900)
        assert market.PRICE_MIN_MULT * 10.0 <= price <= market.PRICE_MAX_MULT * 10.0


def test_the_price_step_is_deterministic_for_a_given_rng():
    one = market.next_price(10.0, 12.0, 0.2, 100, 200, rng=_SeededRng())
    two = market.next_price(10.0, 12.0, 0.2, 100, 200, rng=_SeededRng())
    assert one == two
    seeded = [market.next_price(10.0, 10.0, 0.2, 100, 200, rng=random.Random(7))
              for _ in range(2)]
    assert seeded[0] == seeded[1]


# ── The tick writes what it says it writes ──────────────────────────────


def test_the_tick_refuses_to_guess_without_a_last_tick(monkeypatch):
    stub = _StubDB(resources=None)
    monkeypatch.setattr(market, "Database", stub)
    assert _run(market.run_tick(session_id=5)) == {"skipped": "no last_tick_at"}
    assert stub.writes == []


def test_the_tick_prices_every_commodity_and_writes_history(monkeypatch):
    from datetime import datetime, timedelta, timezone

    stub = _StubDB(resources={"last_tick_at": datetime.now(timezone.utc) - timedelta(days=3)},
                   commodities=[COMMODITY])
    monkeypatch.setattr(market, "Database", stub)

    out = _run(market.run_tick(session_id=3))

    assert out["commodities"] == 1, out
    assert out["game_day"] == 2253
    priced = [args for sql, args in stub.writes if "UPDATE maya_rp.commodities" in sql]
    history = [args for sql, args in stub.writes if "INSERT INTO maya_rp.price_history" in sql]
    assert priced and history
    assert priced[0][-1] == 2253, priced
    assert history[0][1] == 2253, history
    assert 0.4 <= history[0][2] <= 1.6, history      # 0.5x .. 2x of the 0.8 base


def test_the_tick_seeds_before_it_prices(monkeypatch):
    from datetime import datetime, timedelta, timezone

    stub = _StubDB(resources={"last_tick_at": datetime.now(timezone.utc) - timedelta(days=1)})
    monkeypatch.setattr(market, "Database", stub)
    _run(market.run_tick(session_id=3))
    seeds = [sql for sql, _ in stub.writes if "INSERT INTO maya_rp.commodities" in sql]
    assert len(seeds) == len(market.SEED_COMMODITIES)
    assert all("ON CONFLICT (session_id, name) DO NOTHING" in sql for sql in seeds)
