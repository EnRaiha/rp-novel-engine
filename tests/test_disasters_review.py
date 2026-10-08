"""Module review tests for modules/disasters.py (2026-10-03).

Every database call is stubbed. A disaster never touches a live row. The stub's `transaction()` hands back
the stub itself. Every call uses a scratch session: the frozen guard refuses sessions 3 and 5.
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.disasters as dis  # noqa: E402

SID = 900 + os.getpid() % 100


def _run(coro):
    return asyncio.run(coro)


def _disaster(category, ticks=3, severity=2, damage=100):
    return {"id": 1, "name": f"{category} event", "severity": severity,
            "ticks_remaining": ticks, "base_damage": damage, "category": category}


class _StubDB:
    def __init__(self, active=(), applied=True, claimed=True):
        self.active = list(active)
        self.applied = applied
        self.claimed = claimed
        self.reads = []
        self.writes = []

    def transaction(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def fetchval(self, sql, *args):
        self.reads.append((sql, args))
        if "UPDATE maya_rp.active_disasters" in sql:
            self.writes.append((sql, args))
            return 1 if self.claimed else None
        return None

    async def fetch(self, sql, *args):
        self.reads.append((sql, args))
        if "active_disasters" in sql:
            return self.active
        return []

    async def fetchrow(self, sql, *args):
        self.reads.append((sql, args))
        if "UPDATE maya_rp." in sql:
            self.writes.append((sql, args))
            return {"id": 1} if self.applied else None
        return None

    async def execute(self, sql, *args):
        self.writes.append((sql, args))
        return "OK"


def test_an_economic_disaster_drains_credits_and_says_it_did(monkeypatch):
    stub = _StubDB(active=[_disaster("economic")])
    monkeypatch.setattr(dis, "Database", stub)

    events = _run(dis.tick_disasters(SID))

    assert events[0]["applied"] is True, events
    damage = [args for sql, args in stub.writes if "credits=GREATEST" in sql]
    assert damage and damage[0][1] == SID
    assert damage[0][0] == 60        # 100 base * 2 severity * 0.3


def test_a_disaster_with_nothing_to_damage_is_reported(monkeypatch):
    """A session with no resources row booked the loss and moved nothing."""
    stub = _StubDB(active=[_disaster("economic")], applied=False)
    monkeypatch.setattr(dis, "Database", stub)
    logged = []
    monkeypatch.setattr(dis, "info", lambda *a: logged.append(a[-1]))

    events = _run(dis.tick_disasters(SID))

    assert events[0]["applied"] is False, events
    assert any(f"no row in session {SID}" in line for line in logged), logged


def test_a_plague_hits_territory_population_only(monkeypatch):
    stub = _StubDB(active=[_disaster("plague")])
    monkeypatch.setattr(dis, "Database", stub)

    _run(dis.tick_disasters(SID))

    plague = [(sql, args) for sql, args in stub.writes if "population=GREATEST" in sql]
    assert plague, "the plague hit something else"
    assert "maya_rp.territory" in plague[0][0]
    assert plague[0][1][1] == SID


def test_any_other_category_hits_active_hulls(monkeypatch):
    stub = _StubDB(active=[_disaster("solar")])
    monkeypatch.setattr(dis, "Database", stub)

    events = _run(dis.tick_disasters(SID))

    hulls = [(sql, args) for sql, args in stub.writes if "hull_current=GREATEST" in sql]
    assert hulls and "status='active'" in hulls[0][0]
    assert events[0]["title"] == "Solar Damage", events


def test_the_countdown_claims_the_tick_before_any_damage(monkeypatch):
    """The damage and the countdown were separate statements, so an error between them repeated the damage."""
    stub = _StubDB(active=[_disaster("solar", ticks=4)])
    monkeypatch.setattr(dis, "Database", stub)

    _run(dis.tick_disasters(SID))

    claim = [i for i, (sql, _) in enumerate(stub.writes) if "UPDATE maya_rp.active_disasters" in sql]
    damage = [i for i, (sql, _) in enumerate(stub.writes) if "hull_current=GREATEST" in sql]
    assert claim and damage and claim[0] < damage[0], "damage was applied before the tick was claimed"
    sql = stub.writes[claim[0]][0]
    assert "status='active' AND ticks_remaining > 0" in sql and "'resolved'" in sql, sql
    assert stub.writes[claim[0]][1] == (1,)


def test_a_disaster_another_tick_already_claimed_takes_no_damage(monkeypatch):
    stub = _StubDB(active=[_disaster("economic")], claimed=False)
    monkeypatch.setattr(dis, "Database", stub)

    events = _run(dis.tick_disasters(SID))

    assert events == []
    assert not [sql for sql, _ in stub.writes if "credits=GREATEST" in sql], "a lost claim still damaged"


def test_the_tick_reads_its_own_campaign_only(monkeypatch):
    stub = _StubDB()
    monkeypatch.setattr(dis, "Database", stub)
    out = _run(dis.run_tick(session_id=SID))
    assert out == {"disaster_events": 0}
    (sql, args), = stub.reads
    assert "d.session_id=$1" in sql and args == (SID,)


def test_the_tick_reports_an_error_instead_of_raising(monkeypatch):
    class _Boom(_StubDB):
        async def fetch(self, sql, *args):
            raise RuntimeError("connection reset")
    monkeypatch.setattr(dis, "Database", _Boom())
    logged = []
    monkeypatch.setattr(dis, "info", lambda *a: logged.append(a[-1]))
    out = _run(dis.run_tick(session_id=SID))
    assert "connection reset" in out["error"]
    assert any("connection reset" in line for line in logged)
