"""Housekeeping gates: migrations are recorded, and every pure module imports.

Two defects were found by hand during this work, and both are cheap to catch in future:
119_science_assassination.sql was applied but absent from `maya_rp._migrations`, and a
pure module can rot into non-importable without any test noticing. Neither is a
behaviour bug, and both break a rebuild.
"""
from __future__ import annotations

import importlib
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations"
MODULES = ROOT / "modules"

# Pure modules a later unit is allowed to import from the audit path. Each must import
# with no database and no network, because the engine calls them inside a tick.
PURE_MODULES = (
    "modules.magic_cost",
    "modules.well_aegis",
    "modules.programme_cost",
    "modules.economy_physics",
    "modules.unity",
)


# Pre-existing debt, recorded rather than fixed here: seventeen prefixes carry two files
# because the repo numbered SQL and follow-up SQL into the same slot, and three seed files
# were written without a prefix at all. The gate fails on anything NEW, so the debt cannot
# grow while it stays visible.
KNOWN_UNNUMBERED = {"seed_tkg_artifacts.sql", "seed_tkg_combat.sql", "seed_tkg_reference.sql"}
KNOWN_SHARED_PREFIX = {
    "068", "069", "083", "084", "085", "086", "087", "088", "089", "090", "091", "092",
    "093", "094", "095", "096", "097",
}


class TestMigrationBookkeeping:
    def test_every_migration_file_on_disk_is_named_like_a_migration(self):
        found = sorted(MIGRATIONS.glob("*.sql"))
        offenders = [path.name for path in found
                     if not path.name[:3].isdigit() and path.name not in KNOWN_UNNUMBERED]
        assert found, "no migration files found"
        assert not offenders, f"unconventionally named migrations: {offenders}"

    def test_no_duplicate_migration_number(self):
        numbers: dict[str, list[str]] = {}
        for path in sorted(MIGRATIONS.glob("*.sql")):
            if not path.name[:3].isdigit():
                continue  # the unnumbered seed files have their own check above
            numbers.setdefault(path.name[:3], []).append(path.name)
        dupes = {number: names for number, names in numbers.items()
                 if len(names) > 1 and number not in KNOWN_SHARED_PREFIX}
        assert not dupes, f"two migrations share a number: {dupes}"

    async def test_applied_migrations_are_recorded(self):
        """Every migration whose DDL is live must be named in `_migrations`.

        The test cannot know what ran, so it checks the two that this work applied by
        hand and that a rebuild would otherwise skip.
        """
        from core.db import Database

        rows = await Database.fetch("SELECT name FROM maya_rp._migrations")
        recorded = {row["name"] for row in rows}
        for expected in ("119_science_assassination.sql",):
            assert expected in recorded, (
                f"{expected} is applied to maya_rp but missing from _migrations; a rebuild "
                f"replaying that table would skip it"
            )


class TestPureModules:
    @pytest.mark.parametrize("name", PURE_MODULES)
    def test_module_imports(self, name):
        assert importlib.import_module(name) is not None

    @pytest.mark.parametrize("name", PURE_MODULES)
    def test_module_source_has_no_database_or_network_import(self, name):
        source = (ROOT / (name.replace(".", "/") + ".py")).read_text(encoding="utf-8")
        for banned in ("import psycopg2", "import requests", "import socket", "from core.db import"):
            assert banned not in source, f"{name} must stay pure but imports {banned!r}"
