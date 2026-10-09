"""T4 frozen guards, batch A: _economy, economy, crew_system, space_horror, megastructures_ports,
character_profile, faction_ai, fleet, fleet_economy, geopolitics, ideology, infrastructure.

Contract (core/session.py): a frozen campaign stays readable, and a write is refused unless GM MAYA
maintenance is armed. A writer calls `_refuse_frozen` before anything else. A reader resolves its session
with `require_session` and never refuses. A reader that writes skips the write on a frozen campaign.

No test here touches the database. Every module gets a `Database` stand-in, the session is the scratch
session, and `Config.SESSION_ID` is the scratch id so a default cannot name session 3 or 5.
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
    "_economy": [
        ("_deduct_resources", (S, {"credits": 1}), {}),
    ],
    "economy": [
        ("run_tick", (S,), {}),
        ("resolve_intent", (S, "buy", "x", 5), {}),
    ],
    "crew_system": [
        ("produce_crew", (S,), {}),
        ("consume_crew", (S, 1, 5), {}),
        ("backfill_history", (S,), {}),
        ("graduation_cycle", (S,), {}),
        ("ai_allocate_crew", (S,), {}),
        ("screen_crew", (S, 1), {}),
        ("set_min_clearance", (S, 1, 5), {}),
        ("run_tick", (S,), {}),
    ],
    "space_horror": [
        ("seed_infestation", (S, 1), {}),
        ("spread_infestation", (S,), {}),
        ("apply_containment", (S, 1, "m"), {}),
        ("launch_eradication", (S, 1), {}),
        ("advance_eradication", (S,), {}),
        ("run_tick", (S,), {}),
    ],
    "megastructures_ports": [
        ("start_construction", (S, 1), {}),
        ("advance_megastructure", (S,), {}),
        ("build_port", (S, 1, 1), {}),
        ("upgrade_port", (S, 1, "u"), {}),
        ("run_tick", (S,), {}),
    ],
    "character_profile": [
        ("update_profile", (1, {}, S), {}),
        ("add_to_wardrobe", (1, {}, S), {}),
        ("set_outfit", (1, "o", S), {}),
        ("add_item", (1, {}, S), {}),
        ("grant", (1,), {"item": {"name": "i"}, "session_id": S}),
        ("auto_dress_for_mode", (1, "combat", S), {}),
        ("auto_dress_all_present", (S,), {}),
        ("run_tick", (S,), {}),
    ],
    "faction_ai": [("run_tick", (S,), {})],
    "fleet": [
        ("create_fleet", ("f",), {"session_id": S}),
        ("assign_ship", ("s", "f"), {"session_id": S}),
        ("fleet_battle", ("f", "blitz", "t"), {"session_id": S}),
    ],
    "fleet_economy": [
        ("apply_burn", (S,), {}),
        ("run_tick", (S,), {}),
    ],
    "geopolitics": [("run_tick", (S,), {})],
    "ideology": [("run_tick", (S,), {})],
    "infrastructure": [
        ("build_infrastructure", (S, 1), {}),
        ("upgrade_infrastructure", (S, 1), {}),
        ("run_production_tick", (S,), {}),
        ("run_tick", (S,), {}),
    ],
}

#: module -> [(function, args, kwargs, value the frozen call must return on the empty stand-in)]
READERS = {
    "economy": [("gate_toll_income", (S,), {}, 0)],
    "crew_system": [("crew_report", (S,), {}, None)],
    "space_horror": [
        ("get_active_threats", (S,), {}, []),
        ("get_infestation_detail", (1, S), {}, {}),
    ],
    "megastructures_ports": [
        ("get_megastructure_status", (S,), {}, []),
        ("get_port_overview", (S,), {}, []),
    ],
    "character_profile": [
        ("get_character_card", (1, S), {}, "Character not found."),
        ("get_character_card_by_name", ("x", S), {}, "Character not found."),
    ],
    "fleet": [
        ("list_fleets", (S,), {}, []),
        ("run_tick", (S,), {}, {"fleets": 0}),
    ],
    "infrastructure": [
        ("get_infrastructure", (1, S), {}, {}),
        ("list_infrastructure", (S,), {}, []),
    ],
}

#: Readers that resolve a missing session from RP_SESSION (every reader above except the one
#: whose signature has no default: get_active_threats).
DEFAULTING_READERS = [(m, f, a, k) for m, rows in READERS.items() for f, a, k, _ in rows
                      if f != "get_active_threats"]

WRITER_CASES = [(m, f, a, k) for m, rows in WRITERS.items() for f, a, k in rows]
TICK_CASES = [c for c in WRITER_CASES if c[1] == "run_tick"]
READER_CASES = [(m, f, a, k, want) for m, rows in READERS.items() for f, a, k, want in rows]
#: Functions that read and also write (card contract 4); both call `_writes_allowed`, directly or through `get`.
READER_WRITERS = [("ideology", "get"), ("ideology", "get_prompt")]
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
    """The file's scratch session id (900-999), as the process default too, so nothing can fall back to
    a live arc. The id is the one `scratch_session` hands out. The fixture itself is not used: it clears
    every table on teardown, and these tests write nothing."""
    session = scratch_id(request.module.__name__)
    monkeypatch.setattr("core.config.Config.SESSION_ID", session)
    monkeypatch.delenv("RP_SESSION", raising=False)
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
    """Tripwire for every module batch A reaches a database through, plus the mode lookup."""
    wire = _Tripwire()
    for name in WRITERS:
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


@pytest.mark.parametrize("module", sorted(WRITERS))
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


@pytest.mark.parametrize("module,func,args,kwargs", TICK_CASES, ids=[_id(c) for c in TICK_CASES])
async def test_run_tick_surfaces_the_refusal_not_an_error_dict(monkeypatch, sid, module, func, args, kwargs):
    """Seven of these ticks wrap their body in `try ... except Exception: return {"error": ...}`. The guard
    sits above the `try`, so the refusal raises and no tick reports a frozen campaign as an error dict."""
    _freeze(monkeypatch, sid)
    wire = _isolate(monkeypatch)
    a, k = _bind(args, kwargs, sid)
    result = None

    with pytest.raises(ooc.FrozenSession):
        result = await getattr(_module(module), func)(*a, **k)

    assert result is None
    assert wire.calls == []


# ── the guard comes before validation and early returns ──────────────────


async def test_consume_crew_refuses_before_its_negative_check(monkeypatch, sid):
    _freeze(monkeypatch, sid)
    _isolate(monkeypatch)
    from modules import crew_system

    with pytest.raises(ooc.FrozenSession):
        await crew_system.consume_crew(sid, 1, -1)


async def test_deduct_resources_refuses_before_its_unknown_resource_check(monkeypatch, sid):
    from modules import _economy

    _isolate(monkeypatch)
    _freeze(monkeypatch, sid)
    with pytest.raises(ooc.FrozenSession):
        await _economy._deduct_resources(sid, {"nonsense": 1})

    _freeze(monkeypatch)
    with pytest.raises(ValueError, match="cannot charge"):
        await _economy._deduct_resources(sid, {"nonsense": 1})


async def test_update_profile_refuses_before_its_type_check(monkeypatch, sid):
    _freeze(monkeypatch, sid)
    _isolate(monkeypatch)
    from modules import character_profile

    with pytest.raises(ooc.FrozenSession):
        await character_profile.update_profile(1, "not a mapping", sid)


# ── what a writer does when it may write ─────────────────────────────────


async def test_deduct_resources_charges_a_session_that_is_not_frozen(monkeypatch, sid):
    from modules import _economy

    _freeze(monkeypatch)
    db = _RecordingDB(fetchrow={"credits": 4})
    monkeypatch.setattr(_economy, "Database", db)

    assert await _economy._deduct_resources(sid, {"credits": 1}) == {"credits": 1}
    assert db.args[0][0] == sid


async def test_set_min_clearance_writes_the_session_it_resolved(monkeypatch, sid, other):
    from modules import crew_system

    _freeze(monkeypatch)
    monkeypatch.setenv("RP_SESSION", str(other))
    db = _RecordingDB()
    monkeypatch.setattr(crew_system, "Database", db)

    out = await crew_system.set_min_clearance(None, 7, 5)

    assert out == {"ship_id": 7, "min_clearance": 5}
    assert db.writes[0][1] == (5, 7, other)


async def test_create_fleet_writes_when_the_session_is_not_frozen(monkeypatch, sid):
    from modules import fleet

    _freeze(monkeypatch)
    db = _RecordingDB(fetchval=False)
    monkeypatch.setattr(fleet, "Database", db)

    assert await fleet.create_fleet("Alpha", session_id=sid) == {"fleet": "Alpha", "formation": "spearhead"}
    assert db.writes[0][1][0] == sid


# ── a reader stays open ──────────────────────────────────────────────────


@pytest.mark.parametrize("module,func,args,kwargs,want", READER_CASES, ids=[_id(c) for c in READER_CASES])
async def test_a_reader_still_returns_on_a_frozen_session(monkeypatch, sid, module, func, args, kwargs, want):
    _freeze(monkeypatch, sid)
    db = _ReadDB(fetchval=lambda: 0)
    monkeypatch.setattr(_module(module), "Database", db)
    a, k = _bind(args, kwargs, sid)

    out = await getattr(_module(module), func)(*a, **k)

    if func == "crew_report":
        assert out["crew_pool"] == 0 and out["shortage"] == 0
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

_MERCY = [{"action_category": "mercy", "t": 9}]


async def test_ideology_get_derives_without_writing_on_a_frozen_session(monkeypatch, sid):
    from modules import ideology

    _freeze(monkeypatch, sid)
    db = _ReadDB(fetchrow=None, fetch=_MERCY)
    monkeypatch.setattr(ideology, "Database", db)

    out = await ideology.get(sid)

    assert out["ideology"] == "benevolent_democracy"


async def test_ideology_get_prompt_reads_a_frozen_session_without_writing(monkeypatch, sid):
    from modules import ideology

    _freeze(monkeypatch, sid)
    db = _ReadDB(fetchrow=None, fetch=_MERCY)
    monkeypatch.setattr(ideology, "Database", db)

    assert "Benevolent Democracy" in await ideology.get_prompt(sid)


async def test_ideology_get_persists_the_derived_society_when_writes_are_allowed(monkeypatch, sid):
    from modules import ideology

    _freeze(monkeypatch)
    db = _RecordingDB(fetchrow=None, fetch=_MERCY)
    monkeypatch.setattr(ideology, "Database", db)

    out = await ideology.get(sid)

    assert out["ideology"] == "benevolent_democracy"
    assert len(db.writes) == 1
    assert "ideology_state" in db.writes[0][0] and db.writes[0][1][0] == sid


async def test_ideology_get_persists_in_a_frozen_session_under_maintenance(monkeypatch, sid):
    from modules import ideology

    _freeze(monkeypatch, sid)
    monkeypatch.setattr("core.ooc._maintenance_active", lambda: True)
    db = _RecordingDB(fetchrow=None, fetch=_MERCY)
    monkeypatch.setattr(ideology, "Database", db)

    await ideology.get(sid)

    assert len(db.writes) == 1


# ── _writes_allowed ──────────────────────────────────────────────────────


def test_writes_allowed_is_false_for_a_frozen_session_without_maintenance(monkeypatch):
    monkeypatch.setattr("core.session.is_frozen", lambda s: True)
    monkeypatch.setattr("core.ooc._maintenance_active", lambda: False)
    assert ooc._writes_allowed(901) is False


def test_writes_allowed_is_true_when_the_session_is_not_frozen(monkeypatch):
    monkeypatch.setattr("core.session.is_frozen", lambda s: False)
    monkeypatch.setattr("core.ooc._maintenance_active", lambda: False)
    assert ooc._writes_allowed(901) is True


def test_writes_allowed_is_true_for_a_frozen_session_under_maintenance(monkeypatch):
    monkeypatch.setattr("core.session.is_frozen", lambda s: True)
    monkeypatch.setattr("core.ooc._maintenance_active", lambda: True)
    assert ooc._writes_allowed(901) is True


def test_writes_allowed_is_false_when_the_frozen_list_is_unreadable(monkeypatch):
    from core import ooc
    from core.session import FrozenListUnreadable

    def boom(_sid):
        raise FrozenListUnreadable("unreadable")

    monkeypatch.setattr("core.session.is_frozen", boom)
    assert ooc._writes_allowed(901) is False
