"""Wonders: resolving your own encounters, and an overview that knows its session.

Four entry points of space_wonders.py had no caller: the overview and the three actions that resolve a
discovery or an encounter. All three lookups went by id with no session filter, so one campaign could
hunt, tame or explore another's encounter, and the overview listed every campaign's planets.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import Database  # noqa: E402
from modules import space_wonders as sw  # noqa: E402


async def _discovery(session_id: int):
    anomaly = await Database.fetchval(
        "SELECT id FROM maya_rp.space_anomalies ORDER BY id LIMIT 1")
    assert anomaly, "no anomaly to discover"
    return await Database.fetchrow(
        "INSERT INTO maya_rp.discoveries (session_id, type, target_id, explored)"
        " VALUES ($1, 'anomaly', $2, FALSE) RETURNING id", session_id, anomaly)


class TestTheGate:
    async def test_a_discovery_from_another_session_is_refused(self):
        await Database.init()
        row = await _discovery(3)
        try:
            refused = await sw.explore_anomaly(row["id"], 100, 5)
            assert "not found in session 5" in refused.get("error", ""), refused
            explored = await Database.fetchval(
                "SELECT explored FROM maya_rp.discoveries WHERE id=$1", row["id"])
            assert explored is False, "the refused call explored it anyway"
        finally:
            await Database.execute("DELETE FROM maya_rp.discoveries WHERE id=$1", row["id"])
            await Database.close()

    async def test_a_session_can_resolve_its_own_discovery(self):
        await Database.init()
        row = await _discovery(5)
        try:
            out = await sw.explore_anomaly(row["id"], 100, 5)
            assert out.get("error") is None, out
            explored = await Database.fetchval(
                "SELECT explored FROM maya_rp.discoveries WHERE id=$1", row["id"])
            assert explored is True, out
        finally:
            await Database.execute("DELETE FROM maya_rp.discoveries WHERE id=$1", row["id"])
            await Database.close()


class TestTheOverview:
    async def test_the_overview_counts_planets_per_session(self):
        await Database.init()
        for_5 = await sw.get_wonders_overview(5)
        for_3 = await sw.get_wonders_overview(3)
        assert isinstance(for_5.get("planets"), list)
        assert len(for_5["planets"]) != len(for_3["planets"]) or len(for_3["planets"]) == 0, (
            "both sessions returned the same planets, which means neither was filtered")
        await Database.close()

    async def test_the_catalogues_are_galaxy_wide_not_session_scoped(self):
        """Animals and anomalies describe the galaxy, so both sessions see the same list."""
        await Database.init()
        a5 = await sw.get_wonders_overview(5)
        a3 = await sw.get_wonders_overview(3)
        assert len(a5["animals"]) == len(a3["animals"]), "the animal catalogue is filtered by session"
        assert len(a5["anomalies"]) == len(a3["anomalies"]), "the anomaly catalogue is filtered"
        await Database.close()
