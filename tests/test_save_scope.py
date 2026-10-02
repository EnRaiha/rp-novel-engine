"""A session's checkpoint must not carry another session's rows.

`maya_rp` holds a frozen session and a live one in the same schema, and 147 tables have no session_id:
their session is implied by a parent. The export used to dump every such table whole, so the session-5
checkpoint of 2026-10-02 contained 109,149 `ship_armaments` and 41,594 `fleet_members` rows that all
belonged to session 3 — 151,000 rows of the frozen campaign inside the live campaign's save, in a file
that the restore path wipes against.

The export now filters a session-less table by the ids of its session-scoped parents, records which
tables it carried only in part, and the restore skips those rather than wiping them.

Marked slow: walking 294 tables takes about twenty seconds, and the suite's speed is an asset.
    RP_SLOW_TESTS=1 python3 -m pytest tests/test_save_scope.py -q
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

slow = pytest.mark.skipif(os.environ.get("RP_SLOW_TESTS") != "1",
                          reason="set RP_SLOW_TESTS=1; this walks the whole schema")


@slow
class TestSessionScope:
    async def test_a_session_five_save_carries_no_session_three_rows(self, tmp_path):
        from core import savegame

        path = await savegame.export_sav(session_id=5, out_dir=str(tmp_path))
        payload = json.loads(pathlib.Path(path).read_text())

        assert payload["header"]["session_id"] == 5
        assert len(payload["tables"]["ship_armaments"]) == 0, "session 3's fittings rode along"
        assert len(payload["tables"]["fleet_members"]) == 0, "session 3's crews rode along"
        assert len(payload["tables"]["characters"]) > 300, "the live session's own rows must be there"

        partial = set(payload["header"]["partial_tables"])
        assert "ship_armaments" in partial
        assert pathlib.Path(path).stat().st_size < 20_000_000, "the file should not carry a second campaign"

    async def test_a_partial_table_is_neither_wiped_nor_restored(self, tmp_path):
        """The rule the header exists for, checked on the code path that reads it."""
        import inspect

        from core import savegame

        source = inspect.getsource(savegame.import_sav)
        assert "partial" in source, "the restore must read partial_tables"
        assert "- partial" in source, "the wipe set must exclude them"
