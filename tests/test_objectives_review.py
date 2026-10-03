"""Module review tests for modules/objectives.py.

Defects covered:

1. The quarterly auto-tracking listeners were NEVER REGISTERED. `_register_event_listeners`
   had no caller anywhere, so `ship_built`, `duel_resolved` and `battle_completed`
   could fire all day and no task advanced. `run_tick` registers them now.
2. That registration is one-shot: `EventBus.on` APPENDS, so registering per tick
   would stack a duplicate listener every tick and multiply every bump.
3. The kind matcher probed localised BM objective text for English kind names, so
   it could not fire: "kills" matched nothing ("Sweep X hostiles di sempadan") and
   "build" matched nothing ("Development X sistem ke tier 3"). Every live task
   carries `task_type = 'generic'`, so that probe was the only path that could
   ever have matched. The pool's own `kind` field is the mapping now, through the
   task title, and both `update_quarterly_progress` and `_bump_kind` share it.
4. `update_quarterly_progress` accepted `amount < 1`, which walks progress
   backwards or not at all.
5. The expiry write in `run_tick` matched on id alone, and the tick logged its
   crash at info level.

Checked and found correct: every read and write carries session_id; the quarter
is `game_day // 90`; generation refuses to mint a second set of tasks for a
quarter that already has active ones; a task completed by either path is
excluded from the next pass because both filter `status='active'`; the reward is
paid once; and `quarterly_tasks` really does carry task_type, current_progress,
required_amount and reward_blueprint, so the fallback reads are not guessing at
columns.

No database: every test drives a fake Database.
"""
from __future__ import annotations

import pytest

import modules.objectives as objectives


class FakeDB:
    def __init__(self, fetch=None, fetchval=1):
        self.fetch_rows = fetch if fetch is not None else []
        self.fetchval_value = fetchval
        self.calls = []

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", " ".join(sql.split()), args))
        if isinstance(self.fetch_rows, dict):
            for marker, value in self.fetch_rows.items():
                if marker != "*" and marker in sql:
                    return value
            return self.fetch_rows.get("*", [])
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
    for name in ("fetch", "fetchval", "execute"):
        monkeypatch.setattr("modules.objectives.Database." + name, getattr(fake, name))
    return fake


def _task(**over):
    row = {"id": 1, "title": "Fleet Exercise", "objective": "Sweep X hostiles di sempadan",
           "task_type": "generic", "target_value": 10, "progress": 0,
           "current_progress": 0, "required_amount": None, "reward_blueprint": None,
           "reward_value": 250000}
    row.update(over)
    return row


# ── 3. The kind matcher ─────────────────────────────────────────────────

def test_the_pool_maps_every_english_kind_onto_a_task_title():
    assert objectives.task_titles_for("kills") == ["Fleet Exercise"]
    assert objectives.task_titles_for("duels") == ["Duel Champion"]
    assert objectives.task_titles_for("build") == ["Territory Dev"]   # aliased
    assert objectives.task_titles_for("survey") == ["Survey Push"]
    assert objectives.task_titles_for("no such kind") == []


def test_every_pool_kind_is_reachable_by_name():
    kinds = {t["kind"] for t in objectives.QUARTERLY_TASK_POOL}
    for kind in kinds:
        assert objectives.task_titles_for(kind), kind


async def test_progress_matches_the_title_not_only_the_localised_text(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[_task()]))

    out = await objectives.update_quarterly_progress(3, "kills", 1)

    assert out["updated"] == 1, "the Fleet Exercise objective contains no 'kills'"
    sql, args = fake.calls[0][1], fake.calls[0][2]
    assert "title = ANY($3::text[])" in sql
    assert args[1] == "kills" and args[2] == ["Fleet Exercise"]


async def test_progress_still_matches_a_kind_named_in_the_objective(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[_task(title="Something else")]))

    await objectives.update_quarterly_progress(3, "survey", 1)

    assert objectives.task_titles_for("survey") == ["Survey Push"]
    assert "ILIKE '%'||$2||'%'" in fake.calls[0][1]


async def test_the_same_matcher_serves_the_event_listeners(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[_task()]))

    out = await objectives._bump_kind(3, "kills", 1)

    assert out["updated"] == 1
    assert fake.args_for("quarterly_tasks", "fetch")[0][2] == ["Fleet Exercise"]


# ── 4. Progress cannot walk backwards ───────────────────────────────────

@pytest.mark.parametrize("amount", [0, -1, -50])
async def test_a_non_positive_amount_is_refused(monkeypatch, amount):
    fake = _install(monkeypatch, FakeDB())

    with pytest.raises(ValueError, match="amount must be at least 1"):
        await objectives.update_quarterly_progress(3, "kills", amount)

    assert not fake.calls


async def test_a_missing_kind_is_answered_not_crashed(monkeypatch):
    fake = _install(monkeypatch, FakeDB())

    out = await objectives.update_quarterly_progress(3, None, 1)

    assert "kind required" in out["error"]
    assert not fake.sql("fetch")


async def test_a_completed_task_pays_its_reward_once_and_is_flagged(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[_task(target_value=1)]))

    out = await objectives.update_quarterly_progress(3, "kills", 1)

    assert out["completed"] == [{"title": "Fleet Exercise", "reward": 250000}]
    update = fake.args_for("SET progress=$1", "execute")[0]
    assert update[0] == 1 and update[1] == "completed"
    reward = fake.args_for("SET research_points", "execute")[0]
    assert reward == (250, 3)


# ── 1 + 2. The listeners are registered, once ───────────────────────────

async def test_the_tick_registers_the_event_listeners(monkeypatch):
    registered = []

    class Bus:
        @staticmethod
        def on(evt, cb):
            registered.append(evt)

    monkeypatch.setattr("core.events.EventBus", Bus)
    monkeypatch.setattr("modules.objectives._LISTENERS_REGISTERED", False)
    _install(monkeypatch, FakeDB(fetch=[]))

    await objectives.run_tick(5)

    assert registered == ["ship_built", "duel_resolved", "battle_completed"], registered


async def test_a_second_tick_does_not_stack_a_duplicate_listener(monkeypatch):
    registered = []

    class Bus:
        @staticmethod
        def on(evt, cb):
            registered.append(evt)

    monkeypatch.setattr("core.events.EventBus", Bus)
    monkeypatch.setattr("modules.objectives._LISTENERS_REGISTERED", False)
    _install(monkeypatch, FakeDB(fetch=[]))

    await objectives.run_tick(5)
    await objectives.run_tick(5)
    await objectives.run_tick(5)

    assert len(registered) == 3, f"listeners stacked: {registered}"


async def test_the_expiry_write_carries_the_session(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[{"id": 9, "hook_type": "omen"}]))

    out = await objectives.run_tick(5)

    assert out == {"expired": 1}
    assert fake.args_for("SET status='expired'", "execute")[0] == (9, 5)


async def test_run_tick_reports_a_crash_as_an_error(monkeypatch):
    seen = []
    monkeypatch.setattr("modules.objectives.error", lambda mod, msg: seen.append(msg))

    async def boom(*_a, **_k):
        raise RuntimeError("no hooks")

    _install(monkeypatch, FakeDB())
    monkeypatch.setattr("modules.objectives.Database.fetch", boom)

    out = await objectives.run_tick(5)

    assert "no hooks" in out["error"]
    assert any("no hooks" in m for m in seen), seen


# ── Contract: the aggregated view ───────────────────────────────────────

async def test_contract_every_bucket_is_present_and_session_scoped(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch={
        "narrative_hooks": [{"hook_type": "omen", "description": "a sign", "status": "active"}],
        "wars": [{"opponent_faction": "Iron Concord", "phase": "clash", "war_goal": "take the gate"}],
        "quests": [{"title": "The Key", "description": "find it"}],
        "consequence_seeds": [{"trigger_type": "famine", "cause_description": "the blockade"}],
    }))

    out = await objectives.get_active(5)

    assert set(out) == {"critical", "urgent", "active", "background"}
    assert [item["source"] for item in out["active"]] == ["hook", "quest"]
    assert [item["source"] for item in out["urgent"]] == ["war", "consequence"]
    assert out["critical"] == [] and out["background"] == []
    for sql in fake.sql("fetch"):
        assert "session_id=$1" in sql, sql


async def test_contract_the_prompt_says_so_when_nothing_is_active(monkeypatch):
    _install(monkeypatch, FakeDB(fetch=[]))

    prompt = await objectives.objectives_to_prompt(5)

    assert "_No active objectives" in prompt


async def test_contract_generation_refuses_a_quarter_that_already_has_tasks(monkeypatch):
    answers = iter([100, 4])          # game_day, then the active-task count

    async def fetchval(*_a, **_k):
        return next(answers)

    fake = _install(monkeypatch, FakeDB(fetch=None))
    monkeypatch.setattr("modules.objectives.Database.fetchval", fetchval)

    out = await objectives.generate_quarterly_tasks(5)

    assert out == {"quarter": 100 // 90, "already_active": 4}
    assert not fake.sql("execute")


def test_contract_the_pool_is_deep_enough_to_draw_four_distinct_tasks():
    assert len(objectives.QUARTERLY_TASK_POOL) >= 4
    titles = [t["title"] for t in objectives.QUARTERLY_TASK_POOL]
    assert len(set(titles)) == len(titles)
