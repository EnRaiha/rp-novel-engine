"""The migration runner must not replay a migration that was applied by hand.

`maya_rp._migrations` begins at 118, so 20 files on disk predate it and are absent from the table.
`scripts/migrate.py` treats an absent file as pending and executes it, and it continues past failures.
13 of those files carry UPDATE or DROP TABLE, and `084-drop-campaigns.sql` drops a table.

That is a loaded gun pointed at production. The classifier below is the safety, and these tests hold
it: a file older than the newest recorded migration is legacy, never pending.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

from migrate import classify  # noqa: E402


def _files(*names: str) -> list[pathlib.Path]:
    return [pathlib.Path("migrations") / name for name in names]


class TestClassify:
    def test_a_file_older_than_the_newest_recorded_is_legacy(self):
        pending, legacy = classify(_files("084-drop-campaigns.sql", "125_new.sql"),
                                   {"124_affection.sql"}, "124_affection.sql")
        assert [p.name for p in legacy] == ["084-drop-campaigns.sql"]
        assert [p.name for p in pending] == ["125_new.sql"]

    def test_a_recorded_file_is_neither(self):
        pending, legacy = classify(_files("124_affection.sql"), {"124_affection.sql"}, "124_affection.sql")
        assert not pending and not legacy

    def test_a_fresh_database_has_nothing_legacy(self):
        """With no recorded history there is nothing to be older than."""
        pending, legacy = classify(_files("001_init.sql", "002_more.sql"), set(), None)
        assert len(pending) == 2 and not legacy

    def test_the_real_tree_produces_legacy_files_and_they_are_dangerous(self):
        """The actual repository state, so the guard is not theoretical."""
        migrations = ROOT / "migrations"
        files = sorted(migrations.glob("*.sql"))
        recorded = {path.name for path in files if path.name >= "118_migration_bookkeeping.sql"}
        _, legacy = classify(files, recorded, "124_affection.sql")
        assert legacy, "the guard has nothing to refuse, so it proves nothing"
        text = {path.name: path.read_text(encoding="utf-8", errors="replace").upper() for path in legacy}
        dangerous = [name for name, body in text.items() if "DROP TABLE" in body or "UPDATE " in body]
        assert dangerous, "the legacy set lost its dangerous members"
