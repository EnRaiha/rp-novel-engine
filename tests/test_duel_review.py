"""Module review tests for modules/duel.py (2026-10-03).

The roll is stubbed to a fixed value, so every test reads the code's decision
rather than the dice. No database call leaves the process. The stub's `transaction()` hands back the
stub and records how the block exited: an exit on an exception is a rollback.

Every call uses a scratch session: the frozen guard refuses sessions 3 and 5.
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.duel as duel  # noqa: E402

SID = 900 + os.getpid() % 100


def _run(coro):
    return asyncio.run(coro)


SHIP = {"id": 4, "name": "Blizzard Zero", "sub_class": "Corvette", "tier": 3,
        "power_rating": 100, "hull": 400, "hull_current": 400, "status": "active"}
DUEL = {"id": 9, "session_id": SID, "player_ship_id": 4, "opponent_name": "Bald Eagle",
        "opponent_tier": 3, "opponent_power": 100, "stakes_type": "credits",
        "stakes_value": "5000", "status": "pending"}
OPPONENT = {"name": "Bald Eagle", "tier": 3, "hull": 400, "power": 100}


class _StubDB:
    def __init__(self, duel_row="default", ship=SHIP, credits_row=None):
        self.duel_row = dict(DUEL) if duel_row == "default" else duel_row
        self.ship = ship
        self.credits_row = credits_row
        self.reads = []
        self.writes = []
        self.credits_calls = []
        self.exits = []

    def transaction(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.exits.append(exc_type)
        return False

    async def fetchval(self, sql, *args):
        self.reads.append((sql, args))
        if "INSERT INTO maya_rp.duels" in sql:
            self.writes.append((sql, args))
            return 9
        return 0

    async def fetchrow(self, sql, *args):
        self.reads.append((sql, args))
        if "UPDATE maya_rp.resources" in sql:
            self.credits_calls.append(args)
            return self.credits_row
        if "UPDATE maya_rp.duels" in sql and "RETURNING" in sql:
            # The claim: `pending` to `resolved`. No row means someone else resolved it first.
            self.reads.append(("CLAIM", args))
            return self.duel_row
        if "FROM maya_rp.duels" in sql:
            return self.duel_row
        if "FROM maya_rp.ships" in sql:
            return self.ship
        return None

    async def execute(self, sql, *args):
        self.writes.append((sql, args))
        return "OK"

    async def fetch(self, sql, *args):
        self.reads.append((sql, args))
        return []


# ── Stakes are validated where they are written ─────────────────────────


def test_an_unknown_stakes_type_is_refused(monkeypatch):
    stub = _StubDB()
    monkeypatch.setattr(duel, "Database", stub)
    out = _run(duel.challenge(SID, 4, OPPONENT, {"type": "honour", "value": 1}))
    assert "Unknown stakes type" in out["error"], out
    assert stub.writes == []


def test_a_credit_stake_that_is_not_a_number_is_refused_at_challenge_time(monkeypatch):
    """It was stored as text and int() on resolve raised while settling the duel."""
    stub = _StubDB()
    monkeypatch.setattr(duel, "Database", stub)
    for bad in ("abc", -5):
        out = _run(duel.challenge(SID, 4, OPPONENT, {"type": "credits", "value": bad}))
        assert "error" in out, (bad, out)
    assert stub.writes == []


def test_a_valid_challenge_registers_as_pending(monkeypatch):
    stub = _StubDB()
    monkeypatch.setattr(duel, "Database", stub)
    out = _run(duel.challenge(SID, 4, OPPONENT, {"type": "credits", "value": 5000}))
    assert out["duel_id"] == 9 and out["status"] == "pending"
    (sql, args), = stub.writes
    assert "'pending'" in sql and args[0] == SID


# ── Resolution moves what it says it moved ──────────────────────────────


def test_a_win_pays_the_stake_and_reports_it(monkeypatch):
    stub = _StubDB(credits_row={"credits": 1})
    monkeypatch.setattr(duel, "Database", stub)
    monkeypatch.setattr(duel.random, "randint", lambda a, b: 1)   # a clean win

    out = _run(duel.resolve(SID, 9))

    assert out["result"] == "victory_clean", out
    assert stub.credits_calls == [(5000, SID)], stub.credits_calls
    assert "Menang 5,000 credits." in out["stakes"]
    assert "nothing moved" not in out["stakes"]


def test_a_settled_stake_says_when_the_treasury_row_is_missing(monkeypatch):
    """Session 5 has no resources row, so a duel there settles on paper only."""
    stub = _StubDB(credits_row=None)
    monkeypatch.setattr(duel, "Database", stub)
    monkeypatch.setattr(duel.random, "randint", lambda a, b: 1)
    logged = []
    monkeypatch.setattr(duel, "info", lambda *a: logged.append(a[-1]))

    out = _run(duel.resolve(SID, 9))

    assert "nothing moved" in out["stakes"], out
    assert any("not transferred" in line for line in logged), logged


def test_the_hull_update_and_the_duel_row_name_their_session(monkeypatch):
    stub = _StubDB(credits_row={"credits": 1})
    monkeypatch.setattr(duel, "Database", stub)
    monkeypatch.setattr(duel.random, "randint", lambda a, b: 1)

    _run(duel.resolve(SID, 9))

    hull = [sql for sql, _ in stub.writes if "UPDATE maya_rp.ships" in sql]
    settled = [sql for sql, _ in stub.writes if "UPDATE maya_rp.duels" in sql]
    assert hull and "session_id=$4" in hull[0], hull
    assert settled and "session_id=$3" in settled[0], settled
    hull_args = [args for sql, args in stub.writes if "UPDATE maya_rp.ships" in sql]
    assert hull_args[0][-1] == SID


def test_a_duel_from_another_campaign_is_refused(monkeypatch):
    stub = _StubDB(duel_row=None)
    monkeypatch.setattr(duel, "Database", stub)
    out = _run(duel.resolve(SID, 9))
    assert "tidak dijumpai" in out["error"], out
    assert stub.writes == []


def test_a_destroyed_ship_cannot_duel(monkeypatch):
    stub = _StubDB(ship={**SHIP, "status": "destroyed"})
    monkeypatch.setattr(duel, "Database", stub)
    out = _run(duel.resolve(SID, 9))
    assert "musnah" in out["error"], out
    assert stub.writes == []
    assert stub.exits[-1] is not None, "the pending-to-resolved claim was committed for a duel that never ran"


def test_a_heavy_defeat_destroys_the_hull(monkeypatch):
    stub = _StubDB(credits_row={"credits": 1})
    monkeypatch.setattr(duel, "Database", stub)
    monkeypatch.setattr(duel.random, "randint", lambda a, b: 100)  # 100 > 50+30

    out = _run(duel.resolve(SID, 9))

    assert out["result"] == "defeat_destroyed", out
    assert out["hull_remaining"] == 0
    ship_update = [args for sql, args in stub.writes if "UPDATE maya_rp.ships" in sql][0]
    assert ship_update[1] == "destroyed"
