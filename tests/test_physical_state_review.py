"""Module review tests for modules/physical_state.py (2026-10-03). Every call is stubbed."""
from __future__ import annotations

import asyncio
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.physical_state as ps  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


class _StubDB:
    def __init__(self, game_day=2253, injuries=(), scars=()):
        self.game_day = game_day
        self.injuries = list(injuries)
        self.scars = list(scars)
        self.reads = []
        self.writes = []
        self.returning_rows = []

    async def fetchval(self, sql, *args):
        self.reads.append((sql, args))
        # The INSERT carries received_game_day in its column list.
        if "INSERT INTO maya_rp.character_injuries" in sql:
            self.writes.append((sql, args))
            return 77
        if "game_day" in sql:
            return self.game_day
        return None

    async def fetch(self, sql, *args):
        self.reads.append((sql, args))
        if "RETURNING id" in sql:
            self.writes.append((sql, args))
            return self.returning_rows
        if "became_scar=true" in sql:
            return self.scars
        if "heal_by_game_day>$3" in sql:
            return self.injuries
        return []

    async def execute(self, sql, *args):
        self.writes.append((sql, args))
        return "UPDATE 3"


def test_an_unknown_severity_is_refused_instead_of_healing_as_moderate(monkeypatch):
    stub = _StubDB()
    monkeypatch.setattr(ps, "Database", stub)
    out = _run(ps.apply(2071, "took a blade", "catastrophic", session_id=5))
    assert "Unknown severity" in out["error"], out
    assert "permanent" in out["error"]
    assert stub.writes == []


def test_an_injury_is_written_with_its_heal_day(monkeypatch):
    stub = _StubDB(game_day=2253)
    monkeypatch.setattr(ps, "Database", stub)
    out = _run(ps.apply(2071, "took a blade", "severe", "left arm", "duel", session_id=5))
    assert out["injury_id"] == 77 and out["heals_in"] == 30
    (_, args), = stub.writes
    assert args[0] == 5 and args[3] == "severe" and args[6] == 2253 and args[7] == 2283


def test_the_scar_roll_lands_in_the_return(monkeypatch):
    stub = _StubDB()
    monkeypatch.setattr(ps, "Database", stub)
    monkeypatch.setattr(ps.random, "random", lambda: 0.0)      # always scars
    out = _run(ps.apply(2071, "burn", "minor", session_id=5))
    assert out["will_scar"] is True and "leave a mark" in out["narrative"]
    monkeypatch.setattr(ps.random, "random", lambda: 0.99)
    out = _run(ps.apply(2071, "burn", "minor", session_id=5))
    assert out["will_scar"] is False and "heal cleanly" in out["narrative"]


def test_healed_injuries_are_marked_on_read(monkeypatch):
    stub = _StubDB(injuries=[],
                   scars=[{"description": "knife", "body_part": "cheek"}])
    stub.healed = [{"id": 5, "description": "cut", "body_part": "hand", "became_scar": False}]

    async def fetch(sql, *args):
        stub.reads.append((sql, args))
        if "RETURNING id" in sql:
            return []
        if "became_scar=true" in sql:
            return stub.scars
        if "heal_by_game_day>$3" in sql:
            return []
        return stub.healed
    monkeypatch.setattr(stub, "fetch", fetch)
    monkeypatch.setattr(ps, "Database", stub)

    out = _run(ps.get_state(2071, session_id=5))

    assert out["healed"] == 1 and out["visual"] == "They bear a scar on the cheek.", out
    marked = [args for sql, args in stub.writes if "SET status=$1" in sql]
    assert marked == [("healed", 5)], marked


def test_a_character_with_nothing_wrong_reads_no_visual(monkeypatch):
    stub = _StubDB()
    monkeypatch.setattr(ps, "Database", stub)
    out = _run(ps.get_state(2071, session_id=5))
    assert out["visual"] is None and out["healed"] == 0


def test_the_tick_counts_the_rows_it_processed(monkeypatch):
    """execute() returns PostgreSQL's status tag, not a count."""
    stub = _StubDB(game_day=2253)
    stub.returning_rows = [{"id": 1}, {"id": 2}, {"id": 3}]
    monkeypatch.setattr(ps, "Database", stub)

    out = _run(ps.run_tick(session_id=5))

    assert out == {"processed": 3}, out
