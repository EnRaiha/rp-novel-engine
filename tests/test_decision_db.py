"""Live-database tests for core/decision.py.

`tests/test_decision_review.py` drives a fake connection, and a fake accepts any Python object as a
jsonb parameter. The real pool does not: `core.db` registers no jsonb codec, so asyncpg raised
`DataError: expected str, got dict` on every `record()`, and no mocked test could see it.

Defects covered:

1. `record()` bound dicts to jsonb parameters; every call raised.
2. `decisions()` appended `AND status/kind/day` after `A OR B`, so the filter bound to the plan
   branch only and every decree passed through.
3. `record(decree_id=...)` overwrote parent_id, event_ids and state_before with its argument
   defaults, erasing what `link_event` wrote.
4. `record()` read `Config.SESSION_ID`, fixed at import, instead of resolving per call.

Scratch session: 900 + pid % 100, the slot `scratch_session` hands out. Sessions 3 and 5 are never
written. Every decree this file inserts is removed in `finally`.
"""
from __future__ import annotations

import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import decision  # noqa: E402
from core.db import Database  # noqa: E402


async def _open(session_id: int) -> None:
    await Database.init()
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1,'Decision DB scratch','active')"
        " ON CONFLICT (id) DO NOTHING",
        session_id,
    )


async def _clear(session_id: int) -> None:
    """Remove this session's decrees. parent_id is a self-reference, so it is cut first."""
    await Database.execute(
        "UPDATE maya_rp.cabinet_decrees SET parent_id=NULL WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.cabinet_decrees WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", session_id)


async def _row(decree_id: int) -> dict:
    row = await Database.fetchrow(
        "SELECT * FROM maya_rp.cabinet_decrees WHERE id=$1", decree_id)
    return dict(row)


def _json(value) -> dict:
    import json
    return value if isinstance(value, dict) else json.loads(value)


class TestRecordInsert:
    async def test_record_with_dict_state_inserts_a_row_and_returns_its_id(self, scratch_session):
        """Pre-fix: asyncpg raised DataError (expected str, got dict) on the first jsonb bind."""
        sid = scratch_session
        await _open(sid)
        try:
            did = await decision.record(
                "Izzat", "directive", "Scratch decree",
                state_before={"treasury": 100}, state_delta={"treasury": 150},
                game_day=7, event_ids=[1, 2], session_id=sid)
            assert isinstance(did, int), f"record returned {did!r}, expected an id"
            row = await _row(did)
            assert row["session_id"] == sid, "decree landed in another session"
            assert _json(row["state_before"]) == {"treasury": 100}, "state_before not stored as given"
            assert _json(row["state_after"]) == {"treasury": 150}, "state_after not stored"
            assert _json(row["impact_deltas"]) == {"treasury": 150}, \
                "impact_deltas must carry the same delta; by_fact reads both columns"
            assert row["game_day"] == 7 and list(row["event_ids"]) == [1, 2], "scalar columns lost"
        finally:
            await _clear(sid)
            await Database.close()


class TestRecordUpdateKeepsProvenance:
    async def test_update_without_provenance_arguments_keeps_what_link_event_wrote(
            self, scratch_session):
        """Pre-fix: the UPDATE wrote parent_id=NULL, event_ids='{}', state_before='{}' over the row."""
        sid = scratch_session
        await _open(sid)
        try:
            parent = await decision.record("Izzat", "directive", "Parent", session_id=sid)
            child = await decision.record(
                "Izzat", "directive", "Child", parent_id=parent, game_day=3,
                state_before={"ships": 4}, session_id=sid)
            await decision.link_event(sid, child, 11)
            got = await decision.record(
                "Izzat", "directive", "Child", decree_id=child,
                state_delta={"ships": 5}, session_id=sid)
            assert got == child, f"update returned {got!r}, expected {child}"
            row = await _row(child)
            assert row["parent_id"] == parent, "parent_id erased by the update"
            assert row["game_day"] == 3, "game_day erased by the update"
            assert list(row["event_ids"]) == [11], f"event_ids erased: {row['event_ids']!r}"
            assert _json(row["state_before"]) == {"ships": 4}, "state_before erased by the update"
            assert _json(row["state_after"]) == {"ships": 5}, "supplied state_delta not written"
        finally:
            await _clear(sid)
            await Database.close()

    async def test_update_of_a_decree_in_another_session_returns_none(self, scratch_session):
        """A miss is not a write: the id comes back None and the row is untouched."""
        sid = scratch_session
        await _open(sid)
        try:
            did = await decision.record("Izzat", "directive", "Mine", session_id=sid)
            got = await decision.record(
                "Izzat", "directive", "Mine", decree_id=did,
                state_delta={"x": 1}, session_id=sid + 1000)
            assert got is None, f"cross-session update reported {got!r}"
            assert _json((await _row(did))["state_after"]) == {}, "foreign session wrote the row"
        finally:
            await _clear(sid)
            await Database.close()


class TestDecisionsFilters:
    async def _seed(self, sid: int) -> tuple[int, int]:
        done = await decision.record("Izzat", "directive", "Done", session_id=sid)
        await Database.execute(
            "UPDATE maya_rp.cabinet_decrees SET status='completed' WHERE id=$1", done)
        live = await decision.record("Izzat", "directive", "Live", session_id=sid)
        return done, live

    async def test_status_filter_excludes_decrees_of_another_status(self, scratch_session):
        """Pre-fix: `status=` bound to the plan branch only, so the executing decree came back too."""
        sid = scratch_session
        await _open(sid)
        try:
            done, live = await self._seed(sid)
            rows = await decision.decisions(sid, status="completed")
            ids = {r["decision_id"] for r in rows if r["kind"] == "decree"}
            assert done in ids, "the completed decree is missing"
            assert live not in ids, "an executing decree passed the status='completed' filter"
            assert all(r["status"] == "completed" for r in rows), \
                f"statuses returned: {[r['status'] for r in rows]}"
        finally:
            await _clear(sid)
            await Database.close()

    async def test_kind_decree_returns_only_decrees_of_this_session(self, scratch_session):
        """Pre-fix: `kind=` bound to the plan branch only, so plan rows were not excluded."""
        sid = scratch_session
        await _open(sid)
        try:
            done, live = await self._seed(sid)
            rows = await decision.decisions(sid, kind="decree")
            assert {done, live} <= {r["decision_id"] for r in rows}, "a seeded decree is missing"
            assert {r["kind"] for r in rows} == {"decree"}, \
                f"kinds returned: {sorted({r['kind'] for r in rows})}"
        finally:
            await _clear(sid)
            await Database.close()

    async def test_day_filter_matches_decrees_by_game_day_and_drops_plan_rows(
            self, scratch_session):
        """The view reports plan rows with game_day NULL, so a day filter never returns them."""
        sid = scratch_session
        await _open(sid)
        try:
            on = await decision.record("Izzat", "directive", "On", game_day=9, session_id=sid)
            await decision.record("Izzat", "directive", "Off", game_day=10, session_id=sid)
            rows = await decision.decisions(sid, day=9)
            assert [r["decision_id"] for r in rows] == [on], \
                f"day=9 returned {[r['decision_id'] for r in rows]}"
        finally:
            await _clear(sid)
            await Database.close()


class TestRecordResolvesSessionPerCall:
    async def test_no_session_argument_follows_rp_session_not_config(
            self, scratch_session, monkeypatch):
        """Pre-fix: record() used Config.SESSION_ID, fixed at import, and ignored RP_SESSION."""
        sid = scratch_session
        await _open(sid)
        try:
            monkeypatch.setenv("RP_SESSION", str(sid))
            did = await decision.record("Izzat", "directive", "Env resolved")
            assert (await _row(did))["session_id"] == sid, \
                "record() without session_id ignored RP_SESSION"
        finally:
            await _clear(sid)
            await Database.close()
