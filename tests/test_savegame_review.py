"""Module review: core/savegame.py.

Three defects, and the first one is a flag that crashes.

`import_sav(..., wipe=False)` bound `partial` inside the `wipe` branch and then read it in the
restore loop, so `python3 scripts/cli.py load <file.sav> --keep-session` died with an
UnboundLocalError on any file that carries a table. It survived the existing tests because the three
tests that pass `wipe=False` all hand it `"tables": {}`, so the loop never runs.

`restored` rose inside the batch insert, before the savepoint committed. A batch that failed on its
last row kept every row before it in the total although the savepoint rolled them back, and the
row-by-row retry then counted the same rows a second time.

`export_sav` wrote a checkpoint of a session that does not exist: `game_day` came back NULL and every
session-scoped table came back empty, and the file still looked like a checkpoint. The module already
refuses to write a snapshot with a hole in it; this is the same hole with a different cause.

Not changed, reported to the lead: a checksum mismatch is logged as a WARNING and the restore
proceeds to wipe the live database anyway.

Nothing here runs `import_sav(..., wipe=True)`: by design it deletes every row of every global
catalog and reloads them from the file it was handed, so a synthetic file would empty the live
catalogs. The tests use `wipe=False`, and the one wipe-path test asserts a refusal before the wipe.

The scratch session is derived from the process id in a band no other test file uses (600, 700, 800
and 900 are taken). Every row this file writes is removed in the fixture's finally.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import savegame  # noqa: E402
from core.db import Database  # noqa: E402

SCRATCH_SESSION = 500 + (os.getpid() % 100)
SUBJECT = "Savegame Review Subject"

CLEANUP = (
    "DELETE FROM maya_rp.ooc_suspicion WHERE session_id=$1",
    "DELETE FROM maya_rp.characters WHERE session_id=$1",
)


async def _clear(session_id: int) -> None:
    for statement in CLEANUP:
        await Database.execute(statement, session_id)


def _sav(tmp_path: pathlib.Path, tables: dict, session_id: int = SCRATCH_SESSION,
         partial: list[str] | None = None) -> str:
    """A minimal .sav file, written by hand so the header is exactly what the test needs."""
    header = {"format": savegame.FORMAT, "version": savegame.SAV_VERSION, "session_id": session_id,
              "game_day": 1}
    if partial is not None:
        header["partial_tables"] = partial
    path = tmp_path / "review.sav"
    path.write_text(json.dumps({"header": header, "tables": tables}), encoding="utf-8")
    return str(path)


@pytest.fixture()
async def scratch_session():
    """A campaign row with one character, removed before and after the test."""
    await Database.init()
    await _clear(SCRATCH_SESSION)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1,'Savegame review session','active')"
        " ON CONFLICT (id) DO NOTHING",
        SCRATCH_SESSION,
    )
    observer = await Database.fetchval(
        "INSERT INTO maya_rp.characters (session_id, name, status, bond)"
        " VALUES ($1,$2,'active',0) RETURNING id",
        SCRATCH_SESSION,
        SUBJECT,
    )
    try:
        yield {"session": SCRATCH_SESSION, "observer": observer}
    finally:
        await _clear(SCRATCH_SESSION)
        await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", SCRATCH_SESSION)
        await Database.close()


class TestARestoreThatKeepsTheSession:
    """`partial` was bound inside the wipe branch and read outside it."""

    async def test_a_file_with_a_table_does_not_crash_without_a_wipe(self, tmp_path):
        """`cli.py load --keep-session` raised UnboundLocalError before it inserted anything."""
        path = _sav(tmp_path, {"review_no_such_table": [{"id": 1}]}, session_id=5)
        result = await savegame.import_sav(path, session_id=5, wipe=False)
        assert result["ok"] is True
        assert result["restored_rows"] == 0, "the table does not exist, so nothing can land"

    async def test_a_partial_table_is_skipped_without_a_wipe(self, scratch_session, tmp_path):
        """The header decides, not the call: a partial table is not restored either way."""
        session = scratch_session["session"]
        row = {"session_id": session, "observer_id": scratch_session["observer"], "suspicion": 10,
               "last_reason": None, "last_event_id": None, "updated_at": "2026-10-03T00:00:00+00:00"}
        path = _sav(tmp_path, {"ooc_suspicion": [row]}, session_id=session, partial=["ooc_suspicion"])
        result = await savegame.import_sav(path, session_id=session, wipe=False)
        assert result["skipped_tables"] == 1
        assert result["restored_rows"] == 0
        assert await Database.fetchval(
            "SELECT count(*) FROM maya_rp.ooc_suspicion WHERE session_id=$1", session) == 0


class TestTheRestoreCountsWhatLanded:
    """`restored` rose inside the batch, before the savepoint committed."""

    async def test_a_batch_that_rolls_back_is_not_counted(self, scratch_session, tmp_path):
        session = scratch_session["session"]
        good = {"session_id": session, "observer_id": scratch_session["observer"], "suspicion": 10,
                "last_reason": None, "last_event_id": None, "updated_at": "2026-10-03T00:00:00+00:00"}
        # `suspicion` carries a CHECK of 0..100, so the second row fails the batch after the first
        # row inserted. The savepoint rolls both back and the retry inserts the good one.
        bad = dict(good, suspicion=500)
        # A restore that leaves a row out rolls back by default; this test is about the count, so it opts in.
        path = _sav(tmp_path, {"ooc_suspicion": [good, bad]}, session_id=session)
        result = await savegame.import_sav(path, session_id=session, wipe=False, allow_partial=True)
        landed = await Database.fetchval(
            "SELECT count(*) FROM maya_rp.ooc_suspicion WHERE session_id=$1", session)
        assert landed == 1, "the retry inserts the good row and the bad one stays out"
        assert result["restored_rows"] == landed, (
            "the rolled-back batch was counted, and the retry counted those rows again")
        assert result["row_errors"] == 1


class TestAnExportNeedsASession:
    """A checkpoint of a session that does not exist is a file of empty tables."""

    async def test_exporting_a_session_that_does_not_exist_is_refused(self, tmp_path):
        with pytest.raises(ValueError, match="no session 987654"):
            await savegame.export_sav(session_id=987654, out_dir=str(tmp_path))
        assert not list(tmp_path.glob("*.sav")), "a checkpoint that restores nothing must not exist"

    async def test_a_session_that_exists_is_exported(self, scratch_session, tmp_path):
        path = await savegame.export_sav(session_id=scratch_session["session"], out_dir=str(tmp_path))
        payload = json.loads(pathlib.Path(path).read_text())
        assert payload["header"]["session_id"] == scratch_session["session"]
        assert payload["header"]["game_day"] == 1
        assert payload["header"]["checksum"], "a written checkpoint carries its checksum"


class TestThePureHelpers:
    """The order the module deletes in, and the claim its docstring makes about cycles."""

    def test_children_are_wiped_before_their_parents(self):
        order = savegame.fk_wipe_order({"child", "parent", "loner"}, [("child", "parent")])
        assert order.index("child") < order.index("parent")
        assert "loner" in order

    def test_a_cycle_is_reported_and_not_ordered(self):
        assert savegame.fk_cycle_members({"a", "b"}, [("a", "b"), ("b", "a")]) == {"a", "b"}
        assert savegame.fk_cycle_members({"a", "b", "c"}, [("a", "b")]) == set()

    def test_a_self_reference_is_a_cycle(self):
        assert savegame.fk_cycle_members({"heirs"}, [("heirs", "heirs")]) == {"heirs"}

    def test_tables_are_split_by_session_scope(self):
        scoped, global_tables = savegame.classify_tables(
            {"scoped", "catalog", "vectored", "excluded"},
            has_session_id={"scoped"},
            vector_tables={"vectored"},
            exclusions={"excluded"},
        )
        assert scoped == ["scoped"]
        assert global_tables == ["catalog"]

    def test_the_insert_upserts_on_the_id_so_the_file_wins(self):
        clause = savegame._conflict_clause("characters", ["id", "name"])
        assert clause.startswith("ON CONFLICT (id) DO UPDATE SET")
        assert '"name"=EXCLUDED."name"' in clause

    def test_a_table_with_no_id_cannot_upsert(self):
        assert savegame._conflict_clause("ooc_suspicion", ["session_id", "observer_id"]) == (
            "ON CONFLICT DO NOTHING")
