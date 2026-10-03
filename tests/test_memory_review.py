#!/usr/bin/env python3
"""Review of `core/memory.py`.

Three defects:

1. `store_event(event_id, title, description, session_id=None)` **accepted a session and never read
   it**: the UPDATE matched on the id alone. `maya_rp.events` carries `session_id`, so a caller
   naming the wrong campaign still had the vector written onto that campaign's row, and the function
   returned None either way, so a miss and a hit looked identical.
2. Both failure handlers logged at **info**, which is why a failing embed path read as noise rather
   than as a fault. They are `warn` now.
3. Both call sites built the pgvector literal the same way, `vec[:1536]`, and that slice is a no-op
   at this dimension: `core/embed.py` records `nomic-embed-text` as 768-dim and a live call returns
   exactly 768. At any other dimension the slice would have written a silently truncated vector
   instead of refusing. One builder checks the length by name.

The tests never reach Ollama: `_embed` is replaced with a fixed 768-dim vector, so they are about
the write and the refusal rather than about the local GPU.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from core.db import Database  # noqa: E402
from core import memory  # noqa: E402


def _vec(n: int = 768, fill: float = 0.25) -> list[float]:
    return [fill] * n


@pytest.fixture(autouse=True)
async def _scratch_session_row(scratch_session):
    """The scratch session's own `sessions` row, and its events removed by id afterwards."""
    await Database.init()
    before_events = set(await _event_ids(scratch_session))
    made = await Database.fetchval(
        "SELECT 1 FROM maya_rp.sessions WHERE id=$1", scratch_session) is None
    if made:
        await Database.execute(
            "INSERT INTO maya_rp.sessions (id, name) VALUES ($1, $2)",
            scratch_session, f"scratch-memory-{scratch_session}")
    try:
        yield
    finally:
        created = set(await _event_ids(scratch_session)) - before_events
        if created:
            await Database.execute(
                "DELETE FROM maya_rp.events WHERE id = ANY($1::int[])", sorted(created))
        left = await Database.fetchval(
            "SELECT count(*) FROM maya_rp.events WHERE session_id=$1", scratch_session)
        print(f"cleanup: scratch {scratch_session} events left = {left}")
        if made:
            await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", scratch_session)
        assert left == 0, "the scratch session kept an event this test did not create"


async def _event_ids(session_id: int) -> list[int]:
    rows = await Database.fetch("SELECT id FROM maya_rp.events WHERE session_id=$1", session_id)
    return [int(r["id"]) for r in rows]


async def _give_event(session_id: int, title: str = "Review Event") -> int:
    return int(await Database.fetchval(
        "INSERT INTO maya_rp.events (session_id, happened_at, event_type, title, description, tags)"
        " VALUES ($1, NOW(), 'review', $2, 'written by the memory review', '[\"review\"]')"
        " RETURNING id", session_id, title))


class TestTheWriteNamesItsSession:
    async def test_a_foreign_event_id_gets_no_vector(self, scratch_session, monkeypatch):
        """The parameter was accepted and never read; the write matched on the id alone."""
        await Database.init()
        other = scratch_session + 500
        made_other = await Database.fetchval(
            "SELECT 1 FROM maya_rp.sessions WHERE id=$1", other) is None
        foreign_event = None

        async def fake_embed(_text, keep_alive="30m"):
            return _vec()

        monkeypatch.setattr(memory, "_embed", fake_embed)
        try:
            if made_other:
                await Database.execute(
                    "INSERT INTO maya_rp.sessions (id, name) VALUES ($1, $2)",
                    other, f"scratch-memory-{other}")
            foreign_event = await _give_event(other, "Foreign Event")

            stored = await memory.store_event(foreign_event, "Foreign", "foreign event", scratch_session)
            assert stored is False, "a foreign event id was reported as stored"
            embedding = await Database.fetchval(
                "SELECT embedding FROM maya_rp.events WHERE id=$1", foreign_event)
            assert embedding is None, "the vector was written onto another campaign's row"
        finally:
            if foreign_event is not None:
                await Database.execute("DELETE FROM maya_rp.events WHERE id=$1", foreign_event)
            if made_other:
                await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", other)
            await Database.close()

    async def test_the_own_event_gets_a_768_dim_vector_and_reports_it(self, scratch_session,
                                                                     monkeypatch):
        await Database.init()
        event_id = None

        async def fake_embed(_text, keep_alive="30m"):
            return _vec()

        monkeypatch.setattr(memory, "_embed", fake_embed)
        try:
            event_id = await _give_event(scratch_session)
            assert await memory.store_event(event_id, "Review", "own event", scratch_session) is True
            embedding = await Database.fetchval(
                "SELECT embedding FROM maya_rp.events WHERE id=$1", event_id)
            assert embedding is not None, "no vector was stored"
            assert str(embedding).count(",") == memory.EMBED_DIM - 1, "not a 768-dim vector"
        finally:
            if event_id is not None:
                await Database.execute("DELETE FROM maya_rp.events WHERE id=$1", event_id)
            await Database.close()

    async def test_a_miss_is_reported_rather_than_silent(self, scratch_session, monkeypatch):
        """No such event: the old code returned None and said nothing."""
        await Database.init()
        said: list[tuple[str, str]] = []

        async def fake_embed(_text, keep_alive="30m"):
            return _vec()

        monkeypatch.setattr(memory, "_embed", fake_embed)
        monkeypatch.setattr(memory, "warn", lambda module, msg: said.append((module, msg)))
        try:
            assert await memory.store_event(999_999_999, "Ghost", "no such row", scratch_session) is False
            assert said and said[0][0] == "memory", said
            assert "999999999" in said[0][1] and str(scratch_session) in said[0][1], said
        finally:
            await Database.close()


class TestTheLiteralItBuilds:
    def test_a_vector_of_the_wrong_length_is_refused_by_name(self):
        """`vec[:1536]` would have truncated a longer vector into the column without a word."""
        with pytest.raises(ValueError) as exc:
            memory._vector_literal(_vec(1024))
        message = str(exc.value)
        assert "1024" in message and str(memory.EMBED_DIM) in message, message
        assert memory.EMBED_MODEL in message, message

    def test_the_right_length_builds_the_pgvector_literal(self):
        literal = memory._vector_literal([0.5, 0.25] + [0.0] * 766)
        assert literal.startswith("[0.5,0.25,0.0") and literal.endswith("]")
        assert literal.count(",") == memory.EMBED_DIM - 1


class TestAFailingEmbedIsAFaultNotNoise:
    async def test_an_embed_failure_warns_and_names_the_event(self, scratch_session, monkeypatch):
        await Database.init()
        warned: list[tuple[str, str]] = []
        infoed: list[tuple[str, str]] = []

        async def boom(_text, keep_alive="30m"):
            raise RuntimeError("ollama is down")

        monkeypatch.setattr(memory, "_embed", boom)
        monkeypatch.setattr(memory, "warn", lambda module, msg: warned.append((module, msg)))
        monkeypatch.setattr(memory, "info", lambda module, msg: infoed.append((module, msg)))
        try:
            assert await memory.store_event(123, "T", "D", scratch_session) is False
            assert warned and "ollama is down" in warned[0][1], warned
            assert infoed == [], f"a fault was logged at info: {infoed}"
        finally:
            await Database.close()

    async def test_a_failed_recall_warns_and_still_answers_a_list(self, monkeypatch):
        warned: list[tuple[str, str]] = []

        async def boom(_text, keep_alive="30m"):
            raise RuntimeError("ollama is down")

        monkeypatch.setattr(memory, "_embed", boom)
        monkeypatch.setattr(memory, "warn", lambda module, msg: warned.append((module, msg)))
        out = await memory.recall("anything", 3, 3)
        assert out == [], out
        assert warned and "Recall failed" in warned[0][1], warned
