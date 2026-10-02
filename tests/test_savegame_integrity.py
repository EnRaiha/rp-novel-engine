"""A checkpoint that is missing a table is worse than no checkpoint.

`export_sav` used to store `{"__error__": ...}` in place of a table that failed to read, log a line,
and write the file anyway. The restore path wipes every table before loading, so that table comes back
empty and nobody notices until the data is needed. Both directions now refuse.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import savegame  # noqa: E402


class TestExportRefuses:
    async def test_a_failing_table_writes_nothing(self, tmp_path, monkeypatch):
        real_fetch = savegame.Database.fetch

        async def flaky(sql, *args):
            if "maya_rp.territory " in str(sql) or str(sql).endswith("maya_rp.territory"):
                raise RuntimeError("simulated read failure")
            return await real_fetch(sql, *args)

        monkeypatch.setattr(savegame.Database, "fetch", flaky)

        with pytest.raises(savegame.SaveIncomplete) as caught:
            await savegame.export_sav(session_id=3, out_dir=str(tmp_path))
        assert "territory" in str(caught.value)
        assert not list(tmp_path.glob("*.sav")), "a partial snapshot must not be written"

    def test_the_error_names_the_tables(self):
        exc = savegame.SaveIncomplete({"territory": "boom", "ports": "boom"})
        assert "2 table(s)" in str(exc)
        assert "ports" in str(exc) and "territory" in str(exc)


class TestImportRefuses:
    async def test_a_file_with_an_error_stub_is_refused(self, tmp_path, monkeypatch):
        payload = {
            "header": {"format": savegame.FORMAT, "version": savegame.SAV_VERSION, "session_id": 3},
            "tables": {"territory": {"__error__": "read failed"}, "ports": []},
        }
        path = tmp_path / "broken.sav"
        path.write_text(json.dumps(payload), encoding="utf-8")
        monkeypatch.setattr(savegame.Database, "init", lambda: _noop())
        with pytest.raises(savegame.SaveIncomplete) as caught:
            await savegame.import_sav(str(path), session_id=3, wipe=False)
        assert "territory" in str(caught.value)


async def _noop():
    return None


async def _value(value):
    return value


class TestSessionMismatch:
    """A save restored into the wrong session wipes the target and does not put it back.

    The rows keep their own session_id on the way in, so the mismatch is not a rename: it is a wipe
    followed by either a primary-key conflict or another session's rows appearing as themselves.
    """

    async def test_a_mismatched_session_is_refused(self, tmp_path, monkeypatch):
        payload = {"header": {"format": savegame.FORMAT, "version": savegame.SAV_VERSION,
                              "session_id": 3}, "tables": {}}
        path = tmp_path / "three.sav"
        path.write_text(json.dumps(payload), encoding="utf-8")
        monkeypatch.setattr(savegame.Database, "init", lambda: _noop())
        with pytest.raises(savegame.SessionMismatch) as caught:
            await savegame.import_sav(str(path), session_id=5, wipe=True)
        assert "session 3" in str(caught.value) and "session 5" in str(caught.value)

    async def test_the_same_session_is_not_refused(self, tmp_path, monkeypatch):
        payload = {"header": {"format": savegame.FORMAT, "version": savegame.SAV_VERSION,
                              "session_id": 5}, "tables": {}}
        path = tmp_path / "five.sav"
        path.write_text(json.dumps(payload), encoding="utf-8")
        result = await savegame.import_sav(str(path), session_id=5, wipe=False)
        assert result.get("session_id") == 5

    async def test_a_forced_mismatch_proceeds(self, tmp_path, monkeypatch):
        payload = {"header": {"format": savegame.FORMAT, "version": savegame.SAV_VERSION,
                              "session_id": 3}, "tables": {}}
        path = tmp_path / "three.sav"
        path.write_text(json.dumps(payload), encoding="utf-8")
        result = await savegame.import_sav(str(path), session_id=5, wipe=False,
                                           allow_session_mismatch=True)
        assert result.get("session_id") == 5
