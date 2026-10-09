"""Second pass on modules/ideology.py, against the real database and a scratch session.

Defects covered:

1. The tick never re-derived. After the first derivation `get()` returned the stored row forever, so
   `player_action_log` changes never reached `ideology_state`. The tick now re-derives once per run and
   writes only a changed result. No evidence keeps the stored society.
2. `SUM(count)` is NULL when every `count` is NULL, and the NULL reached `sum(dist.values())` and raised.
"""
from __future__ import annotations

import json

import pytest_asyncio

import modules.ideology as ideology
from core.db import Database


async def _wipe(session_id: int) -> None:
    for table in ("player_action_log", "ideology_state"):
        await Database.execute(f"DELETE FROM maya_rp.{table} WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", session_id)


@pytest_asyncio.fixture
async def sid(scratch_session, monkeypatch):
    await Database.init()
    await _wipe(scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status, game_day) "
        "VALUES ($1,'ideology fix2 scratch','active',10)", scratch_session)
    monkeypatch.setattr("core.config.Config.SESSION_ID", scratch_session)
    monkeypatch.setenv("RP_SESSION", str(scratch_session))
    yield scratch_session
    await Database.init()
    await _wipe(scratch_session)
    await Database.close()


async def _act(session_id: int, category: str, count) -> None:
    await Database.execute(
        "INSERT INTO maya_rp.player_action_log (session_id, action_category, count) VALUES ($1,$2,$3)",
        session_id, category, count)


async def _state(session_id: int):
    return await Database.fetchrow(
        "SELECT ideology, scores_jsonb FROM maya_rp.ideology_state WHERE session_id=$1", session_id)


async def _store_old_guess(session_id: int) -> None:
    await Database.execute(
        "INSERT INTO maya_rp.ideology_state (session_id, ideology, scores_jsonb) VALUES ($1,$2,$3)",
        session_id, "military_dictatorship", json.dumps({k: 0 for k in ideology.IDEOS}))


def _spy(monkeypatch) -> list[str]:
    """Record the `ideology_state` writes that go through `Database.execute` from now on."""
    writes: list[str] = []
    real = Database.execute

    async def wrapped(sql, *args, **kw):
        if "ideology_state" in sql:
            writes.append(sql)
        return await real(sql, *args, **kw)

    monkeypatch.setattr(Database, "execute", wrapped)
    return writes


async def test_a_stored_society_follows_new_evidence(sid):
    await _store_old_guess(sid)
    await _act(sid, "mercy", 9)
    await _act(sid, "diplomacy", 40)

    out = await ideology.run_tick(sid)

    assert out == {"ideology": "benevolent_democracy"}
    assert (await _state(sid))["ideology"] == "benevolent_democracy"


async def test_an_unchanged_log_writes_once(sid, monkeypatch):
    await _store_old_guess(sid)
    await _act(sid, "mercy", 9)
    await _act(sid, "diplomacy", 40)
    spy = _spy(monkeypatch)

    await ideology.run_tick(sid)
    await ideology.run_tick(sid)

    assert len(spy) == 1


async def test_no_evidence_keeps_the_stored_society(sid, monkeypatch):
    await _store_old_guess(sid)
    spy = _spy(monkeypatch)

    out = await ideology.run_tick(sid)

    assert out == {"ideology": "military_dictatorship"}
    assert len(spy) == 0


async def test_a_null_count_row_does_not_kill_the_tick(sid):
    await _act(sid, "combat", None)

    out = await ideology.run_tick(sid)

    assert out == {"ideology": "undetermined"}
