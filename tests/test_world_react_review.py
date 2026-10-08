"""Module review tests for modules/world_react.py.

Defects covered:

1. `propagate` read the game day with `SELECT COALESCE(game_day,1) …` and then
   used the RESULT directly: for a session id that does not exist the fetchval
   returns None (the COALESCE is inside the SQL, not on the result), so
   `gd + r["delay"]` raised TypeError. Both reads go through `_game_day` now.
2. `surface` returned None whether or not it matched a row, so a caller could
   not tell a surfaced reaction from a miss. It reports, and names the miss.

Checked and found correct: every read and write carries session_id; an unknown
event type provokes no reactions rather than an error; the trigger set covers
the three canon events and each carries its own delay window; the due list is
capped at three and ordered by the day it surfaces; and `run_tick` counts
instead of consuming.

Deliberately NOT changed, and reported to the lead: `run_tick` does not surface
the reactions it counts. The consumer is `core.master_briefing`, which imports `get_due` from this
# module (`core/master_briefing.py:50`), so a
tick that marked them surfaced first would leave the briefing with nothing to
show. Nothing calls `surface` either, which is why the same three reactions are
due in every briefing — that belongs to the briefing, not here.

No database: every test drives a fake Database.
"""
from __future__ import annotations

import contextlib
import os

import pytest

import modules.world_react as wr

# Scratch session: sessions 3 and 5 are frozen reference data and the writers refuse them.
SID = 900 + os.getpid() % 100


class FakeDB:
    def __init__(self, fetch=None, fetchval=100, execute_tag="UPDATE 1"):
        self.fetch_rows = fetch if fetch is not None else []
        self.fetchval_value = fetchval
        self.execute_tag = execute_tag
        self.calls = []

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", " ".join(sql.split()), args))
        return self.fetch_rows

    async def fetchval(self, sql, *args):
        self.calls.append(("fetchval", " ".join(sql.split()), args))
        return self.fetchval_value

    async def execute(self, sql, *args):
        self.calls.append(("execute", " ".join(sql.split()), args))
        return self.execute_tag

    def sql(self, kind=None):
        return [c[1] for c in self.calls if kind is None or c[0] == kind]

    def args_for(self, needle, kind=None):
        return [c[2] for c in self.calls
                if needle in c[1] and (kind is None or c[0] == kind)]


def _install(monkeypatch, fake):
    for name in ("fetch", "fetchval", "execute"):
        monkeypatch.setattr("modules.world_react.Database." + name, getattr(fake, name))
    monkeypatch.setattr("modules.world_react.Database.transaction", _transaction)
    return fake


class _Conn:
    """Transaction connection: forwards to the module's patched Database calls."""

    async def execute(self, sql, *args):
        return await wr.Database.execute(sql, *args)


@contextlib.asynccontextmanager
async def _transaction():
    yield _Conn()


# ── 1. A missing session does not crash the propagation ─────────────────

async def test_a_missing_session_falls_back_to_day_one(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchval=None))

    reactions = await wr.propagate("major_treaty", {"ally_faction": "Iron Concord"}, SID)

    assert len(reactions) == 1
    inserted = fake.args_for("INSERT INTO maya_rp.world_reactions", "execute")[0]
    assert inserted[0] == SID
    assert 1 <= inserted[5] <= 6, "the surface day should be day 1 plus the delay"


async def test_an_unknown_event_type_provokes_nothing(monkeypatch):
    fake = _install(monkeypatch, FakeDB())

    assert await wr.propagate("nothing_happened", {}, SID) == []
    assert not fake.sql("execute")


async def test_a_conquest_queues_outrage_and_two_neighbours(monkeypatch):
    neighbours = [{"system_name": "Kappa", "controlling_faction": "Iron Concord"},
                  {"system_name": "Vega", "controlling_faction": "The Den"}]
    fake = _install(monkeypatch, FakeDB(fetch=neighbours, fetchval=100))

    reactions = await wr.propagate("territory_conquered",
                                   {"system_name": "Dagger's Rest", "from_faction": "The Den"}, SID)

    assert [r["rt"] for r in reactions] == ["outrage", "fear", "fear"]
    assert reactions[0]["sf"] == "The Den"
    assert len(fake.args_for("INSERT INTO maya_rp.world_reactions", "execute")) == 3


async def test_a_massacre_above_ten_queues_the_recruitment_reaction(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchval=100))

    small = await wr.propagate("massacre", {"count": 4, "faction": "The Den", "location": "Kappa"}, SID)
    big = await wr.propagate("massacre", {"count": 12, "faction": "The Den", "location": "Kappa"}, SID)

    assert [r["rt"] for r in small] == ["horror"]
    assert [r["rt"] for r in big] == ["horror", "recruitment"]


# ── 2. surface reports what it did ──────────────────────────────────────

async def test_surface_reports_a_hit(monkeypatch):
    fake = _install(monkeypatch, FakeDB(execute_tag="UPDATE 1"))

    assert await wr.surface(9, SID) is True
    assert fake.args_for("SET surfaced=true", "execute")[0] == (9, SID)


async def test_surface_reports_a_miss_and_names_it(monkeypatch):
    seen = []
    monkeypatch.setattr("modules.world_react.info", lambda mod, msg: seen.append(msg))
    _install(monkeypatch, FakeDB(execute_tag="UPDATE 0"))

    assert await wr.surface(9, SID) is False
    assert any(f"not in session {SID}" in m for m in seen), seen


async def test_surface_defaults_to_the_resolved_session(monkeypatch):
    fake = _install(monkeypatch, FakeDB())
    monkeypatch.setenv("RP_SESSION", "77")

    await wr.surface(9)

    assert fake.args_for("SET surfaced=true", "execute")[0] == (9, 77)


# ── Contract the module claims ──────────────────────────────────────────

async def test_contract_due_reactions_are_capped_at_three_and_ordered(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[], fetchval=120))

    await wr.get_due(SID)

    sql = fake.sql("fetch")[0]
    assert "session_id=$1" in sql and "surfaced=false" in sql
    assert "surfaces_at_game_day<=$2" in sql and "LIMIT 3" in sql
    assert fake.args_for("world_reactions", "fetch")[0] == (SID, 120)


async def test_contract_the_tick_counts_without_consuming(monkeypatch):
    rows = [{"id": 1}, {"id": 2}]
    fake = _install(monkeypatch, FakeDB(fetch=rows, fetchval=120))

    out = await wr.run_tick(SID)

    assert out == {"due_reactions": 2}
    assert not fake.sql("execute"), "the tick must leave them for the briefing"
