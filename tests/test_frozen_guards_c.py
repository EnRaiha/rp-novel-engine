"""T4 frozen guards, batch C: news, npc_autonomy, objectives, physical_state, population_sentiment,
pregnancy, battle, celestial, pirates, roll_theater, space_wonders.

Contract (core/session.py): a frozen campaign stays readable, and a write is refused unless GM MAYA
maintenance is armed. A writer calls `_refuse_frozen` before anything else. A reader resolves its session
with `require_session` and never refuses. A reader that writes skips the write on a frozen campaign.

No test here touches the database. Every module gets a `Database` stand-in. The session is the scratch
session, and `RP_SESSION` and `Config.SESSION_ID` name it, so a default cannot reach session 3 or 5.
"""
from __future__ import annotations

import ast
import contextlib
import importlib
import pathlib
import random
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import ooc  # noqa: E402
from tests.conftest import scratch_id  # noqa: E402

S = object()      # placeholder for the session argument
STATE = object()  # placeholder for a BattleState that names the session

#: module -> [(function, args, kwargs)]. `S` marks the session argument. A dotted name is Class.method.
WRITERS = {
    "news": [
        ("generate", (S,), {}),
        ("roll_news", (S,), {}),
        ("mark_read", (S, 1), {}),
        ("run_tick", (S,), {}),
    ],
    "npc_autonomy": [
        ("react_to_event", ("combat_victory", S), {}),
        ("discover_off_screen", (S,), {}),
        ("run_tick", (S,), {}),
    ],
    "objectives": [
        ("generate_quarterly_tasks", (S,), {}),
        ("update_quarterly_progress", (S, "kills"), {}),
        ("_bump_kind", (S, "kills"), {}),
        ("run_tick", (S,), {}),
    ],
    "physical_state": [
        ("apply", (1, "a cut", "minor", "arm", "combat", S), {}),
        ("run_tick", (S,), {}),
    ],
    "population_sentiment": [
        ("init_for_territory", (S,), {}),
        ("refresh", (S,), {}),
        ("shift", (S, 1, "F", 3, "r"), {}),
        ("apply_news_bias", (S,), {}),
        ("run_tick", (S,), {}),
    ],
    "pregnancy": [
        ("register", (S, "Mother"), {}),
        ("advance", (S,), {}),
        ("run_tick", (S,), {}),
    ],
    "battle": [
        ("BattleEngine.init", (S, [1], "F"), {}),
        ("BattleEngine.resolve_turn", (STATE, "Direct Assault"), {}),
        ("BattleEngine.set_formation", (7, "Wedge"), {}),
        ("BattleEngine.attempt_retreat", (7,), {}),
        ("run_tick", (S,), {}),
        ("resolve_intent", (S, "attack", "t"), {}),
    ],
    "celestial": [
        ("reveal_system", (S, "Sol"), {}),
    ],
    "pirates": [
        ("run_tick", (S,), {}),
        ("claim_bounty", (S, 1), {}),
        ("raid_pirate_base", (S, 1), {}),
    ],
    "roll_theater": [
        ("memorialize", (S, "combat", 100, 100, 50), {}),
        ("consume_blessing", (S, "Callista"), {}),
        ("open_pool", (S, "p", 50), {}),
        ("resolve_pool", (S, True), {}),
        ("plant_ripple", (S, "combat", "success", 50), {}),
    ],
    "space_wonders": [
        ("survey_planet", (1, S), {}),
        ("encounter_animal", (1,), {"session_id": S}),
        ("hunt_animal", (1,), {"session_id": S}),
        ("tame_animal", (1,), {"session_id": S}),
        ("discover_anomaly", (1,), {"session_id": S}),
        ("explore_anomaly", (1,), {"session_id": S}),
        ("run_tick", (S,), {}),
    ],
}

#: module -> [(function, args, kwargs, value the frozen call returns on the empty stand-in)]
READERS = {
    "objectives": [
        ("get_active", (S,), {}, {"critical": [], "urgent": [], "active": [], "background": []}),
        ("quarterly_tasks_view", (S,), {}, {"quarter": 0, "tasks": []}),
    ],
    "pregnancy": [("status", (S,), {}, [])],
    "population_sentiment": [("status", (S,), {}, [])],
    "battle": [("BattleEngine._make_enemy_fleet", ("F",), {"session_id": S}, "F")],
    "celestial": [
        ("run_tick", (S,), {}, {"systems": 0, "planets": 0, "colonies": 0}),
        ("get_system_detail", (S, "Sol"), {}, None),
    ],
    "roll_theater": [("list_blessings", (S,), {}, [])],
    "space_wonders": [("get_wonders_overview", (S,), {}, {"planets": [], "animals": [], "anomalies": []})],
}

#: Functions that read and also write. Each asks `_writes_allowed` and skips the write on a frozen campaign.
READER_WRITERS = [("physical_state", "get_state")]

#: Readers whose session argument has no default, so a missing session cannot occur.
NO_DEFAULT_READERS = {("celestial", "get_system_detail"), ("roll_theater", "list_blessings")}

#: Writers that do not take the session as an argument. `resolve_turn` reads it from the state, the two
#: battle functions that take only a battle id read it from the battle row, and the two sector functions
#: read it from the sector row when none is named.
DERIVED = {
    "BattleEngine.resolve_turn", "BattleEngine.set_formation", "BattleEngine.attempt_retreat",
    "encounter_animal", "discover_anomaly",
}
#: These read the battle row before they guard, so a stand-in that raises on every call cannot show the
#: guard. They have their own tests below.
READS_FIRST = {"BattleEngine.set_formation", "BattleEngine.attempt_retreat"}
#: `plant_ripple` reaches the database through `core.consequences`, which has its own tests below.
PLANTS = {"plant_ripple"}

ALL_MODULES = sorted(set(WRITERS) | set(READERS) | {m for m, _ in READER_WRITERS})

WRITER_CASES = [(m, f, a, k) for m, rows in WRITERS.items() for f, a, k in rows]
#: Every tick, and `plant_ripple`, whose body sits in `try ... except Exception`.
SWALLOW_CASES = [c for c in WRITER_CASES if c[1] in ("run_tick", "plant_ripple")]
REFUSAL_CASES = [c for c in WRITER_CASES if c[1] not in READS_FIRST]
DEFAULTING_CASES = [c for c in WRITER_CASES if c[1] not in DERIVED]
RUNNING_CASES = [c for c in WRITER_CASES if c[1] not in PLANTS]
READER_CASES = [(m, f, a, k, want) for m, rows in READERS.items() for f, a, k, want in rows]
DEFAULTING_READERS = [(m, f, a, k) for m, f, a, k, _ in READER_CASES if (m, f) not in NO_DEFAULT_READERS]
AST_READERS = [(m, f) for m, f, *_ in READER_CASES] + READER_WRITERS + [("space_wonders", "_log")]


def _id(case):
    return f"{case[0]}.{case[1]}"


def _state(sid):
    from modules.battle import BattleFleet, BattleState
    return BattleState(battle_id=7, player=BattleFleet("p"), enemy=BattleFleet("e"), terrain={}, session_id=sid)


def _bind(args, kwargs, sid):
    def one(value):
        if value is S:
            return sid
        return _state(sid) if value is STATE else value
    return tuple(one(a) for a in args), {k: one(v) for k, v in kwargs.items()}


def _module(name):
    return importlib.import_module(f"modules.{name}")


def _target(module, func):
    """The function `Class.method` or `function` of `modules.<module>`."""
    obj = _module(module)
    for part in func.split("."):
        obj = getattr(obj, part)
    return obj


# ── stand-ins ────────────────────────────────────────────────────────────


class _Tripwire:
    """A `Database` stand-in that records every call and raises on it."""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        async def call(*args, **kwargs):
            self.calls.append((name, args))
            raise AssertionError(f"Database.{name} was reached")
        return call

    @contextlib.asynccontextmanager
    async def transaction(self):
        self.calls.append(("transaction", ()))
        raise AssertionError("Database.transaction was reached")
        yield


class _ReadDB:
    """Answers reads from `returns`, records every argument list, and fails on any write."""

    def __init__(self, **returns):
        self.returns = returns
        self.args = []

    async def _read(self, kind, sql, *args):
        self.args.append(args)
        value = self.returns.get(kind)
        return value() if callable(value) else value

    async def fetch(self, sql, *args):
        return await self._read("fetch", sql, *args) or []

    async def fetchrow(self, sql, *args):
        return await self._read("fetchrow", sql, *args)

    async def fetchval(self, sql, *args):
        return await self._read("fetchval", sql, *args)

    async def execute(self, sql, *args):
        raise AssertionError("wrote a frozen session")


class _RecordingDB(_ReadDB):
    """Like `_ReadDB`, but a write is recorded and succeeds."""

    def __init__(self, **returns):
        super().__init__(**returns)
        self.writes = []

    async def execute(self, sql, *args):
        self.writes.append((sql, args))
        return "UPDATE 1"


class _InjuryDB:
    """Answers `physical_state.get_state` and records the SQL of every `fetch`.

    A `fetch` whose SQL starts with UPDATE is a write: it raises when `writable` is false.
    """

    def __init__(self, writable):
        self.writable = writable
        self.sql = []

    async def fetchval(self, sql, *args):
        return 10

    async def fetch(self, sql, *args):
        self.sql.append(sql)
        if sql.lstrip().startswith("UPDATE"):
            if not self.writable:
                raise AssertionError("wrote a frozen session")
            return [{"id": 1}]
        if sql.lstrip().startswith("SELECT id FROM"):
            return [{"id": 1}]
        return []


class _Bus:
    """An `EventBus` stand-in: `emit` records the event and writes nothing."""

    def __init__(self):
        self.events = []

    async def emit(self, name, data):
        self.events.append((name, data))


def _flat(arg_lists):
    return [x for args in arg_lists for x in args]


# ── fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def sid(request, monkeypatch):
    """The file's scratch session id (900-999), also the process default and `RP_SESSION`, so nothing can
    fall back to a live arc. The id is the one `scratch_session` hands out. The fixture itself is not
    used: it clears every table on teardown, and these tests write nothing."""
    session = scratch_id(request.module.__name__)
    monkeypatch.setattr("core.config.Config.SESSION_ID", session)
    monkeypatch.setenv("RP_SESSION", str(session))
    return session


@pytest.fixture
def other(sid):
    """A second scratch id, unlike the process default."""
    return sid + 1 if sid < 999 else sid - 1


def _freeze(monkeypatch, *ids):
    """Freeze `ids` for `core.session.is_frozen` and leave maintenance off."""
    frozen = set(ids)
    monkeypatch.setattr("core.session.is_frozen", lambda s: s in frozen)
    monkeypatch.setattr("core.ooc._maintenance_active", lambda: False)


def _isolate(monkeypatch):
    """Tripwire for every module batch C reaches a database through, plus the campaign read that
    `resolve_intent` makes. The event listeners and the dice are fixed so each writer reaches its first
    database call."""
    wire = _Tripwire()
    for name in ALL_MODULES:
        monkeypatch.setattr(_module(name), "Database", wire)
    monkeypatch.setattr("core.campaign.Database", wire)

    async def no_listeners():
        return None

    monkeypatch.setattr("modules.objectives._register_event_listeners", no_listeners)
    monkeypatch.setattr(random, "random", lambda: 0.0)
    return wire


# ── structure: the guard is first, readers stay open, no process default ──


def _function(tree, name):
    scope, *rest = name.split(".")
    for node in tree.body:
        if rest and isinstance(node, ast.ClassDef) and node.name == scope:
            return _function(node, ".".join(rest))
        if not rest and isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == scope:
            return node
    raise AssertionError(f"no function {name}")


def _calls(node, *names):
    return [n for n in ast.walk(node)
            if isinstance(n, ast.Call)
            and getattr(n.func, "id", getattr(n.func, "attr", None)) in names]


@pytest.mark.parametrize("module,func,args,kwargs", WRITER_CASES, ids=[_id(c) for c in WRITER_CASES])
def test_a_writer_guards_before_it_does_anything(module, func, args, kwargs):
    tree = ast.parse((ROOT / "modules" / f"{module}.py").read_text())
    node = _function(tree, func)
    for index, stmt in enumerate(node.body):
        if isinstance(stmt, ast.Expr) and _calls(stmt, "_refuse_frozen"):
            break
    else:
        raise AssertionError(f"no top-level _refuse_frozen call in modules/{module}.py {func}")
    for stmt in node.body[:index]:
        is_doc = (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)
                  and isinstance(stmt.value.value, str))
        assert is_doc or isinstance(stmt, (ast.ImportFrom, ast.Assign, ast.AnnAssign)), (
            f"modules/{module}.py {func} runs {type(stmt).__name__} before the guard")
        assert not _calls(stmt, "execute", "executemany", "transaction", "emit"), (
            f"modules/{module}.py {func} touches the database before the guard")


@pytest.mark.parametrize("module", ALL_MODULES)
def test_no_config_session_fallback(module):
    tree = ast.parse((ROOT / "modules" / f"{module}.py").read_text())
    uses = [n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Attribute) and n.attr == "SESSION_ID"
            and isinstance(n.value, ast.Name) and n.value.id == "Config"]
    assert uses == [], f"modules/{module}.py still reads Config.SESSION_ID at lines {uses}"


@pytest.mark.parametrize("module,func", AST_READERS, ids=[f"{m}.{f}" for m, f in AST_READERS])
def test_a_reader_never_refuses(module, func):
    tree = ast.parse((ROOT / "modules" / f"{module}.py").read_text())
    assert not _calls(_function(tree, func), "_refuse_frozen"), f"{module}.{func} guards a reader"


@pytest.mark.parametrize("module,func", READER_WRITERS, ids=[f"{m}.{f}" for m, f in READER_WRITERS])
def test_a_reader_that_writes_asks_before_it_writes(module, func):
    tree = ast.parse((ROOT / "modules" / f"{module}.py").read_text())
    assert _calls(_function(tree, func), "_writes_allowed"), f"{module}.{func} writes without asking"


# ── a writer refuses a frozen campaign and writes nothing ─────────────────


@pytest.mark.parametrize("module,func,args,kwargs", REFUSAL_CASES, ids=[_id(c) for c in REFUSAL_CASES])
async def test_a_writer_refuses_a_frozen_session_before_any_database_call(
        monkeypatch, sid, module, func, args, kwargs):
    _freeze(monkeypatch, sid)
    wire = _isolate(monkeypatch)
    a, k = _bind(args, kwargs, sid)

    with pytest.raises(ooc.FrozenSession):
        await _target(module, func)(*a, **k)

    assert wire.calls == [], f"{module}.{func} reached the database for a frozen session: {wire.calls}"


@pytest.mark.parametrize("module,func,args,kwargs", DEFAULTING_CASES, ids=[_id(c) for c in DEFAULTING_CASES])
async def test_a_writer_resolves_its_session_per_call_and_guards_that_one(
        monkeypatch, sid, other, module, func, args, kwargs):
    """No session argument: RP_SESSION names the campaign. Only that one is frozen, so a process default
    that is not frozen cannot let the write through."""
    _freeze(monkeypatch, other)
    monkeypatch.setenv("RP_SESSION", str(other))
    wire = _isolate(monkeypatch)
    a, k = _bind(args, kwargs, None)

    with pytest.raises(ooc.FrozenSession):
        await _target(module, func)(*a, **k)

    assert wire.calls == []


@pytest.mark.parametrize("module,func,args,kwargs", RUNNING_CASES, ids=[_id(c) for c in RUNNING_CASES])
async def test_a_writer_runs_when_the_session_is_not_frozen(monkeypatch, sid, module, func, args, kwargs):
    """The guard passes and the function proceeds to its first database call."""
    _freeze(monkeypatch)
    wire = _isolate(monkeypatch)
    a, k = _bind(args, kwargs, sid)

    try:
        await _target(module, func)(*a, **k)
    except ooc.FrozenSession:
        pytest.fail(f"{module}.{func} refused a session that is not frozen")
    except Exception:  # noqa: BLE001 - the stand-in raises on the first call, or the tick reports it
        pass

    assert wire.calls, f"{module}.{func} never reached the database"


@pytest.mark.parametrize("module,func,args,kwargs", RUNNING_CASES, ids=[_id(c) for c in RUNNING_CASES])
async def test_maintenance_lets_a_writer_into_a_frozen_session(monkeypatch, sid, module, func, args, kwargs):
    _freeze(monkeypatch, sid)
    monkeypatch.setattr("core.ooc._maintenance_active", lambda: True)
    wire = _isolate(monkeypatch)
    a, k = _bind(args, kwargs, sid)

    try:
        await _target(module, func)(*a, **k)
    except ooc.FrozenSession:
        pytest.fail(f"{module}.{func} refused while maintenance is armed")
    except Exception:  # noqa: BLE001 - see above
        pass

    assert wire.calls


@pytest.mark.parametrize("module,func,args,kwargs", SWALLOW_CASES, ids=[_id(c) for c in SWALLOW_CASES])
async def test_a_try_that_swallows_errors_does_not_swallow_the_refusal(
        monkeypatch, sid, module, func, args, kwargs):
    """Six ticks and `plant_ripple` wrap their body in `try ... except Exception`. The guard sits above the
    `try`, so the refusal raises and no frozen campaign comes back as an error dict or a silent skip.
    The three ticks without a `try` stay in the list so every tick is held to the same contract."""
    _freeze(monkeypatch, sid)
    wire = _isolate(monkeypatch)
    a, k = _bind(args, kwargs, sid)
    result = None

    with pytest.raises(ooc.FrozenSession):
        result = await _target(module, func)(*a, **k)

    assert result is None
    assert wire.calls == []


# ── the guard comes before validation and early returns ──────────────────


async def test_register_refuses_before_its_name_and_gestation_checks(monkeypatch, sid):
    from modules import pregnancy

    _freeze(monkeypatch, sid)
    _isolate(monkeypatch)
    with pytest.raises(ooc.FrozenSession):
        await pregnancy.register(sid, "", gestation_days=0)

    _freeze(monkeypatch)
    with pytest.raises(ValueError, match="mother_name"):
        await pregnancy.register(sid, "")


async def test_update_quarterly_progress_refuses_before_its_kind_check(monkeypatch, sid):
    from modules import objectives

    _freeze(monkeypatch, sid)
    _isolate(monkeypatch)
    with pytest.raises(ooc.FrozenSession):
        await objectives.update_quarterly_progress(sid, None)

    _freeze(monkeypatch)
    assert "kind required" in (await objectives.update_quarterly_progress(sid, None))["error"]


async def test_apply_refuses_before_its_description_check(monkeypatch, sid):
    from modules import physical_state

    _freeze(monkeypatch, sid)
    _isolate(monkeypatch)
    with pytest.raises(ooc.FrozenSession):
        await physical_state.apply(1, "", session_id=sid)

    _freeze(monkeypatch)
    assert await physical_state.apply(1, "", session_id=sid) == {"error": "description is required"}


async def test_open_pool_refuses_before_its_name_check(monkeypatch, sid):
    from modules import roll_theater

    _freeze(monkeypatch, sid)
    _isolate(monkeypatch)
    with pytest.raises(ooc.FrozenSession):
        await roll_theater.open_pool(sid, "", 50)

    _freeze(monkeypatch)
    with pytest.raises(ValueError, match="pool name is empty"):
        await roll_theater.open_pool(sid, "", 50)


async def test_plant_ripple_refuses_a_frozen_session_before_its_tier_skip(monkeypatch, sid):
    """A tier that plants nothing returns early. The refusal comes first, so the skip cannot hide it."""
    from modules import roll_theater

    _freeze(monkeypatch, sid)
    _isolate(monkeypatch)
    with pytest.raises(ooc.FrozenSession):
        await roll_theater.plant_ripple(sid, "combat", "success", 50)

    _freeze(monkeypatch)
    assert await roll_theater.plant_ripple(sid, "combat", "success", 50) is None


@pytest.mark.parametrize("func", ["hunt_animal", "tame_animal", "explore_anomaly"])
async def test_a_wonders_action_refuses_before_its_power_check(monkeypatch, sid, func):
    from modules import space_wonders

    kwargs = {} if func == "tame_animal" else {"fleet_power": 0}
    _freeze(monkeypatch, sid)
    _isolate(monkeypatch)
    with pytest.raises(ooc.FrozenSession):
        await getattr(space_wonders, func)(1, session_id=sid, **kwargs)

    if func != "tame_animal":
        _freeze(monkeypatch)
        assert "fleet_power must be positive" in (
            await getattr(space_wonders, func)(1, session_id=sid, **kwargs))["error"]


async def test_resolve_turn_refuses_before_it_changes_the_state(monkeypatch, sid):
    from modules.battle import BattleEngine

    _freeze(monkeypatch, sid)
    _isolate(monkeypatch)
    state = _state(sid)

    with pytest.raises(ooc.FrozenSession):
        await BattleEngine.resolve_turn(state, "Direct Assault")

    assert state.turn == 0 and state.player_tactic == "Direct Assault" and state.log == []


# ── a battle id names the session ────────────────────────────────────────


async def test_set_formation_refuses_a_battle_of_a_frozen_session(monkeypatch, sid):
    from modules import battle

    _freeze(monkeypatch, sid)
    db = _RecordingDB(fetchval=sid)
    monkeypatch.setattr(battle, "Database", db)

    with pytest.raises(ooc.FrozenSession):
        await battle.BattleEngine.set_formation(7, "Wedge")

    assert db.args == [(7,)] and db.writes == []


async def test_set_formation_writes_a_battle_of_a_session_that_is_not_frozen(monkeypatch, sid):
    from modules import battle

    _freeze(monkeypatch)
    db = _RecordingDB(fetchval=sid, fetchrow={"name": "Wedge"})
    monkeypatch.setattr(battle, "Database", db)

    assert await battle.BattleEngine.set_formation(7, "wedge") == "Wedge"
    assert db.writes[0][1] == ("Wedge", 7)


async def test_set_formation_lets_a_missing_battle_fall_through_to_the_catalogue_check(monkeypatch, sid):
    from modules import battle

    _freeze(monkeypatch, sid)
    db = _RecordingDB(fetchval=None, fetchrow=None)
    monkeypatch.setattr(battle, "Database", db)

    with pytest.raises(ValueError, match="Unknown formation"):
        await battle.BattleEngine.set_formation(7, "nonsense")


async def test_set_formation_writes_a_frozen_battle_under_maintenance(monkeypatch, sid):
    from modules import battle

    _freeze(monkeypatch, sid)
    monkeypatch.setattr("core.ooc._maintenance_active", lambda: True)
    db = _RecordingDB(fetchval=sid, fetchrow={"name": "Wedge"})
    monkeypatch.setattr(battle, "Database", db)

    await battle.BattleEngine.set_formation(7, "Wedge")

    assert len(db.writes) == 1


_BATTLE_ROW = {"session_id": None, "ship_states": {}}


async def test_attempt_retreat_refuses_a_battle_of_a_frozen_session(monkeypatch, sid):
    from modules import battle

    _freeze(monkeypatch, sid)
    bus = _Bus()
    db = _RecordingDB(fetchrow=dict(_BATTLE_ROW, session_id=sid))
    monkeypatch.setattr(battle, "Database", db)
    monkeypatch.setattr(battle, "EventBus", bus)

    with pytest.raises(ooc.FrozenSession):
        await battle.BattleEngine.attempt_retreat(7)

    assert db.writes == [] and bus.events == []


async def test_attempt_retreat_writes_a_battle_of_a_session_that_is_not_frozen(monkeypatch, sid):
    from modules import battle

    _freeze(monkeypatch)
    bus = _Bus()
    db = _RecordingDB(fetchrow=dict(_BATTLE_ROW, session_id=sid))
    monkeypatch.setattr(battle, "Database", db)
    monkeypatch.setattr(battle, "EventBus", bus)

    out = await battle.BattleEngine.attempt_retreat(7)

    assert out["success"] in (True, False)
    assert len(db.writes) == 1 and db.writes[0][1][-1] == 7
    assert bus.events[0][1]["session_id"] == sid


async def test_attempt_retreat_reports_a_missing_battle_without_refusing(monkeypatch, sid):
    from modules import battle

    _freeze(monkeypatch, sid)
    db = _RecordingDB(fetchrow=None)
    monkeypatch.setattr(battle, "Database", db)

    assert await battle.BattleEngine.attempt_retreat(7) == {"success": False, "error": "Not found"}
    assert db.writes == []


# ── a sector names the session when none is given ────────────────────────


@pytest.mark.parametrize("func", ["encounter_animal", "discover_anomaly"])
async def test_a_sector_of_a_frozen_session_is_refused(monkeypatch, sid, other, func):
    """No session is named, so the sector row says which campaign the write belongs to."""
    from modules import space_wonders

    _freeze(monkeypatch, other)
    db = _RecordingDB(fetchval=other)
    monkeypatch.setattr(space_wonders, "Database", db)

    with pytest.raises(ooc.FrozenSession):
        await getattr(space_wonders, func)(1)

    assert db.args == [(1,)] and db.writes == []


@pytest.mark.parametrize("func", ["encounter_animal", "discover_anomaly"])
async def test_a_named_session_skips_the_sector_read(monkeypatch, sid, func):
    from modules import space_wonders

    _freeze(monkeypatch)
    db = _RecordingDB(fetchval="sector read", fetchrow=None)
    monkeypatch.setattr(space_wonders, "Database", db)

    out = await getattr(space_wonders, func)(1, session_id=sid)

    assert "error" in out
    assert not any(a == (1,) for a in db.args)


@pytest.mark.parametrize("func", ["encounter_animal", "discover_anomaly"])
async def test_a_system_without_a_sector_row_resolves_through_rp_session(monkeypatch, sid, other, func):
    from modules import space_wonders

    _freeze(monkeypatch, other)
    monkeypatch.setenv("RP_SESSION", str(other))
    db = _RecordingDB(fetchval=None, fetchrow=None)
    monkeypatch.setattr(space_wonders, "Database", db)

    with pytest.raises(ooc.FrozenSession):
        await getattr(space_wonders, func)(1)

    assert db.writes == []


# ── what a writer does when it can write ─────────────────────────────────


async def test_mark_read_retires_the_article_of_the_session_it_resolved(monkeypatch, sid, other):
    from modules import news

    _freeze(monkeypatch)
    monkeypatch.setenv("RP_SESSION", str(other))
    db = _RecordingDB()
    monkeypatch.setattr(news, "Database", db)

    assert await news.mark_read(article_id=7) is True
    assert db.writes[0][1] == (other, 7)


async def test_register_inserts_the_pregnancy_when_the_session_is_not_frozen(monkeypatch, sid):
    from modules import pregnancy

    _freeze(monkeypatch)
    db = _RecordingDB(fetchval=9)
    monkeypatch.setattr(pregnancy, "Database", db)

    assert await pregnancy.register(sid, "Aisyah") == 9
    assert db.args[1][0] == sid


async def test_shift_writes_the_session_it_resolved(monkeypatch, sid, other):
    from modules import population_sentiment

    _freeze(monkeypatch)
    monkeypatch.setenv("RP_SESSION", str(other))
    db = _RecordingDB(fetchrow={"sentiment": 8})
    monkeypatch.setattr(population_sentiment, "Database", db)

    out = await population_sentiment.shift(None, 1, "F", 3, "r")

    assert out["sentiment"] == 8
    assert db.args[0][0] == other


async def test_bump_kind_reads_the_session_it_was_given(monkeypatch, sid):
    """The event bus calls `_bump_kind` directly with the session from the event payload."""
    from modules import objectives

    _freeze(monkeypatch)
    db = _RecordingDB(fetch=[])
    monkeypatch.setattr(objectives, "Database", db)

    assert await objectives._bump_kind(sid, "kills") == {"updated": 0, "completed": []}
    assert db.args[0][0] == sid


async def test_apply_inserts_the_injury_when_the_session_is_not_frozen(monkeypatch, sid):
    from modules import physical_state

    _freeze(monkeypatch)
    db = _RecordingDB(fetchval=10)
    monkeypatch.setattr(physical_state, "Database", db)

    out = await physical_state.apply(1, "a cut", "minor", session_id=sid)

    assert out["injury_id"] == 10 and out["severity"] == "minor"
    assert db.args[1][0] == sid


async def test_consume_blessing_spends_a_charge_when_the_session_is_not_frozen(monkeypatch, sid):
    from modules import roll_theater

    _freeze(monkeypatch)
    db = _RecordingDB(fetchval=5, fetchrow={"id": 1})
    monkeypatch.setattr(roll_theater, "Database", db)

    assert await roll_theater.consume_blessing(sid, "Callista") is True
    assert db.args[1][0] == sid


async def test_plant_ripple_plants_a_seed_when_the_session_is_not_frozen(monkeypatch, sid):
    from modules import roll_theater

    _freeze(monkeypatch)
    planted = []

    async def plant(seed):
        planted.append(seed)

    monkeypatch.setattr("core.consequences.plant", plant)

    await roll_theater.plant_ripple(sid, "combat", "fumble", 50)

    assert planted[0]["session_id"] == sid and planted[0]["trigger"] == "combat_roll_fumble"


async def test_plant_ripple_plants_into_a_frozen_session_under_maintenance(monkeypatch, sid):
    from modules import roll_theater

    _freeze(monkeypatch, sid)
    monkeypatch.setattr("core.ooc._maintenance_active", lambda: True)
    planted = []

    async def plant(seed):
        planted.append(seed)

    monkeypatch.setattr("core.consequences.plant", plant)

    await roll_theater.plant_ripple(sid, "combat", "partial", 50)

    assert len(planted) == 1


async def test_survey_planet_marks_the_planet_of_the_session_it_resolved(monkeypatch, sid, other):
    from modules import space_wonders

    _freeze(monkeypatch)
    monkeypatch.setenv("RP_SESSION", str(other))
    db = _RecordingDB(fetchrow={"name": "P", "planet_type": "rock", "features": ["ruins"]})
    monkeypatch.setattr(space_wonders, "Database", db)

    out = await space_wonders.survey_planet(1)

    assert out["planet"] == "P"
    assert db.writes[0][1] == (1, other)


# ── a reader stays open ──────────────────────────────────────────────────


@pytest.mark.parametrize("module,func,args,kwargs,want", READER_CASES, ids=[_id(c) for c in READER_CASES])
async def test_a_reader_still_returns_on_a_frozen_session(monkeypatch, sid, module, func, args, kwargs, want):
    _freeze(monkeypatch, sid)
    db = _ReadDB(fetchval=lambda: 0)
    monkeypatch.setattr(_module(module), "Database", db)
    a, k = _bind(args, kwargs, sid)

    out = await _target(module, func)(*a, **k)

    if func.endswith("_make_enemy_fleet"):
        assert out.faction == want and out.ships == []
    else:
        assert out == want


@pytest.mark.parametrize("module,func,args,kwargs", DEFAULTING_READERS,
                         ids=[_id(c) for c in DEFAULTING_READERS])
async def test_a_reader_resolves_its_session_per_call(monkeypatch, sid, other, module, func, args, kwargs):
    """The process default is `sid`. RP_SESSION names `other`, and the query must carry `other`."""
    _freeze(monkeypatch)
    monkeypatch.setenv("RP_SESSION", str(other))
    db = _ReadDB(fetchval=lambda: 0)
    monkeypatch.setattr(_module(module), "Database", db)
    a, k = _bind(args, kwargs, None)

    await _target(module, func)(*a, **k)

    seen = _flat(db.args)
    assert other in seen, f"{module}.{func} did not query the resolved session"
    assert sid not in seen, f"{module}.{func} fell back to the process default"


async def test_the_story_log_writes_the_session_it_resolved(monkeypatch, sid, other):
    """`_log` is a helper that a guarded entry reaches. It resolves a missing session and never refuses."""
    from modules import space_wonders

    _freeze(monkeypatch, other)
    monkeypatch.setenv("RP_SESSION", str(other))
    db = _RecordingDB()
    monkeypatch.setattr(space_wonders, "Database", db)

    await space_wonders._log(None, "exploration", "t", "c")

    assert db.writes[0][1][0] == other


# ── a reader that writes ─────────────────────────────────────────────────


async def test_get_state_counts_the_due_wounds_without_healing_them_on_a_frozen_session(monkeypatch, sid):
    from modules import physical_state

    _freeze(monkeypatch, sid)
    db = _InjuryDB(writable=False)
    monkeypatch.setattr(physical_state, "Database", db)

    out = await physical_state.get_state(7, sid)

    assert out["healed"] == 1
    assert not any(s.lstrip().startswith("UPDATE") for s in db.sql)


async def test_get_state_heals_the_due_wounds_when_writes_are_allowed(monkeypatch, sid):
    from modules import physical_state

    _freeze(monkeypatch)
    db = _InjuryDB(writable=True)
    monkeypatch.setattr(physical_state, "Database", db)

    out = await physical_state.get_state(7, sid)

    assert out["healed"] == 1
    assert sum(s.lstrip().startswith("UPDATE") for s in db.sql) == 1


async def test_get_state_heals_a_frozen_session_under_maintenance(monkeypatch, sid):
    from modules import physical_state

    _freeze(monkeypatch, sid)
    monkeypatch.setattr("core.ooc._maintenance_active", lambda: True)
    db = _InjuryDB(writable=True)
    monkeypatch.setattr(physical_state, "Database", db)

    await physical_state.get_state(7, sid)

    assert sum(s.lstrip().startswith("UPDATE") for s in db.sql) == 1


async def test_get_state_skips_the_heal_when_the_frozen_list_is_unreadable(monkeypatch, sid):
    from core.session import FrozenListUnreadable
    from modules import physical_state

    def boom(_sid):
        raise FrozenListUnreadable("unreadable")

    monkeypatch.setattr("core.session.is_frozen", boom)
    monkeypatch.setattr("core.ooc._maintenance_active", lambda: False)
    db = _InjuryDB(writable=False)
    monkeypatch.setattr(physical_state, "Database", db)

    assert (await physical_state.get_state(7, sid))["healed"] == 1


async def test_get_state_resolves_its_session_per_call(monkeypatch, sid, other):
    from modules import physical_state

    _freeze(monkeypatch)
    monkeypatch.setenv("RP_SESSION", str(other))
    seen = []

    class Db(_InjuryDB):
        async def fetch(self, sql, *args):
            seen.extend(args)
            return await super().fetch(sql, *args)

    monkeypatch.setattr(physical_state, "Database", Db(writable=True))

    await physical_state.get_state(7)

    assert other in seen and sid not in seen
