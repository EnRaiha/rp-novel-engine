"""Module review: core/context.py.

TWO DEFECTS.

`_story_row` answered a failed read and an absent column the same way, a plain `None`, and the caller
turns None into the default brief. A database that could not be read therefore served the default
campaign brief with no line anywhere. It logs now, with the session and the error.

`render_blocks` rebuilt the `[LORE]` block itself while `core/campaign.render_lore` writes the same
heading and the same 320-character truncation. That copy had no production caller: it was exercised
only by a test, and the inline copy was the one the turn actually used. The renderer calls it now, so
the two cannot drift apart and the campaign's own renderer is live.

Also measured and pinned by test, because a silent empty string there would hide it: `STAGE_TO_ACT`
names the same three stages `core/ooc.STAGE_ORDER` does. A stage added to the ladder and not to this
map would drop the `[ACT]` block from every turn without saying so.

Reported, not changed: `act_line` returns an empty string for an unknown stage, which is right for
"no stage" and silent for a wrong one.

The scratch session is derived from the process id in a band no other test file uses. Every row this
file writes is removed in the fixture's finally.
"""
from __future__ import annotations

import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import context  # noqa: E402
from core import ooc  # noqa: E402
from core.db import Database  # noqa: E402

SCRATCH_SESSION = 100 + (os.getpid() % 100)


@pytest.fixture()
async def scratch_session():
    """A session with nothing in it, removed afterwards."""
    await Database.init()
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status)"
        " VALUES ($1,'Context review session','active') ON CONFLICT (id) DO NOTHING",
        SCRATCH_SESSION,
    )
    try:
        yield SCRATCH_SESSION
    finally:
        for statement in ("DELETE FROM maya_rp.ooc_system_state WHERE session_id=$1",
                          "DELETE FROM maya_rp.sessions WHERE id=$1"):
            await Database.execute(statement, SCRATCH_SESSION)
        await Database.close()


class TestTheLoreBlockHasOneRenderer:
    """`campaign.render_lore` had no production caller; `render_blocks` had a copy of it."""

    def test_the_block_is_built_by_the_campaign_renderer(self, monkeypatch):
        seen: list[list] = []
        monkeypatch.setattr(context.campaign, "render_lore",
                            lambda hits, limit=4: seen.append(list(hits)) or "[LORE]\n- one: two")
        lore = [{"title": "one", "content": "two"}]
        text = context.render_blocks({"lore": lore})
        assert "[LORE]" in text and "- one: two" in text
        assert seen == [lore], "the renderer must hand the entries to the module's own renderer"

    def test_the_block_matches_the_campaign_renderer_exactly(self):
        lore = [{"title": "A", "content": "B" * 400}, {"title": "C", "content": "D"}]
        assert context.render_blocks({"lore": lore}) == context.campaign.render_lore(lore).strip()

    def test_an_empty_lore_list_renders_nothing(self):
        assert context.render_blocks({"lore": []}) == ""


class TestTheBriefFallback:
    """An absent column and a failed read both returned None, and only one is documented."""

    async def test_a_failed_read_is_reported_and_the_default_brief_stands(self, monkeypatch):
        said: list[tuple[str, str]] = []

        async def broken(*_args, **_kwargs):
            raise RuntimeError("sessions table gone")

        monkeypatch.setattr(context.Database, "fetchrow", broken)
        monkeypatch.setattr("core.log.warn", lambda module, message: said.append((module, message)))
        assert await context._story_row(1) is None
        assert said and said[0][0] == "context"
        assert "sessions table gone" in said[0][1]

    async def test_a_session_with_no_story_path_reads_the_default(self, scratch_session):
        """The documented case stays quiet: no row value, no warning, the default path."""
        assert await context.brief_path(scratch_session) == context.STORY_PATH

    async def test_no_session_reads_the_default(self):
        assert await context.brief_path(None) == context.STORY_PATH


class TestTheStageToActMap:
    def test_it_names_the_same_stages_as_the_ladder(self):
        """A stage added to `core/ooc.STAGE_ORDER` and not here drops the [ACT] block in silence."""
        assert set(context.STAGE_TO_ACT) == set(ooc.STAGE_ORDER)

    def test_every_stage_resolves_to_an_act_number(self):
        assert sorted(context.STAGE_TO_ACT.values()) == [1, 2, 3]

    def test_no_stage_renders_no_act_line(self):
        assert context.act_line(None) == ""
        assert context.act_line("") == ""


class TestTheAssembly:
    """`build_context` is the one call the harness makes; its text is what the model reads."""

    async def test_the_returned_text_is_the_render_of_the_returned_blocks(self, scratch_session):
        built = await context.build_context(scratch_session)
        assert set(built) == {"session_id", "story", "blocks", "text"}
        assert built["session_id"] == scratch_session
        assert built["text"] == context.render_blocks(built["blocks"])

    async def test_a_campaign_with_nothing_in_it_still_answers(self, scratch_session):
        built = await context.build_context(scratch_session)
        assert built["blocks"]["recent_events"] == []
        assert built["blocks"]["companions"] == []
        assert built["blocks"]["goals"] == []
        assert built["story"], "the default brief is read from the adventures tree"

    async def test_the_sections_that_carry_data_appear(self, scratch_session):
        await Database.execute(
            "INSERT INTO maya_rp.objectives (session_id, title, objective_type, priority, status)"
            " VALUES ($1,'Review objective','review',1,'active')",
            scratch_session,
        )
        try:
            built = await context.build_context(scratch_session)
            assert "[CURRENT GOAL]" in built["text"] and "Review objective" in built["text"]
            assert "[SCENE]" in built["text"], "the scene line carries the game day"
        finally:
            await Database.execute(
                "DELETE FROM maya_rp.objectives WHERE session_id=$1", scratch_session)
