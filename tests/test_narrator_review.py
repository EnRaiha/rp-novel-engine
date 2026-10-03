"""Module review tests for modules/narrator.py (2026-10-03). Every call is stubbed."""
from __future__ import annotations

import asyncio
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import modules.narrator as narrator  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


class _StubDB:
    def __init__(self, events=()):
        self.events = list(events)
        self.reads = []

    async def fetch(self, sql, *args):
        self.reads.append((sql, args))
        return self.events


EVENTS = [
    {"event_type": "build", "title": "Blizzard Zero", "description": "a corvette"},
    {"event_type": "unknown_type", "title": "Odd Thing", "description": ""},
]


def test_a_template_is_chosen_by_event_type(monkeypatch):
    monkeypatch.setattr(narrator.random, "choice", lambda seq: seq[0])
    out = _run(narrator.narrate_event("build", "Blizzard Zero", "a corvette"))
    assert out == "A new vessel joins the fleet: Blizzard Zero. a corvette", out


def test_an_unknown_event_type_falls_back_to_the_default_templates(monkeypatch):
    monkeypatch.setattr(narrator.random, "choice", lambda seq: seq[0])
    out = _run(narrator.narrate_event("weather", "Storm", ""))
    assert out == "Fleet log: Storm.", out


def test_the_tick_hands_the_prose_back(monkeypatch):
    """The prose was built and thrown away; the tick returned only a count."""
    stub = _StubDB(events=EVENTS)
    monkeypatch.setattr(narrator, "Database", stub)
    monkeypatch.setattr(narrator.random, "choice", lambda seq: seq[0])

    out = _run(narrator.run_tick(session_id=5))

    assert out["narrated"] == 2
    assert len(out["narratives"]) == 2, out
    assert out["narratives"][0].startswith("A new vessel joins the fleet:")


def test_the_tick_reads_its_own_campaign(monkeypatch):
    stub = _StubDB()
    monkeypatch.setattr(narrator, "Database", stub)
    _run(narrator.run_tick(session_id=5))
    (sql, args), = stub.reads
    assert "session_id=$1" in sql and args == (5,)


def test_the_tick_reports_an_error_instead_of_raising(monkeypatch):
    class _Boom(_StubDB):
        async def fetch(self, sql, *args):
            raise RuntimeError("connection reset")
    monkeypatch.setattr(narrator, "Database", _Boom())
    logged = []
    monkeypatch.setattr(narrator, "info", lambda *a: logged.append(a[-1]))
    out = _run(narrator.run_tick(session_id=3))
    assert "connection reset" in out["error"]
    assert any("connection reset" in line for line in logged)
