"""The case file: a clue belongs to its own campaign, and the chain runs end to end.

`create_investigation`, `add_clue`, `deduce` and `generate_red_herring` had no production caller at
all, and `run_tick` ages cases that never exist — the feature had never been used. Reviewing `add_clue`
before wiring found that nothing checked the investigation belonged to the session, so a clue could be
filed against another campaign's case.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import Database  # noqa: E402
from modules import mystery  # noqa: E402


async def _case(session_id: int):
    await Database.init()
    out = await mystery.create_investigation(session_id, "pytest case")
    return out["investigation_id"]


async def _drop(investigation_id: int) -> None:
    await Database.execute("DELETE FROM maya_rp.clues WHERE investigation_id=$1", investigation_id)
    await Database.execute("DELETE FROM maya_rp.investigation_log WHERE investigation_id=$1", investigation_id)
    await Database.execute("DELETE FROM maya_rp.investigations WHERE id=$1", investigation_id)
    await Database.close()


class TestTheChain:
    async def test_a_case_takes_a_clue_and_deduces(self, scratch_campaign):
        investigation_id = await _case(scratch_campaign)
        try:
            added = await mystery.add_clue(scratch_campaign, investigation_id, "A witness remembers a grey coat.")
            assert added.get("clue_id"), added
            deduced = await mystery.deduce(scratch_campaign, investigation_id, "The coat places her on the dock.")
            assert deduced.get("error") is None, deduced
            assert deduced.get("investigation_id") == investigation_id
        finally:
            await _drop(investigation_id)


class TestOwnership:
    async def test_a_clue_cannot_be_filed_against_another_session(self, scratch_campaign):
        """The insert never checked this, so one campaign could write into another's case."""
        other = 900 + (scratch_campaign - 900 + 50) % 100
        investigation_id = await _case(scratch_campaign)
        try:
            refused = await mystery.add_clue(other, investigation_id, "leaked clue")
            assert f"belongs to session {scratch_campaign}" in refused.get("error", ""), refused
            count = await Database.fetchval(
                "SELECT count(*) FROM maya_rp.clues WHERE investigation_id=$1", investigation_id)
            assert count == 0, "the refused clue was written anyway"
        finally:
            await _drop(investigation_id)

    async def test_a_clue_for_a_case_that_does_not_exist_is_refused(self, scratch_campaign):
        await Database.init()
        refused = await mystery.add_clue(scratch_campaign, 999_999, "nowhere")
        assert "does not exist" in refused.get("error", ""), refused
        await Database.close()
