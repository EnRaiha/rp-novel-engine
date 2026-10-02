"""The door prisoners come through, and a tier that says it does not exist.

Eleven entry points of prison.py had no caller, and they are the module's whole surface. The live
paths (interrogate, check_conversion, process_escapes) could only ever run against prisoners nothing
could create, because resolve_capture was unreachable.

`get_interrogation_tier_info` fell back to `standard` for any unknown name, so a typo read as a real
tier and two different names printed the same configuration.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import Database  # noqa: E402
from modules import prison  # noqa: E402


class TestTheDoor:
    async def test_capture_creates_prisoners_and_they_can_be_released(self):
        await Database.init()
        rows = await prison.resolve_capture(5, "Iron Concord", session_id=5)
        try:
            assert len(rows) == 5, rows
            generic = "Iron Concord Soldier"
            assert any(r.get("name") != generic for r in rows), (
                f"every capture is generic, so the named-officer rule is not running: {rows}")
            held = await Database.fetchval(
                "SELECT count(*) FROM maya_rp.prisoners WHERE session_id=5")
            assert held == 5, held
        finally:
            await Database.execute(
                "DELETE FROM maya_rp.interrogation_log WHERE prisoner_id IN"
                " (SELECT id FROM maya_rp.prisoners WHERE session_id=5)")
            await Database.execute("DELETE FROM maya_rp.prisoners WHERE session_id=5")
            await Database.close()

    async def test_capture_of_nobody_creates_nothing(self):
        await Database.init()
        rows = await prison.resolve_capture(0, "Iron Concord", session_id=5)
        assert rows == [], rows
        await Database.close()


class TestTheTier:
    def test_a_real_tier_returns_its_config(self):
        assert prison.get_interrogation_tier_info("brutal")["intel_multiplier"] == 1.0

    def test_an_unknown_tier_says_so(self):
        out = prison.get_interrogation_tier_info("soft")
        assert "unknown interrogation tier" in out.get("error", ""), out
        assert "brutal" in out.get("available", []), out
