"""Module review tests for modules/corporations.py (2026-10-03).

Every database call is stubbed. A blueprint sale moves the treasury and a faction
war chest, so the tests read what the module would send and never send it. The stub's
`transaction()` hands back the stub and records how the block exited: a block that
exits on an exception is a rollback.

Writers use a scratch session: the frozen guard refuses sessions 3 and 5.
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.corporations as corps  # noqa: E402
from core.db import Database  # noqa: E402

SID = 900 + os.getpid() % 100


def _run(coro):
    return asyncio.run(coro)


class _StubDB:
    """Answers the module's statements and records every SQL string and argument."""

    def __init__(self, project=None, credits_row=None, faction_row=None, corp_row=None,
                 contracts=()):
        self.project = project
        self.credits_row = credits_row
        self.faction_row = faction_row
        self.corp_row = corp_row
        self.contracts = list(contracts)
        self.reads = []
        self.writes = []
        self.credits_updates = []
        self.faction_updates = []
        self.exits = []

    def transaction(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.exits.append(exc_type)
        return False

    async def fetchrow(self, sql, *args):
        self.reads.append((sql, args))
        if "UPDATE maya_rp.resources" in sql:
            self.credits_updates.append(args)
            return self.credits_row
        if "UPDATE maya_rp.factions" in sql:
            self.faction_updates.append(args)
            return self.faction_row
        if "FROM maya_rp.research_projects" in sql:
            return self.project
        return None

    async def fetchval(self, sql, *args):
        self.reads.append((sql, args))
        if "FROM maya_rp.corporations" in sql:
            return self.corp_row
        if "INSERT INTO maya_rp.corporate_contracts" in sql:
            self.writes.append((sql, args))
            return 77
        return 1

    async def fetch(self, sql, *args):
        self.reads.append((sql, args))
        if "FROM maya_rp.corporate_contracts" in sql:
            return self.contracts
        return []

    async def execute(self, sql, *args):
        self.writes.append((sql, args))
        return "OK"


PROJECT = {"id": 5, "name": "Redacted Drive", "blueprint_price": 10000,
           "saleable": True, "unlocked": True}


# ── A sale that paid the buyer instead of the crown ─────────────────────


def test_the_markdown_is_a_percentage_like_the_cli_calls_it(monkeypatch):
    """`cli.py craft sell <id> <buyer> 20` passes 20, and the body read a fraction."""
    stub = _StubDB(project=PROJECT, credits_row={"credits": 1}, faction_row={"treasury": 1},
                   corp_row=None)
    monkeypatch.setattr(corps, "Database", stub)

    out = _run(corps.sell_blueprint(SID, 5, "Iron Concord", 20))

    assert out["price"] == 8000, out
    assert stub.credits_updates == [(8000, SID)], "the crown was paid something other than 8000"
    assert stub.faction_updates == [(8000, SID, "Iron Concord")]
    assert out["markdown_pct"] == 20


def test_a_full_markdown_asks_nothing_and_a_zero_markdown_asks_the_price(monkeypatch):
    for markdown, expected in ((0, 10000), (100, 0)):
        stub = _StubDB(project=PROJECT, credits_row={"credits": 1},
                       faction_row={"treasury": 1}, corp_row=9)
        monkeypatch.setattr(corps, "Database", stub)
        out = _run(corps.sell_blueprint(SID, 5, "Iron Concord", markdown))
        assert out["price"] == expected, (markdown, out)


def test_a_markdown_outside_the_percentage_range_is_refused(monkeypatch):
    stub = _StubDB(project=PROJECT)
    monkeypatch.setattr(corps, "Database", stub)
    for bad in (-5, 150, 1000):
        out = _run(corps.sell_blueprint(SID, 5, "Iron Concord", bad))
        assert "percentage 0..100" in out["error"], (bad, out)
    assert stub.reads == [], "a refused sale still read the database"


def test_a_blueprint_with_no_price_is_refused(monkeypatch):
    stub = _StubDB(project={**PROJECT, "blueprint_price": None}, corp_row=9)
    monkeypatch.setattr(corps, "Database", stub)
    out = _run(corps.sell_blueprint(SID, 5, "Iron Concord", 20))
    assert "no price" in out["error"], out
    assert stub.credits_updates == []


def test_an_unknown_buyer_is_refused_and_the_player_is_not_paid(monkeypatch):
    """Pre-fix the player was credited the full price first, so a buyer that does not exist minted money."""
    stub = _StubDB(project=PROJECT, credits_row={"credits": 1}, faction_row=None, corp_row=None)
    monkeypatch.setattr(corps, "Database", stub)
    logged = []
    monkeypatch.setattr(corps, "info", lambda *a: logged.append(a[-1]))

    out = _run(corps.sell_blueprint(SID, 5, "Nobody", 20))

    assert "error" in out and "Nobody" in out["error"], out
    assert stub.credits_updates == [], "the player was credited for a sale to a nonexistent buyer"
    assert stub.writes == [], "a refused sale still wrote a ledger row or an event"
    assert "treasury >= $1" in [s for s, _ in stub.reads if "UPDATE maya_rp.factions" in s][0]
    assert any("not a faction in session" in line for line in logged)


def test_a_missing_player_wallet_rolls_the_buyer_charge_back(monkeypatch):
    """The buyer is charged first; with no resources row the whole block must roll back."""
    stub = _StubDB(project=PROJECT, credits_row=None, faction_row={"treasury": 1}, corp_row=None)
    monkeypatch.setattr(corps, "Database", stub)

    out = _run(corps.sell_blueprint(SID, 5, "Iron Concord", 20))

    assert "No treasury row" in out["error"], out
    assert stub.exits and stub.exits[-1] is not None, "the buyer charge was committed without the credit"
    assert stub.writes == []


def test_the_ledger_row_names_the_corporation_it_could_not_find(monkeypatch):
    stub = _StubDB(project=PROJECT, credits_row={"credits": 1}, faction_row={"treasury": 1},
                   corp_row=None)
    monkeypatch.setattr(corps, "Database", stub)
    logged = []
    monkeypatch.setattr(corps, "info", lambda *a: logged.append(a[-1]))

    out = _run(corps.sell_blueprint(SID, 5, "Iron Concord", 20))

    assert out["contract_id"] == 77
    contract_args = [args for sql, args in stub.writes if "corporate_contracts" in sql]
    assert contract_args and contract_args[0][1] is None, "no BHI corporation exists to attach"
    assert any("no BHI corporation" in line for line in logged)


# ── Chartering: the money moves with the company, or not at all ─────────


class _TxnStub(_StubDB):
    """The same stub, usable as `async with Database.transaction() as conn`."""

    def __init__(self, credits, game_day=2253):
        super().__init__()
        self.credits = credits
        self.game_day = game_day

    async def fetchrow(self, sql, *args):
        self.reads.append((sql, args))
        if "UPDATE maya_rp.resources" in sql:
            # The guarded debit (`credits >= $1`) returns a row only when the treasury covers it.
            if self.credits < args[0]:
                return None
            self.writes.append((sql, args))
            return {"credits": self.credits - args[0]}
        return None

    async def fetchval(self, sql, *args):
        self.reads.append((sql, args))
        if "FROM maya_rp.sessions" in sql:
            return self.game_day
        if "INSERT INTO maya_rp.corporations" in sql:
            self.writes.append((sql, args))
            return 12
        return None


def test_chartering_an_unaffordable_company_writes_nothing(monkeypatch):
    stub = _TxnStub(credits=1000)
    monkeypatch.setattr(corps, "Database", stub)

    out = _run(corps.charter_company("Review Ltd", "mining", None, SID))

    assert "Insufficient funds" in out["error"], out
    assert stub.writes == [], "a refused charter still wrote"


def test_chartering_deducts_the_cost_and_returns_it(monkeypatch):
    stub = _TxnStub(credits=1_000_000)
    monkeypatch.setattr(corps, "Database", stub)

    out = _run(corps.charter_company("Review Ltd", "mining", 2071, SID))

    assert out["corp_id"] == 12
    assert out["cost"] == corps.INDUSTRIES["mining"]["cost"]
    deducted = [args for sql, args in stub.writes if "credits = credits -" in sql]
    assert deducted == [(out["cost"], SID)]


def test_an_unknown_industry_is_refused(monkeypatch):
    stub = _TxnStub(credits=1_000_000)
    monkeypatch.setattr(corps, "Database", stub)
    out = _run(corps.charter_company("Review Ltd", "agriculture", None, SID))
    assert "Invalid industry" in out["error"], out
    assert stub.writes == []


# ── The tick: an unknown industry is named, not silently defaulted ──────


def test_the_tick_names_an_industry_the_table_does_not_carry(monkeypatch):
    contract = {"id": 1, "corp_id": 2, "contract_type": "resource_extraction",
                "target_system": None, "payout_credits": 1000, "payout_alloys": 10,
                "days_remaining": 5, "corp_name": "Review Shipping", "industry": "smuggling",
                "efficiency": 50, "standing": 50}
    stub = _StubDB(contracts=[contract])
    monkeypatch.setattr(corps, "Database", stub)
    logged = []
    monkeypatch.setattr(corps, "info", lambda *a: logged.append(a[-1]))

    out = _run(corps.run_tick(SID))

    assert out["active_contracts"] == 1
    assert any("'smuggling' is not in INDUSTRIES" in line for line in logged), logged
    assert any("days_remaining = $1" in sql for sql, _ in stub.writes)


def test_the_tick_keeps_its_progress_when_no_industry_matches(monkeypatch):
    """Fifteen of twenty live industries are unknown, so the tick must not stop."""
    contracts = [
        {"id": 1, "corp_id": 2, "contract_type": "resource_extraction", "target_system": None,
         "payout_credits": 1000, "payout_alloys": 10, "days_remaining": 3,
         "corp_name": "A", "industry": "banking", "efficiency": 50, "standing": 50},
        {"id": 2, "corp_id": 3, "contract_type": "production_boost", "target_system": None,
         "payout_credits": 2000, "payout_alloys": 0, "days_remaining": 1,
         "corp_name": "B", "industry": "mining", "efficiency": 50, "standing": 50},
    ]
    stub = _StubDB(contracts=contracts)
    monkeypatch.setattr(corps, "Database", stub)

    out = _run(corps.run_tick(SID))

    assert out["completed"] == 1, out
    assert out["credits_gained"] == 2000
    assert out["alloys_gained"] == 0


def test_the_saleable_catalogue_is_galaxy_wide(monkeypatch):
    """research_projects carries no session_id, so the argument is parity only."""
    stub = _StubDB()
    monkeypatch.setattr(corps, "Database", stub)
    rows = _run(corps.list_saleable_blueprints(5))
    assert isinstance(rows, list)
    (sql, args), = [r for r in stub.reads if "research_projects" in r[0]]
    assert "session_id" not in sql
    assert args == ()
