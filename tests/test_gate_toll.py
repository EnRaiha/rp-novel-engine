"""Gate toll income tests — third-party pays, Setia collects (2026-08-15).

Izzat canon: "gate setia doesnt need exotic matter, only third party use it."
+ "the cost is smaller, but price is adjust for standardize" → Setia's own
fleet pays only the SMALLER internal cost (20% share); the PUBLIC price is
standardized at 25,000C and paid by common people / anyone else, credited to
the treasury via the economy tick.
"""
import pytest

from modules.economy import gate_toll_income, GATE_TOLL_RATE
from modules.voyage import GATE_INTERNAL_COST_SHARE


async def test_no_third_party_no_income(monkeypatch):
    async def fetchval(sql, *args):
        return 0
    monkeypatch.setattr("modules.economy.Database.fetchval", fetchval)
    assert await gate_toll_income() == 0


async def test_toll_scales_with_volume(monkeypatch):
    # 521 units of foreign trade → 521/40 = 13 crossings → 13 × 25,000 = 325,000
    async def fetchval(sql, *args):
        return 521
    monkeypatch.setattr("modules.economy.Database.fetchval", fetchval)
    assert await gate_toll_income() == 13 * GATE_TOLL_RATE


async def test_small_volume_no_income():
    # under one crossing of volume → no toll yet
    assert (39 // 40) * GATE_TOLL_RATE == 0
    assert (40 // 40) * GATE_TOLL_RATE == GATE_TOLL_RATE


async def test_public_price_standardized():
    # the "appropriate fair" — affordable enough that traders prefer the gate
    assert 10000 <= GATE_TOLL_RATE <= 100000
    assert GATE_TOLL_RATE == 25000


def test_internal_cost_smaller_than_public():
    # fleet internal cost is a SMALLER share of the standardized public price
    assert 0 < GATE_INTERNAL_COST_SHARE < 1
    assert 25000 * GATE_INTERNAL_COST_SHARE < 25000
    assert 25000 * GATE_INTERNAL_COST_SHARE == 5000
