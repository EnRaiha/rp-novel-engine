"""Novel binding: the class registry, the two migrations, and `session.novel_of`.

Reads `maya_rp` through `core.db.Database` and writes no live row. The two migration dry runs create
an empty `pg_temp` copy of every table the file names, point the file's search path at that copy,
execute the file's statements there twice, and roll the whole transaction back. A live table is
unreachable under that path, so the dry run proves the file runs and re-runs without applying it.

The suite connects as `rp_engine`, which owns none of these tables. `ALTER TABLE` needs the owner,
so the copies are the only way a test can execute the file's DDL at all. `tests/test_research_gate.py`
sets the precedent for a retargeted dry run.
"""
from __future__ import annotations

import pathlib
import re

import pytest
from asyncpg.exceptions import PostgresError

from core import binding, config, session
from core.db import Database

ROOT = pathlib.Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations"
MIGRATION_137 = MIGRATIONS / "137_novels.sql"
MIGRATION_138 = MIGRATIONS / "138_bind_state.sql"
MIGRATION_139 = MIGRATIONS / "139_population_sentiment_unique.sql"

#: The four novels 137 inserts, keyed by `novel_id`:
#: (title, universe, adventures_dir, status, supersedes, story_order).
NOVELS = {
    "tkg-prequel": ("TKG Prequel", "TKG", "adventures/tkg/novel", "superseded", None, 0),
    "tkg-the-sunrise": ("TKG — Arc I: The Sunrise", "TKG", "adventures/tkg-arc1-restart",
                        "active", "tkg-prequel", 0),
    "tkg-setia-kingdom": ("TKG Setia Kingdom", "TKG", "adventures/tkg", "active", None, 1),
    "scratch": ("Scratch", "TKG", None, "active", None, None),
}

#: Which session is canon for which novel.
SESSION_NOVELS = {3: "tkg-setia-kingdom", 5: "tkg-the-sunrise"}

#: The eight tables 138 binds, with the default the seven NOT NULL columns take.
BOUND_BY_138 = tuple(sorted(binding.AWAITING_SESSION_ID))

#: The last four take the Setia default. `trait_assignments` stays nullable.
DEFAULT_THREE = tuple(sorted(set(BOUND_BY_138) - {"trait_assignments"}))

#: Phase 2 state tables as designed on 2026-10-10. `PENDING_BINDING` must only shrink: a new name
#: fails `test_pending_binding_only_shrinks` and needs an owner decision.
PENDING_BASELINE = frozenset({
    "character_arcs", "character_presence_log", "damage_resistances", "enrolled_crew",
    "global_modifiers", "global_settings", "guardrail_log", "production_consumption_log",
    "research_projects", "resource_inventory", "scientist_assignments", "ship_tech_bonuses",
    "stock_prices", "stream_templates", "war_exhaustion_effects", "weapon_blueprints",
    "weapon_upgrades", "weapons",
})

SEARCH_PATH_LINE = "SET LOCAL search_path TO maya_rp;"
SHADOW_PATH_LINE = "SET LOCAL search_path TO pg_temp, maya_rp, public;"

#: Every table the two files name. Each gets an empty `pg_temp` copy before the file runs.
SHADOWED = (
    "academy_campuses", "colonies", "novels", "pirate_zones", "pool_bets", "production_lines",
    "research_labs", "resource_production", "sectors", "sessions", "ships",
    "trait_assignments", "university_campuses",
)

#: One row per bound table with `session_id` left to its default. The id is explicit, so the live
#: serial behind it does not move. `resource_production` has no id, and `pool_bets` carries four
#: NOT NULL columns the insert must fill.
DEFAULT_INSERT = ('INSERT INTO "{table}" (id, session_id) VALUES (990002, DEFAULT)'
                  " RETURNING session_id")
POOL_INSERT = ("INSERT INTO pool_bets (id, pool_id, bettor_name, bet_credits, bet_side, session_id)"
               " VALUES (990002, 1, 'dry run 138', 1, 'king', DEFAULT) RETURNING session_id")
RESOURCE_INSERT = ("INSERT INTO resource_production"
                   " (source, resource_type, amount_per_day, session_id)"
                   " VALUES ('dry run 138', 'tax', 1, DEFAULT) RETURNING session_id")

#: The insert that proves each default fires, keyed by table.
DEFAULT_PROOF = {
    "pool_bets": POOL_INSERT,
    "resource_production": RESOURCE_INSERT,
}


# ── live schema reads ────────────────────────────────────────────────────────────────────────────

async def _base_tables() -> set[str]:
    rows = await Database.fetch(
        "SELECT table_name FROM information_schema.tables"
        " WHERE table_schema = 'maya_rp' AND table_type = 'BASE TABLE'")
    return {row["table_name"] for row in rows}


async def _columns(table: str) -> dict[str, dict]:
    rows = await Database.fetch(
        "SELECT column_name, is_nullable, column_default FROM information_schema.columns"
        " WHERE table_schema = 'maya_rp' AND table_name = $1", table)
    return {row["column_name"]: dict(row) for row in rows}


async def _session_columns() -> set[str]:
    """Every `maya_rp` base table that carries `session_id`."""
    rows = await Database.fetch(
        "SELECT c.table_name FROM information_schema.columns c"
        " JOIN information_schema.tables t ON t.table_schema = c.table_schema"
        " AND t.table_name = c.table_name AND t.table_type = 'BASE TABLE'"
        " WHERE c.table_schema = 'maya_rp' AND c.column_name = 'session_id'")
    return {row["table_name"] for row in rows}


async def _fk_parents() -> dict[str, set[str]]:
    rows = await Database.fetch(
        "SELECT con.conrelid::regclass::text AS child, con.confrelid::regclass::text AS parent"
        " FROM pg_constraint con"
        " WHERE con.contype = 'f' AND con.connamespace = 'maya_rp'::regnamespace")
    parents: dict[str, set[str]] = {}
    for row in rows:
        parents.setdefault(row["child"], set()).add(row["parent"])
    return parents


async def _require_137() -> None:
    """Skip when the orchestrator has not applied 137 yet. The file is written, not run, by design."""
    if "novels" not in await _base_tables() or "novel_id" not in await _columns("sessions"):
        pytest.skip("137_novels.sql is not applied: maya_rp.novels or sessions.novel_id is absent")


async def _require_138() -> None:
    missing = [table for table in BOUND_BY_138 if "session_id" not in await _columns(table)]
    if missing:
        pytest.skip(f"138_bind_state.sql is not applied: no session_id on {', '.join(missing)}")


async def _binding_fingerprint() -> tuple:
    """The live schema the two files would change, so a dry run can prove it changed nothing."""
    columns = {table: tuple(sorted((await _columns(table)).items()))
               for table in ("sessions",) + BOUND_BY_138}
    return (tuple(sorted(await _base_tables())), tuple(sorted(columns.items())))


# ── the registry ────────────────────────────────────────────────────────────────────────────────

async def test_every_base_table_is_in_exactly_one_class():
    """A new table in no class stops here: classifying it is the decision the registry forces."""
    base = await _base_tables()
    bound = await _session_columns()
    classes = {
        "has session_id": bound,
        # A table `138_bind_state.sql` binds leaves this class the moment it carries a `session_id`,
        # so the set stays a record of what that file binds and the class check keeps its meaning
        # before the apply and after it.
        "AWAITING_SESSION_ID": set(binding.AWAITING_SESSION_ID) - bound,
        "DERIVED": set(binding.DERIVED),
        "CATALOGUE": set(binding.CATALOGUE),
        "SYSTEM": set(binding.SYSTEM),
        "PENDING_BINDING": set(binding.PENDING_BINDING),
    }
    unclassified = sorted(base - set().union(*classes.values()))
    assert not unclassified, (
        "these tables are in no class: " + ", ".join(unclassified)
        + ". Give the table a session_id, or add it to a set in core/binding.py")

    doubled: dict[str, list[str]] = {}
    names = sorted(classes)
    for index, first in enumerate(names):
        for second in names[index + 1:]:
            both = sorted(classes[first] & classes[second])
            if both:
                doubled[f"{first} + {second}"] = both
    assert not doubled, f"a table sits in two classes: {doubled}"


async def test_the_registry_names_only_tables_that_exist():
    base = await _base_tables()
    named = set().union(*(set(value) for value in (
        binding.AWAITING_SESSION_ID, binding.DERIVED, binding.CATALOGUE, binding.SYSTEM,
        binding.PENDING_BINDING)))
    assert not sorted(named - base), f"core/binding.py names tables maya_rp does not hold: {sorted(named - base)}"


async def test_a_derived_table_reaches_a_session_through_a_parent():
    parents = await _fk_parents()
    scoped = (await _session_columns()) | set(binding.DERIVED)
    orphans = sorted(table for table in binding.DERIVED
                     if not parents.get(table, set()) & scoped)
    assert not orphans, (
        f"DERIVED tables with no FK to a session-bound or derived table: {orphans}"
        ". A table that only reads from catalogues belongs in CATALOGUE")


async def test_a_catalogue_table_is_not_reachable_from_a_session():
    parents = await _fk_parents()
    scoped = (await _session_columns()) | set(binding.DERIVED)
    leaked = {table: sorted(parents.get(table, set()) & scoped)
              for table in sorted(binding.CATALOGUE) if parents.get(table, set()) & scoped}
    assert not leaked, f"a catalogue row belongs to one campaign: {leaked}"


async def test_the_system_class_holds_the_session_root():
    assert binding.SYSTEM == {"_migrations", "migration_hashes", "migration_versions", "sessions"}
    bound = await _session_columns()
    assert not set(binding.SYSTEM) & bound, (
        "the migration ledger and sessions carry no session_id: sessions is the root")


async def test_pending_binding_only_shrinks():
    grew = sorted(set(binding.PENDING_BINDING) - PENDING_BASELINE)
    assert not grew, (
        f"PENDING_BINDING grew: {grew}. It is a debt list of Phase 2 tables, and a table leaves it "
        "when a migration binds it, never by adding a name here")
    bound = await _session_columns()
    assert not set(binding.PENDING_BINDING) & bound
    assert not set(binding.PENDING_BINDING) & set(binding.AWAITING_SESSION_ID)


async def test_the_shared_entity_allowlist_names_the_iron_concord():
    """Faction 3 is canon in both novels, so the one cross-session reference the test allows is its."""
    assert binding.SHARED_ENTITIES == {"factions": {3}}, binding.SHARED_ENTITIES
    bound = await _session_columns()
    assert set(binding.SHARED_ENTITIES) <= bound, (
        "an allowlisted table must itself be session-scoped")
    row = await Database.fetchrow("SELECT id, name, session_id FROM maya_rp.factions WHERE id = 3")
    assert row is not None, "faction 3 is gone; the allowlist entry is stale"
    assert (row["name"], row["session_id"]) == ("Iron Concord", 5), dict(row)
    crossed = await Database.fetchval(
        "SELECT count(*) FROM maya_rp.ships s JOIN maya_rp.factions f ON f.id = s.faction_id"
        " WHERE f.id = 3 AND s.session_id <> f.session_id")
    assert crossed > 0, (
        "no ship names faction 3 across sessions; the shared row is gone and the allowlist is stale")


# ── the live binding, once 137 is applied ───────────────────────────────────────────────────────

async def test_sessions_three_and_five_name_their_novel():
    await _require_137()
    rows = await Database.fetch(
        "SELECT id, novel_id FROM maya_rp.sessions WHERE id IN (3, 5) ORDER BY id")
    assert {row["id"]: row["novel_id"] for row in rows} == SESSION_NOVELS


async def test_the_novels_table_holds_the_four_rows():
    await _require_137()
    rows = await Database.fetch(
        "SELECT novel_id, title, universe, adventures_dir, status, supersedes, story_order"
        " FROM maya_rp.novels")
    found = {row["novel_id"]: (row["title"], row["universe"], row["adventures_dir"],
                               row["status"], row["supersedes"], row["story_order"])
             for row in rows}
    assert found == NOVELS, found


async def test_the_prequel_keeps_its_own_row():
    """The Sunrise revamps the prequel. The prequel rows stay, so its chunks still name their novel."""
    await _require_137()
    row = await Database.fetchrow(
        "SELECT status, supersedes FROM maya_rp.novels WHERE novel_id = 'tkg-prequel'")
    assert row is not None and row["status"] == "superseded", dict(row) if row else None
    sunrise = await Database.fetchrow(
        "SELECT supersedes FROM maya_rp.novels WHERE novel_id = 'tkg-the-sunrise'")
    assert sunrise is not None and sunrise["supersedes"] == "tkg-prequel", dict(sunrise) if sunrise else None


async def test_the_sessions_novel_column_is_not_null_and_defaults_to_scratch():
    await _require_137()
    column = (await _columns("sessions")).get("novel_id")
    assert column is not None, "sessions.novel_id is absent"
    assert column["is_nullable"] == "NO", column
    assert column["column_default"] == "'scratch'::text", column


async def test_a_fresh_session_lands_in_scratch(scratch_campaign):
    """A test that inserts a sessions row names no novel, so the default decides."""
    await _require_137()
    novel = await Database.fetchval(
        "SELECT novel_id FROM maya_rp.sessions WHERE id = $1", scratch_campaign)
    assert novel == "scratch", novel


async def test_novel_of_reads_the_live_row():
    await _require_137()
    for session_id, novel_id in SESSION_NOVELS.items():
        assert await session.novel_of(session_id) == novel_id


# ── the live binding, once 138 is applied ───────────────────────────────────────────────────────

async def test_the_bound_tables_hold_the_new_column():
    await _require_138()
    for table in DEFAULT_THREE:
        column = (await _columns(table)).get("session_id")
        assert column is not None, table
        assert column["is_nullable"] == "NO", (table, column)
        assert column["column_default"] == "3", (table, column)
    column = (await _columns("trait_assignments")).get("session_id")
    assert column is not None, "trait_assignments.session_id is absent"
    assert column["is_nullable"] == "YES", column
    assert column["column_default"] is None, column


async def test_no_sectors_row_carries_a_null_session():
    await _require_138()
    nulls = await Database.fetchval("SELECT count(*) FROM maya_rp.sectors WHERE session_id IS NULL")
    assert nulls == 0, f"{nulls} sectors still name no session"
    three = await Database.fetchval("SELECT count(*) FROM maya_rp.sectors WHERE session_id = 3")
    assert three >= 625, f"session 3 holds {three} sectors, below the 625 it held before 138"


async def test_resource_production_is_keyed_by_session_and_source():
    await _require_138()
    definition = await Database.fetchval(
        "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c"
        " WHERE c.conrelid = 'maya_rp.resource_production'::regclass AND c.contype = 'p'")
    assert definition == "PRIMARY KEY (session_id, source)", definition


# ── the migration files ─────────────────────────────────────────────────────────────────────────

def test_the_migration_numbers_are_free_and_139_keeps_its_own():
    assert MIGRATION_137.name == "137_novels.sql"
    assert MIGRATION_138.name == "138_bind_state.sql"
    assert MIGRATION_139.exists(), "139_population_sentiment_unique.sql keeps its number"
    numbers: dict[str, list[str]] = {}
    for path in sorted(MIGRATIONS.glob("*.sql")):
        numbers.setdefault(path.name[:3], []).append(path.name)
    assert numbers["137"] == ["137_novels.sql"], numbers["137"]
    assert numbers["138"] == ["138_bind_state.sql"], numbers["138"]


@pytest.mark.parametrize("path", [MIGRATION_137, MIGRATION_138])
def test_the_file_names_no_table_through_the_schema(path):
    """The dry run shadows a table by name, so a `maya_rp.`-qualified name must not appear."""
    offenders = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
                 if re.search(r"\bmaya_rp\.\w", line) and line.strip() != SEARCH_PATH_LINE]
    assert not offenders, (
        f"{path.name} qualifies a table through its schema, which bypasses the temp copy: {offenders}")


def _transaction_body(path: pathlib.Path) -> str:
    """The file's statements, without its `BEGIN;` and `COMMIT;`, and on the shadow search path.

    The dry run owns the transaction, so the file's own COMMIT comes out: leaving it in would commit
    the copies and the assertions onto the live schema. The one edit to the text retargets the search
    path at `pg_temp` first, so an unqualified table name in the file resolves to the empty copy the
    dry run made. The assertion on the transaction holds the file to one BEGIN and one COMMIT.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    opens = [index for index, line in enumerate(lines) if line == "BEGIN;"]
    closes = [index for index, line in enumerate(lines) if line == "COMMIT;"]
    assert len(opens) == 1 and len(closes) == 1, (
        f"{path.name} must open and close exactly one transaction:"
        f" {len(opens)} opens, {len(closes)} closes")
    assert opens[0] < closes[0], f"{path.name} commits before it opens"
    body = lines[opens[0] + 1:closes[0]]
    settings = [index for index, line in enumerate(body) if line == SEARCH_PATH_LINE]
    assert len(settings) == 1, f"{path.name} must set its search path once: {len(settings)} lines"
    body[settings[0]] = SHADOW_PATH_LINE
    return "\n".join(body)


async def _shadow(conn) -> None:
    """An empty temp copy of every table the files name, and a search path that prefers them."""
    for table in SHADOWED:
        await conn.execute(
            f'CREATE TEMP TABLE "{table}" (LIKE maya_rp."{table}" INCLUDING ALL) ON COMMIT DROP')
    await conn.execute(SHADOW_PATH_LINE)
    resolved = await conn.fetchval(
        "SELECT n.nspname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
        " WHERE c.oid = 'sessions'::regclass")
    assert resolved.startswith("pg_temp"), (
        f"a temp copy must shadow the live table; 'sessions' resolved to {resolved}")


async def _dry_run(path: pathlib.Path, seed, check) -> None:
    """Run the file's statements twice on a scratch connection, then roll everything back.

    The second run is the idempotency claim: each column, table, row and index is guarded, so the
    file must survive its own re-run. The connection is taken from the pool directly because
    `Database.transaction()` commits when its block ends, which would apply the file.
    """
    pool = await Database.init()
    conn = await pool.acquire()
    try:
        await conn.execute("BEGIN")
        await _shadow(conn)
        await seed(conn)
        await conn.execute(_transaction_body(path))
        await conn.execute(_transaction_body(path))
        await check(conn)
    finally:
        await conn.execute("ROLLBACK")
        await pool.release(conn)


async def _temp_column(conn, table: str, column: str) -> dict:
    """`attnotnull` and the default of one column of the temp copy of `table`."""
    row = await conn.fetchrow(
        "SELECT a.attnotnull, pg_get_expr(d.adbin, d.adrelid) AS default_expr"
        " FROM pg_attribute a"
        " LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum"
        " WHERE a.attrelid = $1::text::regclass AND a.attname = $2", table, column)
    return dict(row) if row else {}


async def _temp_index_count(conn, table: str, index: str) -> int:
    return await conn.fetchval(
        "SELECT count(*) FROM pg_indexes"
        " WHERE schemaname = (SELECT nspname FROM pg_namespace WHERE oid = pg_my_temp_schema())"
        " AND tablename = $1 AND indexname = $2", table, index)


@pytest.mark.live_session_ok
async def test_the_137_dry_run_binds_the_sessions_and_the_novels():
    """The file's own DDL against an empty copy of `sessions`, twice, then rolled back.

    The guard stands down because the file writes sessions 3 and 5 by design. Every table it names is
    a temp copy inside this transaction, so no live row is reachable, and the fingerprint proves the
    live schema is the same afterwards.
    """
    before = await _binding_fingerprint()

    async def seed(conn):
        # An applied 137 leaves `novel_id` on the live table, and `LIKE` copies the column without its
        # foreign key. Drop the copy so the file always runs against its own pre-137 shape.
        await conn.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS novel_id")
        await conn.execute(
            "INSERT INTO sessions (id, name, status) VALUES"
            " (3, 'TKG', 'active'), (5, 'TKG — Arc I: The Sunrise', 'active'),"
            " (990001, 'dry run scratch', 'active')")

    async def check(conn):
        rows = await conn.fetch(
            "SELECT id, novel_id FROM sessions WHERE id IN (3, 5, 990001) ORDER BY id")
        assert [(row["id"], row["novel_id"]) for row in rows] == [
            (3, "tkg-setia-kingdom"), (5, "tkg-the-sunrise"), (990001, "scratch")]

        rows = await conn.fetch(
            "SELECT novel_id, title, universe, adventures_dir, status, supersedes, story_order"
            " FROM novels")
        found = {row["novel_id"]: (row["title"], row["universe"], row["adventures_dir"],
                                   row["status"], row["supersedes"], row["story_order"])
                 for row in rows}
        assert found == NOVELS, found

        column = await _temp_column(conn, "sessions", "novel_id")
        assert column == {"attnotnull": True, "default_expr": "'scratch'::text"}, column

        foreign_keys = await conn.fetchval(
            "SELECT count(*) FROM pg_constraint WHERE contype = 'f'"
            " AND conrelid = 'sessions'::regclass AND confrelid = 'novels'::regclass")
        assert foreign_keys == 1, "sessions.novel_id does not reference novels"
        assert await _temp_index_count(conn, "sessions", "sessions_novel_id_idx") == 1

    await _dry_run(MIGRATION_137, seed, check)
    assert await _binding_fingerprint() == before, "the dry run changed the live schema"


@pytest.mark.live_session_ok
async def test_the_138_dry_run_binds_the_state_tables():
    """The eight columns, the key swap, the sector backfill and the trait backfill, twice, rolled back.

    The guard stands down because the file writes session 3 for the NULL sectors and the orphan
    traits by design. Every table it names is a temp copy, so no live row is reachable.
    """
    before = await _binding_fingerprint()

    async def seed(conn):
        await conn.execute(
            "INSERT INTO sectors (id, session_id, name, x_coord, y_coord) VALUES"
            " (990001, NULL, 'dry run sector', 1, 1), (990002, 5, 'dry run arc one', 2, 2)")
        await conn.execute(
            "INSERT INTO colonies (id, name, session_id) VALUES (990001, 'dry run colony', 5)")
        await conn.execute(
            "INSERT INTO ships (id, name, session_id) VALUES (990001, 'dry run ship', 3)")
        await conn.execute(
            "INSERT INTO trait_assignments (assignment_id, trait_id, target_type, target_id) VALUES"
            " (990001, 1, 'colony', 990001), (990002, 1, 'ship', 990001),"
            " (990003, 1, 'ship', 990999), (990004, 1, 'fleet', 990999)")

    async def check(conn):
        for table in DEFAULT_THREE:
            column = await _temp_column(conn, table, "session_id")
            assert column == {"attnotnull": True, "default_expr": "3"}, (table, column)
            insert = DEFAULT_PROOF.get(table) or DEFAULT_INSERT.format(table=table)
            landed = await conn.fetchval(insert)
            assert landed == 3, (table, landed)
            count = await _temp_index_count(conn, table, f"{table}_session_idx")
            assert count == 1, (table, count)

        column = await _temp_column(conn, "trait_assignments", "session_id")
        assert column == {"attnotnull": False, "default_expr": None}, column
        count = await _temp_index_count(conn, "trait_assignments", "trait_assignments_session_idx")
        assert count == 1, count

        key = await conn.fetchval(
            "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c"
            " WHERE c.conrelid = 'resource_production'::regclass AND c.contype = 'p'")
        assert key == "PRIMARY KEY (session_id, source)", key

        rows = await conn.fetch(
            "SELECT id, session_id FROM sectors WHERE id IN (990001, 990002) ORDER BY id")
        assert [(row["id"], row["session_id"]) for row in rows] == [(990001, 3), (990002, 5)], (
            "the backfill must take the NULL row only")

        rows = await conn.fetch(
            "SELECT assignment_id, session_id FROM trait_assignments"
            " WHERE assignment_id BETWEEN 990001 AND 990004 ORDER BY assignment_id")
        assert [row["session_id"] for row in rows] == [5, 3, 3, 3], [dict(row) for row in rows]

    await _dry_run(MIGRATION_138, seed, check)
    assert await _binding_fingerprint() == before, "the dry run changed the live schema"


@pytest.mark.live_session_ok
async def test_the_138_guard_refuses_a_row_outside_session_three():
    """A state row that names no session-3 parent stops the file before a column is added."""
    pool = await Database.init()
    conn = await pool.acquire()
    try:
        await conn.execute("BEGIN")
        await conn.execute(
            'CREATE TEMP TABLE "pirate_zones" (LIKE maya_rp."pirate_zones" INCLUDING ALL)'
            " ON COMMIT DROP")
        await conn.execute(SHADOW_PATH_LINE)
        await conn.execute("INSERT INTO pirate_zones (id, system_id) VALUES (990001, 999999999)")
        with pytest.raises(PostgresError) as raised:
            await conn.execute(_transaction_body(MIGRATION_138))
        message = str(raised.value)
        assert "pirate_zones" in message and "session-3 planet" in message, message
    finally:
        await conn.execute("ROLLBACK")
        await pool.release(conn)


# ── novel_of ────────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    """A private arc file and no RP_SESSION, so the resolver cannot read the live arc."""
    monkeypatch.setattr(session, "ACTIVE_ARC", tmp_path / "active_arc")
    monkeypatch.setattr(session, "FROZEN", tmp_path / "frozen_sessions")
    monkeypatch.setattr(session, "_maintenance_active", lambda: False)
    monkeypatch.delenv("RP_SESSION", raising=False)
    return tmp_path


def _stub_row(monkeypatch, row) -> list:
    """Replace the one read `novel_of` makes, and record what it asked for."""
    asked: list = []

    async def fetchrow(sql, *args):
        asked.append((sql, args))
        return row

    monkeypatch.setattr(Database, "fetchrow", fetchrow)
    return asked


async def test_novel_of_reads_the_resolved_session(state_dir, monkeypatch):
    session.set_active_arc(5)
    asked = _stub_row(monkeypatch, {"novel_id": "tkg-the-sunrise"})
    assert await session.novel_of() == "tkg-the-sunrise"
    assert asked[0][1] == (5,), asked


async def test_novel_of_takes_the_session_it_is_told(state_dir, monkeypatch):
    """The engine default is not a fallback: the caller's id decides, the arc file does not."""
    session.set_active_arc(5)
    monkeypatch.setattr(config.Config, "SESSION_ID", 5)
    asked = _stub_row(monkeypatch, {"novel_id": "tkg-setia-kingdom"})
    assert await session.novel_of(3) == "tkg-setia-kingdom"
    assert asked[0][1] == (3,), asked


async def test_novel_of_refuses_a_session_with_no_row(state_dir, monkeypatch):
    _stub_row(monkeypatch, None)
    with pytest.raises(ValueError) as raised:
        await session.novel_of(7)
    assert "7" in str(raised.value) and "no row" in str(raised.value), str(raised.value)


async def test_novel_of_refuses_a_null_novel(state_dir, monkeypatch):
    _stub_row(monkeypatch, {"novel_id": None})
    with pytest.raises(ValueError) as raised:
        await session.novel_of(7)
    assert "NULL novel_id" in str(raised.value), str(raised.value)


async def test_novel_of_refuses_when_no_session_resolves(state_dir):
    with pytest.raises(RuntimeError):
        await session.novel_of()


def test_require_session_is_unchanged(state_dir):
    assert session.require_session(7) == 7
    with pytest.raises(RuntimeError):
        session.require_session()
