"""Module review tests for modules/characters.py (2026-10-03).

Every database call is stubbed. A bond is never shifted on a real character.
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

import modules.characters as characters  # noqa: E402


#: Scratch campaign: sessions 3 and 5 are frozen, and the writers refuse them.
SID = 900 + os.getpid() % 100


def sql_norm(sql):
    return " ".join(sql.split())


def _run(coro):
    return asyncio.run(coro)


class _StubDB:
    def __init__(self, char=None, stale=()):
        self.char = char
        self.stale = list(stale)
        self.reads = []
        self.writes = []

    async def fetchrow(self, sql, *args):
        self.reads.append((sql, args))
        if "FROM maya_rp.characters" in sql:
            return self.char
        return None

    async def fetch(self, sql, *args):
        self.reads.append((sql, args))
        if "character_arcs" in sql:
            return self.stale
        return []

    async def execute(self, sql, *args):
        self.writes.append((sql, args))
        return "OK"

    @asynccontextmanager
    async def transaction(self):
        yield _Conn(self)


class _Conn:
    """The transaction connection: the scoped arc UPDATE returns the rows it staled."""

    def __init__(self, stub):
        self.stub = stub

    async def fetch(self, sql, *args):
        self.stub.writes.append((sql, args))
        return self.stub.stale

    async def execute(self, sql, *args):
        self.stub.writes.append((sql, args))
        return "OK"


CHAR_ZERO = {"id": 2071, "name": "Rika Voss", "bond": 0, "role": "Queen"}


# ── A stored bond of zero is a bond ─────────────────────────────────────


def test_a_zero_bond_is_read_as_zero_not_as_the_default(monkeypatch):
    """696 of 715 live characters sit at bond 0; `or 50` raised them all."""
    stub = _StubDB(char=CHAR_ZERO)
    monkeypatch.setattr(characters, "Database", stub)

    out = _run(characters.resolve_intent(SID, "talk", "Rika", 2071))

    assert out["bond_before"] == 0, out
    assert out["bond_after"] == 1, out
    written = [args for sql, args in stub.writes if "SET bond=" in sql]
    assert written == [(1, 2071, SID)], written


def test_an_arrest_cannot_lift_a_zero_bond(monkeypatch):
    stub = _StubDB(char=CHAR_ZERO)
    monkeypatch.setattr(characters, "Database", stub)

    out = _run(characters.resolve_intent(SID, "arrest", "Rika", 2071))

    assert out["bond_shift"] == -5
    assert out["bond_after"] == 0, out


def test_a_null_bond_still_reads_the_documented_default(monkeypatch):
    stub = _StubDB(char={**CHAR_ZERO, "bond": None})
    monkeypatch.setattr(characters, "Database", stub)
    out = _run(characters.resolve_intent(SID, "gift", "Rika", 2071))
    assert out["bond_before"] == 50 and out["bond_after"] == 52, out


def test_the_bond_update_names_the_session(monkeypatch):
    stub = _StubDB(char=CHAR_ZERO)
    monkeypatch.setattr(characters, "Database", stub)
    _run(characters.resolve_intent(SID, "promote", "Rika", 2071))
    (sql, args), = [w for w in stub.writes if "SET bond=" in w[0]]
    assert "session_id=$3" in sql and args[-1] == SID


def test_an_unknown_action_shifts_nothing_and_writes_nothing(monkeypatch):
    stub = _StubDB(char=CHAR_ZERO)
    monkeypatch.setattr(characters, "Database", stub)
    out = _run(characters.resolve_intent(SID, "levitate", "Rika", 2071))
    assert out["bond_shift"] == 0 and out["success"] is True
    assert stub.writes == []


def test_a_character_from_another_campaign_is_refused(monkeypatch):
    stub = _StubDB(char=None)
    monkeypatch.setattr(characters, "Database", stub)
    out = _run(characters.resolve_intent(SID, "talk", "Someone", 2071))
    assert out["success"] is False and "not found" in out["narrative_hook"], out
    assert stub.writes == []


def test_no_character_named_is_refused_by_name(monkeypatch):
    stub = _StubDB()
    monkeypatch.setattr(characters, "Database", stub)
    out = _run(characters.resolve_intent(SID, "talk", "", 0))
    assert "No character specified" in out["narrative_hook"], out
    assert stub.reads == []


# ── The arc sweep ───────────────────────────────────────────────────────


def test_the_stale_sweep_marks_and_reports(monkeypatch):
    stale = [{"id": 1, "character_table": "characters", "character_id": 9,
              "arc_name": "The Long Winter"}]
    stub = _StubDB(stale=stale)
    monkeypatch.setattr(characters, "Database", stub)

    out = _run(characters.run_tick(session_id=SID))

    assert out == {"character_arcs": 0, "stale_arcs": 1}
    marked = [args for sql, args in stub.writes if "SET status='stale'" in sql]
    assert marked == [(SID,)], "the sweep must bind the session, not the arc ids"
    sweep = [sql for sql, _ in stub.writes if "SET status='stale'" in sql][0]
    assert "c.session_id=$1" in sql_norm(sweep), sweep
    event = [args for sql, args in stub.writes if "INSERT INTO maya_rp.events" in sql]
    assert event and event[0][0] == SID


def test_a_clean_sweep_writes_no_event(monkeypatch):
    stub = _StubDB(stale=[])
    monkeypatch.setattr(characters, "Database", stub)
    out = _run(characters.run_tick(session_id=SID))
    assert out == {"character_arcs": 0, "stale_arcs": 0}
    assert not [sql for sql, _ in stub.writes if "INSERT INTO maya_rp.events" in sql]


def test_a_failing_sweep_returns_the_error(monkeypatch):
    class _Boom(_StubDB):
        @asynccontextmanager
        async def transaction(self):
            raise RuntimeError("connection reset")
            yield
    stub = _Boom()
    monkeypatch.setattr(characters, "Database", stub)
    logged = []
    monkeypatch.setattr(characters, "info", lambda *a: logged.append(a[-1])) if hasattr(characters, "info") else None
    out = _run(characters.run_tick(session_id=SID))
    assert "connection reset" in out["error"], out
