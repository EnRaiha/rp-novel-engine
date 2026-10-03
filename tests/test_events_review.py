#!/usr/bin/env python3
"""Review of `core/events.py`.

Three defects:

1. `data.get("session_id", 3)` stood at three sites, so any payload that omitted `session_id` was
   filed in the **frozen reference campaign**. The protocol records the live cost of this shape from
   `battle.py`, whose payloads omitted it. `core.session.resolve_session` is the engine's one source
   of session: explicit, then `RP_SESSION`, then the active arc, then a refusal that names what to
   pass.
2. `logging.info` and `logging.error` went to the root logger, which has no handler here and sits at
   WARNING: the info line was dropped outright and the error line never reached
   `logs/tick_YYYYMMDD.log`, the file the engine is read back from. Both go through `core.log` now.
3. `asyncio.create_task(...)` with no reference kept, twice. The loop holds a task weakly, so a task
   nobody keeps can be collected before it runs, and its exception is never retrieved. Measured
   while reviewing: **330 events carry the `bus` tag in session 5 and 3 of them hold an embedding**,
   and the engine log has **no** "Embedding failed" line for those days, so the embedding task never
   reached `store_event` at all.

Every test here writes to a per-process scratch session, removes the event ids it introduced by id,
and re-reads session 3 to prove it did not gain a row.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import Database  # noqa: E402
from core import events as events_mod  # noqa: E402
from core.events import EventBus  # noqa: E402

import pytest  # noqa: E402

FROZEN = 3


@pytest.fixture(autouse=True)
async def _scratch_session_row(scratch_session):
    """`events.session_id` is a foreign key into `sessions`, so a scratch session needs that row.

    Created only when it is absent and removed only when this fixture made it, by id.
    """
    await Database.init()
    made = await Database.fetchval(
        "SELECT 1 FROM maya_rp.sessions WHERE id=$1", scratch_session) is None
    if made:
        await Database.execute(
            "INSERT INTO maya_rp.sessions (id, name) VALUES ($1, $2)",
            scratch_session, f"scratch-events-{scratch_session}")
    try:
        yield
    finally:
        if made:
            await Database.execute(
                "DELETE FROM maya_rp.sessions WHERE id=$1", scratch_session)
            print(f"cleanup: scratch {scratch_session} sessions row removed")


async def _ids(session_id: int) -> set[int]:
    rows = await Database.fetch(
        "SELECT id FROM maya_rp.events WHERE session_id=$1", session_id)
    return {int(r["id"]) for r in rows}


async def _drop_new(session_id: int, before: set[int]) -> int:
    created = (await _ids(session_id)) - before
    if created:
        await Database.execute(
            "DELETE FROM maya_rp.events WHERE id = ANY($1::int[])", sorted(created))
    return len(created)


async def _no_embed(monkeypatch):
    """Keep Ollama out of the suite: the embed path is not what these tests are about."""
    seen: list[tuple] = []

    async def fake_store(event_id, title, description, session_id=None):
        seen.append((event_id, session_id))

    monkeypatch.setattr("core.memory.store_event", fake_store)
    return seen


class TestTheSessionItFilesUnder:
    async def test_a_payload_with_no_session_is_not_filed_in_the_frozen_campaign(
            self, scratch_session, monkeypatch):
        await Database.init()
        frozen_before = await _ids(FROZEN)
        scratch_before = await _ids(scratch_session)
        try:
            await _no_embed(monkeypatch)
            monkeypatch.setattr("core.session.resolve_session",
                                lambda explicit=None: scratch_session)

            await EventBus.emit("review_probe", {"what": "no session in the payload"})

            created = (await _ids(scratch_session)) - scratch_before
            assert len(created) == 1, f"expected one row, got {len(created)}"
            row = await Database.fetchrow(
                "SELECT session_id FROM maya_rp.events WHERE id=$1", created.pop())
            assert row["session_id"] == scratch_session, row
            assert await _ids(FROZEN) == frozen_before, (
                "the frozen campaign gained a row from a payload that named no session")
        finally:
            await _drop_new(FROZEN, frozen_before)
            await _drop_new(scratch_session, scratch_before)
            await Database.close()

    async def test_an_explicit_session_in_the_payload_is_honoured(self, scratch_session,
                                                                  monkeypatch):
        await Database.init()
        frozen_before = await _ids(FROZEN)
        scratch_before = await _ids(scratch_session)
        try:
            await _no_embed(monkeypatch)
            await EventBus.emit("review_probe", {"session_id": scratch_session})
            created = (await _ids(scratch_session)) - scratch_before
            assert len(created) == 1, created
            assert await _ids(FROZEN) == frozen_before
        finally:
            await _drop_new(FROZEN, frozen_before)
            await _drop_new(scratch_session, scratch_before)
            await Database.close()


class TestTheBackgroundWorkIsKept:
    async def test_the_embedding_task_is_held_and_runs(self, scratch_session, monkeypatch):
        """`asyncio.create_task` with no reference is a task that can vanish before it runs."""
        await Database.init()
        scratch_before = await _ids(scratch_session)
        frozen_before = await _ids(FROZEN)
        seen = await _no_embed(monkeypatch)
        try:
            monkeypatch.setattr("core.session.resolve_session",
                                lambda explicit=None: scratch_session)
            for _ in range(100):
                if not events_mod._pending:
                    break
                await asyncio.sleep(0.01)

            await EventBus.emit("review_probe", {"what": "tracked"})
            assert events_mod._pending, "the background task was not kept"

            for _ in range(100):
                if not events_mod._pending:
                    break
                await asyncio.sleep(0.01)
            assert not events_mod._pending, "the background task never settled"
            assert len(seen) == 1, f"the embedding task never ran: {seen}"
            assert seen[0][1] == scratch_session, seen
        finally:
            await _drop_new(FROZEN, frozen_before)
            await _drop_new(scratch_session, scratch_before)
            await Database.close()


class TestItDoesNotHideAnError:
    async def test_a_failing_listener_is_logged_where_the_engine_reads(self, scratch_session,
                                                                      monkeypatch):
        """The module's own comment: `EventBus should never hide errors`."""
        await Database.init()
        scratch_before = await _ids(scratch_session)
        frozen_before = await _ids(FROZEN)
        logged: list[str] = []
        await _no_embed(monkeypatch)
        monkeypatch.setattr(events_mod, "error",
                            lambda module, msg: logged.append(f"{module}: {msg}"))

        async def boom(_data):
            raise RuntimeError("listener exploded")

        EventBus.on("review_boom", boom)
        try:
            await EventBus.emit("review_boom", {"session_id": scratch_session})
        finally:
            EventBus.off("review_boom", boom)
            await _drop_new(FROZEN, frozen_before)
            await _drop_new(scratch_session, scratch_before)
            await Database.close()

        assert any("listener exploded" in line for line in logged), logged
        assert any(line.startswith("events:") for line in logged), logged

    async def test_a_refusal_to_resolve_a_session_writes_nothing_and_says_so(
            self, scratch_session, monkeypatch):
        await Database.init()
        frozen_before = await _ids(FROZEN)
        scratch_before = await _ids(scratch_session)
        logged: list[str] = []
        await _no_embed(monkeypatch)
        monkeypatch.setattr(events_mod, "error",
                            lambda module, msg: logged.append(f"{module}: {msg}"))

        def refuse(explicit=None):
            raise RuntimeError("no session resolved: pass --session=<id>")

        monkeypatch.setattr("core.session.resolve_session", refuse)
        try:
            await EventBus.emit("review_probe", {"what": "no session anywhere"})
            assert await _ids(FROZEN) == frozen_before, "filed a guess into the frozen campaign"
            assert await _ids(scratch_session) == scratch_before
        finally:
            await _drop_new(FROZEN, frozen_before)
            await _drop_new(scratch_session, scratch_before)
            await Database.close()
        assert any("no session resolved" in line for line in logged), logged
