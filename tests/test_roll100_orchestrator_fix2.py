"""Fix round 2 for scripts/roll100.py and scripts/orchestrator.py.

roll100:
- the session was an import-time constant (`SID = Config.SESSION_ID`, session 3 or 5 by arc state);
  it now resolves per call and takes `--session`.
- a roll ran while GM MAYA maintenance was armed and on a frozen session.
- the docstring promised a checkpoint and none existed.
- the resource override wrote `before + line items` from a snapshot read before the sim, so a write
  made in between was lost. The override is now a relative change under row lock.
- resources, builds, roll_state and Sarang carriers were separate autocommits; they now share one
  transaction.

orchestrator:
- `run_single` took `Config.SESSION_ID` and skipped the maintenance and frozen brakes.
- housekeeping archived and deleted events older than 180 days across ALL sessions.

Isolation: every write lands in a scratch session (900-999). `Config.SESSION_ID`, `RP_SESSION` and the
module-level `roll100.SID` of the old code are all pointed at the scratch id, so the old code cannot
reach session 3 or 5 during a red run. The sim, the module steps and `export_sav` are fakes, except
in the one test that writes a real .sav into `tmp_path`. The orchestrator housekeeping test replaces
`Database` with a recorder.
"""
from __future__ import annotations

import json
import sys
import types
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import pytest_asyncio

from core.config import Config
from core.db import Database
from core.savegame import export_sav as REAL_EXPORT
from scripts import orchestrator as orch
from scripts import roll100

SEED = {"credits": 1_000_000, "alloys": 10_000, "fuel": 20_000}
#: Per-day line items. Ten days give 1000 credits, 100 alloys, 10 fuel.
RATES = ("--rates", "100,10,1")
DAYS = "10"
#: What the fake sim adds to credits, alloys, fuel.
SIM_MOVE = (1000, 50, 5)
CREDITS_LINE, ALLOYS_LINE, FUEL_LINE = 1000, 100, 10


# ── roll100 rig ──────────────────────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def rig(scratch_campaign, monkeypatch):
    """A scratch campaign with a resources row, a fake sim, fake module steps and a fake checkpoint."""
    sid = scratch_campaign
    await Database.init()
    await Database.execute("UPDATE maya_rp.sessions SET game_day=100 WHERE id=$1", sid)
    await Database.execute(
        "INSERT INTO maya_rp.resources (session_id, credits, alloys, fuel) VALUES ($1, $2, $3, $4) "
        "ON CONFLICT (session_id) DO UPDATE SET credits=$2, alloys=$3, fuel=$4",
        sid, SEED["credits"], SEED["alloys"], SEED["fuel"])

    state = types.SimpleNamespace(
        sid=sid, order=[], sim_calls=[], module_calls=[], checkpoint_calls=[], checkpoint_credits=[],
        during_sim=None, clamp_fuel=False, export_error=None)

    # No path of the old or the new code may resolve to the live arc.
    monkeypatch.setattr(Config, "SESSION_ID", sid)
    monkeypatch.setattr(roll100, "SID", sid, raising=False)
    monkeypatch.setenv("RP_SESSION", str(sid))
    monkeypatch.setattr("core.maintenance.active", lambda: False)
    monkeypatch.setattr("core.session.is_frozen", lambda session: False)

    async def fake_sim(days, focus="balanced", session_id=None):
        state.order.append("sim")
        state.sim_calls.append((days, focus, session_id))
        credits_before = await Database.fetchval(
            "SELECT credits FROM maya_rp.resources WHERE session_id=$1", session_id)
        fuel_sql = "LEAST(5000000::bigint, fuel + $3)" if state.clamp_fuel else "fuel + $3"
        await Database.execute(
            f"UPDATE maya_rp.resources SET credits = credits + $1, alloys = alloys + $2, fuel = {fuel_sql} "
            "WHERE session_id=$4", *SIM_MOVE, session_id)
        await Database.execute(
            "UPDATE maya_rp.sessions SET game_day = game_day + $1 WHERE id=$2", days, session_id)
        if state.during_sim:
            await state.during_sim(session_id)
        return {"days_skipped": days, "events": [], "economy": "fake",
                "credits_before": credits_before, "credits_after": credits_before + SIM_MOVE[0]}

    async def fake_export(session_id, out_dir=None):
        state.order.append("checkpoint")
        state.checkpoint_calls.append(session_id)
        state.checkpoint_credits.append(await Database.fetchval(
            "SELECT credits FROM maya_rp.resources WHERE session_id=$1", session_id))
        if state.export_error:
            raise state.export_error
        return "/tmp/fake-roll100.sav"

    def module_step(name, result):
        async def step(session_id, *_a, **_k):
            state.module_calls.append((name, session_id))
            return result
        return step

    monkeypatch.setattr(roll100, "execute_time_skip", fake_sim)
    monkeypatch.setattr("core.savegame.export_sav", fake_export)
    monkeypatch.setattr("modules.pregnancy.advance", module_step("pregnancy", {"births": []}))
    monkeypatch.setattr("modules.voyage.advance", module_step("voyage", {"arrivals": 0}))
    monkeypatch.setattr("modules.population_sentiment.run_tick", module_step("sentiment", {"updated": 0}))
    monkeypatch.setattr("modules.ministry_ai.run_tick", module_step("ministry", {}))
    monkeypatch.setattr("modules.collapse.check_for_collapse", module_step("collapse", None))

    async def run(*args):
        monkeypatch.setattr(sys, "argv", ["roll100.py", *args])
        return await roll100.main()

    async def resources():
        await Database.init()
        return await Database.fetchrow(
            "SELECT credits, alloys, fuel FROM maya_rp.resources WHERE session_id=$1", sid)

    async def query(sql, *args):
        await Database.init()
        return await Database.fetch(sql, *args)

    state.run, state.resources, state.query = run, resources, query
    return state


async def seed_builds(sid, *builds):
    """Insert in_build rows: (name, build_time_days). Returns their ids in order."""
    ids = []
    for name, build_days in builds:
        ids.append(await Database.fetchval(
            "INSERT INTO maya_rp.build_queue (session_id, project_name, project_type, status, build_time_days) "
            "VALUES ($1, $2, 'ship', 'in_build', $3) RETURNING id", sid, name, build_days))
    return ids


def fail_on_ship_insert(monkeypatch):
    """Make the Sarang ship INSERT raise on both paths: `Database.execute` and a transaction's conn."""
    real_execute, real_tx = Database.execute, Database.transaction

    def boom(sql):
        if "INSERT INTO maya_rp.ships" in sql:
            raise RuntimeError("injected: ships insert refused")

    async def execute(sql, *args, **kw):
        boom(sql)
        return await real_execute(sql, *args, **kw)

    class Conn:
        def __init__(self, conn):
            self._conn = conn

        def __getattr__(self, name):
            return getattr(self._conn, name)

        async def execute(self, sql, *args, **kw):
            boom(sql)
            return await self._conn.execute(sql, *args, **kw)

    @asynccontextmanager
    async def transaction():
        async with real_tx() as conn:
            yield Conn(conn)

    monkeypatch.setattr(Database, "execute", execute)
    monkeypatch.setattr(Database, "transaction", transaction)


# ── roll100: session ─────────────────────────────────────────────────────────────────────────────────

def test_roll100_holds_no_import_time_session():
    assert not hasattr(roll100, "SID"), "roll100.SID is resolved once, at import"
    source = Path(roll100.__file__).read_text(encoding="utf-8")
    assert "Config.SESSION_ID" not in source, "roll100 reads the process default session"


def test_the_session_value_is_not_the_day_count():
    assert roll100.parse_flags(["--session", "907"])["days"] == 100
    assert roll100.parse_flags(["--session", "907"])["session"] == "907"
    assert roll100.parse_flags(["--session=907", "12"])["days"] == 12
    assert roll100.parse_flags(["--session=907", "12"])["session"] == "907"


async def test_the_session_option_wins_over_the_environment(rig, monkeypatch):
    monkeypatch.setenv("RP_SESSION", str(rig.sid + 1 if rig.sid < 999 else 900))

    rc = await rig.run("--session", str(rig.sid), *RATES)

    assert [call[2] for call in rig.sim_calls] == [rig.sid], "the sim ran on another session"
    assert rig.sim_calls[0][0] == 100, "the session id was read as the day count"
    assert rc == 0


async def test_the_session_follows_the_environment_when_no_option_is_given(rig):
    rc = await rig.run(DAYS, *RATES)

    assert [call[2] for call in rig.sim_calls] == [rig.sid]
    assert {sid for _name, sid in rig.module_calls} == {rig.sid}, "a module step ran on another session"
    assert rc == 0


async def test_an_unresolved_session_is_refused_not_guessed(rig, monkeypatch):
    monkeypatch.delenv("RP_SESSION")
    monkeypatch.setattr("core.session.active_arc", lambda: None)

    rc = await rig.run(DAYS, *RATES)

    assert rig.sim_calls == [] and rig.checkpoint_calls == [], "the roll started without a session"
    assert dict(await rig.resources()) == SEED
    assert rc == 1


# ── roll100: brakes ──────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("extra", [(), ("--dry-run",)])
async def test_a_roll_is_refused_while_maintenance_is_armed(rig, monkeypatch, capsys, extra):
    monkeypatch.setattr("core.maintenance.active", lambda: True)

    rc = await rig.run("--session", str(rig.sid), DAYS, *RATES, *extra)

    assert rig.sim_calls == [] and rig.checkpoint_calls == [], "the roll ran under maintenance"
    assert dict(await rig.resources()) == SEED
    assert "maintenance" in capsys.readouterr().err
    assert rc == 1


async def test_a_frozen_session_is_refused(rig, monkeypatch, capsys):
    monkeypatch.setattr("core.session.is_frozen", lambda session: True)

    rc = await rig.run("--session", str(rig.sid), DAYS, *RATES)

    assert rig.sim_calls == [] and rig.checkpoint_calls == [], "the roll ran on a frozen session"
    assert dict(await rig.resources()) == SEED
    assert "frozen" in capsys.readouterr().err
    assert rc == 1


async def test_an_unreadable_frozen_list_refuses_the_roll(rig, monkeypatch):
    from core.session import FrozenListUnreadable

    def unreadable(session):
        raise FrozenListUnreadable("frozen list is unreadable")

    monkeypatch.setattr("core.session.is_frozen", unreadable)

    rc = await rig.run("--session", str(rig.sid), DAYS, *RATES)

    assert rig.sim_calls == [], "a list that cannot be read counted as not frozen"
    assert rc == 1


# ── roll100: checkpoint ──────────────────────────────────────────────────────────────────────────────

async def test_the_checkpoint_is_taken_before_the_first_write(rig):
    rc = await rig.run(DAYS, *RATES)

    assert rig.order == ["checkpoint", "sim"], f"no checkpoint ahead of the sim: {rig.order}"
    assert rig.checkpoint_calls == [rig.sid]
    assert rig.checkpoint_credits == [SEED["credits"]], "the checkpoint saw a row the roll had already written"
    assert rc == 0


async def test_a_failed_checkpoint_stops_the_roll_before_any_write(rig):
    rig.export_error = RuntimeError("2 table(s) could not be read")

    rc = await rig.run(DAYS, *RATES)

    assert rig.sim_calls == [], "the sim ran without a checkpoint"
    assert dict(await rig.resources()) == SEED
    assert rc == 1


async def test_a_dry_run_takes_no_checkpoint_and_writes_nothing(rig):
    await rig.run("--dry-run", DAYS, *RATES)

    assert rig.order == []
    assert dict(await rig.resources()) == SEED


async def test_the_real_checkpoint_is_a_sav_of_the_session(rig, monkeypatch, tmp_path):
    async def into_tmp(session_id, out_dir=None):
        return await REAL_EXPORT(session_id, out_dir=str(tmp_path))

    monkeypatch.setattr("core.savegame.export_sav", into_tmp)

    rc = await rig.run(DAYS, *RATES)

    saves = list(tmp_path.glob("*.sav"))
    assert len(saves) == 1, f"expected one .sav, found {saves}"
    assert json.loads(saves[0].read_text(encoding="utf-8")), "the .sav is empty"
    assert rc == 0


# ── roll100: resources ───────────────────────────────────────────────────────────────────────────────

async def test_the_override_replaces_the_sim_economy_with_the_line_items(rig):
    await rig.run(DAYS, *RATES)

    row = await rig.resources()
    assert row["credits"] == SEED["credits"] + CREDITS_LINE
    assert row["alloys"] == SEED["alloys"] + ALLOYS_LINE
    assert row["fuel"] == SEED["fuel"] + FUEL_LINE


async def test_a_cap_clamp_by_the_sim_does_not_survive_the_override(rig):
    """The sim clamps fuel to 5M. The override restores `stock + line items`, as the absolute write did."""
    await Database.execute("UPDATE maya_rp.resources SET fuel=$1 WHERE session_id=$2", 9_000_000, rig.sid)
    rig.clamp_fuel = True

    await rig.run(DAYS, *RATES)

    assert (await rig.resources())["fuel"] == 9_000_000 + FUEL_LINE


async def test_a_write_made_during_the_sim_survives_the_override(rig):
    async def concurrent_spend(session_id):
        await Database.execute(
            "UPDATE maya_rp.resources SET credits = credits + $1 WHERE session_id=$2", 777, session_id)

    rig.during_sim = concurrent_spend

    await rig.run(DAYS, *RATES)

    assert (await rig.resources())["credits"] == SEED["credits"] + 777 + CREDITS_LINE, \
        "the override wrote the stale snapshot back over a concurrent write"


# ── roll100: one transaction ─────────────────────────────────────────────────────────────────────────

async def test_builds_roll_state_and_sarang_commit_with_the_resources(rig):
    done, slow = await seed_builds(rig.sid, ("Sarang Alpha", 5), ("Slow Dock", 50))

    await rig.run(DAYS, *RATES)

    status = {r["id"]: r["status"] for r in await rig.query(
        "SELECT id, status FROM maya_rp.build_queue WHERE session_id=$1", rig.sid)}
    assert status[done] == "completed" and status[slow] == "in_build"
    progress = await Database.fetchval(
        "SELECT build_progress FROM maya_rp.roll_state WHERE session_id=$1", rig.sid)
    assert json.loads(progress) == {str(slow): 10}
    ships = await rig.query(
        "SELECT name FROM maya_rp.ships WHERE session_id=$1 AND name LIKE 'Sarang-%'", rig.sid)
    assert [r["name"] for r in ships] == ["Sarang-1"]
    assert (await rig.resources())["credits"] == SEED["credits"] + CREDITS_LINE


async def test_a_failure_in_the_roll_rolls_back_every_roll_write(rig, monkeypatch):
    done, slow = await seed_builds(rig.sid, ("Sarang Alpha", 5), ("Slow Dock", 50))
    after_sim = (SEED["credits"] + SIM_MOVE[0], SEED["alloys"] + SIM_MOVE[1], SEED["fuel"] + SIM_MOVE[2])
    fail_on_ship_insert(monkeypatch)

    try:
        rc = await rig.run(DAYS, *RATES)
    except RuntimeError:
        rc = "raised"

    row = await rig.resources()
    assert (row["credits"], row["alloys"], row["fuel"]) == after_sim, \
        "the resource override committed although the roll failed"
    status = {r["id"]: r["status"] for r in await rig.query(
        "SELECT id, status FROM maya_rp.build_queue WHERE session_id=$1", rig.sid)}
    assert status == {done: "in_build", slow: "in_build"}, "a build completed although the roll failed"
    assert await rig.query("SELECT 1 FROM maya_rp.roll_state WHERE session_id=$1", rig.sid) == []
    assert [c[0] for c in rig.module_calls] == [], "module steps ran after a failed roll"
    assert rc == 1, "the failure did not end the roll with a non-zero code"


# ── orchestrator: run_single ─────────────────────────────────────────────────────────────────────────

@pytest.fixture
def single(scratch_session, monkeypatch):
    """A fake module in MODULE_MAP that records the session it ran on. No database is touched."""
    ran: list = []

    async def run_tick(session_id):
        ran.append(session_id)
        return {}

    async def noop(*_a, **_k):
        return None

    monkeypatch.setitem(orch.MODULE_MAP, "fake_mod", types.SimpleNamespace(run_tick=run_tick))
    monkeypatch.setitem(Config.MODULES, "fake_mod", True)
    monkeypatch.setattr(orch.Database, "init", noop)
    monkeypatch.setattr(orch.Database, "close", noop)
    monkeypatch.setattr("core.maintenance.active", lambda: False)
    monkeypatch.setattr("core.session.is_frozen", lambda session: False)
    monkeypatch.setenv("RP_SESSION", str(scratch_session))
    monkeypatch.setattr(Config, "SESSION_ID", scratch_session)
    return types.SimpleNamespace(ran=ran, sid=scratch_session)


async def test_run_single_is_refused_while_maintenance_is_armed(single, monkeypatch, capsys):
    monkeypatch.setattr("core.maintenance.active", lambda: True)

    await orch.run_single(single.sid, "fake_mod")

    assert single.ran == [], "a single module ran under maintenance"
    assert "SKIPPED" in capsys.readouterr().out, "the refusal was silent"


async def test_run_single_is_refused_on_a_frozen_session(single, monkeypatch, capsys):
    monkeypatch.setattr("core.session.is_frozen", lambda session: True)

    await orch.run_single(single.sid, "fake_mod")

    assert single.ran == [], "a single module ran on a frozen session"
    assert "frozen" in capsys.readouterr().out


async def test_run_single_resolves_its_session_per_call(single, monkeypatch):
    monkeypatch.setattr(Config, "SESSION_ID", single.sid + 50)

    await orch.run_single(None, "fake_mod")

    assert single.ran == [single.sid], f"run_single used {single.ran}, not the resolved session"


async def test_run_single_honours_an_explicit_session(single):
    await orch.run_single(single.sid, "fake_mod")

    assert single.ran == [single.sid]


def test_the_entry_point_does_not_pass_the_process_default():
    source = Path(orch.__file__).read_text(encoding="utf-8")
    entry = source.split('if __name__ == "__main__":', 1)[1]

    assert "Config.SESSION_ID" not in entry, "the entry point hands run_single the import-time session"


# ── orchestrator: housekeeping ───────────────────────────────────────────────────────────────────────

async def test_housekeeping_statements_are_scoped_to_the_tick_session(scratch_session, monkeypatch, tmp_path):
    """`Database` is a recorder: no statement reaches the database, old code included."""
    log: list = []

    class RecordingDatabase:
        @staticmethod
        async def init(*_a, **_k):
            return None

        @staticmethod
        async def close(*_a, **_k):
            return None

        @staticmethod
        async def execute(sql, *args, **_k):
            log.append((sql, args))
            return "OK"

        @staticmethod
        async def fetch(sql, *args, **_k):
            log.append((sql, args))
            return []

        @staticmethod
        async def fetchrow(sql, *args, **_k):
            log.append((sql, args))

        @staticmethod
        async def fetchval(sql, *args, **_k):
            log.append((sql, args))
            if "COUNT(*)" in sql:
                return 7 if "180 days" in sql else 6000
            return 1

    async def no_snapshot():
        return {}

    async def no_report(_before, _after):
        return {"readable": False, "note": "stub"}

    async def fake_tick(name, mod, session_id):
        return True

    async def fake_export(session_id, out_dir=None):
        return str(tmp_path / f"save_{session_id}_day1_x.sav")

    monkeypatch.setattr(orch, "Database", RecordingDatabase)
    monkeypatch.setattr(orch, "tick", fake_tick)
    monkeypatch.setattr("core.tick_writes.snapshot", no_snapshot)
    monkeypatch.setattr("core.tick_writes.report", no_report)
    monkeypatch.setattr("core.savegame.export_sav", fake_export)
    monkeypatch.setattr("core.maintenance.active", lambda: False)
    monkeypatch.setattr("core.session.is_frozen", lambda session: False)

    await orch.run_full_tick(session_id=scratch_session, verbose=False)

    moves = [(sql, args) for sql, args in log
             if "maya_rp.events" in sql and ("DELETE" in sql or "INSERT" in sql)]
    assert moves, "housekeeping moved no events; the fake counts did not reach it"
    for sql, args in moves:
        assert "session_id" in sql, f"unscoped events statement: {' '.join(sql.split())}"
        assert scratch_session in args, f"statement is not bound to the tick session: {args}"


@pytest.fixture
async def two_campaigns(scratch_campaign, monkeypatch):
    """The fixture's scratch campaign plus a second one, both with old events. Cleans the second."""
    other = 900 + (scratch_campaign - 900 + 1) % 100
    await Database.init()
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1, 'rp-engine test scratch 2', 'active') "
        "ON CONFLICT (id) DO NOTHING", other)
    for sid in (scratch_campaign, other):
        for _ in range(3):
            await Database.execute(
                "INSERT INTO maya_rp.events (session_id, event_type, title, happened_at) "
                "VALUES ($1, 'fix2', 'old', NOW() - INTERVAL '200 days')", sid)
    await Database.execute(
        "INSERT INTO maya_rp.events (session_id, event_type, title, happened_at) "
        "VALUES ($1, 'fix2', 'recent', NOW())", scratch_campaign)
    yield types.SimpleNamespace(mine=scratch_campaign, other=other)
    await Database.init()
    for table in ("events", "events_archive"):
        await Database.execute(f"DELETE FROM maya_rp.{table} WHERE session_id=$1", other)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", other)


async def count(table, sid, *, old=False):
    where = " AND happened_at < NOW() - INTERVAL '180 days'" if old else ""
    return await Database.fetchval(f"SELECT COUNT(*) FROM maya_rp.{table} WHERE session_id=$1{where}", sid)


async def test_archiving_moves_only_the_tick_sessions_old_events(two_campaigns, monkeypatch):
    monkeypatch.setattr(orch, "EVENTS_ARCHIVE_MIN_ROWS", 2)

    archived = await orch.archive_old_events(two_campaigns.mine)

    assert archived == 3
    assert await count("events", two_campaigns.mine, old=True) == 0
    assert await count("events", two_campaigns.mine) == 1, "the recent event left the table"
    assert await count("events_archive", two_campaigns.mine) == 3
    assert await count("events", two_campaigns.other, old=True) == 3, "another session's events were deleted"
    assert await count("events_archive", two_campaigns.other) == 0, "another session's events were archived"


async def test_a_session_under_the_row_threshold_keeps_its_old_events(two_campaigns):
    archived = await orch.archive_old_events(two_campaigns.mine)

    assert archived == 0
    assert await count("events", two_campaigns.mine, old=True) == 3
    assert await count("events_archive", two_campaigns.mine) == 0
