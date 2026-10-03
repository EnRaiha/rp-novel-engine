"""Module review tests for core/pacing.py.

Defects covered:

1. `get_mode` fell back to `MODES["downtime"]` for a mode the engine does not
   know, and returned the unknown name beside it, so the GM got downtime prose
   labelled with a mode nothing recognises. Now it says so.
2. `transition` returned early for an unknown mode with no word to anyone.
3. `transition` read `SELECT COALESCE(game_day,1) ... WHERE id=$1`, whose COALESCE
   never fires when the session row is absent: fetchval answers None and NULL was
   written into `entered_at_game_day`.
4. `adjust_tension` raised TypeError on a session with no `narrative_pacing` row:
   the UPDATE matched nothing and the read that followed got None. `increment`
   silently did nothing on the same session.
5. `run_tick` logged its fault at info level, and the orchestrator runs it every
   tick.

Checked and found correct, so the row is not silent about what it looked at:
every query is scoped by session_id; CHECK_QUERIES carries the session filter and
the comments record why `status='active'` and not the column default; `horror` is
deliberately excluded from auto-detection; `instruction` emits the same fields the
MODES table holds.

No database: every test drives a fake connection.
"""
from __future__ import annotations

import pytest

from core import pacing


class FakeDB:
    """Stateful enough to model `ensure` creating the row the next read needs."""

    def __init__(self, row=None, game_day=None):
        self.row = row
        self.game_day = game_day
        self.executes: list[tuple[str, tuple]] = []

    async def execute(self, sql, *args):
        flat = " ".join(sql.split())
        self.executes.append((flat, args))
        if flat.startswith("INSERT INTO maya_rp.narrative_pacing") and self.row is None:
            self.row = {"session_id": args[0], "mode": "downtime", "tension": 0, "scenes_in_mode": 0}
        return "INSERT 0 1"

    async def fetchrow(self, sql, *args):
        return self.row

    async def fetchval(self, sql, *args):
        if "COUNT" in sql:
            return 0
        return self.game_day


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()
    logs = {"info": [], "warn": [], "error": []}
    monkeypatch.setattr(pacing, "info", lambda m, msg: logs["info"].append(msg))
    monkeypatch.setattr(pacing, "warn", lambda m, msg: logs["warn"].append(msg))
    monkeypatch.setattr(pacing, "error", lambda m, msg: logs["error"].append(msg))
    monkeypatch.setattr(pacing.Database, "execute", staticmethod(fake.execute))
    monkeypatch.setattr(pacing.Database, "fetchrow", staticmethod(fake.fetchrow))
    monkeypatch.setattr(pacing.Database, "fetchval", staticmethod(fake.fetchval))
    return fake, logs


async def test_get_mode_reports_an_unknown_mode(db):
    """(1) The fallback was silent and the returned mode did not match its config."""
    fake, logs = db
    fake.row = {"mode": "melodrama", "tension": 3, "scenes_in_mode": 1}
    out = await pacing.PacingDirector.get_mode(5)
    assert logs["warn"], "an unknown mode was served as downtime without a word"
    assert out["config"] is pacing.MODES["downtime"]


async def test_transition_refuses_an_unknown_mode_out_loud(db):
    """(2) Nothing was written and nothing was said."""
    fake, logs = db
    await pacing.PacingDirector.transition("melodrama", "test", session_id=5)
    assert logs["warn"], "the rejected mode was silent"
    assert [e for e in fake.executes if e[0].startswith("UPDATE")] == []


async def test_transition_writes_a_day_when_the_session_row_is_absent(db):
    """(3) COALESCE inside the SELECT cannot cover a missing row."""
    fake, _ = db
    fake.game_day = None
    await pacing.PacingDirector.transition("combat", "test", session_id=5)
    update = [e for e in fake.executes if e[0].startswith("UPDATE")][0]
    assert update[1][1] == 1, update[1]


async def test_adjust_tension_works_without_an_existing_row(db):
    """(4) TypeError on the read, and increment matched nothing."""
    fake, logs = db
    await pacing.PacingDirector.adjust_tension(2, "test", session_id=5)
    assert any(e[0].startswith("INSERT INTO maya_rp.narrative_pacing") for e in fake.executes), \
        "no row was created, so the tension update matched nothing"
    assert logs["info"], "the tension change was not reported"


async def test_increment_creates_the_row_it_counts(db):
    fake, _ = db
    await pacing.PacingDirector.increment(session_id=5)
    assert any(e[0].startswith("INSERT INTO maya_rp.narrative_pacing") for e in fake.executes)


async def test_run_tick_logs_a_fault_at_error_level(db, monkeypatch):
    """(5) The orchestrator runs this every tick; info level hid the fault."""
    fake, logs = db

    async def boom(session_id):
        raise RuntimeError("pacing table is gone")

    monkeypatch.setattr(pacing.PacingDirector, "ensure", staticmethod(boom))
    out = await pacing.PacingDirector.run_tick(5)
    assert out == {"error": "pacing table is gone"}
    assert logs["error"], "a failed tick was not logged as an error"
    assert not logs["info"]
