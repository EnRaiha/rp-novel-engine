"""Module review tests for modules/artifacts.py (2026-10-03).

Every database call is stubbed. No artifact or medal row is created. The stub's `transaction()` yields
the stub itself. Writers use a scratch session: the frozen guard refuses sessions 3 and 5.
"""
from __future__ import annotations

import asyncio
import os
import pathlib
from contextlib import asynccontextmanager
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.artifacts as art  # noqa: E402

SID = 900 + os.getpid() % 100


def _run(coro):
    return asyncio.run(coro)


class _StubDB:
    def __init__(self, artifact=None):
        self.artifact = artifact
        self.reads = []
        self.writes = []

    async def fetchrow(self, sql, *args):
        self.reads.append((sql, args))
        if "FROM maya_rp.artifacts" in sql:
            return self.artifact
        return None

    async def fetchval(self, sql, *args):
        self.reads.append((sql, args))
        if "INSERT INTO maya_rp.artifacts" in sql:
            self.writes.append((sql, args))
            return 55
        return 0

    async def fetch(self, sql, *args):
        self.reads.append((sql, args))
        return []

    async def execute(self, sql, *args):
        self.writes.append((sql, args))
        return "OK"

    @asynccontextmanager
    async def transaction(self):
        yield self


def test_equipping_names_the_session_in_the_write(monkeypatch):
    stub = _StubDB(artifact={"id": 55, "name": "Echo of Kael"})
    monkeypatch.setattr(art, "Database", stub)

    out = _run(art.equip(55, 2071, session_id=SID))

    assert out == {"equipped": "Echo of Kael", "target_id": 2071}
    (sql, args), = stub.writes
    assert "session_id=$3" in sql and args == (2071, 55, SID)


def test_an_artifact_from_another_campaign_cannot_be_equipped(monkeypatch):
    stub = _StubDB(artifact=None)
    monkeypatch.setattr(art, "Database", stub)
    out = _run(art.equip(55, 2071, session_id=SID))
    assert out["error"] == "Artifact not found"
    assert stub.writes == []


def test_a_medal_without_a_recipient_is_refused(monkeypatch):
    stub = _StubDB()
    monkeypatch.setattr(art, "Database", stub)
    for bad in ("", "   ", None):
        out = _run(art.award_medal(SID, bad, "merit"))
        assert "needs a recipient" in out["error"], (bad, out)
    assert stub.writes == []


def test_an_unknown_medal_tier_is_refused_by_name(monkeypatch):
    stub = _StubDB()
    monkeypatch.setattr(art, "Database", stub)
    out = _run(art.award_medal(SID, "Rika Voss", "gold"))
    assert "Tier mesti" in out["error"] and "resurrection" in out["error"], out
    assert stub.writes == []


def test_a_medal_is_awarded_with_its_backstory(monkeypatch):
    stub = _StubDB()
    monkeypatch.setattr(art, "Database", stub)

    out = _run(art.award_medal(SID, "Rika Voss", "sacrifice", "she paid with a life"))

    assert out["medal_id"] == 55 and out["bonus"] == 10
    insert = [args for sql, args in stub.writes if "INSERT INTO maya_rp.artifacts" in sql][0]
    assert insert[0] == SID and insert[3] == "she paid with a life"
    assert insert[5] == "she paid with a life"          # sacrifice_backstory
    assert insert[6] == "Rika Voss"                     # award_recipient
    event = [args for sql, args in stub.writes if "INSERT INTO maya_rp.events" in sql]
    assert event and event[0][0] == SID


def test_the_discovery_rolls_inside_the_declared_tables(monkeypatch):
    monkeypatch.setattr(art.random, "choice", lambda seq: seq[0])
    monkeypatch.setattr(art.random, "choices", lambda seq, weights=None: ["legendary"])
    monkeypatch.setattr(art.random, "randint", lambda a, b: 10)
    stub = _StubDB()
    monkeypatch.setattr(art, "Database", stub)

    out = _run(art.discover(session_id=SID))

    assert out["type"] == art.ARTIFACT_TYPES[0]
    assert out["rarity"] == "legendary" and out["bonus"] == 10 * 15
    assert out["name"].startswith("Echo of Aethel")
