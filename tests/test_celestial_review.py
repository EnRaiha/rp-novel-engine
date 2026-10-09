"""Celestial module review: what reading `modules/celestial.py` in full turned up.

Four fixes. Every row this file creates belongs to `scratch_campaign`, which clears them afterwards.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from core.db import Database  # noqa: E402
from modules import celestial  # noqa: E402

A, B, C = "review-alpha", "review-beta", "review-gamma"


async def _territory(sid, name, status="lost", fleet=0, faction="Iron Concord"):
    return await Database.fetchval(
        "INSERT INTO maya_rp.territory (id, session_id, system_name, controlling_faction, status, "
        "fleet_presence) "
        "VALUES ((SELECT COALESCE(MAX(id), 0) + 1 FROM maya_rp.territory), $1, $2, $3, $4, $5) "
        "RETURNING id",
        sid, name, faction, status, fleet)


async def _lane(sid, origin, destination, threat=1):
    return await Database.fetchval(
        "INSERT INTO maya_rp.space_lanes (id, session_id, origin, destination, lane_type, threat_level) "
        "VALUES ((SELECT COALESCE(MAX(id), 0) + 1 FROM maya_rp.space_lanes), $1, $2, $3, 'trade', $4) "
        "RETURNING id",
        sid, origin, destination, threat)


async def _drop(sid):
    await Database.execute("DELETE FROM maya_rp.space_lanes WHERE session_id = $1", sid)
    await Database.execute(
        "DELETE FROM maya_rp.territory WHERE session_id = $1 AND system_name LIKE 'review-%'", sid)


class TestTheFilterSet:
    async def test_a_filter_the_query_cannot_answer_is_refused(self, scratch_campaign):
        """`sector` and `threat` are not columns the SELECT reads, and they matched nothing silently."""
        await Database.init()
        try:
            out = await celestial.query_systems(scratch_campaign, {"sector": "Alpha"})
            assert "sector" in out.get("error", ""), out
            assert out["available"] == sorted(celestial.SYSTEM_FILTER_KEYS)
        finally:
            await Database.close()

    async def test_a_supported_filter_still_filters(self, scratch_campaign):
        await Database.init()
        await _territory(scratch_campaign, A, status="controlled", faction="Iron Concord")
        await _territory(scratch_campaign, B, status="lost", faction="Den")
        try:
            by_faction = await celestial.query_systems(scratch_campaign, {"faction": "Iron Concord"})
            assert [s["system_name"] for s in by_faction] == [A], by_faction
            by_status = await celestial.query_systems(scratch_campaign, {"status": "lost"})
            assert [s["system_name"] for s in by_status] == [B], by_status
        finally:
            await _drop(scratch_campaign)
            await Database.close()


class TestTheReveal:
    async def test_a_reveal_reports_what_it_did(self, scratch_campaign):
        await Database.init()
        await _territory(scratch_campaign, A, status="lost", fleet=0)
        try:
            out = await celestial.reveal_system(scratch_campaign, A, "surveyed")
            assert out["revealed"] is True, out
            assert out["previous_level"] == "scanned", out
            assert out["level"] == "surveyed"
            status = await Database.fetchval(
                "SELECT status FROM maya_rp.territory WHERE session_id = $1 AND system_name = $2",
                scratch_campaign, A)
            assert status == "neutral", status
            assert out["read_back"] == "scanned", out
        finally:
            await _drop(scratch_campaign)
            await Database.close()

    async def test_a_reveal_that_changes_nothing_says_so(self, scratch_campaign):
        await Database.init()
        await _territory(scratch_campaign, A, status="lost", fleet=0)
        try:
            out = await celestial.reveal_system(scratch_campaign, A, "uncharted")
            assert out["revealed"] is False, out
            assert "uncharted" in out["reason"], out
        finally:
            await _drop(scratch_campaign)
            await Database.close()

    async def test_a_system_that_is_not_in_the_territory_is_uncharted(self, scratch_campaign):
        await Database.init()
        try:
            out = await celestial.get_visibility(scratch_campaign, "nowhere-review")
            assert out["level"] == "uncharted" and out["can_travel"] is False, out
        finally:
            await Database.close()


class TestTheSystemDetail:
    async def test_lanes_are_listed_in_both_directions(self, scratch_campaign):
        """Every other function in this module reads a lane as bidirectional."""
        await Database.init()
        await _territory(scratch_campaign, A, status="controlled")
        await _lane(scratch_campaign, A, B)
        await _lane(scratch_campaign, C, A)
        try:
            detail = await celestial.get_system_detail(scratch_campaign, A)
            pairs = {(r["origin"], r["destination"]) for r in detail["routes"]}
            assert pairs == {(A, B), (C, A)}, pairs
        finally:
            await _drop(scratch_campaign)
            await Database.close()

    async def test_a_system_with_no_territory_row_is_not_found(self, scratch_campaign):
        await Database.init()
        try:
            assert await celestial.get_system_detail(scratch_campaign, "nowhere-review") is None
        finally:
            await Database.close()


class TestTheTickSpeaks:
    async def test_a_failing_tick_is_logged_as_a_fault(self, scratch_campaign, monkeypatch):
        seen = []

        async def boom(session_id):
            raise RuntimeError("territory query died")

        monkeypatch.setattr(celestial, "get_universe_stats", boom)
        monkeypatch.setattr(celestial, "error", lambda module, message: seen.append(message))
        out = await celestial.run_tick(scratch_campaign)
        assert "territory query died" in out["error"], out
        assert seen, "a failing tick returned a dict and said nothing at fault level"
