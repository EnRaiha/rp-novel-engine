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
