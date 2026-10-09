"""The bug war: a session that filters, and gates that hold across campaigns.

Six entry points of space_horror.py had no caller. The module carries the bug war, which the
five-plane gradient puts one plane from the human core, so nothing could read a threat, apply a
containment measure or launch an eradication while the tick advanced infestations.

`get_active_threats(session_id)` was the defect worth keeping: it took a session and ran
`SELECT * FROM infestation_threats` with no WHERE at all, because the view had no session_id to filter
on. Migration 130 added the column.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import Database  # noqa: E402
from modules import space_horror as sh  # noqa: E402


class TestTheParametersMeanSomething:
    async def test_active_threats_filters_on_the_session_it_is_given(self):
        """The mutation this exists for: removing the WHERE clause. Counts differ per session, so a
        session with no threats must not be able to see another session's."""
        await Database.init()
        threats_3 = await sh.get_active_threats(3)
        threats_5 = await sh.get_active_threats(5)
        for threat in threats_5:
            assert threat.get("session_id") in (None, 5), threat
        for threat in threats_3:
            assert threat.get("session_id") in (None, 3), threat
        await Database.close()

    async def test_an_infestation_from_another_session_is_refused(self, scratch_session):
        """The infestation lives in the scratch session. A session that owns no rows asks for it."""
        await Database.init()
        stage = await Database.fetchval("SELECT id FROM maya_rp.infestation_stages LIMIT 1")
        if stage is None:
            await Database.close()
            return
        await Database.execute(
            "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1, 'space-horror wiring scratch', 'active')"
            " ON CONFLICT (id) DO NOTHING", scratch_session)
        other = scratch_session + 1000
        row = await Database.fetchrow(
            "INSERT INTO maya_rp.infestation_instances"
            " (session_id, stage_id, biomass, spread_progress, status)"
            " VALUES ($1, $2, 1, 0, 'active') RETURNING id", scratch_session, stage)
        try:
            detail = await sh.get_infestation_detail(row["id"], other)
            assert detail == {}, "the detail read leaks across sessions"
            refused = await sh.apply_containment(other, row["id"], "Flame Wall")
            assert f"not found in session {other}" in refused.get("error", ""), refused
        finally:
            await Database.execute(
                "DELETE FROM maya_rp.infestation_instances WHERE id=$1", row["id"])
            await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", scratch_session)
            await Database.close()


class TestTheCatalogues:
    async def test_measures_and_assets_answer(self):
        await Database.init()
        measures = await sh.get_containment_measures()
        assets = await sh.get_bug_war_assets()
        assert measures, "no containment measures defined"
        assert assets, "no bug war assets defined"
        await Database.close()
