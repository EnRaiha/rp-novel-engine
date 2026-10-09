"""Ministry AI review: what reading `modules/ministry_ai.py` in full turned up.

The module held `SID = Config.SESSION_ID` at import, so every default path was pinned to whichever
campaign was current when the module was first imported. Every write lands in a scratch session
(900-999). Sessions 3 and 5 are not touched. Every prompt is intercepted, so no prompt row is written.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

from core.db import Database  # noqa: E402
from modules import ministry_ai as mia  # noqa: E402

#: Children of `sessions` this file writes, removed before the session row (territory has a foreign key to it).
_TABLES = ("governor_applicants", "adjutant_prompts", "events", "territory")


async def _wipe(session_id):
    for table in _TABLES:
        await Database.execute(f"DELETE FROM maya_rp.{table} WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", session_id)


@pytest_asyncio.fixture
async def sid(scratch_session):
    """A scratch session row, King present, with the pool open for the test."""
    await Database.init()
    await _wipe(scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status, game_day, king_present, dark_mode) "
        "VALUES ($1, 'ministry review scratch', 'active', 1, true, false)", scratch_session)
    try:
        yield scratch_session
    finally:
        await _wipe(scratch_session)
        await Database.close()


async def _capital(session_id):
    return await Database.fetchval(
        "INSERT INTO maya_rp.territory "
        "(id, session_id, system_name, controlling_faction, crisis_level, requires_king_prompt) "
        "VALUES ((SELECT COALESCE(MAX(id), 0) + 1 FROM maya_rp.territory), $1, 'review capital', "
        "'Iron Concord', 5, true) RETURNING id",
        session_id)


class TestTheSessionIsResolvedAtCallTime:
    async def test_the_default_session_is_not_frozen_at_import(self, monkeypatch):
        seen = []

        async def fake_fetchval(query, *args):
            seen.append(args[0] if args else None)
            return True

        monkeypatch.setattr(mia.Database, "fetchval", fake_fetchval)
        monkeypatch.setenv("RP_SESSION", "905")
        await mia.king_status()
        monkeypatch.setenv("RP_SESSION", "906")
        await mia.king_status()
        assert seen == [905, 906], seen

    def test_no_module_level_session_constant_survives(self):
        """A module-level copy freezes on the import-time session for the life of the process."""
        assert not hasattr(mia, "SID"), "SID is back and it pins every default to one campaign"

    async def test_the_flag_writers_take_a_session(self, monkeypatch, sid):
        calls = []

        async def fake_execute(query, *args):
            calls.append(args)
            return "UPDATE 1"

        monkeypatch.setattr(mia.Database, "execute", fake_execute)
        await mia.set_king(sid, True)
        await mia.set_dark(sid, True)
        assert calls[0][0] == sid and calls[1][0] == sid, calls


class TestTheCapitalPrompt:
    async def test_the_capital_is_found_by_its_own_flag(self, monkeypatch, sid):
        """The capital was read as the literal territory id 170, which is session 3's row."""
        await _capital(sid)
        prompts = []

        async def record(session_id, ministry, holder, action, target, impact,
                         urgency="normal", adj=None):
            prompts.append((session_id, ministry, action, urgency))
            return True

        monkeypatch.setattr(mia, "_prompt", record)
        out = await mia.run_tick(sid)
        assert (sid, "Cabinet", "Mastika crisis response", "critical") in prompts, prompts
        assert out["prompted"] >= 1, out

    async def test_a_capital_that_is_not_in_crisis_prompts_nothing_extra(self, monkeypatch, sid):
        prompts = []

        async def record(session_id, ministry, holder, action, target, impact,
                         urgency="normal", adj=None):
            prompts.append((ministry, action, urgency))
            return True

        monkeypatch.setattr(mia, "_prompt", record)
        await mia.run_tick(sid)
        assert not [p for p in prompts if p[0] == "Cabinet"], prompts


class TestTheTickContract:
    async def test_the_tick_answers_with_the_documented_keys(self, monkeypatch, sid):
        async def record(*args, **kwargs):
            return True

        monkeypatch.setattr(mia, "_prompt", record)
        out = await mia.run_tick(sid)
        assert set(out) == {"king_present", "dark_mode", "taken_autonomous",
                            "prompted", "governors_assigned"}, out
        assert isinstance(out["king_present"], bool)
        assert out["prompted"] == 4, out

    async def test_a_tick_never_writes_a_prompt_when_the_prompt_fn_is_stubbed(self, monkeypatch, sid):
        before = await Database.fetchval(
            "SELECT COUNT(*) FROM maya_rp.adjutant_prompts WHERE session_id = $1", sid)

        async def record(*args, **kwargs):
            return True

        monkeypatch.setattr(mia, "_prompt", record)
        await mia.run_tick(sid)
        after = await Database.fetchval(
            "SELECT COUNT(*) FROM maya_rp.adjutant_prompts WHERE session_id = $1", sid)
        assert after == before


class TestThePromptDoor:
    async def test_resolving_a_prompt_that_does_not_exist_is_refused(self, sid):
        out = await mia.resolve(sid, 999999999, "accepted")
        assert "not found" in out.get("error", ""), out

    async def test_a_decision_outside_the_vocabulary_is_refused(self, sid):
        out = await mia.resolve(sid, 1, "maybe")
        assert "error" in out, out
