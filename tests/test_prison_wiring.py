"""The door prisoners come through, and a tier that says it does not exist.

Eleven entry points of prison.py had no caller, and they are the module's whole surface. The live
paths (interrogate, check_conversion, process_escapes) could only ever run against prisoners nothing
could create, because resolve_capture was unreachable.

`get_interrogation_tier_info` fell back to `standard` for any unknown name, so a typo read as a real
tier and two different names printed the same configuration.
"""
from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest_asyncio  # noqa: E402

from core.db import Database  # noqa: E402
from modules import prison  # noqa: E402

#: Scratch campaign. Sessions 3 and 5 are frozen reference data and are never written.
SESSION = 900 + os.getpid() % 100


async def _purge(session_id: int) -> None:
    """Remove the scratch session's rows in foreign-key order."""
    await Database.execute("DELETE FROM maya_rp.interrogation_log WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.prisoners WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", session_id)


@pytest_asyncio.fixture(autouse=True)
async def _scratch_session():
    """Create the scratch `sessions` row, and remove everything it owns afterwards."""
    await Database.init()
    await _purge(SESSION)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1,'Prison wiring scratch','active') "
        "ON CONFLICT DO NOTHING", SESSION)
    try:
        yield
    finally:
        await Database.init()
        await _purge(SESSION)
        await Database.close()


class TestTheDoor:
    async def test_capture_creates_prisoners_and_they_can_be_released(self):
        await Database.init()
        rows = await prison.resolve_capture(5, "Iron Concord", session_id=SESSION)
        try:
            assert len(rows) == 5, rows
            generic = "Iron Concord Soldier"
            assert any(r.get("name") != generic for r in rows), (
                f"every capture is generic, so the named-officer rule is not running: {rows}")
            held = await Database.fetchval(
                "SELECT count(*) FROM maya_rp.prisoners WHERE session_id=$1", SESSION)
            assert held == 5, held
        finally:
            await Database.execute(
                "DELETE FROM maya_rp.interrogation_log WHERE prisoner_id IN"
                " (SELECT id FROM maya_rp.prisoners WHERE session_id=$1)", SESSION)
            await Database.execute("DELETE FROM maya_rp.prisoners WHERE session_id=$1", SESSION)
            await Database.close()

    async def test_capture_of_nobody_creates_nothing(self):
        await Database.init()
        rows = await prison.resolve_capture(0, "Iron Concord", session_id=SESSION)
        assert rows == [], rows
        await Database.close()


class TestTheTier:
    def test_a_real_tier_returns_its_config(self):
        assert prison.get_interrogation_tier_info("brutal")["intel_multiplier"] == 1.0

    def test_an_unknown_tier_says_so(self):
        out = prison.get_interrogation_tier_info("soft")
        assert "unknown interrogation tier" in out.get("error", ""), out
        assert "brutal" in out.get("available", []), out
