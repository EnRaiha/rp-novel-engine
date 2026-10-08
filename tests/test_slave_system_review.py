"""Module review tests for modules/slave_system.py.

The fake below holds one slave, one market row, one revolt and one territory, all
belonging to the scratch session OWNER. It applies the session filter it is given, exactly as the
database would, so a statement that names no session sees OWNER rows even
while the caller asks as OTHER. Both ids are scratch ids, never a frozen campaign.
Nothing here touches the database.
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys
from contextlib import asynccontextmanager

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.slave_system as ss  # noqa: E402

OWNER = 900 + os.getpid() % 100            # the session that owns every row the fake holds
OTHER = 900 + (os.getpid() + 50) % 100     # the session the tests act as


def _run(coro):
    return asyncio.run(coro)


class _Fake:
    """The rows the campaign owns, and the statements the module issues."""

    def __init__(self, fail_on_fetch: bool = False):
        self.reads = []
        self.writes = []
        self.fail_on_fetch = fail_on_fetch

    def _visible(self, sql, args):
        """A row is visible only to the session the query names."""
        if "session_id" in sql:
            return OWNER in args
        return True

    async def fetchrow(self, sql, *args):
        self.reads.append((sql, args))
        if "INSERT INTO slaves" in sql:
            self.writes.append((sql, args))
            return {"id": 900}
        if not self._visible(sql, args):
            return None
        if "AVG(loyalty)" in sql:
            return {"a": 55.0}
        if "FROM slaves" in sql:
            return {"id": 42, "session_id": OWNER, "name": "Kael Mira", "species": "Human",
                    "strength": 6, "intelligence": 7, "loyalty": 50, "health": 80,
                    "status": "active", "assigned_to": None, "assigned_id": None}
        if "FROM territory" in sql:
            return {"id": 7, "session_id": OWNER, "system_name": "TKG", "population": 1000,
                    "slave_population": 300, "slave_revolt_risk": 10, "morale": 50}
        if "FROM slave_market" in sql:
            return {"id": 55, "session_id": OWNER, "slave_name": "Mira", "species": "Human",
                    "gender": "F", "age": 25, "strength": 5, "intelligence": 6, "price": 1000,
                    "hidden_talent": "tactics", "functional_role": "gunner",
                    "clearance_level": 1, "price_tier": "common"}
        if "FROM slave_revolts" in sql:
            return {"id": 8, "session_id": OWNER, "territory_id": 7, "size": 100,
                    "severity": 3, "outcome": "ongoing"}
        if "FROM resources" in sql:
            return {"credits": 999_999}
        return None

    async def fetch(self, sql, *args):
        self.reads.append((sql, args))
        if self.fail_on_fetch:
            raise RuntimeError("connection reset")
        return []

    async def fetchval(self, sql, *args):
        self.reads.append((sql, args))
        return 1

    async def execute(self, sql, *args):
        self.writes.append((sql, args))
        return "UPDATE 1"

    @asynccontextmanager
    async def transaction(self):
        """Yields a conn that records into the same lists; an exception drops the transaction's writes."""
        mark = len(self.writes)
        try:
            yield self
        except BaseException:
            del self.writes[mark:]
            raise

    def statements_touching(self, *tables):
        out = []
        for sql, args in self.reads + self.writes:
            if any(t in sql for t in tables):
                out.append((sql, args))
        return out


@pytest.fixture
def fake(monkeypatch):
    f = _Fake()
    monkeypatch.setattr(ss, "Database", f)
    return f


# ── Session scope, one action at a time ─────────────────────────────────


def test_assign_refuses_a_slave_from_another_campaign(fake):
    out = _run(ss.cmd(OTHER, "assign", {"slave_id": 42, "target_type": "territory",
                                       "target_id": 7}))
    assert out["error"] == "Not found", out
    assert fake.writes == [], "an assignment crossed campaigns"


def test_train_refuses_a_slave_from_another_campaign(fake):
    out = _run(ss.cmd(OTHER, "train", {"slave_id": 42}))
    assert out["error"] == "Slave not found", out
    assert fake.writes == []


def test_buy_refuses_another_campaigns_market_row(fake):
    out = _run(ss.cmd(OTHER, "buy", {"market_id": 55}))
    assert out["error"] == "Not available", out
    assert fake.writes == []


def test_suppress_refuses_another_campaigns_revolt(fake):
    out = _run(ss.cmd(OTHER, "suppress", {"revolt_id": 8}))
    assert out["error"] == "Not found", out
    assert fake.writes == []


def test_breed_refuses_parents_from_another_campaign(fake):
    out = _run(ss.cmd(OTHER, "breed", {"parent_a": 42, "parent_b": 42}))
    assert out["error"] == "Parent not found", out
    assert fake.writes == []


def test_every_statement_the_tick_sends_names_its_session(monkeypatch):
    f = _Fake()
    monkeypatch.setattr(ss, "Database", f)
    _run(ss.run_tick(OTHER))
    scoped = [sql for sql, _ in f.statements_touching("slaves", "territory")
              if sql.strip().upper().startswith("SELECT")]
    assert scoped, "the tick read nothing"
    for sql in scoped:
        assert "session_id" in sql, sql


def test_the_tick_resolves_its_session_instead_of_defaulting_to_the_frozen_one(fake, monkeypatch):
    monkeypatch.setenv("RP_SESSION", str(OWNER))
    out = _run(ss.run_tick())
    assert out["session_id"] == OWNER, out


def test_the_tick_reports_a_crash_instead_of_printing_it(monkeypatch):
    f = _Fake(fail_on_fetch=True)
    monkeypatch.setattr(ss, "Database", f)
    logged = []
    monkeypatch.setattr(ss, "error", lambda *a: logged.append(a[-1]))
    out = _run(ss.run_tick(OTHER))
    assert "connection reset" in out["error"], out
    assert any("connection reset" in line for line in logged)


# ── One child, one name ─────────────────────────────────────────────────


def test_breeding_names_one_child_for_both_birth_rows(monkeypatch):
    f = _Fake()
    monkeypatch.setattr(ss, "Database", f)
    out = _run(ss.cmd(OWNER, "breed", {"parent_a": 42, "parent_b": 43}))
    assert out["child_id"] == 900
    births = [args for sql, args in f.writes if "slave_births" in sql]
    assert len(births) == 2, births
    assert {args[1] for args in births} == {out["child_name"]}, births
    born = [args[1] for sql, args in f.writes if "INSERT INTO slaves" in sql]
    assert born == [out["child_name"]], born


def test_the_revolt_risk_lookup_can_be_scoped(monkeypatch):
    f = _Fake()
    monkeypatch.setattr(ss, "Database", f)
    assert _run(ss._revolt_risk(7, OTHER)) == 0, "another campaign's territory answered"
    assert _run(ss._revolt_risk(7, OWNER)) > 0
