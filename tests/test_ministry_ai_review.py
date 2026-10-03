"""Ministry AI review: what reading `modules/ministry_ai.py` in full turned up.

The module held `SID = Config.SESSION_ID` at import, so every default path was pinned to whichever
campaign was current when the module was first imported. Nothing here writes to session 3. The
capital test creates one territory in session 5 and removes it in a `finally`; every prompt is
intercepted, so no prompt row is written at all.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from core.db import Database  # noqa: E402
from modules import ministry_ai as mia  # noqa: E402

SESSION = 5


async def _capital():
    return await Database.fetchval(
        "INSERT INTO maya_rp.territory "
        "(id, session_id, system_name, controlling_faction, crisis_level, requires_king_prompt) "
        "VALUES ((SELECT COALESCE(MAX(id), 0) + 1 FROM maya_rp.territory), $1, 'review capital', "
        "'Iron Concord', 5, true) RETURNING id",
        SESSION)


async def _drop(tid):
    await Database.execute("DELETE FROM maya_rp.territory WHERE id = $1", tid)


class TestTheSessionIsResolvedAtCallTime:
    async def test_the_default_session_is_not_frozen_at_import(self, monkeypatch):
        seen = []

        async def fake_fetchval(query, *args):
            seen.append(args[0] if args else None)
            return True

        monkeypatch.setattr(mia.Database, "fetchval", fake_fetchval)
        monkeypatch.setattr(mia.Config, "SESSION_ID", 5)
        await mia.king_status()
        monkeypatch.setattr(mia.Config, "SESSION_ID", 3)
        await mia.king_status()
        assert seen == [5, 3], seen

    def test_no_module_level_session_constant_survives(self):
        """A module-level copy freezes on the import-time session for the life of the process."""
        assert not hasattr(mia, "SID"), "SID is back and it pins every default to one campaign"

    async def test_the_flag_writers_take_a_session(self, monkeypatch):
        calls = []

        async def fake_execute(query, *args):
            calls.append(args)
            return "UPDATE 1"

        monkeypatch.setattr(mia.Database, "execute", fake_execute)
        await mia.set_king(SESSION, True)
        await mia.set_dark(SESSION, True)
        assert calls[0][0] == SESSION and calls[1][0] == SESSION, calls


class TestTheCapitalPrompt:
    async def test_the_capital_is_found_by_its_own_flag(self, monkeypatch):
        """The capital was read as the literal territory id 170, which is session 3's row."""
        await Database.init()
        tid = await _capital()
        prompts = []

        async def record(session_id, ministry, holder, action, target, impact,
                         urgency="normal", adj=None):
            prompts.append((session_id, ministry, action, urgency))

        monkeypatch.setattr(mia, "_prompt", record)
        try:
            out = await mia.run_tick(SESSION)
            assert (SESSION, "Cabinet", "Mastika crisis response", "critical") in prompts, prompts
            assert out["prompted"] >= 1, out
        finally:
            await _drop(tid)
            await Database.close()

    async def test_a_capital_that_is_not_in_crisis_prompts_nothing_extra(self, monkeypatch):
        await Database.init()
        prompts = []

        async def record(session_id, ministry, holder, action, target, impact,
                         urgency="normal", adj=None):
            prompts.append((ministry, action, urgency))

        monkeypatch.setattr(mia, "_prompt", record)
        try:
            await mia.run_tick(SESSION)
            assert not [p for p in prompts if p[0] == "Cabinet"], prompts
        finally:
            await Database.close()


class TestTheTickContract:
    async def test_the_tick_answers_with_the_documented_keys(self, monkeypatch):
        await Database.init()

        async def record(*args, **kwargs):
            return None

        monkeypatch.setattr(mia, "_prompt", record)
        try:
            out = await mia.run_tick(SESSION)
            assert set(out) == {"king_present", "dark_mode", "taken_autonomous",
                                "prompted", "governors_assigned"}, out
            assert isinstance(out["king_present"], bool)
        finally:
            await Database.close()

    async def test_a_tick_never_writes_a_prompt_when_the_prompt_fn_is_stubbed(self, monkeypatch):
        """The lock on the campaign: this file must not add adjutant prompts to session 5."""
        await Database.init()
        before = await Database.fetchval(
            "SELECT COUNT(*) FROM maya_rp.adjutant_prompts WHERE session_id = $1", SESSION)

        async def record(*args, **kwargs):
            return None

        monkeypatch.setattr(mia, "_prompt", record)
        try:
            await mia.run_tick(SESSION)
            after = await Database.fetchval(
                "SELECT COUNT(*) FROM maya_rp.adjutant_prompts WHERE session_id = $1", SESSION)
            assert after == before
        finally:
            await Database.close()


class TestThePromptDoor:
    async def test_resolving_a_prompt_that_does_not_exist_is_refused(self):
        await Database.init()
        try:
            out = await mia.resolve(SESSION, 999999999, "accepted")
            assert "not found" in out.get("error", ""), out
        finally:
            await Database.close()

    async def test_a_decision_outside_the_vocabulary_is_refused(self):
        await Database.init()
        try:
            out = await mia.resolve(SESSION, 1, "maybe")
            assert "error" in out, out
        finally:
            await Database.close()
