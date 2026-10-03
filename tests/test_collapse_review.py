#!/usr/bin/env python3
"""Review of `modules/collapse.py`.

Two defects, both reachable from the tick that runs this module today:

1. `_trigger_collapse` logged its `events` row outside the `if not existing_collapse:` branch, so a
   collapse condition that stays true **wrote one `importance 5` event on every tick** for as long as
   it lasted. Nothing had run it yet: the `events` table holds zero `event_type='collapse'` rows.
2. The hull check compared `hull_current` without a NULL test. Both `hull` and `hull_current` are
   nullable, and `None <= float` raises TypeError, which reaches the tick as a module crash.

Every test here writes to a per-process scratch session and removes only what it created. The three
tables it touches are scoped by the set difference of their ids before and after the test, never by a
ceiling; the `resources` and `sessions` rows are removed only when this call created them. Nothing
names session 3 or session 5.

`resources`, `events`, `story_arcs` and `ships` each carry a foreign key to `sessions`, so a scratch
session cannot own a row until it owns the session row. Reading that off
`information_schema.table_constraints` returned zero rows and I believed it for one run; `pg_constraint`
is the view that answers.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import Database  # noqa: E402
from modules import collapse  # noqa: E402

SCOPED_TABLES = ("events", "story_arcs", "ships")


async def _ids(table: str, session_id: int) -> set[int]:
    rows = await Database.fetch(
        f"SELECT id FROM maya_rp.{table} WHERE session_id=$1", session_id)
    return {int(r["id"]) for r in rows}


async def _begin(scratch_session: int, **cols) -> dict:
    """Create the scratch session, and its `resources` row when columns are given.

    Returns what this call created, plus the id set each scoped table held beforehand, so `_end` can
    remove exactly the difference.
    """
    made = {
        "session": await Database.fetchval(
            "SELECT 1 FROM maya_rp.sessions WHERE id=$1", scratch_session) is None,
        "resources": False,
        "before": {t: await _ids(t, scratch_session) for t in SCOPED_TABLES},
    }
    if made["session"]:
        await Database.execute(
            "INSERT INTO maya_rp.sessions (id, name) VALUES ($1, $2)",
            scratch_session, f"scratch-collapse-{scratch_session}")
    if cols:
        keys = ", ".join(cols)
        args = ", ".join(f"${i + 2}" for i in range(len(cols)))
        await Database.execute(
            f"INSERT INTO maya_rp.resources (session_id, {keys}) VALUES ($1, {args})",
            scratch_session, *cols.values())
        made["resources"] = True
    return made


async def _end(scratch_session: int, made: dict) -> None:
    """Remove what `_begin` and the test created, and nothing else."""
    for table in SCOPED_TABLES:
        created = (await _ids(table, scratch_session)) - made["before"][table]
        if created:
            await Database.execute(
                f"DELETE FROM maya_rp.{table} WHERE id = ANY($1::int[])", sorted(created))
    if made["resources"]:
        await Database.execute(
            "DELETE FROM maya_rp.resources WHERE session_id=$1", scratch_session)
    if made["session"]:
        await Database.execute(
            "DELETE FROM maya_rp.sessions WHERE id=$1", scratch_session)


class TestAPersistentConditionIsOneEvent:
    async def test_a_collapse_that_stays_true_is_logged_once(self, scratch_session):
        """The tick runs every cycle and the treasury stays empty, so this is the ordinary path."""
        await Database.init()
        made = None
        try:
            made = await _begin(scratch_session, fuel=0, credits=500, population=500,
                                aggregate_morale=50)

            first = await collapse.check_for_collapse(scratch_session)
            assert first and first["collapsed"] is True, first
            assert first["type"] == "fuel_zero", first

            # The condition is a state, not an incident: three more ticks change nothing.
            for _ in range(3):
                again = await collapse.check_for_collapse(scratch_session)
                assert again and again["type"] == "fuel_zero", again

            events = await Database.fetch(
                "SELECT id FROM maya_rp.events WHERE session_id=$1 AND event_type='collapse'",
                scratch_session)
            assert len(events) == 1, f"one collapse wrote {len(events)} events"

            arcs = await Database.fetch(
                "SELECT id FROM maya_rp.story_arcs WHERE session_id=$1 AND status='active'"
                " AND collapse_type='fuel_zero'", scratch_session)
            assert len(arcs) == 1, f"one collapse opened {len(arcs)} arcs"

            # The arc keeps the recovery text, which is the whole point of storing it.
            recovery = await Database.fetchval(
                "SELECT collapse_recovery FROM maya_rp.story_arcs WHERE id=$1", arcs[0]["id"])
            assert recovery == collapse.COLLAPSE_STATES["fuel_zero"]["recovery"], recovery
        finally:
            if made is not None:
                await _end(scratch_session, made)
            remaining = await Database.fetchval(
                "SELECT count(*) FROM maya_rp.resources WHERE session_id=$1", scratch_session)
            await Database.close()
            print(f"cleanup: scratch {scratch_session} resources rows left = {remaining}")
            assert remaining == 0, "the scratch session's resources row was not removed"


class TestTheHullCheckAnswersInsteadOfRaising:
    async def test_a_null_hull_current_does_not_raise(self, scratch_session):
        """`hull_current` is nullable. `None <= float` raised TypeError and took the tick with it."""
        await Database.init()
        made = None
        try:
            made = await _begin(scratch_session, fuel=1000, credits=1000, population=1000,
                                aggregate_morale=50)
            await Database.execute(
                "INSERT INTO maya_rp.ships (session_id, name, hull, hull_current, status)"
                " VALUES ($1, 'review null hull', 100, NULL, 'active')", scratch_session)

            out = await collapse.check_for_collapse(scratch_session)
            assert out is None, f"a NULL hull_current is not a collapse, got {out}"
        finally:
            if made is not None:
                await _end(scratch_session, made)
            await Database.close()

    async def test_a_real_critical_hull_is_still_a_collapse(self, scratch_session):
        """The NULL guard must not disarm the check it guards."""
        await Database.init()
        made = None
        try:
            made = await _begin(scratch_session, fuel=1000, credits=1000, population=1000,
                                aggregate_morale=50)
            await Database.execute(
                "INSERT INTO maya_rp.ships (session_id, name, hull, hull_current, status)"
                " VALUES ($1, 'review broken hull', 100, 5, 'active')", scratch_session)

            out = await collapse.check_for_collapse(scratch_session)
            assert out and out["type"] == "hull_critical", out
        finally:
            if made is not None:
                await _end(scratch_session, made)
            await Database.close()


class TestTheContractsItClaims:
    async def test_a_healthy_session_is_stable_and_writes_nothing(self, scratch_session):
        await Database.init()
        made = None
        try:
            made = await _begin(scratch_session, fuel=1000, credits=1000, population=1000,
                                aggregate_morale=50)

            assert await collapse.check_for_collapse(scratch_session) is None
            assert await collapse.run_tick(scratch_session) == {"status": "stable"}
            assert await _ids("story_arcs", scratch_session) == made["before"]["story_arcs"]
            assert await _ids("events", scratch_session) == made["before"]["events"]
        finally:
            if made is not None:
                await _end(scratch_session, made)
            await Database.close()

    async def test_an_unknown_collapse_type_names_the_value(self):
        out = await collapse._trigger_collapse("no_such_collapse", 999999)
        assert out == {"collapsed": False, "error": "Unknown collapse type: no_such_collapse"}, out

    async def test_a_session_with_no_resources_row_is_not_a_collapse(self, scratch_session):
        """No row is not a collapse condition. `run_tick` must not open an arc for a session that has
        no economy to measure: session 5 spent most of its life in exactly that state."""
        await Database.init()
        made = None
        try:
            made = await _begin(scratch_session)
            assert await Database.fetchval(
                "SELECT 1 FROM maya_rp.resources WHERE session_id=$1", scratch_session) is None

            assert await collapse.check_for_collapse(scratch_session) is None
            assert await collapse.run_tick(scratch_session) == {"status": "stable"}
            assert await _ids("story_arcs", scratch_session) == made["before"]["story_arcs"]
            assert await _ids("events", scratch_session) == made["before"]["events"]
        finally:
            if made is not None:
                await _end(scratch_session, made)
            await Database.close()
