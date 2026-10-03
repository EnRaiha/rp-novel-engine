"""Module review tests for core/master_briefing.py.

Defects covered:

1. `PacingDirector.get_mode(session_id)` ran twice per briefing — block 3 held the
   answer in `pm` and block 12 asked the database for it again.
2. The scene-appearance block ended in `except Exception: pass`, so a failure of
   `auto_dress_all_present` or the character card read was invisible.
3. `_generate_ui_dashboard`'s handler bound the exception and returned
   "(unavailable)" without logging it. The dashboard is the only block that reads
   the treasury before the LLM narrates, and it was the one block that could fail
   in silence.
4. The GM-Brain wrapper loop appended the same string in both branches of an
   `if`/`else` that the comment said added XML tags.

Checked and found correct, so the row is not silent about what it looked at:
every scoped query in `generate` and `_generate_ui_dashboard` carries
`session_id=$1`; `res` is guarded for the missing `resources` row (session 5 has
none); `scars_jsonb` is handled both as a list and as the TEXT asyncpg returns
for jsonb; `day = fetchval(...) or 0` cannot misread a real value, because a
missing sessions row and game_day 0 both mean day 0.

No database: every collaborator is replaced by a stub.
"""
from __future__ import annotations

import pytest

from core import master_briefing
from core import pacing as pacing_mod
from core import session_rituals, dramatic_structure, scene_stack, player_profile
from modules import themes, objectives, chekhov, world_react, character_profile


class Stub:
    """Every collaborator `generate` touches, plus a call log."""

    def __init__(self):
        self.sessions_seen: list[int] = []
        self.mode_reads = 0
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.raise_dashboard = False
        self.raise_scene = False

    async def _record(self, *args):
        if args:
            self.sessions_seen.append(args[0])

    # --- collaborators ---
    async def generate_open(self, session_id):
        self.sessions_seen.append(session_id)
        return "## SESSION OPEN"

    async def get_current_arc(self, session_id):
        self.sessions_seen.append(session_id)
        return {"arc": "test"}

    def get_prompt(self, arc):
        return "## ARC"

    async def get_mode(self, session_id):
        self.mode_reads += 1
        self.sessions_seen.append(session_id)
        return {"mode": "downtime", "config": {}, "tension": 0, "scenes_in_mode": 0}

    def instruction(self, cfg, mode):
        return "## PACING"

    async def text(self, session_id, *a, **k):
        self.sessions_seen.append(session_id)
        return ""

    async def due(self, session_id, *a, **k):
        self.sessions_seen.append(session_id)
        return []

    async def profile(self, session_id):
        self.sessions_seen.append(session_id)
        return {}

    async def characters(self, session_id, *a, **k):
        self.sessions_seen.append(session_id)
        return []

    # --- database ---
    async def init(self):
        pass

    async def fetchrow(self, sql, *args):
        if self.raise_dashboard:
            raise RuntimeError("dashboard boom")
        if "resources" in sql:
            return {"credits": 1000, "alloys": 20, "fuel": 5, "population": 7}
        if "AVG" in sql:
            return {"count": 3, "avg_tier": 4.5}
        return None

    async def fetch(self, sql, *args):
        if self.raise_scene and "presence" in sql:
            raise RuntimeError("scene boom")
        return []

    async def fetchval(self, sql, *args):
        return 1


@pytest.fixture
def stub(monkeypatch):
    s = Stub()
    monkeypatch.setattr(master_briefing, "error", lambda m, msg: s.errors.append(msg))
    monkeypatch.setattr(master_briefing, "warn", lambda m, msg: s.warnings.append(msg))
    monkeypatch.setattr(master_briefing.Database, "init", staticmethod(s.init))
    monkeypatch.setattr(master_briefing.Database, "fetchrow", staticmethod(s.fetchrow))
    monkeypatch.setattr(master_briefing.Database, "fetch", staticmethod(s.fetch))
    monkeypatch.setattr(master_briefing.Database, "fetchval", staticmethod(s.fetchval))
    monkeypatch.setattr(session_rituals, "generate_open", s.generate_open)
    monkeypatch.setattr(dramatic_structure, "get_current_arc", s.get_current_arc)
    monkeypatch.setattr(dramatic_structure, "get_prompt", s.get_prompt)
    monkeypatch.setattr(pacing_mod.PacingDirector, "get_mode", staticmethod(s.get_mode))
    monkeypatch.setattr(pacing_mod.PacingDirector, "instruction", staticmethod(s.instruction))
    monkeypatch.setattr(themes, "get_instruction", s.text)
    monkeypatch.setattr(objectives, "objectives_to_prompt", s.text)
    monkeypatch.setattr(chekhov, "get_prompt", s.text)
    monkeypatch.setattr(world_react, "get_due", s.due)
    monkeypatch.setattr(scene_stack, "get_stack_summary", s.due)
    monkeypatch.setattr(player_profile, "get_profile", s.profile)
    monkeypatch.setattr(character_profile, "auto_dress_all_present", s.characters)

    async def _card(name, session_id=None):
        s.sessions_seen.append(session_id)
        return f"card:{name}"

    monkeypatch.setattr(character_profile, "get_character_card_by_name", _card)
    return s


async def test_briefing_is_wrapped_and_scoped(stub):
    """The contract: one call, everything scoped to the session it was given."""
    out = await master_briefing.generate(session_id=5)
    assert out.startswith("<gm_brain>\n")
    assert out.endswith("\n</gm_brain>")
    assert stub.sessions_seen, "no collaborator was called"
    assert set(stub.sessions_seen) == {5}, stub.sessions_seen


async def test_pacing_mode_is_read_once(stub):
    """(1) Block 12 asked the database a second time for block 3's answer."""
    await master_briefing.generate(session_id=5)
    assert stub.mode_reads == 1


async def test_dashboard_failure_is_reported(stub):
    """(3) The handler swallowed the reason and only the caller's text survived."""
    stub.raise_dashboard = True
    out = await master_briefing.generate(session_id=5)
    assert "(unavailable)" in out
    assert stub.errors, "dashboard failed and nothing was logged"


async def test_scene_profile_failure_is_reported(stub):
    """(2) `except Exception: pass` hid a failure of the appearance block."""
    stub.raise_scene = True
    await master_briefing.generate(session_id=5)
    assert stub.warnings, "appearance block failed and nothing was logged"


async def test_blocks_are_stripped_and_joined(stub, monkeypatch):
    """(4) The wrapper used to branch and append the same string either way."""
    monkeypatch.setattr(session_rituals, "generate_open", lambda sid: _padded(sid))

    async def _padded(sid):
        stub.sessions_seen.append(sid)
        return "   ## PADDED BLOCK   "

    monkeypatch.setattr(session_rituals, "generate_open", _padded)
    out = await master_briefing.generate(session_id=5)
    assert "\n\n## PADDED BLOCK\n\n" in out
    assert "   ##" not in out
