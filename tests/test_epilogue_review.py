"""Module review tests for modules/epilogue.py (2026-10-03). Every call is stubbed."""
from __future__ import annotations

import asyncio
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.epilogue as epilogue  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


class _StubDB:
    def __init__(self, counts=(275, 4000, 900), victories=()):
        self.counts = list(counts)
        self.victories = list(victories)
        self.reads = []

    async def fetchval(self, sql, *args):
        self.reads.append((sql, args))
        return self.counts.pop(0) if self.counts else 0

    async def fetch(self, sql, *args):
        self.reads.append((sql, args))
        return self.victories


def test_the_summary_counts_the_campaign(monkeypatch):
    stub = _StubDB(counts=(275, 4000, 900),
                   victories=[{"victory_type": "military", "progress": 12.5}])
    monkeypatch.setattr(epilogue, "Database", stub)

    out = _run(epilogue.generate(session_id=5))

    assert out["characters"] == 275 and out["ships"] == 4000 and out["events"] == 900
    assert out["victory_data"] == {"military": 12.5}
    assert "275 characters, 4000 ships, 900 events" in out["summary"]


def test_every_read_names_the_session(monkeypatch):
    stub = _StubDB()
    monkeypatch.setattr(epilogue, "Database", stub)
    _run(epilogue.generate(session_id=5))
    assert stub.reads
    for sql, args in stub.reads:
        assert "session_id" in sql or "f.session_id = $1" in sql, sql
        assert 5 in args, (sql, args)


def test_a_campaign_with_no_victory_rows_reports_an_empty_map(monkeypatch):
    stub = _StubDB(victories=[])
    monkeypatch.setattr(epilogue, "Database", stub)
    out = _run(epilogue.generate(session_id=3))
    assert out["victory_data"] == {}


def test_the_tick_is_reachable_and_silent(monkeypatch):
    stub = _StubDB()
    monkeypatch.setattr(epilogue, "Database", stub)
    assert _run(epilogue.run_tick(session_id=5)) == {"status": "epilogue_ready"}
    assert stub.reads == []
