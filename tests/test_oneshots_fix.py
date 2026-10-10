"""The nine one-shot scripts need `--session`, report by default, refuse a frozen session, and refuse a second run.

Every test passes a scratch id (900-999) and patches `Config.SESSION_ID` to it, so no default can reach
session 3 or 5. The only test that reaches the table-global DELETE in `rebuild_production` runs it
inside a transaction that is rolled back.
"""
from __future__ import annotations

import importlib
import pathlib
import re
import sys
from contextlib import asynccontextmanager, contextmanager

import pytest
import pytest_asyncio

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.config import Config  # noqa: E402
from core.db import Database  # noqa: E402
from tests.conftest import _clear_session_rows  # noqa: E402

NAMES = ["rebuild_production", "seed_species_pop", "materialize_legio", "materialize_legio_full",
         "east_judgment", "seed_complaints", "fleet_expansion", "seed_decision_provenance",
         "generate_slave_names"]

#: The flag that turns a dry run into a write. `fleet_expansion` keeps its old `--commit`.
FLAG = {name: ("--commit" if name == "fleet_expansion" else "--apply") for name in NAMES}

#: Child rows first. `combat_stats` has no cascade, so it goes before `ships`.
_OWNED = ("fleets", "ships", "build_queue", "resources", "complaints", "complaint_boxes", "territory",
          "prisoners", "cabinet_decrees", "slaves", "events")

_WRITE = re.compile(r"\s*(?:INSERT|UPDATE|DELETE)\b", re.I)


def _script(name: str):
    return importlib.import_module(f"scripts.{name}")


async def _wipe(sid: int) -> None:
    await Database.init()
    ships = "SELECT id FROM maya_rp.ships WHERE session_id = $1"
    await Database.execute(f"DELETE FROM maya_rp.combat_stats WHERE ship_id IN ({ships})", sid)
    await Database.execute(
        "DELETE FROM maya_rp.fleet_members WHERE fleet_id IN"
        " (SELECT id FROM maya_rp.fleets WHERE session_id = $1)"
        f" OR ship_id IN ({ships})", sid)
    for table in _OWNED:
        await Database.execute(f"DELETE FROM maya_rp.{table} WHERE session_id = $1", sid)
    await _clear_session_rows(sid)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", sid)


@pytest_asyncio.fixture
async def sid(scratch_session, monkeypatch):
    """A scratch campaign at day 10. `Config.SESSION_ID` points at it, so no default reaches a live arc."""
    await _wipe(scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status, game_day) VALUES ($1, 'oneshots scratch', 'active', 10)",
        scratch_session)
    monkeypatch.setattr(Config, "SESSION_ID", scratch_session)
    yield scratch_session
    await _wipe(scratch_session)
    await Database.close()


def _freeze(monkeypatch, frozen_ids):
    monkeypatch.setattr("core.session.frozen", lambda: set(frozen_ids))
    monkeypatch.setattr("core.ooc._maintenance_active", lambda: False)


@contextmanager
def _no_writes(message: str):
    """Make every write raise `AssertionError(message)` inside the block.

    Covers `Database.execute`, `Database.transaction`, and a write sent through `fetch`, `fetchrow` or
    `fetchval`. The patch ends with the block, so the fixture teardown can still clean up.
    """
    def boom(*args, **kwargs):
        raise AssertionError(message)

    def reads_only(real):
        async def checked(sql, *args, **kwargs):
            if _WRITE.match(sql):
                raise AssertionError(message)
            return await real(sql, *args, **kwargs)

        return checked

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Database, "execute", boom)
        patch.setattr(Database, "transaction", boom)
        for name in ("fetch", "fetchrow", "fetchval"):
            patch.setattr(Database, name, reads_only(getattr(Database, name)))
        yield


def _argv(sid: int, *rest: str) -> list[str]:
    return ["--session", str(sid), *rest]


async def _count(sql: str, *args) -> int:
    await Database.init()
    return int(await Database.fetchval(sql, *args))


# ── the shared front end ─────────────────────────────────────────────────────────────────────────────────

def test_parse_requires_a_session():
    from scripts._oneshot import parse

    with pytest.raises(SystemExit) as raised:
        parse("d", [])
    assert raised.value.code == 2


def test_parse_defaults_to_a_dry_run():
    from scripts._oneshot import parse

    assert parse("d", ["--session", "900"]).apply is False
    assert parse("d", ["--session", "900", "--apply"]).apply is True
    assert parse("d", ["--session", "900", "--commit"], write_flag="--commit").apply is True


def test_guard_refuses_a_frozen_session(monkeypatch):
    from core.ooc import FrozenSession
    from scripts._oneshot import guard, parse

    _freeze(monkeypatch, {900})
    with pytest.raises(FrozenSession):
        guard(parse("d", ["--session", "900", "--apply"]))
    guard(parse("d", ["--session", "900"]))


def test_no_script_falls_back_to_a_default_session():
    for name in NAMES:
        source = (ROOT / "scripts" / f"{name}.py").read_text()
        assert "Config.SESSION_ID" not in source, name
        assert not re.search(r"^(?:SID|SESSION)\s*=\s*(?:\d|Config)", source, re.M), name


# ── all nine scripts ─────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", NAMES)
async def test_session_is_required(name):
    with pytest.raises(SystemExit) as raised:
        await _script(name).main([])
    assert raised.value.code == 2


@pytest.mark.parametrize("name", NAMES)
async def test_a_frozen_session_is_refused_on_write(name, sid, monkeypatch):
    from core.ooc import FrozenSession

    mod = _script(name)
    _freeze(monkeypatch, {sid})
    with _no_writes("write before the guard"), pytest.raises(FrozenSession):
        await mod.main(_argv(sid, FLAG[name]))


@pytest.mark.parametrize("name", NAMES)
async def test_a_dry_run_writes_nothing(name, sid):
    mod = _script(name)
    rest = ["--count", "5"] if name == "generate_slave_names" else []
    with _no_writes("a dry run wrote"):
        await mod.main(_argv(sid, *rest))


# ── idempotency and shape ────────────────────────────────────────────────────────────────────────────────

async def test_east_judgment_writes_once(sid, capsys):
    mod = _script("east_judgment")
    sql = ("SELECT count(*) FROM maya_rp.prisoners"
           " WHERE session_id = $1 AND captured_from_ship = 'eastern_cleanup'")
    assert await mod.main(_argv(sid, "--apply")) == 0
    assert await _count(sql, sid) == 1142
    capsys.readouterr()
    assert await mod.main(_argv(sid, "--apply")) == 1
    assert "REFUSED" in capsys.readouterr().out
    assert await _count(sql, sid) == 1142


async def test_seed_complaints_writes_once(sid, capsys):
    mod = _script("seed_complaints")
    await Database.init()
    territory = await Database.fetchval(
        "INSERT INTO maya_rp.territory (session_id, system_name, controlling_faction)"
        " VALUES ($1, 'Scratch Prime', 'Setia Empire') RETURNING id", sid)
    await Database.execute(
        "INSERT INTO maya_rp.complaint_boxes (session_id, territory_id) VALUES ($1, $2)", sid, territory)
    sql = "SELECT count(*) FROM maya_rp.complaints WHERE session_id = $1"
    args = _argv(sid, "--apply", "--count", "5")
    assert await mod.main(args) == 0
    assert await _count(sql, sid) == 5
    capsys.readouterr()
    assert await mod.main(args) == 1
    assert "REFUSED" in capsys.readouterr().out
    assert await _count(sql, sid) == 5


async def _legion(sid: int, name: str, members: int) -> int:
    await Database.init()
    fleet = await Database.fetchval(
        "INSERT INTO maya_rp.fleets (session_id, name) VALUES ($1, $2) RETURNING id", sid, name)
    for index in range(members):
        ship = await Database.fetchval(
            "INSERT INTO maya_rp.ships (session_id, name) VALUES ($1, $2) RETURNING id",
            sid, f"scratch hull {index}")
        await Database.execute(
            "INSERT INTO maya_rp.fleet_members (fleet_id, ship_id) VALUES ($1, $2)", fleet, ship)
    return fleet


def _no_ships(monkeypatch, mod):
    async def boom(*args, **kwargs):
        raise AssertionError("a filled legion rolled a ship")

    monkeypatch.setattr(mod, "generate_ship", boom)


async def test_materialize_legio_skips_a_filled_legion(sid, monkeypatch):
    mod = _script("materialize_legio")
    await _legion(sid, "Legio I", 1)
    _no_ships(monkeypatch, mod)
    assert await mod.main(_argv(sid, "--apply")) == 0
    assert await _count("SELECT count(*) FROM maya_rp.ships WHERE session_id = $1", sid) == 1
    events = "SELECT count(*) FROM maya_rp.events WHERE session_id = $1 AND event_type = 'legion_deploy'"
    assert await _count(events, sid) == 0


async def test_materialize_legio_scopes_the_cancel_to_the_session(sid, monkeypatch):
    mod = _script("materialize_legio")
    seen: list[tuple] = []
    real = Database.execute

    async def record(sql, *args):
        seen.append((sql, args))
        return await real(sql, *args)

    monkeypatch.setattr(Database, "execute", record)
    assert await mod.main(_argv(sid, "--apply")) == 0
    cancels = [(sql, args) for sql, args in seen if "UPDATE maya_rp.build_queue" in sql]
    assert cancels, "the cancel of builds 82-85 did not run"
    assert all("session_id=$1" in sql and args == (sid,) for sql, args in cancels)


async def test_materialize_legio_full_skips_a_filled_legion(sid, monkeypatch):
    mod = _script("materialize_legio_full")
    monkeypatch.setattr(mod, "TARGET", 1)
    await _legion(sid, "Legio I", 1)
    _no_ships(monkeypatch, mod)
    assert await mod.main(_argv(sid, "--apply")) == 0
    assert await _count("SELECT count(*) FROM maya_rp.ships WHERE session_id = $1", sid) == 1


async def test_materialize_legio_full_creates_only_the_shortfall(sid, monkeypatch):
    mod = _script("materialize_legio_full")
    monkeypatch.setattr(mod, "TARGET", 3)
    fleet = await _legion(sid, "Legio I", 1)
    rolled: list[tuple] = []

    async def fake_ship(class_name, tier, ship_type, name, session_id):
        rolled.append((tier, ship_type, name, session_id))
        return {"class_id": None, "ship_type": ship_type, "mass": 1, "length_m": 1, "hull": 10,
                "speed": 30, "crew": 2, "armaments": [], "modules": []}

    monkeypatch.setattr(mod, "generate_ship", fake_ship)
    events = "SELECT count(*) FROM maya_rp.events WHERE session_id = $1 AND event_type = 'legion_deploy'"
    members = "SELECT count(*) FROM maya_rp.fleet_members WHERE fleet_id = $1"

    assert await mod.main(_argv(sid, "--apply")) == 0
    assert rolled == [(5, "battle_cruiser", "TKG Legio I-0002", sid),
                      (5, "battle_cruiser", "TKG Legio I-0003", sid)]
    assert await _count(members, fleet) == 3
    assert await _count(events, sid) == 1

    assert await mod.main(_argv(sid, "--apply")) == 0
    assert len(rolled) == 2
    assert await _count(members, fleet) == 3
    assert await _count(events, sid) == 1


async def _treasury(sid: int, credits=10**12, alloys=10**9, crew_pool=10**6) -> None:
    await Database.init()
    await Database.execute(
        "INSERT INTO maya_rp.resources (session_id, credits, alloys, crew_pool) VALUES ($1, $2, $3, $4)",
        sid, credits, alloys, crew_pool)


async def test_fleet_expansion_queues_once(sid):
    mod = _script("fleet_expansion")
    await _treasury(sid)
    await _legion(sid, "Legion Test", 0)
    args = _argv(sid, "--commit", "--legion", "Legion Test")
    ledger = "SELECT credits, alloys, crew_pool FROM maya_rp.resources WHERE session_id = $1"
    queue = "SELECT count(*) FROM maya_rp.build_queue WHERE session_id = $1"
    events = ("SELECT count(*) FROM maya_rp.events"
              " WHERE session_id = $1 AND title = 'FLEET EXPANSION WORKFLOW executed'")

    await mod.main(args)
    await Database.init()
    first = dict(await Database.fetchrow(ledger, sid))
    assert await _count(queue, sid) == 1
    assert first["credits"] < 10**12 and first["crew_pool"] < 10**6

    await mod.main(args)
    await Database.init()
    assert await _count(queue, sid) == 1
    assert dict(await Database.fetchrow(ledger, sid)) == first
    assert await _count(events, sid) == 1


async def test_fleet_expansion_charge_and_queue_commit_together(sid, monkeypatch, capsys):
    """A crew shortfall found after the credits were charged rolls the charge back and queues nothing."""
    mod = _script("fleet_expansion")
    await _treasury(sid)
    await _legion(sid, "Legion Test", 0)
    real = mod._deduct_resources

    async def charge_then_lose_the_crew(session_id, costs, conn=None):
        charged = await real(session_id, costs, conn=conn)
        await conn.execute("UPDATE maya_rp.resources SET crew_pool = 0 WHERE session_id = $1", session_id)
        return charged

    monkeypatch.setattr(mod, "_deduct_resources", charge_then_lose_the_crew)
    await mod.main(_argv(sid, "--commit", "--legion", "Legion Test"))
    assert "ABORT Legion Test" in capsys.readouterr().out
    await Database.init()
    row = await Database.fetchrow(
        "SELECT credits, alloys, crew_pool FROM maya_rp.resources WHERE session_id = $1", sid)
    assert dict(row) == {"credits": 10**12, "alloys": 10**9, "crew_pool": 10**6}
    assert await _count("SELECT count(*) FROM maya_rp.build_queue WHERE session_id = $1", sid) == 0


async def test_seed_decision_provenance_inserts_each_decree_once(sid, capsys):
    mod = _script("seed_decision_provenance")
    args = _argv(sid, "--apply")
    sql = "SELECT count(*) FROM maya_rp.cabinet_decrees WHERE session_id = $1 AND title = $2"
    await mod.main(args)
    assert f"WARN decree 19 not found in session {sid}" in capsys.readouterr().out
    await mod.main(args)
    assert await _count(sql, sid, "RS-2 P1+P3 SIGNED") == 1
    assert await _count(sql, sid, "RS-2 P2 + MINISTRY TRACKS SIGNED") == 1
    child = await Database.fetchrow(
        "SELECT child.parent_id AS parent, root.id AS root FROM maya_rp.cabinet_decrees child"
        " JOIN maya_rp.cabinet_decrees root ON root.session_id = child.session_id"
        " AND root.title = 'RS-2 P1+P3 SIGNED'"
        " WHERE child.session_id = $1 AND child.title = 'RS-2 P2 + MINISTRY TRACKS SIGNED'", sid)
    assert child["parent"] == child["root"]


async def test_rebuild_production_refuses_a_session_without_territory(sid, capsys):
    mod = _script("rebuild_production")
    count = "SELECT count(*) FROM maya_rp.resource_production"
    before = await _count(count)
    with _no_writes("the refusal must come before any write"):
        assert await mod.main(_argv(sid, "--apply")) == 1
    assert "REFUSED" in capsys.readouterr().out
    assert await _count(count) == before


async def test_rebuild_production_apply_rolls_back(sid, monkeypatch):
    """The DELETE and the INSERTs run in a transaction that never commits."""
    mod = _script("rebuild_production")
    count = "SELECT count(*) FROM maya_rp.resource_production"
    taxes = ("SELECT count(*) FROM maya_rp.resource_production"
             " WHERE (source ILIKE '%Tax Revenue%' OR source ILIKE '%Collective Tax%')")
    await Database.init()
    before = await _count(count)
    others = await _count(f"{taxes} AND session_id <> $1", sid)
    assert others > 0, "no other campaign holds a tax row, so the scoping claim has nothing to test"
    await Database.execute(
        "INSERT INTO maya_rp.territory (session_id, system_name, controlling_faction, population, tax_rate)"
        " VALUES ($1, 'Scratch Prime', 'Setia Empire', 5000000, 0.05)", sid)
    pool = await Database._ensure_pool()
    conn = await pool.acquire()
    tx = conn.transaction()
    await tx.start()

    @asynccontextmanager
    async def sandbox():
        yield conn

    async def keep_open():
        return None

    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(Database, "transaction", sandbox)
            patch.setattr(Database, "close", keep_open)
            assert await mod.main(_argv(sid, "--apply")) == 0
        mine = await conn.fetch(
            "SELECT source FROM maya_rp.resource_production WHERE session_id = $1", sid)
        assert [row["source"] for row in mine] == ["Scratch Prime — Tax Revenue"]
        # The DELETE names the session: every other campaign's tax row survives it.
        assert int(await conn.fetchval(f"{taxes} AND session_id <> $1", sid)) == others
    finally:
        await tx.rollback()
        await pool.release(conn)
    assert await _count(count) == before


async def test_seed_species_pop_replaces_the_session_rows(sid):
    mod = _script("seed_species_pop")
    await Database.init()
    territory = await Database.fetchval(
        "INSERT INTO maya_rp.territory (session_id, system_name, controlling_faction)"
        " VALUES ($1, 'Scratch Prime', 'Setia Empire') RETURNING id", sid)
    planet = await Database.fetchval(
        "INSERT INTO maya_rp.planets (session_id, name, territory_id, population)"
        " VALUES ($1, 'Scratch I', $2, 1000000) RETURNING id", sid, territory)
    await Database.execute(
        "INSERT INTO maya_rp.planet_population (session_id, planet_id, species_name, count)"
        " VALUES ($1, $2, 'stale', 1)", sid, planet)
    names = "SELECT species_name FROM maya_rp.planet_population WHERE session_id = $1"

    assert await mod.main(_argv(sid, "--apply")) == 0
    await Database.init()
    first = sorted(row["species_name"] for row in await Database.fetch(names, sid))
    assert "stale" not in first and len(first) >= 2
    dominant = "SELECT count(*) FROM maya_rp.planet_population WHERE session_id = $1 AND dominant"
    assert await _count(dominant, sid) == 1

    assert await mod.main(_argv(sid, "--apply")) == 0
    await Database.init()
    assert sorted(row["species_name"] for row in await Database.fetch(names, sid)) == first


async def test_generate_slave_names_fills_a_lot_once(sid):
    mod = _script("generate_slave_names")
    sql = "SELECT count(*) FROM maya_rp.slaves WHERE session_id = $1 AND assigned_to = 'Marlon Bregg — lot 890'"
    args = _argv(sid, "--count", "3", "--apply")
    assert await mod.main(args) == 0
    assert await _count(sql, sid) == 3
    assert await mod.main(args) == 0
    assert await _count(sql, sid) == 3
