"""narrative_seeds and objectives fixes: a payoff and a task reward are claimed once, hinted seeds reach the tick.

Real database. Every write lands in a scratch session (900-999) and `Config.SESSION_ID` points at it, so
no default can reach session 3 or 5.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest_asyncio  # noqa: E402

import core.config  # noqa: E402
from core.db import Database  # noqa: E402
from modules import narrative_seeds, objectives  # noqa: E402

#: Children of `sessions` this file writes, removed before the session row.
_TABLES = ("events", "narrative_seeds", "quarterly_tasks", "resources")


async def _wipe(session_id):
    for table in _TABLES:
        await Database.execute(f"DELETE FROM maya_rp.{table} WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", session_id)


@pytest_asyncio.fixture
async def sid(scratch_session, monkeypatch):
    """A scratch session at game day 100 (quarter 1) with a zeroed resources row."""
    monkeypatch.setattr(core.config.Config, "SESSION_ID", scratch_session)
    await Database.init()
    await _wipe(scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status, game_day) "
        "VALUES ($1,'seeds objectives scratch','active',100)", scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.resources (session_id, research_points) VALUES ($1, 0)", scratch_session)
    try:
        yield scratch_session
    finally:
        await _wipe(scratch_session)
        await Database.close()


async def _warm_pool():
    """Open a second connection so a race test does not queue on one."""
    await asyncio.gather(Database.fetchval("SELECT pg_sleep(0.2)"), Database.fetchval("SELECT pg_sleep(0.2)"))


async def _seed(sid, status="planted", day=50, seed_type="review", template=""):
    return await Database.fetchval(
        "INSERT INTO maya_rp.narrative_seeds (session_id, seed_type, content, planted_at_game_day, "
        "payoff_event_template, payoff_game_day, status) VALUES ($1,$2,'a hidden thing',1,$3,$4,$5) RETURNING id",
        sid, seed_type, template, day, status)


async def _status(seed_id):
    return await Database.fetchval("SELECT status FROM maya_rp.narrative_seeds WHERE id=$1", seed_id)


async def _payoffs(sid):
    return await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.events WHERE session_id=$1 AND event_type='payoff'", sid)


async def _task(sid, progress=0, target=10, status="active", title="Fleet Exercise", index=1):
    return await Database.fetchval(
        "INSERT INTO maya_rp.quarterly_tasks (session_id, quarter, task_index, title, objective, "
        "target_value, progress, current_progress, status, reward_type, reward_value) "
        "VALUES ($1,1,$2,$3,'Sweep X hostiles di sempadan',$4,$5,$5,$6,'blueprint',250000) RETURNING id",
        sid, index, title, target, progress, status)


async def _points(sid):
    return await Database.fetchval("SELECT research_points FROM maya_rp.resources WHERE session_id=$1", sid)


async def _counters(task_id):
    row = await Database.fetchrow(
        "SELECT progress, current_progress, status FROM maya_rp.quarterly_tasks WHERE id=$1", task_id)
    return row["progress"], row["current_progress"], row["status"]


def _compete_once(monkeypatch, write):
    """Make the next quarterly-task SELECT return stale rows: run the real fetch, await `write()`, return the rows."""
    real = Database.fetch
    state = {"done": False}

    async def fetch(sql, *a):
        rows = await real(sql, *a)
        if not state["done"]:
            state["done"] = True
            await write()
        return rows

    monkeypatch.setattr("modules.objectives.Database.fetch", fetch)


# ── narrative_seeds ─────────────────────────────────────────────────────

async def test_the_tick_pays_off_a_foreshadowed_seed(sid):
    seed = await _seed(sid, status="foreshadowed", day=50)

    out = await narrative_seeds.run_tick(sid)

    assert out == {"auto_payoffs": 1}
    assert await _status(seed) == "paid_off"
    assert await _payoffs(sid) == 1


async def test_a_second_payoff_emits_no_second_event(sid):
    seed = await _seed(sid)

    first = await narrative_seeds.pay_off(seed, sid)
    second = await narrative_seeds.pay_off(seed, sid)

    assert first["paid_off"] is True
    assert second["paid_off"] is False and "paid_off" in second["error"]
    assert await _payoffs(sid) == 1


async def test_concurrent_payoffs_emit_one_event(sid):
    seed = await _seed(sid)
    await _warm_pool()

    await asyncio.gather(narrative_seeds.pay_off(seed, sid), narrative_seeds.pay_off(seed, sid))

    assert await _payoffs(sid) == 1


async def test_a_closed_seed_is_not_revived_by_a_hint(sid):
    seed = await _seed(sid, status="paid_off")

    out = await narrative_seeds.mark_foreshadowed(seed, sid)

    assert out["marked"] is False
    assert await _status(seed) == "paid_off"


async def test_a_quoted_seed_type_makes_valid_tags(sid):
    seed = await _seed(sid, seed_type='say "hi"')

    out = await narrative_seeds.pay_off(seed, sid)

    assert out["paid_off"] is True
    tags = await Database.fetchval(
        "SELECT tags FROM maya_rp.events WHERE session_id=$1 AND event_type='payoff'", sid)
    assert json.loads(tags) == ["narrative", "payoff", 'say "hi"']


async def test_the_title_falls_back_to_the_seed_type(sid):
    seed = await _seed(sid, template="", seed_type="review")
    bare = await _seed(sid, template="", seed_type=None)

    await narrative_seeds.pay_off(seed, sid)
    titles = await Database.fetch(
        "SELECT title FROM maya_rp.events WHERE session_id=$1 AND event_type='payoff'", sid)
    assert [r["title"] for r in titles] == ["PAYOFF: review"]

    await narrative_seeds.pay_off(bare, sid)
    row = await Database.fetchrow(
        "SELECT title, tags FROM maya_rp.events WHERE session_id=$1 AND event_type='payoff' "
        "ORDER BY id DESC LIMIT 1", sid)
    assert row["title"] == "PAYOFF: seed"
    assert json.loads(row["tags"]) == ["narrative", "payoff", "unknown"]


async def test_one_failing_seed_does_not_stop_the_tick(sid, monkeypatch):
    bad = await _seed(sid, day=40)
    good = await _seed(sid, day=41)
    real = narrative_seeds.pay_off

    async def pay_off(seed_id, session_id=None):
        if seed_id == bad:
            raise RuntimeError("boom")
        return await real(seed_id, session_id)

    monkeypatch.setattr(narrative_seeds, "pay_off", pay_off)
    monkeypatch.setattr(narrative_seeds, "error", lambda module, message: None)

    out = await narrative_seeds.run_tick(sid)

    assert out["auto_payoffs"] == 1 and out["failed"] == 1
    assert await _status(good) == "paid_off"
    assert await _status(bad) == "planted"


# ── objectives ──────────────────────────────────────────────────────────

async def test_progress_adds_to_the_stored_value(sid, monkeypatch):
    task = await _task(sid, progress=0, target=10)

    async def write():
        await Database.execute(
            "UPDATE maya_rp.quarterly_tasks SET progress=progress+5, current_progress=current_progress+5 "
            "WHERE session_id=$1", sid)

    _compete_once(monkeypatch, write)

    await objectives.update_quarterly_progress(sid, "kills", 1)

    progress, current, _ = await _counters(task)
    assert progress == 6
    assert current == 6


async def test_a_completion_pays_once(sid, monkeypatch):
    await _task(sid, progress=1, target=2)

    async def write():
        await Database.execute(
            "UPDATE maya_rp.quarterly_tasks SET status='completed', progress=2, current_progress=2 "
            "WHERE session_id=$1", sid)
        await Database.execute(
            "UPDATE maya_rp.resources SET research_points = research_points + 250 WHERE session_id=$1", sid)

    _compete_once(monkeypatch, write)

    out = await objectives.update_quarterly_progress(sid, "kills", 1)

    assert await _points(sid) == 250
    assert out["completed"] == []


async def test_the_event_path_pays_the_reward(sid):
    task = await _task(sid, progress=0, target=10)

    out = await objectives._bump_kind(sid, "kills", 10)

    assert (await _counters(task))[2] == "completed"
    assert await _points(sid) == 250
    assert out["completed"] == [{"title": "Fleet Exercise", "reward": 250000}]


async def test_the_two_counters_stay_equal(sid):
    task = await _task(sid, target=100)

    await objectives._bump_kind(sid, "kills", 5)
    await objectives.update_quarterly_progress(sid, "kills", 1)
    await objectives._bump_kind(sid, "kills", 1)

    progress, current, _ = await _counters(task)
    assert progress == current == 7


async def test_a_finished_quarter_is_not_regenerated(sid):
    for index in range(1, 5):
        await _task(sid, progress=10, target=10, status="completed", index=index)

    out = await objectives.generate_quarterly_tasks(sid)

    count = await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.quarterly_tasks WHERE session_id=$1", sid)
    assert count == 4
    assert out == {"quarter": 1, "already_active": 4}
