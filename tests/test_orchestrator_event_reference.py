"""`archive_old_events` must give the `roll_history` reference way before it moves an event.

`maya_rp.roll_history.context_event_id` references `maya_rp.events(id)` with NO ACTION and is not
deferrable, measured on the live schema: constraint `roll_history_context_event_id_fkey`,
`confdeltype` 'a', `condeferrable` false, `roll_history` its only child. `scripts/cli.py` met it in
`clear --yes`; the housekeeping pass of `scripts/orchestrator.py` deletes the same rows, so one roll
row naming a 180-day-old event failed the whole archive on a foreign key violation.

The release is scoped to the rows the pass moves. `clear --yes` nulls the column for the whole
session because its delete takes every event of the session; an archive leaves the recent events, so
a roll row whose event stays must keep its reference.

Everything here writes inside the scratch campaign and nothing else. The two database arms carry the
red proof: a stub cannot fail the way the server fails.
"""
from __future__ import annotations

import pathlib
import sys

import pytest_asyncio

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.db import Database  # noqa: E402
from scripts import orchestrator as orch  # noqa: E402

#: The fixture writes this many old events, and the archive moves all of them.
OLD_EVENTS = 3


@pytest_asyncio.fixture
async def named_events(scratch_campaign) -> dict:
    """Old and recent events in the scratch campaign, with roll rows naming one of each.

    `m4-old-a` names an event the archive moves; its reference aborts the move unless the release
    gives way first. `m4-recent` names an event the archive leaves in `events`, so its reference
    must survive.
    """
    await Database.init()
    ids: dict = {}
    for name in ("old-a", "old-b", "old-c"):
        ids[name] = int(await Database.fetchval(
            "INSERT INTO maya_rp.events (session_id, event_type, title, happened_at)"
            " VALUES ($1, 'm4', $2, NOW() - INTERVAL '200 days') RETURNING id",
            scratch_campaign, name))
    ids["recent"] = int(await Database.fetchval(
        "INSERT INTO maya_rp.events (session_id, event_type, title, happened_at)"
        " VALUES ($1, 'm4', 'recent', NOW()) RETURNING id", scratch_campaign))
    for name in ("old-a", "recent"):
        ids[f"roll-{name}"] = int(await Database.fetchval(
            "INSERT INTO maya_rp.roll_history"
            " (session_id, roll_code, source_table, source_id, dice_used, raw_roll, final_score,"
            "  dc, outcome, context_event_id)"
            " VALUES ($1, $2, 'events', $3, '1d100', 50, 50, 50, 'success', $4) RETURNING id",
            scratch_campaign, f"m4-{name}", ids[name], ids[name]))
    yield ids


async def _count(table: str, session_id: int) -> int:
    return int(await Database.fetchval(
        f"SELECT COUNT(*) FROM maya_rp.{table} WHERE session_id=$1", session_id))


async def _roll(session_id: int, roll_code: str):
    """The scratch campaign's roll row, or None when the archive removed it."""
    return await Database.fetchrow(
        "SELECT id, context_event_id FROM maya_rp.roll_history WHERE session_id=$1 AND roll_code=$2",
        session_id, roll_code)


async def test_the_archive_completes_when_a_roll_row_names_an_event_it_moves(
        named_events, scratch_campaign, monkeypatch):
    """The arm that fails on the unfixed code: the server raises `ForeignKeyViolationError`.

    A roll row names an event of its own session. The archive completes anyway: the roll row stays
    and the reference gives way, the same trade `clear --yes` makes.
    """
    monkeypatch.setattr(orch, "EVENTS_ARCHIVE_MIN_ROWS", 2)

    archived = await orch.archive_old_events(scratch_campaign)

    assert archived == OLD_EVENTS, f"archived {archived} of {OLD_EVENTS} old events"
    assert await _count("events", scratch_campaign) == 1, "the recent event left `events`"
    assert await _count("events_archive", scratch_campaign) == OLD_EVENTS
    named = await _roll(scratch_campaign, "m4-old-a")
    assert named is not None, "the roll row went with the event it named"
    assert named["context_event_id"] is None, "the reference to the moved event survived the move"


async def test_the_archive_keeps_every_reference_to_an_event_it_leaves_in_place(
        named_events, scratch_campaign, monkeypatch):
    """The release is scoped to the rows this pass moves, so a kept event keeps its reference."""
    monkeypatch.setattr(orch, "EVENTS_ARCHIVE_MIN_ROWS", 2)

    await orch.archive_old_events(scratch_campaign)

    kept = await _roll(scratch_campaign, "m4-recent")
    assert kept is not None and kept["context_event_id"] == named_events["recent"], (
        "a roll row whose event stayed in `events` lost its reference")
    assert await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.events WHERE id=$1", named_events["recent"]) == 1
    nulls = await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.roll_history WHERE session_id=$1 AND context_event_id IS NULL"
        " AND roll_code IN ('m4-old-a', 'm4-recent')", scratch_campaign)
    assert nulls == 1, (
        f"{nulls} of this arm's 2 roll rows hold no reference; only the moved event's gives way")


async def test_the_release_and_the_move_run_on_one_transaction_connection(
        scratch_session, monkeypatch):
    """A release that commits outside the transaction survives the abort it exists to prevent.

    The roll history then forgets an event that stayed in `events`, which is worse than the error
    the abort reports. So every statement of the archive arrives on the connection
    `Database.transaction()` yields, and the pool's own executors refuse one that arrives anywhere
    else.
    """
    statements: list[str] = []
    opened: list[int] = []

    class RecordingConnection:
        async def fetchval(self, sql, *args):
            flat = " ".join(sql.split())
            statements.append(flat)
            if "COUNT(*) FROM maya_rp.events WHERE session_id" in flat and "180 days" not in flat:
                return 6000  # over the threshold: the archive moves
            return OLD_EVENTS

        async def execute(self, sql, *args):
            statements.append(" ".join(sql.split()))
            return "UPDATE 1"

    class OneTransaction:
        async def __aenter__(self):
            opened.append(1)
            return RecordingConnection()

        async def __aexit__(self, *_exc):
            return False

    class PoolLessDatabase:
        @staticmethod
        def transaction():
            return OneTransaction()

        @staticmethod
        async def fetchval(*_a, **_k):
            raise AssertionError("a statement ran outside the archive transaction")

        @staticmethod
        async def execute(*_a, **_k):
            raise AssertionError("a statement ran outside the archive transaction")

    monkeypatch.setattr(orch, "Database", PoolLessDatabase)
    monkeypatch.setattr(orch, "EVENTS_ARCHIVE_MIN_ROWS", 2)

    archived = await orch.archive_old_events(scratch_session)

    assert archived == OLD_EVENTS
    assert len(opened) == 1, f"the archive opened {len(opened)} transaction(s)"
    release = [sql for sql in statements if "context_event_id = NULL" in sql]
    moves = [sql for sql in statements if sql.startswith("WITH moved AS")]
    assert len(release) == 1 and len(moves) == 1, statements
    assert statements.index(release[0]) < statements.index(moves[0]), (
        "the move ran before the release that lets it through")
    assert "180 days" in release[0], (
        "the release is not scoped to the rows this pass moves: " + release[0])
