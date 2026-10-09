"""T4 frozen guards, batch B: image_gen, locations, logistics, manufacturing, market, meanwhile,
memories, ministry_ai, mystery, narrative, narrative_seeds, narrator.

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
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import ooc  # noqa: E402
from tests.conftest import scratch_id  # noqa: E402

S = object()  # placeholder for the session argument

#: module -> [(function, args, kwargs)]. `S` marks the session argument.
WRITERS = {
    "image_gen": [
        ("generate_prompt", (S,), {}),
    ],
    "locations": [
        ("set_player_location", (S, "bridge"), {}),
        ("set_character_presence", (1, "bridge", S), {}),
    ],
    "logistics": [
        ("create_cargo", ("ore", 5, "sector", 1, S), {}),
        ("transport", (1, "sector", 2, 3, S), {}),
        ("run_tick", (S,), {}),
    ],
    "manufacturing": [
        ("run_tick", (S,), {}),
    ],
    "market": [
        ("run_tick", (S,), {}),
    ],
    "memories": [
        ("store", (1, "promise", "c"), {"session_id": S}),
        ("run_tick", (S,), {}),
        ("consolidate_memories", (S,), {}),
    ],
    "ministry_ai": [
        ("set_king", (S, True), {}),
        ("set_dark", (S, True), {}),
        ("run_tick", (S,), {}),
        ("resolve", (S, 1, "accepted"), {}),
    ],
    "mystery": [
        ("create_investigation", (S, "t"), {}),
        ("add_clue", (S, 1, "x"), {}),
        ("deduce", (S, 1), {}),
        ("generate_red_herring", (S, 1), {}),
        ("run_tick", (S,), {}),
    ],
    "narrative": [
        ("run_tick", (S,), {}),
    ],
    "narrative_seeds": [
        ("plant_seed", ("t", "c"), {"session_id": S}),
        ("mark_foreshadowed", (1, S), {}),
        ("pay_off", (1, S), {}),
        ("run_tick", (S,), {}),
    ],
}

#: module -> [(function, args, kwargs, value the frozen call returns on the empty stand-in)]
READERS = {
    "image_gen": [("run_tick", (S,), {}, {"status": "image_gen_ready"})],
    "locations": [("run_tick", (S,), {}, {"status": "locations_ready"})],
    "market": [("get_market_index", (S,), {}, 1.0)],
    "memories": [
        ("get_inner_world", (1, S), {}, None),
        ("cmd_memory_surface", ("x", "ctx", S), {}, None),
    ],
    "ministry_ai": [
        ("king_status", (S,), {}, False),
        ("dark_status", (S,), {}, False),
        ("pending", (S,), {}, []),
    ],
    "narrative_seeds": [("get_foreshadow_ops", (S,), {}, [])],
    "narrator": [("run_tick", (S,), {}, {"narrated": 0, "narratives": []})],
}

#: Readers that also write. Both call `_writes_allowed` and skip the write on a frozen campaign.
READER_WRITERS = [("memories", "recall"), ("meanwhile", "generate")]

#: Modules with no function that queries or writes by itself, so a per-call session cannot be observed.
NO_QUERY = {("image_gen", "run_tick"), ("locations", "run_tick")}

ALL_MODULES = sorted(set(WRITERS) | set(READERS) | {m for m, _ in READER_WRITERS})

WRITER_CASES = [(m, f, a, k) for m, rows in WRITERS.items() for f, a, k in rows]
#: Every function here wraps its body in `try ... except Exception: return {"error": ...}` or is a tick.
SWALLOW_CASES = [c for c in WRITER_CASES if c[1] in ("run_tick", "consolidate_memories")]
READER_CASES = [(m, f, a, k, want) for m, rows in READERS.items() for f, a, k, want in rows]
DEFAULTING_READERS = [(m, f, a, k) for m, f, a, k, _ in READER_CASES if (m, f) not in NO_QUERY]
AST_READERS = [(m, f) for m, f, *_ in READER_CASES] + READER_WRITERS


def _id(case):
    return f"{case[0]}.{case[1]}"


def _bind(args, kwargs, sid):
    return (tuple(sid if a is S else a for a in args),
            {k: (sid if v is S else v) for k, v in kwargs.items()})


def _module(name):
    return importlib.import_module(f"modules.{name}")


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
    """Tripwire for every module batch B reaches a database through, plus the mode lookup."""
    wire = _Tripwire()
    for name in ALL_MODULES:
        monkeypatch.setattr(_module(name), "Database", wire)

    async def mode(_sid):
        return {"mode": "downtime"}

    monkeypatch.setattr("core.pacing.PacingDirector.get_mode", mode)
    return wire


# ── structure: the guard is first, readers stay open, no process default ──


def _function(tree, name):
    for node in tree.body:
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name:
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


@pytest.mark.parametrize("module,func,args,kwargs", WRITER_CASES, ids=[_id(c) for c in WRITER_CASES])
async def test_a_writer_refuses_a_frozen_session_before_any_database_call(
        monkeypatch, sid, module, func, args, kwargs):
    _freeze(monkeypatch, sid)
    wire = _isolate(monkeypatch)
    a, k = _bind(args, kwargs, sid)

    with pytest.raises(ooc.FrozenSession):
        await getattr(_module(module), func)(*a, **k)

    assert wire.calls == [], f"{module}.{func} reached the database for a frozen session: {wire.calls}"


@pytest.mark.parametrize("module,func,args,kwargs", WRITER_CASES, ids=[_id(c) for c in WRITER_CASES])
async def test_a_writer_resolves_its_session_per_call_and_guards_that_one(
        monkeypatch, sid, other, module, func, args, kwargs):
    """No session argument: RP_SESSION names the campaign. Only that one is frozen, so a process default
    that is not frozen cannot let the write through."""
    _freeze(monkeypatch, other)
    monkeypatch.setenv("RP_SESSION", str(other))
    wire = _isolate(monkeypatch)
    a, k = _bind(args, kwargs, None)

    with pytest.raises(ooc.FrozenSession):
        await getattr(_module(module), func)(*a, **k)

    assert wire.calls == []


@pytest.mark.parametrize("module,func,args,kwargs", WRITER_CASES, ids=[_id(c) for c in WRITER_CASES])
async def test_a_writer_runs_when_the_session_is_not_frozen(monkeypatch, sid, module, func, args, kwargs):
    """The guard passes and the function proceeds to its first database call."""
    _freeze(monkeypatch)
    wire = _isolate(monkeypatch)
    a, k = _bind(args, kwargs, sid)

    try:
        await getattr(_module(module), func)(*a, **k)
    except ooc.FrozenSession:
        pytest.fail(f"{module}.{func} refused a session that is not frozen")
    except Exception:  # noqa: BLE001 - the stand-in raises on the first call, or the tick reports it
        pass

    assert wire.calls, f"{module}.{func} never reached the database"


@pytest.mark.parametrize("module,func,args,kwargs", WRITER_CASES, ids=[_id(c) for c in WRITER_CASES])
async def test_maintenance_lets_a_writer_into_a_frozen_session(monkeypatch, sid, module, func, args, kwargs):
    _freeze(monkeypatch, sid)
    monkeypatch.setattr("core.ooc._maintenance_active", lambda: True)
    wire = _isolate(monkeypatch)
    a, k = _bind(args, kwargs, sid)

    try:
        await getattr(_module(module), func)(*a, **k)
    except ooc.FrozenSession:
        pytest.fail(f"{module}.{func} refused while maintenance is armed")
    except Exception:  # noqa: BLE001 - see above
        pass

    assert wire.calls


@pytest.mark.parametrize("module,func,args,kwargs", SWALLOW_CASES, ids=[_id(c) for c in SWALLOW_CASES])
async def test_a_try_that_returns_an_error_dict_does_not_swallow_the_refusal(
        monkeypatch, sid, module, func, args, kwargs):
    """These bodies sit in `try ... except Exception: return {"error": ...}`. The guard sits above the
    `try`, so the refusal raises and no frozen campaign comes back as an error dict."""
    _freeze(monkeypatch, sid)
    wire = _isolate(monkeypatch)
    a, k = _bind(args, kwargs, sid)
    result = None

    with pytest.raises(ooc.FrozenSession):
        result = await getattr(_module(module), func)(*a, **k)

    assert result is None
    assert wire.calls == []


# ── the guard comes before validation and early returns ──────────────────


async def test_create_cargo_refuses_before_its_quantity_check(monkeypatch, sid):
    from modules import logistics

    _freeze(monkeypatch, sid)
    _isolate(monkeypatch)

    with pytest.raises(ooc.FrozenSession):
        await logistics.create_cargo("ore", -1, "", None, sid)


async def test_transport_refuses_before_its_destination_check(monkeypatch, sid):
    from modules import logistics

    _freeze(monkeypatch, sid)
    _isolate(monkeypatch)

    with pytest.raises(ooc.FrozenSession):
        await logistics.transport(1, "", None, None, sid)


async def test_resolve_refuses_before_its_decision_check(monkeypatch, sid):
    from modules import ministry_ai

    _freeze(monkeypatch, sid)
    _isolate(monkeypatch)

    with pytest.raises(ooc.FrozenSession):
        await ministry_ai.resolve(sid, 1, "bogus")

    _freeze(monkeypatch)
    assert await ministry_ai.resolve(sid, 1, "bogus") == {"error": "decision must be accepted/rejected"}


async def test_consolidate_refuses_before_its_window_check(monkeypatch, sid):
    from modules import memories

    _freeze(monkeypatch, sid)
    _isolate(monkeypatch)

    with pytest.raises(ooc.FrozenSession):
        await memories.consolidate_memories(sid, age_days=-1)

    _freeze(monkeypatch)
    with pytest.raises(ValueError, match="age_days"):
        await memories.consolidate_memories(sid, age_days=-1)


async def test_goto_refuses_a_frozen_session_through_its_writer(monkeypatch, sid, capsys):
    from modules import locations

    _freeze(monkeypatch, sid)
    wire = _isolate(monkeypatch)

    with pytest.raises(ooc.FrozenSession):
        await locations.cmd_goto("bridge", session_id=sid)

    assert wire.calls == []
    assert capsys.readouterr().out == ""


# ── what a writer does when it may write ─────────────────────────────────


async def test_generate_prompt_stores_the_prompt_when_the_session_is_not_frozen(monkeypatch, sid):
    from modules import image_gen

    _freeze(monkeypatch)
    db = _RecordingDB(fetchrow=None)
    monkeypatch.setattr(image_gen, "Database", db)

    out = await image_gen.generate_prompt(sid)

    assert out["scene_type"] == "planet-landscape"
    assert len(db.writes) == 1 and db.writes[0][1][0] == sid


async def test_set_player_location_writes_the_session_it_resolved(monkeypatch, sid, other):
    from modules import locations

    _freeze(monkeypatch)
    monkeypatch.setenv("RP_SESSION", str(other))
    db = _RecordingDB(fetchval=1)
    monkeypatch.setattr(locations, "Database", db)

    await locations.set_player_location(None, "bridge")

    assert db.writes[0][1][0] == other


async def test_create_cargo_inserts_when_the_session_is_not_frozen(monkeypatch, sid):
    from modules import logistics

    _freeze(monkeypatch)
    db = _RecordingDB(fetchval=9)
    monkeypatch.setattr(logistics, "Database", db)

    out = await logistics.create_cargo("ore", 5, "sector", 1, sid)

    assert out["cargo_id"] == 9
    assert db.args[0][0] == sid


async def test_store_writes_when_the_session_is_not_frozen(monkeypatch, sid):
    from modules import memories

    _freeze(monkeypatch)
    db = _RecordingDB(fetchval=40)
    monkeypatch.setattr(memories, "Database", db)

    await memories.store(1, "promise", "kept", session_id=sid)

    assert db.writes[0][1][0] == sid and db.writes[0][1][5] == 40


async def test_set_king_writes_the_session_it_resolved(monkeypatch, sid, other):
    from modules import ministry_ai

    _freeze(monkeypatch)
    monkeypatch.setenv("RP_SESSION", str(other))
    db = _RecordingDB()
    monkeypatch.setattr(ministry_ai, "Database", db)

    await ministry_ai.set_king(None, True)

    assert db.writes[0][1] == (other, True)


async def test_resolve_decides_a_prompt_when_the_session_is_not_frozen(monkeypatch, sid):
    from modules import ministry_ai

    _freeze(monkeypatch)
    db = _RecordingDB(fetchval=1)
    monkeypatch.setattr(ministry_ai, "Database", db)

    assert await ministry_ai.resolve(sid, 1, "accepted") == {"prompt_id": 1, "decision": "accepted"}
    assert db.writes[0][1] == (1, sid, "accepted")


async def test_create_investigation_inserts_when_the_session_is_not_frozen(monkeypatch, sid):
    from modules import mystery

    _freeze(monkeypatch)
    db = _RecordingDB(fetchval=4)
    monkeypatch.setattr(mystery, "Database", db)

    out = await mystery.create_investigation(sid, "the missing relay")

    assert out["investigation_id"] == 4
    assert db.args[0][0] == sid


async def test_plant_seed_writes_when_the_session_is_not_frozen(monkeypatch, sid):
    from modules import narrative_seeds

    _freeze(monkeypatch)
    db = _RecordingDB(fetchval=12)
    monkeypatch.setattr(narrative_seeds, "Database", db)

    await narrative_seeds.plant_seed("promise", "a debt", session_id=sid)

    assert db.writes[0][1][0] == sid and db.writes[0][1][3] == 12


# ── a reader stays open ──────────────────────────────────────────────────


@pytest.mark.parametrize("module,func,args,kwargs,want", READER_CASES, ids=[_id(c) for c in READER_CASES])
async def test_a_reader_still_returns_on_a_frozen_session(monkeypatch, sid, module, func, args, kwargs, want):
    _freeze(monkeypatch, sid)
    db = _ReadDB(fetchval=lambda: 0)
    monkeypatch.setattr(_module(module), "Database", db)
    a, k = _bind(args, kwargs, sid)

    out = await getattr(_module(module), func)(*a, **k)

    if func == "get_inner_world":
        assert out["total_memories"] == 0 and out["character_id"] == 1
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

    await getattr(_module(module), func)(*a, **k)

    seen = _flat(db.args)
    assert other in seen, f"{module}.{func} did not query the resolved session"
    assert sid not in seen, f"{module}.{func} fell back to the process default"


# ── readers that write ───────────────────────────────────────────────────

_MEMORY = {"id": 1, "memory_type": "promise", "content": "c", "emotional_weight": 5,
           "recalled_count": 0, "created_at_game_day": 1}


async def test_recall_returns_the_memories_without_writing_on_a_frozen_session(monkeypatch, sid):
    from modules import memories

    _freeze(monkeypatch, sid)
    db = _ReadDB(fetchval=100, fetch=[_MEMORY])
    monkeypatch.setattr(memories, "Database", db)

    assert await memories.recall(7, "vault", sid) == [_MEMORY]


async def test_recall_bumps_the_recall_count_when_writes_are_allowed(monkeypatch, sid):
    from modules import memories

    _freeze(monkeypatch)
    db = _RecordingDB(fetchval=100, fetch=[_MEMORY])
    monkeypatch.setattr(memories, "Database", db)

    assert await memories.recall(7, "vault", sid) == [_MEMORY]
    assert len(db.writes) == 1
    assert db.writes[0][1] == (100, 1, sid)


async def test_recall_bumps_in_a_frozen_session_under_maintenance(monkeypatch, sid):
    from modules import memories

    _freeze(monkeypatch, sid)
    monkeypatch.setattr("core.ooc._maintenance_active", lambda: True)
    db = _RecordingDB(fetchval=100, fetch=[_MEMORY])
    monkeypatch.setattr(memories, "Database", db)

    await memories.recall(7, "vault", sid)

    assert len(db.writes) == 1


async def test_recall_skips_the_bump_when_the_frozen_list_is_unreadable(monkeypatch, sid):
    from core.session import FrozenListUnreadable
    from modules import memories

    def boom(_sid):
        raise FrozenListUnreadable("unreadable")

    monkeypatch.setattr("core.session.is_frozen", boom)
    monkeypatch.setattr("core.ooc._maintenance_active", lambda: False)
    db = _ReadDB(fetchval=100, fetch=[_MEMORY])
    monkeypatch.setattr(memories, "Database", db)

    assert await memories.recall(7, "vault", sid) == [_MEMORY]


async def test_recall_resolves_its_session_per_call(monkeypatch, sid, other):
    from modules import memories

    _freeze(monkeypatch)
    monkeypatch.setenv("RP_SESSION", str(other))
    db = _RecordingDB(fetchval=100, fetch=[_MEMORY])
    monkeypatch.setattr(memories, "Database", db)

    await memories.recall(7, "vault")

    assert other in _flat(db.args) and sid not in _flat(db.args)
    assert db.writes[0][1][2] == other


async def test_cmd_memory_surface_lists_a_frozen_sessions_memories(monkeypatch, sid, capsys):
    from modules import memories

    _freeze(monkeypatch, sid)
    db = _ReadDB(fetchrow={"id": 7, "name": "Nadia"}, fetchval=100, fetch=[_MEMORY])
    monkeypatch.setattr(memories, "Database", db)

    await memories.cmd_memory_surface("nadia", "vault", sid)

    assert "[promise] c" in capsys.readouterr().out


_RAID = {"id": 1, "faction_name": "F", "target_system": "S", "enemy_power": 5, "ticks_remaining": 2}


@pytest.fixture
def raid_roll(monkeypatch):
    """Force the 15% roll and a pacing mode that allows a cut."""
    import random

    monkeypatch.setattr(random, "random", lambda: 0.0)

    async def mode(_sid):
        return {"mode": "normal"}

    monkeypatch.setattr("core.pacing.PacingDirector.get_mode", mode)


async def test_generate_returns_the_cut_without_marking_the_raid_on_a_frozen_session(
        monkeypatch, sid, raid_roll):
    from modules import meanwhile

    _freeze(monkeypatch, sid)
    db = _ReadDB(fetchrow=_RAID)
    monkeypatch.setattr(meanwhile, "Database", db)

    out = await meanwhile.generate(sid)

    assert out["type"] == "enemy_pov" and "Target: S" in out["narrative"]


async def test_generate_marks_the_raid_detected_when_writes_are_allowed(monkeypatch, sid, raid_roll):
    from modules import meanwhile

    _freeze(monkeypatch)
    db = _RecordingDB(fetchrow=_RAID)
    monkeypatch.setattr(meanwhile, "Database", db)

    out = await meanwhile.generate(sid)

    assert out["type"] == "enemy_pov"
    assert len(db.writes) == 1 and db.writes[0][1] == (sid, 1)


async def test_generate_marks_the_raid_in_a_frozen_session_under_maintenance(monkeypatch, sid, raid_roll):
    from modules import meanwhile

    _freeze(monkeypatch, sid)
    monkeypatch.setattr("core.ooc._maintenance_active", lambda: True)
    db = _RecordingDB(fetchrow=_RAID)
    monkeypatch.setattr(meanwhile, "Database", db)

    await meanwhile.generate(sid)

    assert len(db.writes) == 1


async def test_generate_resolves_its_session_per_call(monkeypatch, sid, other, raid_roll):
    from modules import meanwhile

    _freeze(monkeypatch)
    monkeypatch.setenv("RP_SESSION", str(other))
    db = _RecordingDB(fetchrow=_RAID)
    monkeypatch.setattr(meanwhile, "Database", db)

    await meanwhile.generate()

    assert other in _flat(db.args) and sid not in _flat(db.args)
    assert db.writes[0][1][0] == other
