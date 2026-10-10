"""A migration's search path must not outlive the migration.

`SET search_path` is session-scoped: on a pooled connection it stays after `COMMIT`, so the next
user of that connection resolves unqualified names against `maya_rp` whether it asked to or not.
`SET LOCAL` ends with its transaction. Both halves are held here: the 18 files that set a path, and
the runner, which now sends one of its own in front of every file it applies.

No database. `scripts/migrate.py` is imported and `Database` is replaced by a fake whose connection
models the one rule that matters, so a leak is observable without a server:

    SET search_path ...         session-scoped, survives the statement
    SET LOCAL search_path ...   transaction-scoped, reverts when the transaction ends

The fake also models asyncpg's implicit transaction: a multi-statement string is one transaction,
so a `SET LOCAL` first in that string governs every statement the file runs.
"""
from __future__ import annotations

import pathlib
import re
import sys
from contextlib import asynccontextmanager

ROOT = pathlib.Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import migrate  # noqa: E402

#: What every migration sets now. The files name their tables unqualified on purpose: they rely on
#: the path, which is why a leaked one is dangerous.
LOCAL_LINE = "SET LOCAL search_path TO maya_rp;"

#: The line the runner must send in front of a file. Spelled out here, not read from `migrate`, so
#: the test still fails if the runner's own constant changes shape.
EXPECTED_PREFIX = "SET LOCAL search_path TO maya_rp;\n"

#: Any path statement that is not `SET LOCAL`, the runner's own included.
BARE_PATH = re.compile(r"^\s*SET\s+search_path", re.I)
PATH_LINE = re.compile(r"^\s*SET\s+(LOCAL\s+)?search_path\b", re.I)


def _scripts(root: pathlib.Path) -> list[tuple[str, str]]:
    """(file name, text) for every migration, in the order the runner applies them."""
    return [(path.name, path.read_text(encoding="utf-8")) for path in sorted(root.glob("*.sql"))]


# ── The files ────────────────────────────────────────────────────────────────────────────────────

def test_every_search_path_line_is_local():
    """18 files set a path. A bare `SET` among them is the leak this unit closes."""
    bare = [(name, line.strip())
            for name, text in _scripts(MIGRATIONS)
            for line in text.splitlines()
            if BARE_PATH.match(line)]
    assert not bare, f"a session-scoped search path outlives its migration: {bare}"


def test_every_migration_that_sets_a_path_sets_it_local():
    """The counter-test: no file may set a path with a bare `SET`."""
    assert not [name for name, text in _scripts(MIGRATIONS) if PATH_LINE.search(text)
                and LOCAL_LINE not in text]


def test_the_files_that_set_a_path_are_the_ones_this_unit_edited():
    edited = sorted(name for name, text in _scripts(MIGRATIONS) if LOCAL_LINE in text)
    assert edited == [
        "115_faction_axes.sql", "116_world_models.sql", "117_trust_numeric.sql",
        "118_migration_bookkeeping.sql", "119_science_assassination.sql",
        "123_migration_bookkeeping.sql", "124_affection.sql", "125_trade_deals_session.sql",
        "126_asset_framing.sql", "127_weapon_upgrade_applied.sql",
        "136_ship_modules_slot_unique.sql", "137_novels.sql", "138_bind_state.sql",
        "139_population_sentiment_unique.sql", "140_research_gate_names.sql",
        "seed_tkg_artifacts.sql", "seed_tkg_combat.sql", "seed_tkg_reference.sql",
    ], "the set of files that set a search path changed"


# ── The runner ───────────────────────────────────────────────────────────────────────────────────

class _Transaction:
    """A connection's `search_path` while one transaction is open, reset when it ends."""

    def __init__(self, conn: "_Conn") -> None:
        self.conn = conn
        self.path = conn.session

    def close(self) -> None:
        self.path = self.conn.session


class _Conn:
    """A pooled connection with both scopes of `SET`, as PostgreSQL applies them.

    `SET LOCAL` changes the transaction's path and reverts when that transaction ends. A bare `SET`
    changes the session's path and is recorded: that is the path the next user of this pooled
    connection would inherit.
    """

    def __init__(self, base: str) -> None:
        self.session = base
        self.leaked: list[str] = []
        self.warnings: list[str] = []
        self.sent: list[str] = []
        self.transaction: _Transaction | None = None

    @property
    def path(self) -> str:
        """What `current_setting('search_path')` answers: the transaction's, or the session's."""
        inner = self.transaction
        return inner.path if inner is not None else self.session

    @property
    def base(self) -> str:
        return self.session

    def execute(self, sql: str, *args) -> str:
        self.sent.append(sql)
        tx = self.transaction
        for statement in sql.split(";"):
            words = statement.strip().split()
            if not words or " TO " not in statement:
                continue
            head = words[0].upper()
            second = words[1].lower() if len(words) > 1 else ""
            value = statement.split(" TO ", 1)[1].strip()
            if head == "SET" and second == "local":
                if tx is not None:
                    tx.path = value
                else:
                    self.warnings.append(statement.strip())  # a warning, and no effect
            elif head == "SET" and second == "search_path":
                self.leaked.append(statement.strip())
                self.session = value
        if tx is not None:
            tx.close()  # the transaction ends with the call
        return "OK"


class _Database:
    """The two methods `run_migrations` uses, against one connection reused like a pooled one."""

    def __init__(self, recorded: tuple[str, ...] = (), base: str = "maya_rp, public") -> None:
        self.conn = _Conn(base)
        self.recorded = list(recorded)

    async def init(self):
        return self.conn

    async def fetch(self, query: str, *args):
        assert "_migrations" in query, query
        return [{"name": name} for name in self.recorded]

    async def execute(self, query: str, *args):
        # The bookkeeping insert carries the name as a parameter. A migration file never does, even
        # when it mentions `_migrations` in its own SQL, as 140 does.
        if args:
            self.recorded.append(args[0])
            return "INSERT 0 1"
        # asyncpg runs each call inside its own transaction. When the caller already holds one, its
        # calls share it, which is the only difference a dry run makes.
        held = self.conn.transaction
        if held is not None:
            return self.conn.execute(query)
        self.conn.transaction = _Transaction(self.conn)
        try:
            return self.conn.execute(query)
        finally:
            self.conn.transaction = None

    async def close(self):
        """`run_migrations` closes the pool; the fake records that it was asked to."""

    @asynccontextmanager
    async def transaction(self):
        """The connection `Database.transaction()` yields, with a transaction open on it."""
        self.conn.transaction = _Transaction(self.conn)
        try:
            yield self.conn
        finally:
            self.conn.transaction = None


def _fixture_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    """Two pending files: one with its own transaction, one without, as the tree has both."""
    (tmp_path / "149_first.sql").write_text(
        "-- 149: written like 115 to 140, with its own transaction\n"
        f"BEGIN;\n{LOCAL_LINE}\nALTER TABLE factions ADD COLUMN IF NOT EXISTS probe integer;\n"
        "COMMIT;\n", encoding="utf-8")
    (tmp_path / "150_second.sql").write_text(
        "-- 150: sets the path once and lets the runner own the transaction\n"
        f"{LOCAL_LINE}\nINSERT INTO maya_rp.commodities (name) VALUES ('probe');\n",
        encoding="utf-8")
    return tmp_path


async def test_the_runner_sets_the_path_once_per_file(monkeypatch, tmp_path):
    """The file's text and the runner's path statement go in ONE call, so one transaction holds both."""
    migrations = _fixture_dir(tmp_path)
    fake = _Database(recorded=("148_older.sql",))

    class Config:
        MIGRATIONS_DIR = str(migrations)

    monkeypatch.setattr(migrate, "Database", fake)
    monkeypatch.setattr(migrate, "Config", Config)
    monkeypatch.delenv("MIGRATE_ALLOW_LEGACY", raising=False)

    await migrate.run_migrations()

    applied = "\n".join(fake.conn.sent)
    for path in sorted(migrations.glob("*.sql")):
        text = path.read_text(encoding="utf-8")
        assert text in applied, f"{path.name} was not applied"
        assert (EXPECTED_PREFIX + text) in applied, (
            f"{path.name} was applied without a local search path of the runner's own")
    assert not fake.conn.leaked, f"the runner sent a session-scoped path: {fake.conn.leaked}"
    assert not fake.conn.warnings, f"a SET LOCAL ran outside a transaction: {fake.conn.warnings}"


async def test_a_reused_connection_keeps_the_dsn_path(monkeypatch, tmp_path):
    """Criterion: reuse the pooled connection after a migration and read the path it now carries.

    A file that set the path with a bare `SET` shows up in `leaked`, and the path assertion fails
    with it, so the test is red against the old shape and green against `SET LOCAL`.
    """
    migrations = _fixture_dir(tmp_path)
    fake = _Database(recorded=("148_older.sql",))

    class Config:
        MIGRATIONS_DIR = str(migrations)

    monkeypatch.setattr(migrate, "Database", fake)
    monkeypatch.setattr(migrate, "Config", Config)
    monkeypatch.delenv("MIGRATE_ALLOW_LEGACY", raising=False)

    await migrate.run_migrations()

    assert not fake.conn.leaked, f"a session-scoped search path reached the connection: {fake.conn.leaked}"
    assert not fake.conn.warnings, f"a SET LOCAL outside a transaction did nothing: {fake.conn.warnings}"
    assert fake.conn.path == fake.conn.base, (
        f"the connection hands on '{fake.conn.path}', not '{fake.conn.base}'")
    assert fake.recorded[-2:] == ["149_first.sql", "150_second.sql"]


# ── The script the runner sends ──────────────────────────────────────────────────────────────────

async def test_one_migration_does_not_hand_its_path_to_the_next(monkeypatch, tmp_path):
    """The two shapes the tree holds, applied in order on one reused connection.

    149 opens and closes its own transaction, as 115 to 140 do; 150 does not, as the seed files do
    not. Both leave the connection on the DSN's path, so the second never inherits the first's.
    """
    migrations = _fixture_dir(tmp_path)
    fake = _Database()

    class Config:
        MIGRATIONS_DIR = str(migrations)

    monkeypatch.setattr(migrate, "Database", fake)
    monkeypatch.setattr(migrate, "Config", Config)
    monkeypatch.setenv("MIGRATE_ALLOW_LEGACY", "1")  # the fixture names do not match the tree's

    await migrate.run_migrations()
    assert [name for name in fake.recorded] == ["149_first.sql", "150_second.sql"]
    assert not fake.conn.leaked, f"a session-scoped path reached the connection: {fake.conn.leaked}"
    assert not fake.conn.warnings, f"a SET LOCAL ran outside a transaction: {fake.conn.warnings}"
    assert fake.conn.path == fake.conn.base, (
        f"the connection hands on '{fake.conn.path}', not '{fake.conn.base}'")


def test_both_transaction_shapes_exist_in_the_real_tree():
    """The fixtures above copy two shapes the tree holds; both must stay in the tree."""
    own = (MIGRATIONS / "115_faction_axes.sql").read_text(encoding="utf-8")
    loose = (MIGRATIONS / "seed_tkg_combat.sql").read_text(encoding="utf-8")
    assert own.count("BEGIN;") == 1 and own.count("COMMIT;") == 1, "115 lost its own transaction"
    assert "BEGIN;" not in loose, "the seed file gained a transaction, so the loose shape is untested"


def test_a_file_without_its_own_transaction_touches_only_qualified_tables():
    """`SET LOCAL` outside a transaction does nothing, so such a file must name its own schema.

    `seed_tkg_combat.sql` and `seed_tkg_artifacts.sql` are the two files with a path line and no
    `BEGIN;`. Applied by hand, their `SET LOCAL` has no effect; under the runner it holds. Either
    way every table they touch is spelled `maya_rp.<name>`, so neither path resolves a bare name.
    """
    unqualified = re.compile(
        r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM|ALTER\s+TABLE|CREATE\s+(?:UNIQUE\s+)?"
        r"(?:TABLE|INDEX)|TRUNCATE)\s+(?!maya_rp\.)(?!pg_)[A-Za-z_][A-Za-z0-9_]*", re.I)
    for name in ("seed_tkg_artifacts.sql", "seed_tkg_combat.sql"):
        text = (MIGRATIONS / name).read_text(encoding="utf-8")
        assert "BEGIN;" not in text, f"{name} now owns a transaction; this check is for the other case"
        touched = unqualified.findall(text)
        assert not touched, f"{name} names a table without its schema: {sorted(set(touched))}"


async def test_a_recorded_file_is_not_run_again(monkeypatch, tmp_path):
    """Criterion 4: re-running is safe because an applied file is skipped, path statement and all."""
    migrations = _fixture_dir(tmp_path)
    fake = _Database(recorded=("148_older.sql", "149_first.sql", "150_second.sql"))

    class Config:
        MIGRATIONS_DIR = str(migrations)

    monkeypatch.setattr(migrate, "Database", fake)
    monkeypatch.setattr(migrate, "Config", Config)
    monkeypatch.delenv("MIGRATE_ALLOW_LEGACY", raising=False)

    await migrate.run_migrations()

    ran = [call for call in fake.conn.sent if "_migrations" not in call]
    assert not ran, f"a recorded file was executed again: {ran}"


def test_the_whole_file_travels_with_the_path_line(tmp_path):
    for path in sorted(_fixture_dir(tmp_path).glob("*.sql")):
        text = path.read_text(encoding="utf-8")
        script = migrate.migration_script(text)
        assert script.startswith(EXPECTED_PREFIX), "the path line must open the script"
        assert script.endswith(text), "the file's last line must be the script's last line"
        assert text in script, "the runner must send the file verbatim"


def test_the_path_statement_is_local():
    """The runner's own statement is the fix; a bare `SET` here would re-open the leak."""
    assert migrate.SEARCH_PATH == LOCAL_LINE
    assert not BARE_PATH.match(migrate.SEARCH_PATH), "a bare `SET search_path`"
    assert migrate.SEARCH_PATH.startswith("SET LOCAL search_path TO ")
    assert migrate.SEARCH_PATH.endswith(";")
