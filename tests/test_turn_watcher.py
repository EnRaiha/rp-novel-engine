#!/usr/bin/env python3
"""The turn watcher: monitor, track, and stop cleanly when a turn will not process.

`new_turns` is stubbed rather than reading `maya_rag.dsh_turns`, because the engine role holds
SELECT there and not INSERT, so a test could not create a turn to read. The pass logic is what is
under test; the query is one indexed read.
"""
from __future__ import annotations

import json

import pytest
import pytest_asyncio

from core.db import Database
from scripts import turn_watcher as tw

TURN_WITH_TERMS = ("### 4. Zulaikha Nadira\n\n"
                   "*Perkara satu kamu tidak boleh diukur, jadi saya tidak akan menerimanya.*\n")
TURN_WITH_SCENE = "Prosa.\n\n[SCENE] lokasi=rumah_agung | masuk=Boyet | masa=petang\n"


async def _ensure_session(session: int, name: str = "Watcher") -> None:
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1, $2, 'active')"
        " ON CONFLICT (id) DO NOTHING",
        session, name)


@pytest_asyncio.fixture
async def watcher(tmp_path, monkeypatch, scratch_session):
    """A scratch session, an isolated watermark, and a turn list the test controls."""
    await Database.init()
    await _ensure_session(scratch_session)
    for who in ("Zulaikha Nadira", "Boyet"):
        await Database.execute(
            "INSERT INTO maya_rp.characters (session_id, name, status)"
            " VALUES ($1, $2, 'active')", scratch_session, who)
    await Database.execute("DELETE FROM maya_rp.terms WHERE session_id=$1", scratch_session)
    monkeypatch.setattr(tw, "WATERMARK", tmp_path / "watermark.json")

    turns: list[dict] = []

    async def fake_new_turns(label, after, limit):
        return [t for t in turns if t["id"] > after][:limit]

    monkeypatch.setattr(tw, "new_turns", fake_new_turns)
    # Captured before the patch: binding the wrapper to the same name it calls recursed forever.
    original = tw.process_one

    async def with_scratch(_session, turn, *, write):
        return await original(scratch_session, turn, write=write)

    monkeypatch.setattr(tw, "process_one", with_scratch)
    yield {"session": scratch_session, "turns": turns, "watermark": tmp_path / "watermark.json"}
    await Database.execute("DELETE FROM maya_rp.terms WHERE session_id=$1", scratch_session)
    await Database.execute("DELETE FROM maya_rp.characters WHERE session_id=$1", scratch_session)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", scratch_session)


def _turn(id_: int, text: str) -> dict:
    return {"id": id_, "role": "assistant", "text_content": text, "created_at": None}


# ── the watermark ────────────────────────────────────────────────────────────

def test_a_missing_watermark_starts_at_zero(watcher):
    assert tw.read_watermark()["last_id"] == 0


def test_the_watermark_round_trips(watcher):
    tw.write_watermark({"last_id": 42, "processed": 7})

    assert tw.read_watermark()["last_id"] == 42
    assert tw.read_watermark()["updated_at"], "a watermark with no time cannot be judged stale"


def test_a_corrupt_watermark_is_reported_and_not_fatal(watcher):
    watcher["watermark"].write_text("{not json", encoding="utf-8")

    state = tw.read_watermark()

    assert state["last_id"] == 0, "a bad watermark must not stop the watcher"


# ── one pass ─────────────────────────────────────────────────────────────────

async def test_no_new_turns_is_a_clean_no_op(watcher):
    code = await tw.once(session_id=watcher["session"], label="x", apply=True, limit=10,
                         skip_failed=False)

    assert code == 0
    assert tw.read_watermark()["last_id"] == 0


async def test_a_turn_advances_the_watermark_and_is_counted(watcher):
    watcher["turns"].append(_turn(1, TURN_WITH_TERMS))

    code = await tw.once(session_id=watcher["session"], label="x", apply=True, limit=10,
                         skip_failed=False)

    assert code == 0
    assert tw.read_watermark()["last_id"] == 1
    assert await Database.fetchval(
        "SELECT count(*) FROM maya_rp.terms WHERE session_id=$1", watcher["session"]) == 1


async def test_a_dry_run_leaves_the_watermark_alone(watcher):
    watcher["turns"].append(_turn(1, TURN_WITH_TERMS))

    code = await tw.once(session_id=watcher["session"], label="x", apply=False, limit=10,
                         skip_failed=False)

    assert code == 0
    assert tw.read_watermark()["last_id"] == 0, "a dry run that moves the cursor loses the turn"
    assert await Database.fetchval(
        "SELECT count(*) FROM maya_rp.terms WHERE session_id=$1", watcher["session"]) == 0


async def test_a_scene_declaration_is_tracked(watcher):
    watcher["turns"].append(_turn(2, TURN_WITH_SCENE))

    await tw.once(session_id=watcher["session"], label="x", apply=True, limit=10, skip_failed=False)

    where = await Database.fetchval(
        "SELECT location FROM maya_rp.player_context WHERE session_id=$1", watcher["session"])
    assert where == "rumah_agung", "the declaration reached the engine"
    boyet = await Database.fetchval(
        "SELECT scene_location FROM maya_rp.characters WHERE session_id=$1 AND name='Boyet'",
        watcher["session"])
    assert boyet == "rumah_agung", "an entered character is placed"


# ── a turn that will not process ─────────────────────────────────────────────

async def test_a_failing_turn_stops_the_pass_and_keeps_the_watermark(watcher, monkeypatch):
    """Advancing past it would lose it silently. Retrying forever would hide that it is stuck. So the
    pass stops, the exit code says so, and an operator decides."""
    watcher["turns"].append(_turn(3, "anything"))

    async def explode(_session, _turn, *, write):
        raise RuntimeError("this turn is poison")

    monkeypatch.setattr(tw, "process_one", explode)

    code = await tw.once(session_id=watcher["session"], label="x", apply=True, limit=10,
                         skip_failed=False)

    assert code == 3, "a failure must be visible in the exit code, not only the log"
    assert tw.read_watermark()["last_id"] == 0


async def test_skip_failed_advances_past_it_on_request(watcher, monkeypatch):
    watcher["turns"].append(_turn(3, "anything"))

    async def explode(_session, _turn, *, write):
        raise RuntimeError("this turn is poison")

    monkeypatch.setattr(tw, "process_one", explode)

    code = await tw.once(session_id=watcher["session"], label="x", apply=True, limit=10,
                         skip_failed=True)

    assert code == 0
    assert tw.read_watermark()["last_id"] == 3, "--skip-failed is how an operator says move on"


# ── what it never does ───────────────────────────────────────────────────────

async def test_a_status_message_is_read_and_writes_nothing(watcher):
    """The table mixes GM narrative with agent status lines; every row has role='assistant'. No
    filter is needed because a status line carries no declaration and no marker."""
    watcher["turns"].append(_turn(4, "Siap. Arc II disalin, dan ingest jalan dengan bukti."))

    await tw.once(session_id=watcher["session"], label="x", apply=True, limit=10, skip_failed=False)

    assert await Database.fetchval(
        "SELECT count(*) FROM maya_rp.terms WHERE session_id=$1", watcher["session"]) == 0
    assert tw.read_watermark()["last_id"] == 4, "it still advances: the turn was read"


# ── the freeze door ──────────────────────────────────────────────────────────

def test_a_frozen_session_is_not_writable(watcher, monkeypatch):
    """The watcher calls `scene_tracker` and `terms` directly, so it never passed `core/session.py`
    and never met `is_frozen`. Installed 2026-10-04, frozen 2026-10-05, and the service kept
    running: the last write preceded the freeze by 44 minutes, which is the only reason no frozen
    row was written. Turn 233 would have been."""
    monkeypatch.setattr("core.session.is_frozen", lambda sid: True)
    monkeypatch.setattr("core.ooc._maintenance_active", lambda: False)

    assert tw._session_is_writable(5) is False


def test_maintenance_makes_it_writable_again(watcher, monkeypatch):
    """Maintenance armed means the operator is repairing the campaign, which is the one way in."""
    monkeypatch.setattr("core.session.is_frozen", lambda sid: True)
    monkeypatch.setattr("core.ooc._maintenance_active", lambda: True)

    assert tw._session_is_writable(5) is True


def test_an_unreadable_freeze_list_writes_nothing(watcher, monkeypatch):
    """`is_frozen` is fail-closed and raises on an unreadable list. A watcher that treated that as
    writable would write into a campaign it cannot prove is reference-only."""
    def explode(sid):
        raise RuntimeError("frozen_sessions is unreadable")

    monkeypatch.setattr("core.session.is_frozen", explode)
    monkeypatch.setattr("core.ooc._maintenance_active", lambda: False)

    assert tw._session_is_writable(5) is False


async def test_a_pass_over_a_frozen_session_writes_nothing(watcher, monkeypatch):
    watcher["turns"].append(_turn(9, TURN_WITH_TERMS))
    monkeypatch.setattr("core.session.is_frozen", lambda sid: True)
    monkeypatch.setattr("core.ooc._maintenance_active", lambda: False)

    code = await tw.once(session_id=watcher["session"], label="x", apply=True, limit=10,
                         skip_failed=False)

    assert code == 0, "refusing a frozen campaign is not an error; the poll keeps running"
    assert tw.read_watermark()["last_id"] == 0, "the cursor did not move over a frozen campaign"
    assert await Database.fetchval(
        "SELECT count(*) FROM maya_rp.terms WHERE session_id=$1", watcher["session"]) == 0


async def test_a_frozen_session_is_reported_once_not_every_poll(watcher, monkeypatch):
    """The service polls every 60 seconds. A notice per pass is a flooded journal."""
    monkeypatch.setattr("core.session.is_frozen", lambda sid: True)
    monkeypatch.setattr("core.ooc._maintenance_active", lambda: False)
    monkeypatch.setattr(tw, "_FREEZE_NOTICE", "")

    seen = []
    monkeypatch.setattr(tw, "info", lambda tag, msg: seen.append(msg))

    for _ in range(5):
        tw._session_is_writable(5)

    assert len(seen) == 1, f"the freeze was announced {len(seen)} times: {seen}"
