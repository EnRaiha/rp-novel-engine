"""Research gate: the four catalogues name a `research_projects` row, and one helper says why a gate is shut.

Defects measured here:

1. The four catalogues held snake_case slugs (`asteroid_tech`) while `research_projects.name` holds
   display names (`Extraction Automation`), so every gated row was refused before it charged.
2. A missing project and a locked project returned the same text, which hid defect 1.

The live database is read only. The migration text runs inside a transaction this file rolls back, so
no rename, no constraint and no catalogue row survives a run. Sessions 3 and 5 are never written.

The runner applies the migration as `maya`, the owner of every table it touches. The suite connects as
`rp_engine`, which holds UPDATE but not ownership, so the `ALTER TABLE` block of the migration runs
here against a scratch copy of the table. `test_the_unique_name_constraint_refuses_a_duplicate` says
which block and why; `test_the_migration_adds_the_constraint_to_the_live_table` pins its live text.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
from asyncpg.exceptions import PostgresError, UniqueViolationError  # noqa: E402

from core.db import Database  # noqa: E402
from modules import infrastructure as infra  # noqa: E402
from modules import megastructures_ports as mp  # noqa: E402
from modules import space_horror as sh  # noqa: E402

MIGRATION = ROOT / "migrations" / "140_research_gate_names.sql"

#: The catalogues that gate a build, and the column that holds the gate value.
GATE_COLUMNS = (
    ("megastructure_types", "research_required"),
    ("containment_measures", "research_required"),
    ("bug_war_assets", "research_required"),
    ("infrastructure_types", "required_tech"),
)

#: One live gated row per catalogue, named by the value its column holds today.
HARVESTER = 3               # infrastructure_types: required_tech = 'asteroid_tech'
DYSON = 1                   # megastructure_types: research_required = 'dyson_tech'
FLAME_WALL = "Flame Wall"   # containment_measures: research_required = 'plasma_tech'

SLUG = "asteroid_tech"          # what the catalogues hold today
PROJECT = "Extraction Automation"   # its project, unlocked
LOCKED = "Plasma Cannons"           # a live project, unlocked = false

CATALOGUE_MISS = 'Catalogue names research "{}" but no such project exists.'
LOCKED_ERROR = 'Research "{}" is locked.'


# ── stand-ins ────────────────────────────────────────────────────────────────


class _Tx:
    """`Database.transaction()` as the call sites use it: the same answers on the connection."""

    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *exc):
        return False


class _GateDatabase:
    """A pool stand-in for one gated call: `rows` answers a statement by a needle in its SQL.

    The `research_projects` lookup is answered from `catalogue`, keyed by project name, so the string
    the call site compares is the string under test. A name the catalogue lacks returns None, which is
    what the live query returns for a slug.
    """

    def __init__(self, rows, catalogue):
        self.rows = rows
        self.catalogue = catalogue
        self.asked = []
        self.written = []

    async def fetchrow(self, sql, *args):
        if "research_projects" in sql:
            self.asked.append(args[0])
            if args[0] in self.catalogue:
                return {"unlocked": self.catalogue[args[0]]}
            return None
        if "FOR UPDATE" in sql:
            # `start_construction` holds its campaign row for the whole build.
            return {"locked": 1}
        if "AS site_id" in sql:
            # No site of this type yet, so the duplicate guard opens.
            return None
        for needle, row in self.rows.items():
            if needle in sql:
                return dict(row)
        raise AssertionError(f"unexpected fetchrow: {sql}")

    async def fetch(self, sql, *args):
        return []

    async def fetchval(self, sql, *args):
        return None

    async def execute(self, sql, *args):
        self.written.append(sql)
        return "UPDATE 1"

    def transaction(self):
        return _Tx(self)


class _FakeConn:
    """A connection that answers one research lookup and records what it was asked."""

    def __init__(self, row):
        self.row = row
        self.asked = []

    async def fetchrow(self, sql, *args):
        self.asked.append((sql, args))
        return self.row


def _infra_db(required_tech, catalogue):
    return _GateDatabase(
        rows={
            "infrastructure_types": {
                "id": HARVESTER, "name": "Asteroid Harvester", "category": "mining",
                "required_tech": required_tech, "build_cost_credits": 50000,
                "build_cost_resources": None},
            "INSERT INTO maya_rp.infrastructure_instances": {"id": 1},
        },
        catalogue=catalogue)


def _mega_db(research_required, catalogue):
    return _GateDatabase(
        rows={
            "megastructure_types": {
                "id": DYSON, "name": "Dyson Sphere", "research_required": research_required,
                "construction_phases": [{"phase": 1, "cost": {"alloys": 100}, "time_days": 365}]},
            "INSERT INTO maya_rp.megastructure_construction": {"id": 7},
        },
        catalogue=catalogue)


def _horror_db(research_required, catalogue):
    return _GateDatabase(
        rows={
            "infestation_instances": {"id": 7, "containment_level": 0, "status": "active"},
            "containment_measures": {
                "id": 4, "name": FLAME_WALL, "research_required": research_required,
                "effectiveness": 0.5, "cost_credits": 1000, "cost_resources": None},
        },
        catalogue=catalogue)


def _recorder(charges):
    """A `_deduct_resources` that records the charge and returns it."""

    async def record(session_id, cost, conn=None):
        charges.append((session_id, dict(cost)))
        return dict(cost)

    return record


# ── the helper ───────────────────────────────────────────────────────────────


async def test_no_requirement_is_no_gate():
    import core.research_gate

    conn = _FakeConn({"unlocked": False})

    assert await core.research_gate.check_gate(None, conn) is None
    assert await core.research_gate.check_gate("", conn) is None
    assert conn.asked == [], "an empty requirement still queried the catalogue"


async def test_a_name_no_project_carries_is_a_catalogue_miss():
    import core.research_gate

    conn = _FakeConn(None)

    assert await core.research_gate.check_gate(SLUG, conn) == CATALOGUE_MISS.format(SLUG)
    assert conn.asked[0][1] == (SLUG,), conn.asked


async def test_a_locked_project_is_locked():
    import core.research_gate

    assert await core.research_gate.check_gate(LOCKED, _FakeConn({"unlocked": False})) == \
        LOCKED_ERROR.format(LOCKED)


async def test_an_unlocked_project_opens():
    import core.research_gate

    assert await core.research_gate.check_gate(PROJECT, _FakeConn({"unlocked": True})) is None


# ── the three call sites ─────────────────────────────────────────────────────


async def test_a_build_refuses_a_catalogue_that_holds_a_slug(monkeypatch):
    """The live catalogue holds `asteroid_tech`, so this gated row is refused before it charges.

    The unfixed call site answered `Research "asteroid_tech" required.` here: it compared a slug to
    the display names in `research_projects` and blamed a lock that does not exist, which is the
    defect that hid itself. Migration 140 turns this value into `Extraction Automation`, and
    the next test builds the same row.
    """
    monkeypatch.setattr(infra, "Database", _infra_db(SLUG, {PROJECT: True}))
    charges = []
    monkeypatch.setattr(infra, "_deduct_resources", _recorder(charges))

    out = await infra.build_infrastructure(905, HARVESTER)

    assert out == {"error": CATALOGUE_MISS.format(SLUG)}, out
    assert charges == [], "a refused gate still charged the treasury"

    # The fixed call site routes the refusal through the shared helper. Imported here, not at module
    # scope, so a tree without the helper still reports the assertion above, not a missing import.
    import core.research_gate
    assert await core.research_gate.check_gate(SLUG, infra.Database) == out["error"]


async def test_start_construction_refuses_a_catalogue_that_holds_a_slug(monkeypatch):
    """`dyson_tech` names no project, so the site is refused and nothing is charged."""
    monkeypatch.setattr(mp, "Database", _mega_db("dyson_tech", {PROJECT: True}))
    charges = []
    monkeypatch.setattr(mp, "_deduct_resources", _recorder(charges))

    out = await mp.start_construction(905, DYSON)

    assert out == {"error": CATALOGUE_MISS.format("dyson_tech")}, out
    assert charges == [], "a refused gate still charged the treasury"


async def test_apply_containment_refuses_a_catalogue_that_holds_a_slug(monkeypatch):
    """`plasma_tech` names no project, so the measure is refused and nothing is charged."""
    monkeypatch.setattr(sh, "Database", _horror_db("plasma_tech", {PROJECT: True}))
    charges = []
    monkeypatch.setattr(sh, "_deduct_resources", _recorder(charges))

    out = await sh.apply_containment(905, 7, FLAME_WALL)

    assert out == {"error": CATALOGUE_MISS.format("plasma_tech")}, out
    assert charges == [], "a refused gate still charged the treasury"


async def test_a_locked_project_refuses_the_build(monkeypatch):
    """A project that exists and is locked says so, which the old text did not."""
    monkeypatch.setattr(infra, "Database", _infra_db(LOCKED, {LOCKED: False}))
    charges = []
    monkeypatch.setattr(infra, "_deduct_resources", _recorder(charges))

    out = await infra.build_infrastructure(905, HARVESTER)

    assert out == {"error": LOCKED_ERROR.format(LOCKED)}, out
    assert charges == [], "a locked gate still charged the treasury"


async def test_a_build_opens_once_the_catalogue_names_its_project(monkeypatch):
    """The post-migration row: the column holds `Extraction Automation` and the build charges once."""
    db = _infra_db(PROJECT, {PROJECT: True})
    monkeypatch.setattr(infra, "Database", db)
    charges = []
    monkeypatch.setattr(infra, "_deduct_resources", _recorder(charges))

    out = await infra.build_infrastructure(905, HARVESTER, name="Harvester One")

    assert "error" not in out, out
    assert db.asked == [PROJECT], db.asked
    assert charges == [(905, {"credits": 50000})], charges
    assert out["infrastructure_id"] == 1


async def test_start_construction_opens_once_the_catalogue_names_its_project(monkeypatch):
    """A megastructure row passes the gate when its column holds the project name."""
    db = _mega_db("Fusion Reactor Design", {"Fusion Reactor Design": True})
    monkeypatch.setattr(mp, "Database", db)
    charges = []
    monkeypatch.setattr(mp, "_deduct_resources", _recorder(charges))

    async def afford(*_args, **_kwargs):
        return True, ""

    async def logged(*_args, **_kwargs):
        return None

    monkeypatch.setattr(mp, "_check_afford", afford)
    monkeypatch.setattr(mp, "_log", logged)

    out = await mp.start_construction(905, DYSON)

    assert "error" not in out, out
    assert db.asked == ["Fusion Reactor Design"], db.asked
    assert charges == [(905, {"alloys": 100})], charges


# ── the migration, dry run ───────────────────────────────────────────────────


OWNER_ONLY_BEGIN = "-- owner-only begin"
OWNER_ONLY_END = "-- owner-only end"

#: The statement the runner applies as the table owner, and the test asserts by its text.
CONSTRAINT = ("ALTER TABLE maya_rp.research_projects ADD CONSTRAINT"
              " research_projects_name_key UNIQUE (name)")


def _marker_lines(lines, opening, closing) -> list[int]:
    """The line numbers strictly between one marker pair."""
    starts = [i for i, line in enumerate(lines) if line == opening]
    ends = [i for i, line in enumerate(lines) if line == closing]
    assert len(starts) == 1 and len(ends) == 1, f"{opening}: {len(starts)} opens, {len(ends)} closes"
    assert starts[0] < ends[0], f"{closing} precedes {opening}"
    return list(range(starts[0] + 1, ends[0]))


def _transaction_lines() -> list[str]:
    """The migration lines between its own `BEGIN;` and `COMMIT;`."""
    lines = MIGRATION.read_text().splitlines()
    opens = [i for i, line in enumerate(lines) if line == "BEGIN;"]
    closes = [i for i, line in enumerate(lines) if line == "COMMIT;"]
    assert len(opens) == 1 and len(closes) == 1, (
        f"the migration must open and close exactly one transaction:"
        f" {len(opens)} opens, {len(closes)} closes")
    assert opens[0] < closes[0], "the migration closes its transaction before it opens it"
    return lines[opens[0] + 1:closes[0]]


def _migration_body() -> str:
    """The migration statements, without the outer transaction and without the owner-only block.

    The dry run owns the transaction and rolls it back, so `_transaction_lines` strips the file's
    closing statement: that statement commits the renames onto the live catalogue.

    `ALTER TABLE ... ADD CONSTRAINT` needs the table owner. The suite connects as `rp_engine`, which
    holds UPDATE on the table but not ownership, so step 5 sits between two markers and
    `_owner_only_sql` runs it against a scratch copy.
    """
    lines = _transaction_lines()
    owner_only = set(_marker_lines(lines, OWNER_ONLY_BEGIN, OWNER_ONLY_END))
    return "\n".join(line for index, line in enumerate(lines) if index not in owner_only)


def _owner_only_sql() -> str:
    """The file's unique-name block, retargeted at a scratch copy of `research_projects`."""
    lines = _transaction_lines()
    block = "\n".join(lines[i] for i in _marker_lines(lines, OWNER_ONLY_BEGIN, OWNER_ONLY_END))
    retargeted = (
        block.replace("'maya_rp.research_projects'::regclass", "'pg_temp._gate_names'::regclass")
             .replace("ALTER TABLE maya_rp.research_projects", "ALTER TABLE pg_temp._gate_names"))
    assert "maya_rp.research_projects" not in retargeted, "a live table reference stayed in the block"
    return retargeted


async def _dry_run_migration(check) -> None:
    """Apply the migration text on a scratch connection, run `check(conn)`, then roll back.

    No rename, no constraint and no catalogue row survives: the transaction is opened and rolled back
    here, on the pool connection, and the file's own COMMIT is removed by `_migration_body`.
    """
    pool = await Database.init()
    conn = await pool.acquire()
    try:
        await conn.execute("BEGIN")
        await conn.execute(_migration_body())
        await check(conn)
    finally:
        await conn.execute("ROLLBACK")
        await pool.release(conn)


async def _gate_values(conn) -> dict:
    """Every distinct non-empty gate value per catalogue, as the gate columns hold them now."""
    values = {}
    for table, column in GATE_COLUMNS:
        rows = await conn.fetch(
            f"SELECT DISTINCT {column} AS v FROM maya_rp.{table}"
            f" WHERE {column} IS NOT NULL AND {column} <> ''")
        values[table] = sorted(row["v"] for row in rows)
    return values


async def test_every_gate_value_names_exactly_one_project_after_the_migration():
    """Red before migration 140: the four catalogues hold 36 slugs that name no project row."""
    async def check(conn):
        values = await _gate_values(conn)
        for table, column in GATE_COLUMNS:
            for value in values[table]:
                count = await conn.fetchval(
                    "SELECT count(*) FROM maya_rp.research_projects WHERE name = $1", value)
                assert count == 1, f"{table}.{column} = {value!r} names {count} research projects"

    await _dry_run_migration(check)


async def test_the_rename_removes_the_only_duplicate_name():
    """Ids 9 and 27 were both `Hyperdrive Calibration`; the newer row takes the disambiguated name."""
    async def check(conn):
        rows = await conn.fetch(
            "SELECT id, name FROM maya_rp.research_projects"
            " WHERE name IN ('Hyperdrive Calibration', 'Hyperdrive Calibration II') ORDER BY id")
        assert [dict(row) for row in rows] == [
            {"id": 9, "name": "Hyperdrive Calibration"},
            {"id": 27, "name": "Hyperdrive Calibration II"}], [dict(row) for row in rows]

    await _dry_run_migration(check)


async def test_the_migration_refuses_a_catalogue_with_a_duplicate_name():
    """Step 4 stops the file when two rows share a name that no map row references."""
    async def check(conn):
        try:
            await conn.execute(
                "UPDATE maya_rp.research_projects SET name ="
                " (SELECT name FROM maya_rp.research_projects WHERE id = 60) WHERE id = 61")
        except PostgresError as exc:
            # Once 140 is applied its own unique constraint refuses the duplicate at the update,
            # which is the guarantee step 5 adds. Before the apply the file's step 4 must catch it.
            assert "research_projects_name_key" in str(exc), exc
            return
        with pytest.raises(PostgresError) as raised:
            await conn.execute(_migration_body())
        assert "duplicate project names remain" in str(raised.value), raised.value

    await _dry_run_migration(check)


async def test_the_unique_name_constraint_refuses_a_duplicate():
    """The file's step 5 against a scratch copy of the table.

    The suite's role holds UPDATE on `research_projects` but is not its owner, so the block cannot
    touch the live table here. Both table references move to the copy; the rest is the file's text,
    so the guard and the constraint are the ones the runner applies.
    """
    async def check(conn):
        await conn.execute("CREATE TEMP TABLE _gate_names (LIKE maya_rp.research_projects)")
        block = _owner_only_sql()
        await conn.execute(block)
        await conn.execute(block)      # the pg_constraint guard: a second run adds nothing
        insert = ("INSERT INTO pg_temp._gate_names"
                  " (id, name, cost_credits, cost_research_points, duration_days)"
                  " VALUES ($1, 'Aetheric Theory', 0, 0, 1)")
        await conn.execute(insert, 1)
        with pytest.raises(UniqueViolationError):
            await conn.execute(insert, 2)

    await _dry_run_migration(check)


def test_the_migration_adds_the_constraint_to_the_live_table():
    """The owner-only block keeps the live table and the live constraint name."""
    text = MIGRATION.read_text()
    assert CONSTRAINT in text, CONSTRAINT
    assert "IF NOT EXISTS (SELECT 1 FROM pg_constraint" in text
    assert "conname = 'research_projects_name_key'" in text


async def test_the_migration_leaves_the_ungated_rows_alone():
    """Six `infrastructure_types` rows hold `''`; the code reads that as no gate, so it stays."""
    pool = await Database.init()
    before = await pool.fetchval(
        "SELECT count(*) FROM maya_rp.infrastructure_types WHERE required_tech = ''")

    async def check(conn):
        after = await conn.fetchval(
            "SELECT count(*) FROM maya_rp.infrastructure_types WHERE required_tech = ''")
        assert after == before, f"the migration changed the ungated rows: {before} -> {after}"

    await _dry_run_migration(check)


async def test_the_migration_runs_twice():
    """The second run matches no slug, re-inserts nothing and rewrites no gate value."""
    async def check(conn):
        before = await _gate_values(conn)
        await conn.execute(_migration_body())
        after = await _gate_values(conn)
        assert after == before, f"the second run rewrote a gate value: {before} -> {after}"

    await _dry_run_migration(check)
