"""A save file names its novel, and a restore refuses a file from another novel.

One schema holds two campaigns: session 3 plays `tkg-setia-kingdom` and session 5 plays
`tkg-the-sunrise` (migration 137). A `.sav` carries one session's rows, and the restore wipes the
target before it loads, so a file from another novel merges two stories the engine keeps apart. The
header now names the novel, `NovelMismatch` refuses the crossing, and a file written before the
header carried a novel resolves through its own `session_id` instead of being refused.

`university_campuses`, `academy_campuses` and `pirate_zones` are what make a session-5 file free of
session-3 rows: migration 138 gave each one a `session_id`, so the export filters them by session
instead of dumping them whole. Before that, a session-5 file carried session 3's 37 campuses and 25
zones.

Nothing here writes session 3 or 5. The export of session 5 and the novel read of session 3 are
reads; every restore that reaches `_restore` passes `wipe=False` with `"tables": {}` and touches no
row; the one call with `wipe=True` is refused before `_restore` runs; and the one `UPDATE` names the
scratch row the fixture deletes.
"""
from __future__ import annotations

import asyncio
import contextlib
import io
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import savegame  # noqa: E402
from core import session  # noqa: E402
from core.db import Database  # noqa: E402
from scripts import cli  # noqa: E402
from scripts import gm_maint  # noqa: E402
from scripts import relive_session  # noqa: E402

#: The novel each live session plays, from migration 137. No test writes session 3 or 5.
SETIA = "tkg-setia-kingdom"
SUNRISE = "tkg-the-sunrise"
SCRATCH = "scratch"


class _LoadDatabase:
    """`Database` for `cli.py load`: no pool is opened, and every close is counted."""

    def __init__(self):
        self.opened = 0
        self.closed = 0

    async def init(self):
        self.opened += 1

    async def close(self):
        self.closed += 1


def _arm_load(monkeypatch, argv, behaviour):
    """Run `cli.cmd_load` against a recording `import_sav` and a pool-free `Database`.

    @param behaviour - what the stub does: return a result dict, or raise.
    @returns `(the keyword arguments the loader passed, the stub Database, stdout, exit code)`.
    """
    seen: dict = {}
    db = _LoadDatabase()

    async def fake_import(path, **kwargs):
        seen.update({"path": path, **kwargs})
        return await behaviour(path, **kwargs)

    monkeypatch.setattr(cli, "Database", db)
    monkeypatch.setattr(savegame, "import_sav", fake_import)
    own_argv = cli.sys.argv
    cli.sys.argv = ["cli.py", *argv]
    out, code = io.StringIO(), None
    try:
        with contextlib.redirect_stdout(out):
            asyncio.run(cli.cmd_load())
    except SystemExit as exc:
        code = exc.code
    finally:
        cli.sys.argv = own_argv
    return seen, db, out.getvalue(), code


def _sav(tmp_path: pathlib.Path, *, session_id, novel_id=None, tables: dict | None = None,
         name: str = "novel.sav") -> str:
    """A hand-written .sav, so the header holds exactly the keys a test needs.

    `novel_id` is omitted when None: that is the file the export wrote before this change.
    """
    header = {"format": savegame.FORMAT, "version": savegame.SAV_VERSION, "session_id": session_id}
    if novel_id is not None:
        header["novel_id"] = novel_id
    path = tmp_path / name
    path.write_text(json.dumps({"header": header, "tables": tables or {}}), encoding="utf-8")
    return str(path)


async def _export(tmp_path: pathlib.Path, session_id: int) -> dict:
    path = await savegame.export_sav(session_id=session_id, out_dir=str(tmp_path))
    return json.loads(pathlib.Path(path).read_text())


# ── 1. the header names the novel ─────────────────────────────────────────────────────────────

class TestTheHeaderNamesTheNovel:
    async def test_a_session_five_export_names_its_novel(self, tmp_path):
        payload = await _export(tmp_path, 5)
        assert payload["header"]["session_id"] == 5
        assert payload["header"]["novel_id"] == await session.novel_of(5)
        assert payload["header"]["novel_id"] == SUNRISE

    async def test_the_checksum_covers_the_novel(self, tmp_path):
        """A rewritten novel is a changed file: `novel_id` sits inside the checksum."""
        payload = await _export(tmp_path, 5)
        assert savegame._verify_checksum(payload) is True
        payload["header"]["novel_id"] = SETIA
        assert savegame._verify_checksum(payload) is False


# ── 2. a novel mismatch is refused ────────────────────────────────────────────────────────────

class TestAnotherNovelIsRefused:
    def test_the_cli_handler_covers_the_refusal(self):
        """`scripts/cli.py load` catches `SessionMismatch`, so the novel guard must be one of those.

        The CLI is not this unit's file: it reports both refusals through the one handler.
        """
        assert issubclass(savegame.NovelMismatch, savegame.SessionMismatch)

    async def test_a_file_from_another_novel_is_refused(self, scratch_campaign, tmp_path):
        path = _sav(tmp_path, session_id=3, novel_id=SETIA)
        with pytest.raises(savegame.NovelMismatch) as caught:
            await savegame.import_sav(path, session_id=scratch_campaign, wipe=False,
                                      allow_session_mismatch=True)
        message = str(caught.value)
        assert SETIA in message, message
        assert SCRATCH in message, message
        assert "allow_novel_mismatch" in message, "the refusal must name the way through"
        assert caught.value.target_novel == SCRATCH

    async def test_the_refusal_lands_before_the_restore_runs(self, scratch_campaign, tmp_path,
                                                             monkeypatch):
        """A wipe runs inside `_restore`, so the refusal must precede the call, not the commit."""
        calls = []

        async def spy(*args, **kwargs):
            calls.append(args)

        monkeypatch.setattr(savegame, "_restore", spy)
        path = _sav(tmp_path, session_id=3, novel_id=SETIA)
        with pytest.raises(savegame.NovelMismatch):
            await savegame.import_sav(path, session_id=scratch_campaign, wipe=True,
                                      allow_session_mismatch=True)
        assert calls == [], "the restore ran for a file the guard had already refused"

    async def test_the_flag_restores_the_other_novel(self, scratch_campaign, tmp_path):
        path = _sav(tmp_path, session_id=3, novel_id=SETIA)
        result = await savegame.import_sav(path, session_id=scratch_campaign, wipe=False,
                                           allow_session_mismatch=True,
                                           allow_novel_mismatch=True)
        assert result["ok"] is True
        assert result["session_id"] == scratch_campaign

    def test_the_cli_load_verb_refuses_the_other_novel_by_default(self, monkeypatch, tmp_path):
        """`NovelMismatch` names `--allow-novel-mismatch`; the verb must offer that switch.

        The refusal arrives through the loader's own handler, so the operator reads it as a refused
        load rather than a traceback. `--allow-session-mismatch` is passed here and does not cover it:
        the two switches are separate refusals.
        """
        path = _sav(tmp_path, session_id=3, novel_id=SETIA)

        async def refuse(_path, **kwargs):
            raise savegame.NovelMismatch(SETIA, 201, SUNRISE)

        seen, db, out, code = _arm_load(
            monkeypatch, ["load", path, "--allow-session-mismatch"], refuse)

        assert code is None, "a refusal is reported, not raised out of the verb"
        assert "LOAD REFUSED" in out, out
        assert SETIA in out and SUNRISE in out, out
        assert db.closed == 1, "the loader left the pool open"
        assert seen["allow_novel_mismatch"] is False, seen
        assert seen["allow_session_mismatch"] is True, seen
        assert seen["path"] == path

    def test_the_cli_load_verb_passes_the_flag_through(self, monkeypatch, tmp_path):
        """With the switch the loader asks the restore for the crossing, and reports it."""
        path = _sav(tmp_path, session_id=3, novel_id=SETIA)

        async def restore(_path, **kwargs):
            return {"ok": True, "restored_rows": 12, "session_id": 201, "game_day": 34}

        seen, db, out, code = _arm_load(
            monkeypatch, ["load", path, "--keep-session", "--allow-session-mismatch",
                          "--allow-novel-mismatch"], restore)

        assert code is None and "LOADED: 12 rows" in out, out
        assert seen["allow_novel_mismatch"] is True, seen
        assert seen["wipe"] is False, "the verb calls --keep-session wipe=False"
        assert seen["allow_session_mismatch"] is True, seen
        assert seen["force"] is False, seen
        assert db.closed == 1

    async def test_a_file_whose_novel_the_session_left_is_refused(self, scratch_campaign,
                                                                  tmp_path):
        """A binding moved after the write leaves a file naming a novel its session has left."""
        await Database.execute("UPDATE maya_rp.sessions SET novel_id=$2 WHERE id=$1",
                               scratch_campaign, SUNRISE)
        path = _sav(tmp_path, session_id=scratch_campaign, novel_id=SCRATCH)
        with pytest.raises(savegame.NovelMismatch) as caught:
            await savegame.import_sav(path, session_id=scratch_campaign, wipe=False)
        assert caught.value.target_novel == SUNRISE

    async def test_a_file_with_a_novel_is_not_refused_by_its_own_session(self, scratch_campaign,
                                                                        tmp_path):
        await Database.execute("UPDATE maya_rp.sessions SET novel_id=$2 WHERE id=$1",
                               scratch_campaign, SUNRISE)
        path = _sav(tmp_path, session_id=scratch_campaign, novel_id=SUNRISE)
        result = await savegame.import_sav(path, session_id=scratch_campaign, wipe=False)
        assert result["ok"] is True


# ── 3. a file written before the header carried a novel ───────────────────────────────────────

class TestAPreNovelFileResolvesThroughItsSession:
    async def test_an_old_file_of_the_target_session_restores(self, scratch_campaign, tmp_path):
        path = _sav(tmp_path, session_id=scratch_campaign)
        result = await savegame.import_sav(path, session_id=scratch_campaign, wipe=False)
        assert result["ok"] is True, "an old file must not be refused for a key it never held"

    async def test_the_files_own_session_resolves_the_novel(self, scratch_campaign, tmp_path):
        """Session 3 plays Setia, so the file carries Setia and the Setia target accepts it."""
        await Database.execute("UPDATE maya_rp.sessions SET novel_id=$2 WHERE id=$1",
                               scratch_campaign, SETIA)
        path = _sav(tmp_path, session_id=3)
        result = await savegame.import_sav(path, session_id=scratch_campaign, wipe=False,
                                           allow_session_mismatch=True)
        assert result["ok"] is True

    async def test_a_target_of_another_novel_refuses_the_resolved_novel(self, scratch_campaign,
                                                                        tmp_path):
        """The resolution must decide the check, not silence it: scratch is not Setia."""
        path = _sav(tmp_path, session_id=3)
        with pytest.raises(savegame.NovelMismatch) as caught:
            await savegame.import_sav(path, session_id=scratch_campaign, wipe=False,
                                      allow_session_mismatch=True)
        assert caught.value.file_novel == SETIA

    async def test_a_file_naming_a_missing_session_is_not_refused_for_its_novel(self,
                                                                                scratch_campaign,
                                                                                tmp_path):
        """No row names no novel, and a file the session guard already passed is not guessed at."""
        path = _sav(tmp_path, session_id=987654)
        result = await savegame.import_sav(path, session_id=scratch_campaign, wipe=False,
                                           allow_session_mismatch=True)
        assert result["ok"] is True


# ── 4. a session-5 file carries no session-3 row ──────────────────────────────────────────────

class TestASessionFiveFileCarriesOneSession:
    """`university_campuses`, `academy_campuses` and `pirate_zones` are the tables that make this
    true: each carries a `session_id` since migration 138, so the export filters the three."""

    async def test_a_session_five_export_carries_no_session_three_row(self, tmp_path):
        payload = await _export(tmp_path, 5)
        for table in ("university_campuses", "academy_campuses", "pirate_zones"):
            rows = payload["tables"][table]
            ids = {row.get("session_id") for row in rows}
            assert 3 not in ids, f"session 3's rows ride in a session-5 file: {table}"
            assert ids <= {5}, f"{table} carries a row that is not session 5's: {sorted(ids)}"

    async def test_every_scoped_row_in_the_file_names_the_one_session(self, tmp_path):
        payload = await _export(tmp_path, 5)
        foreign = {}
        for table, rows in payload["tables"].items():
            if not isinstance(rows, list):
                continue
            ids = {row["session_id"] for row in rows if row.get("session_id") not in (None, 5)}
            if ids:
                foreign[table] = sorted(ids)
        assert foreign == {}, f"a session-5 file carries another session's rows: {foreign}"


# ── 5. relive_session.py takes the novel of the session it replays ────────────────────────────

class _FakeDb:
    """Stands in for `core.db.Database`: canned answers, recorded writes, no connection."""

    def __init__(self, *, novel_exists: bool = True, target_novel: str | None = None):
        self.novel_exists = novel_exists
        self.target_novel = target_novel
        self.executed: list[str] = []
        self.closed = 0

    async def init(self):
        return None

    async def close(self):
        self.closed += 1

    async def fetchval(self, sql, *args):
        if "FROM maya_rp.novels" in sql:
            return args[0] if self.novel_exists else None
        if "FROM maya_rp.sessions" in sql:
            return self.target_novel
        return 0

    async def fetch(self, sql, *args):
        if "information_schema.columns" in sql:
            return [{"column_name": c} for c in ("id", "session_id", "name", "role")]
        return []

    async def execute(self, sql, *args):
        self.executed.append(sql)
        return "INSERT 0 1"


class TestReliveSessionNamesTheNovel:
    """`scripts/relive_session.py` reads `sys.argv`, so the tests hand it one."""

    def test_the_novel_flag_is_required(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["relive_session.py", "--from", "3", "--to", "905",
                                          "--dry-run"])
        with pytest.raises(SystemExit) as caught:
            asyncio.run(relive_session.main())
        assert caught.value.code == 2, "argparse exits 2 on a missing required option"
        assert "--novel" in capsys.readouterr().err

    async def test_a_novel_that_does_not_match_the_target_is_refused(self, monkeypatch, capsys):
        db = _FakeDb(target_novel=SETIA)
        monkeypatch.setattr(relive_session, "Database", db)
        monkeypatch.setattr(sys, "argv", ["relive_session.py", "--from", "3", "--to", "905",
                                          "--novel", SUNRISE])
        code = await relive_session.main()
        assert code == 2
        assert SETIA in capsys.readouterr().err, "the refusal must name the novel the target plays"
        assert db.executed == [], "a refused novel must not write the target session"

    async def test_a_target_that_plays_the_novel_is_cloned(self, monkeypatch, capsys):
        db = _FakeDb(target_novel=SUNRISE)
        monkeypatch.setattr(relive_session, "Database", db)
        monkeypatch.setattr(sys, "argv", ["relive_session.py", "--from", "3", "--to", "905",
                                          "--novel", SUNRISE, "--dry-run"])
        code = await relive_session.main()
        assert code == 0
        assert f"novel {SUNRISE}" in capsys.readouterr().out

    async def test_a_new_target_lands_with_the_novel(self, monkeypatch):
        db = _FakeDb(target_novel=None)
        monkeypatch.setattr(relive_session, "Database", db)
        monkeypatch.setattr(sys, "argv", ["relive_session.py", "--from", "3", "--to", "905",
                                          "--novel", SUNRISE, "--dry-run"])
        code = await relive_session.main()
        assert code == 0
        inserts = [sql for sql in db.executed if "INSERT INTO maya_rp.sessions" in sql]
        assert inserts, "a target session with no row must be created"
        assert "novel_id" in inserts[0]

    async def test_an_unknown_novel_is_refused(self, monkeypatch, capsys):
        db = _FakeDb(novel_exists=False)
        monkeypatch.setattr(relive_session, "Database", db)
        monkeypatch.setattr(sys, "argv", ["relive_session.py", "--from", "3", "--to", "905",
                                          "--novel", "nope"])
        code = await relive_session.main()
        assert code == 2
        assert "no novel" in capsys.readouterr().err


# ── 6. gm_maint.py names the novel beside the arc ─────────────────────────────────────────────

class TestGmMaintNamesTheNovel:
    def test_status_prints_the_novel_beside_the_arc(self, monkeypatch, capsys):
        monkeypatch.setattr(gm_maint.s, "active_arc", lambda: 5)
        monkeypatch.setattr(gm_maint, "novel_label", lambda arc: SUNRISE)
        assert gm_maint.main(["status"]) == 0
        lines = capsys.readouterr().out.splitlines()
        assert "arc: 5" in lines, lines
        assert lines[lines.index("arc: 5") + 1] == f"novel: {SUNRISE}", lines

    def test_the_arc_verb_prints_the_novel_too(self, monkeypatch, capsys):
        monkeypatch.setattr(gm_maint.s, "active_arc", lambda: 5)
        monkeypatch.setattr(gm_maint, "novel_label", lambda arc: SUNRISE)
        assert gm_maint.main(["arc"]) == 0
        lines = capsys.readouterr().out.splitlines()
        assert lines[-1] == f"novel: {SUNRISE}", lines

    def test_an_arc_of_none_names_no_novel(self):
        assert gm_maint.novel_label(None) == "none"

    def test_the_label_reads_the_sessions_novel(self):
        assert gm_maint.novel_label(5) == SUNRISE
