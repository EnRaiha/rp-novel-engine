#!/usr/bin/env python3
"""Migration runner — applies pending SQL migrations in order."""
import asyncio, sys, os
from pathlib import Path
sys.path.insert(0, str(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from core.db import Database
from core.config import Config
from core.log import info

DESTRUCTIVE = ("DROP TABLE", "DROP COLUMN", "TRUNCATE", "DELETE FROM", "UPDATE ")

#: The search path every migration runs on, set once per file rather than per connection.
#:
#: `SET LOCAL` ends with the transaction, so the path cannot outlive the file that set it. A pooled
#: connection handed to the next user keeps the DSN's path, never a migration's.
SEARCH_PATH = "SET LOCAL search_path TO maya_rp;"


def migration_script(sql: str) -> str:
    """The SQL sent for one migration: its own text, behind this runner's search path.

    The two go in ONE statement string. asyncpg runs a bounded multi-statement string inside an
    implicit transaction, and `SET LOCAL` outside a transaction block does nothing, so splitting
    them into two calls would leave the path unset and the second call would warn to the client.
    A file that opens its own `BEGIN;` keeps the setting alive across its own `COMMIT;` too: the
    setting is transaction-scoped, and the file's commit ends that transaction.

    The newline separates the file's first line from this one. The file's own `SET LOCAL` follows
    and agrees with it; nothing else in the file changes.

    @param sql - the migration file's text, verbatim.
    @returns the statement string to execute.
    """
    return f"{SEARCH_PATH}\n{sql}"


def classify(files: list, recorded: set, newest_recorded: str | None) -> tuple[list, list]:
    """Split migration files into the ones to run and the ones that must not be run blind.

    `_migrations` begins at 118, so files older than the newest recorded migration are either applied
    by hand or were never recorded. Executing them again is not idempotent: 13 of them carry UPDATE or
    DROP TABLE, one drops a table. So a file that sorts before the newest recorded migration is
    **legacy**: reported, never executed, unless the caller asks for it explicitly.

    @param files - migration paths, sorted by name.
    @param recorded - names already in `_migrations`.
    @param newest_recorded - the last name in `_migrations`, or None on a fresh database.
    @returns (pending, legacy) where pending is safe to run and legacy needs a human.
    """
    pending, legacy = [], []
    for path in files:
        if path.name in recorded:
            continue
        if newest_recorded is not None and path.name < newest_recorded:
            legacy.append(path)
        else:
            pending.append(path)
    return pending, legacy


async def run_migrations():
    await Database.init()
    await Database.execute(
        "CREATE TABLE IF NOT EXISTS maya_rp._migrations ("
        "id SERIAL PRIMARY KEY, name TEXT UNIQUE, applied_at TIMESTAMPTZ DEFAULT NOW())")

    rows = await Database.fetch("SELECT name FROM maya_rp._migrations ORDER BY name")
    applied = {r["name"] for r in rows}
    newest_recorded = rows[-1]["name"] if rows else None
    mig_dir = Path(Config.MIGRATIONS_DIR)
    files = sorted(mig_dir.glob("*.sql"))

    if not files:
        print("No migration files found.")
        return

    pending, legacy = classify(files, applied, newest_recorded)
    if legacy:
        print(f"⛔ {len(legacy)} migration(s) predate {newest_recorded} and were never recorded.")
        print("   They are NOT run. Replaying them is not idempotent; some carry UPDATE or DROP.")
        for path in legacy:
            text = path.read_text(errors="replace")
            marks = [word for word in DESTRUCTIVE if word in text.upper()]
            print(f"     {path.name}{'  ⚠ ' + ', '.join(marks) if marks else ''}")
        print("   Record the ones that were applied: scripts/record_legacy_migrations.py --apply")
        print("   Run them anyway (dangerous): MIGRATE_ALLOW_LEGACY=1")
        if os.environ.get("MIGRATE_ALLOW_LEGACY") != "1":
            # Do not return here. The loop below skips `legacy` on its own, so a warning is enough
            # to protect them. Returning would stop every future migration as well, for as long as
            # one old file stays unrecorded — and `record_legacy_migrations.py` can prove none of
            # them applied, since a DROP or an UPDATE names nothing the recorder can look for. So
            # the block was permanent, and no new migration could ever be applied.
            print(f"   Continuing with {len(pending)} pending migration(s), which are not legacy.")

    count = 0
    for f in files:
        if f.name in applied:
            continue
        if f in legacy and os.environ.get("MIGRATE_ALLOW_LEGACY") != "1":
            continue
        try:
            sql = f.read_text()
            await Database.execute(migration_script(sql))
            await Database.execute("INSERT INTO maya_rp._migrations (name) VALUES ($1)", f.name)
            print(f"  ✅ {f.name}")
            count += 1
        except Exception as e:
            print(f"  ❌ {f.name}: {e}")
            return

    if count == 0:
        print("  No pending migrations.")
    else:
        print(f"  Applied {count} migration(s).")
    await Database.close()

if __name__ == "__main__":
    asyncio.run(run_migrations())
