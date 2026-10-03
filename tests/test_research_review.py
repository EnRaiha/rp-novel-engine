"""Module review tests for modules/research.py.

Defects covered:

1. `run_tick` defaulted to the literal session 3, the frozen reference campaign,
   while Config.SESSION_ID resolves to the active arc. The module did not even
   import Config, so a fallback would have raised NameError.
2. `float(active["progress_pct"])` raised TypeError on a NULL percentage, which
   the column allows, and `gd / active["duration_days"]` divided by zero on a
   project with no duration. Both are guarded, and a durationless project says so
   instead of killing the tick.
3. The `research_queue` writes matched on id alone. `ship_tech_bonuses` carries no
   session_id (it is a global table), so its insert is correctly unscoped.

Checked and found correct: the active project is selected for this session and in
queue order; a pending project is only started when the strategic-resource pool
covers its costs, and the costs are taken in a second pass so a shortfall charges
nothing; the completion bonus writes are session-scoped except the two global
tables; and `resource_inventory` is the global pool by design, matching how
pirates and the ledger treat it.

Reported to the lead, not fixed: the affordability check and the deduction are
separate statements, so two ticks racing could start a project without paying.

No database: every test drives a fake Database.
"""
from __future__ import annotations

import pytest

import modules.research as research


class FakeDB:
    def __init__(self, rows=None, fetch=None, fetchval=None):
        self.row_map = rows or {}
        self.fetch_rows = fetch if fetch is not None else []
        self.fetchval_value = fetchval
        self.calls = []

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", " ".join(sql.split()), args))
        for marker, value in self.row_map.items():
            if marker in sql:
                return value
        return None

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", " ".join(sql.split()), args))
        return self.fetch_rows

    async def fetchval(self, sql, *args):
        self.calls.append(("fetchval", " ".join(sql.split()), args))
        return self.fetchval_value

    async def execute(self, sql, *args):
        self.calls.append(("execute", " ".join(sql.split()), args))
        return "UPDATE 1"

    def sql(self, kind=None):
        return [c[1] for c in self.calls if kind is None or c[0] == kind]

    def args_for(self, needle, kind=None):
        return [c[2] for c in self.calls
                if needle in c[1] and (kind is None or c[0] == kind)]


def _install(monkeypatch, fake):
    for name in ("fetchrow", "fetch", "fetchval", "execute"):
        monkeypatch.setattr("modules.research.Database." + name, getattr(fake, name))
    return fake


def _project(**over):
    row = {"qid": 5, "id": 9, "name": "Deep Mining", "duration_days": 10,
           "progress_pct": 40.0, "resource_costs": None, "bonus_type": None,
           "bonus_value": None}
    row.update(over)
    return row


# ── 1. The session default ──────────────────────────────────────────────

async def test_the_tick_defaults_to_the_engine_session(monkeypatch):
    seen = []
    _install(monkeypatch, FakeDB())
    monkeypatch.setattr("modules.research.Config.SESSION_ID", 77)

    async def fetchrow(sql, *args):
        seen.append(args)
        return None

    monkeypatch.setattr("modules.research.Database.fetchrow", fetchrow)

    await research.run_tick()

    assert seen == [(77,)]


# ── 2. A NULL percentage or a zero duration cannot kill the tick ────────

async def test_a_null_progress_starts_from_zero(monkeypatch):
    fake = _install(monkeypatch, FakeDB(rows={"rq.status='active'": _project(progress_pct=None)}))
    monkeypatch.setattr("modules.research.calc_game_days", lambda when: 1.0)

    async def fetchrow(sql, *args):
        if "last_tick_at" in sql:
            return {"last_tick_at": "x"}
        return _project(progress_pct=None)

    monkeypatch.setattr("modules.research.Database.fetchrow", fetchrow)

    await research.run_tick(5)

    written = fake.args_for("SET progress_pct=$1", "execute")[0]
    assert written[0] == pytest.approx(10.0)      # 1 day of 10 → +10%
    assert written[1] == 9


async def test_a_project_with_no_duration_is_named_not_divided(monkeypatch):
    _install(monkeypatch, FakeDB())
    monkeypatch.setattr("modules.research.calc_game_days", lambda when: 1.0)

    async def fetchrow(sql, *args):
        if "last_tick_at" in sql:
            return {"last_tick_at": "x"}
        return _project(duration_days=0)

    monkeypatch.setattr("modules.research.Database.fetchrow", fetchrow)

    await research.run_tick(5)      # must not raise ZeroDivisionError


# ── 3. The queue writes are scoped ──────────────────────────────────────

async def test_the_queue_writes_carry_the_session(monkeypatch):
    pending = _project(qid=6, progress_pct=0.0)
    fake = _install(monkeypatch, FakeDB(fetch=[{"ship_type": "frigate"}]))

    async def fetchrow(sql, *args):
        if "last_tick_at" in sql:
            return {"last_tick_at": "x"}
        if "rq.status='active'" in sql:
            return None
        if "rq.status='pending'" in sql:
            return pending
        return pending

    monkeypatch.setattr("modules.research.Database.fetchrow", fetchrow)
    monkeypatch.setattr("modules.research.calc_game_days", lambda when: 1.0)

    await research.run_tick(5)

    started = fake.args_for("SET status='active'", "execute")
    assert started and started[0] == (6, 5)
    assert all("session_id=$2" in s for s in fake.sql("execute") if "research_queue" in s)


async def test_a_completion_moves_the_queue_on_with_the_session(monkeypatch):
    done = _project(progress_pct=95.0, duration_days=1)
    fake = _install(monkeypatch, FakeDB())

    async def fetchrow(sql, *args):
        if "last_tick_at" in sql:
            return {"last_tick_at": "x"}
        if "rq.status='active'" in sql:
            return done
        if "status='pending'" in sql:
            return {"id": 12}
        return done

    monkeypatch.setattr("modules.research.Database.fetchrow", fetchrow)
    monkeypatch.setattr("modules.research.calc_game_days", lambda when: 1.0)

    await research.run_tick(5)

    complete = fake.args_for("SET status='complete'", "execute")[0]
    assert complete == (5, 5)
    nxt = fake.args_for("SET status='active' WHERE id=$1 AND session_id=$2", "execute")[0]
    assert nxt == (12, 5)


# ── Contract around the costs ───────────────────────────────────────────

async def test_a_shortfall_charges_nothing(monkeypatch):
    pending = _project(resource_costs={"Titanium": 50})
    fake = _install(monkeypatch, FakeDB())

    async def fetchrow(sql, *args):
        if "last_tick_at" in sql:
            return {"last_tick_at": "x"}
        if "rq.status='active'" in sql:
            return None
        if "rq.status='pending'" in sql:
            return pending
        if "resource_inventory" in sql:
            return {"avail": 10}
        return pending

    monkeypatch.setattr("modules.research.Database.fetchrow", fetchrow)
    monkeypatch.setattr("modules.research.calc_game_days", lambda when: 1.0)

    await research.run_tick(5)

    assert not fake.args_for("SET status='active'", "execute"), "a project started without paying"
    assert not fake.args_for("ri.quantity-$1", "execute")


async def test_a_covered_cost_is_taken_from_the_pool(monkeypatch):
    pending = _project(resource_costs={"Titanium": 5})
    fake = _install(monkeypatch, FakeDB())

    async def fetchrow(sql, *args):
        if "last_tick_at" in sql:
            return {"last_tick_at": "x"}
        if "rq.status='active'" in sql:
            return None
        if "rq.status='pending'" in sql:
            return pending
        if "resource_inventory" in sql:
            return {"avail": 10}
        return pending

    monkeypatch.setattr("modules.research.Database.fetchrow", fetchrow)
    monkeypatch.setattr("modules.research.calc_game_days", lambda when: 1.0)

    await research.run_tick(5)

    assert fake.args_for("ri.quantity-$1", "execute")[0] == (5, "Titanium")
