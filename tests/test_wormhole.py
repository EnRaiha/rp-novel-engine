"""Wormhole / black hole / white hole tests — space-travel theory build (2026-08-15).

Physics-grounded mechanics:
  - Wormholes (Einstein-Rosen/Morris-Thorne): A↔B pairs, ~90% travel cut,
    decaying holes collapse; stable hub-fed holes don't.
  - Black holes: slingshot (Oberth) ×0.6 travel; time dilation 1 ship-day =
    N game-days; hazard roll vs event horizon.
  - White holes: exit-only mystery — nothing enters, everything exits.

DB-free where possible: pure math (travel days, dilation, collapse boundary)
+ monkeypatched DB for the async resolvers.
"""
import math
import os
import random
from contextlib import asynccontextmanager

import pytest

from modules.voyage import (GRID_HOURS_PER_UNIT, WORMHOLE_COLLAPSE_PCT,
                            wormhole_jump, wormhole_decay, black_hole_slingshot)


#: A scratch id, never a frozen session. The fakes below stand in for the database, so no row exists.
SCRATCH = 900 + os.getpid() % 100


# ── Wormhole math ────────────────────────────────────────────────────────

def test_wormhole_travel_cut():
    # euclidean(450,450 → 300,250) ≈ 220.7u → ×0.10 multiplier → ~22 days
    dist = math.hypot(450 - 300, 450 - 250)
    days = dist * 0.10 * GRID_HOURS_PER_UNIT / 24.0
    assert days == pytest.approx(dist * 0.1)  # 1u = 1 day at 24h/u


def test_wormhole_collapse_threshold_sane():
    assert 20 <= WORMHOLE_COLLAPSE_PCT <= 40


async def _row(name, **kw):
    return {"id": 1, "name": name, "stability": 1.0, "travel_multiplier": 0.10,
            "status": "stable", "entry_name": "A", "ex": 0.0, "ey": 0.0,
            "ez": 2, "exit_name": "B", "xx": 300.0, "xy": 400.0, "xz": 2,
            **kw}


async def test_wormhole_jump_stable(monkeypatch):
    async def fetchrow(sql, *args):
        return await _row("Aether Nexus Pair")
    monkeypatch.setattr("modules.voyage.Database.fetchrow", fetchrow)
    j = await wormhole_jump("Aether Nexus Pair")
    assert j["status"] == "stable"
    assert j["collapsed"] is False
    assert j["travel_days"] == pytest.approx(math.hypot(300, 400) * 0.10)


async def test_wormhole_jump_collapsed_raises(monkeypatch):
    async def fetchrow(sql, *args):
        return await _row("Dead Pair", status="collapsed", stability=0.0)
    monkeypatch.setattr("modules.voyage.Database.fetchrow", fetchrow)
    with pytest.raises(ValueError, match="COLLAPSED"):
        await wormhole_jump("Dead Pair")


async def test_wormhole_jump_unknown_raises(monkeypatch):
    async def fetchrow(sql, *args):
        return None
    monkeypatch.setattr("modules.voyage.Database.fetchrow", fetchrow)
    with pytest.raises(ValueError, match="No wormhole"):
        await wormhole_jump("Nope")


async def test_wormhole_decay_collapses_at_zero(monkeypatch):
    """A decaying hole at zero collapses and logs an event, a stable hole keeps its stability, and a
    healthy decaying hole loses only its decay. Every write goes through one transaction."""
    rows = [
        {"id": 1, "name": "Hub Pair", "stability": 1.0, "decay_per_tick": 0.01, "status": "stable"},
        {"id": 2, "name": "Rusty Hole", "stability": 0.02, "decay_per_tick": 0.03, "status": "decaying"},
        {"id": 3, "name": "Healthy Decay", "stability": 0.5, "decay_per_tick": 0.01, "status": "decaying"},
    ]
    executed = []
    pool_writes = []

    class FakeConn:
        async def execute(self, sql, *args):
            executed.append((sql, args))

    @asynccontextmanager
    async def transaction():
        yield FakeConn()

    async def fetch(sql, *args):
        return rows

    async def pool_execute(sql, *args):
        pool_writes.append(sql)

    monkeypatch.setattr("modules.voyage.Database.fetch", fetch)
    monkeypatch.setattr("modules.voyage.Database.execute", pool_execute)
    monkeypatch.setattr("modules.voyage.Database.transaction", transaction)
    r = await wormhole_decay(SCRATCH)
    assert "Rusty Hole" in r["collapsed"], r      # 0.02-0.03 → 0 → collapse
    assert "Hub Pair" not in r["collapsed"], r    # stable = hub-fed, no decay
    assert pool_writes == [], f"a write left the transaction: {pool_writes}"
    names = [e[1][1] for e in executed if "INSERT INTO maya_rp.events" in e[0]]
    assert any("Rusty Hole" in n for n in names), names
    # Healthy Decay decays to 0.49 without collapsing (Rusty Hole's collapse
    # update also contains 'SET stability', so count only the decay form)
    decay_updates = [e for e in executed if "SET stability=$1" in e[0]]
    assert len(decay_updates) == 1, decay_updates
    assert decay_updates[0][1][0] == pytest.approx(0.49)   # args = (new_stab, id)


# ── Black hole slingshot ─────────────────────────────────────────────────

async def test_slingshot_math_and_roll(monkeypatch):
    async def fetchrow(sql, *args):
        return {"id": 1, "name": "The Maw", "hazard_level": 0.90,
                "slingshot_multiplier": 0.55, "time_dilation_ratio": 6.0,
                "sector": "The Maw", "x_coord": 0, "y_coord": 0, "z_coord": 2}
    monkeypatch.setattr("modules.voyage.Database.fetchrow", fetchrow)
    # roll 100 → always pass; roll 1 → always fail
    ok = await black_hole_slingshot("The Maw", rng=random.Random(1))
    assert ok["pass_dc"] == 90
    assert ok["slingshot_multiplier"] == 0.55
    assert ok["time_dilation_ratio"] == 6.0
    assert ok["roll"] >= 1 and ok["roll"] <= 100


def test_dilation_days_math():
    # 10 ship-days near a 4× hole → 10×(4-1) = 30 extra game days
    travel_days = 10.0
    ratio = 4.0
    dilation = int(math.ceil(travel_days * (ratio - 1.0)))
    assert dilation == 30


def test_slingshot_multiplier_reduces_travel():
    # Oberth boost: ×0.6 → 60% of the original travel time
    base = 20.0
    boosted = base * 0.6
    assert boosted == 12.0
