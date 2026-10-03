#!/usr/bin/env python3
"""Review of `modules/local_gen.py`.

Two defects:

1. `_strip_think` stripped `slash-any-word`, not a list of artifact tags, so it ate ordinary slash
   writing out of every generated template: "24/7", "he/she", "and/or". The same strip matched
   `/thinking` with its `/think` alternative and left the tail as "ING" in the prose. This module is
   the only writer of `stream_templates.expanded_text`.
2. `upsert_template` pushed `trigger_tag_embed = EXCLUDED.trigger_tag_embed` unconditionally. A caller
   that supplies no `readable_hint` computes no vector, so the upsert overwrote a good embedding with
   NULL, and `StreamInterceptor.load_cache` skips every row whose vector is NULL: the template stayed
   servable by exact tag and silently left the semantic tier.

No caller passes `readable_hint=""` today, `cli.py cmd_intimacy` always builds one, so the wipe is
latent. It is reachable through the parameter's own default and it destroys a stored vector, so it is
fixed rather than reported.

The DB test writes one `stream_templates` row and removes that row by the id it captured from the
insert. The table carries no `session_id`; it is a catalogue, so an unfiltered upsert is correct.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from core.db import Database  # noqa: E402
from modules import guardrails, local_gen  # noqa: E402

#: `trigger_tag_embed` is `vector(768)`, so a fixture vector has to carry 768 numbers.
DIM = 768


def _vec(fill: float = 0.1) -> str:
    return "[" + ",".join([str(fill)] * DIM) + "]"


class TestTheStripKeepsProseAndDropsArtifacts:
    def test_ordinary_slashes_survive(self):
        """The broad strip ate the word after every slash. None of these is a generation artifact."""
        for text in ("Open 24/7, no exceptions.",
                     "He/she decides, and/or asks first.",
                     "Rated 9/10 by the dock crew.",
                     "She read km/h off the dial."):
            assert local_gen._strip_think(text) == text, text

    def test_the_artifact_tags_still_go(self):
        assert local_gen._strip_think("Fine /think but slow") == "Fine but slow"
        assert local_gen._strip_think("Yes /assistant") == "Yes"
        # The space the removed token left behind is pre-existing behaviour: the old broad strip
        # left "Done !" too, and tidying punctuation here would rewrite prose the strip never
        # touched. Pinned as it is rather than fixed under a claim about mangling.
        assert local_gen._strip_think("Done /answer!") == "Done !"
        # `/thinking` used to lose its prefix and leave "ING" behind; the first pattern now needs a
        # word boundary, so the whole tag goes.
        assert local_gen._strip_think("ok /THINKING") == "ok"

    def test_a_clean_paragraph_is_untouched(self):
        text = "The pool glows warmly. Steam finds the ceiling and stays there."
        assert local_gen._strip_think(text) == text


class TestGenerateKeepsTheGateItClaims:
    async def test_generate_strips_what_the_provider_returns(self, monkeypatch):
        async def fake(*_a, **_kw):
            return "Fine /think but slow"

        monkeypatch.setattr(local_gen.ds, "generate", fake)
        assert await local_gen.generate("anything") == "Fine but slow"

    async def test_a_blocked_generation_is_not_returned_as_prose(self, monkeypatch):
        async def fake(*_a, **_kw):
            return "mind control the captain"

        monkeypatch.setattr(local_gen.ds, "generate", fake)
        monkeypatch.setattr(guardrails, "check_generation",
                            lambda _t: {"allowed": False, "reason": "blocked concept"})
        out = await local_gen.generate("anything")
        assert out == "[generation blocked: blocked concept]", out

    async def test_a_broken_guardrail_returns_the_text_and_says_so(self, monkeypatch):
        """Pinned current behaviour, not an endorsement: the gate is fail-open.

        When `check_generation` itself raises, `generate` logs at error level and returns the
        unguarded text anyway. Pinned so the ruling on fail-open has a test to change.
        """
        async def fake(*_a, **_kw):
            return "unguarded prose"

        def explode(_t):
            raise RuntimeError("guardrail unavailable")

        monkeypatch.setattr(local_gen.ds, "generate", fake)
        monkeypatch.setattr(guardrails, "check_generation", explode)
        assert await local_gen.generate("anything") == "unguarded prose"


class TestUpsertKeepsAVectorItWasNotGiven:
    async def test_an_upsert_with_no_hint_keeps_the_stored_embedding(self):
        """`trigger_tag_embed = EXCLUDED.trigger_tag_embed` wrote NULL over a live vector."""
        await Database.init()
        tag = f"[REVIEW local_gen {__import__('os').getpid()}]"
        row_id = None
        try:
            row_id = await Database.fetchval(
                "INSERT INTO maya_rp.stream_templates"
                " (trigger_tag, expanded_text, category, readable_hint, trigger_tag_embed)"
                " VALUES ($1, $2, 'review', 'a readable hint', $3::vector) RETURNING id",
                tag, "first text", _vec())
            assert row_id is not None

            out = await local_gen.upsert_template(tag, "second text")
            assert out == {"trigger_tag": tag, "category": "intimacy"}, out

            row = await Database.fetchrow(
                "SELECT expanded_text, trigger_tag_embed FROM maya_rp.stream_templates WHERE id=$1",
                row_id)
            assert row["expanded_text"] == "second text", row
            assert row["trigger_tag_embed"] is not None, (
                "the hint-less upsert wiped a stored vector, which drops the template out of the"
                " interceptor's semantic tier")
        finally:
            if row_id is not None:
                await Database.execute(
                    "DELETE FROM maya_rp.stream_templates WHERE id=$1", row_id)
            gone = await Database.fetchval(
                "SELECT count(*) FROM maya_rp.stream_templates WHERE id=$1", row_id)
            await Database.close()
            print(f"cleanup: stream_templates rows left for id {row_id} = {gone}")
            assert gone == 0

    async def test_the_catalogue_has_no_session_column(self):
        """Pins why the upsert carries no session filter: there is nothing to filter on."""
        await Database.init()
        try:
            cols = await Database.fetch(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_schema='maya_rp' AND table_name='stream_templates'")
            names = {c["column_name"] for c in cols}
            assert "session_id" not in names, names
        finally:
            await Database.close()
