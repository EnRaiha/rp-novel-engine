"""Module review: core/portraits.py.

Three defects, and the first is a rule this module wrote twice and let drift.

`queue` recorded a negative prompt belonging to the `real` style whatever style the prompt was
built with, while `scripts/portrait_render.py` recomputes that negative from `style()["negative"]`
and never reads the stored column. At the default `semi` the row described a semi prompt beside a
photoreal negative. `negative_for` is now the one place the rule lives; the renderer should call it
and cannot be changed from here, so that half is reported to the lead.

`inspect_line` promised the current emotion and delivered the portrait asset's, which is always
`neutral`: twelve of the thirteen reads in `INSPECT_READS` were unreachable and every `/inspect`
answered the same line. The caller now states the emotion it is narrating.

Two of the module's three caller-supplied keys were accepted in silence. `pending` refused an
unknown queue order while `queue` and `lookup` took an unknown occasion and `build_prompt` took an
unknown framing, so a typo queued a row the renderer would write to `emotions/<typo>.png`.
Measured before the change: 0 of the 686 asset rows carry a framing outside `FRAMING`, so nothing
stored depends on the old fallback.

The scratch session is derived from the process id in a band no other test file uses (700, 800 and
900 are taken), so concurrent runs do not delete each other's rows. Every row this file writes is
removed in the fixture's finally, and no test here goes near session 3 or session 5.
"""
from __future__ import annotations

import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import portraits  # noqa: E402
from core.db import Database  # noqa: E402

SCRATCH_SESSION = 600 + (os.getpid() % 100)
SUBJECT = "Portrait Review Subject"

CLEANUP = (
    "DELETE FROM maya_rp.character_assets WHERE session_id=$1",
    "DELETE FROM maya_rp.characters WHERE session_id=$1",
)


async def _clear(session_id: int) -> None:
    for statement in CLEANUP:
        await Database.execute(statement, session_id)


@pytest.fixture()
async def subject():
    """One character in this run's own session, removed before and after the test.

    `characters.session_id` carries a foreign key to `sessions.id`, so the session row comes first
    and goes last.
    """
    await Database.init()
    await _clear(SCRATCH_SESSION)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status)"
        " VALUES ($1,'Portrait review session','active') ON CONFLICT (id) DO NOTHING",
        SCRATCH_SESSION,
    )
    await Database.execute(
        "INSERT INTO maya_rp.characters (session_id, name, role, traits, bond, romance_stage)"
        " VALUES ($1,$2,'review subject','[\"loyal\"]'::jsonb,3,'companion')",
        SCRATCH_SESSION,
        SUBJECT,
    )
    try:
        yield SCRATCH_SESSION
    finally:
        await _clear(SCRATCH_SESSION)
        await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", SCRATCH_SESSION)
        await Database.close()


class TestTheRenderRecipeNamesOneStyle:
    """The prompt and the negative prompt in one row described two different styles."""

    def test_every_style_keeps_its_own_negative(self):
        for key, table in portraits.STYLES.items():
            assert portraits.negative_for("waist", key) == (
                f"{table['negative']}, {portraits.FRAMING_NEGATIVE}"), key

    def test_a_bust_shot_does_not_negate_the_crop_it_wants(self):
        for key, table in portraits.STYLES.items():
            assert portraits.negative_for("bust", key) == table["negative"], key
        assert "headshot" not in portraits.negative_for("bust", "semi")

    def test_the_default_negative_belongs_to_the_default_style(self, monkeypatch):
        """Before the fix this was `NEGATIVE_PROMPT`, which is the `real` style's negative."""
        monkeypatch.delenv("TKG_PORTRAIT_STYLE", raising=False)
        assert portraits.STYLES["semi"]["negative"] != portraits.NEGATIVE_PROMPT, (
            "the two styles have to differ for this test to mean anything")
        assert portraits.negative_for("waist").startswith(portraits.STYLES["semi"]["negative"])

    async def test_a_style_switch_reaches_the_recorded_row(self, subject, monkeypatch):
        monkeypatch.setenv("TKG_PORTRAIT_STYLE", "anime")
        queued = await portraits.queue(SCRATCH_SESSION, SUBJECT, "portrait")
        row = await Database.fetchrow(
            "SELECT prompt, negative_prompt, framing FROM maya_rp.character_assets WHERE id=$1",
            queued["asset_id"])
        assert portraits.STYLES["anime"]["suffix"] in row["prompt"]
        assert row["negative_prompt"] == (
            f"{portraits.STYLES['anime']['negative']}, {portraits.FRAMING_NEGATIVE}")
        assert row["framing"] == portraits.DEFAULT_FRAMING


class TestTheKeysTheModuleOwns:
    """An unknown key fell back to a default, so a typo rendered and said nothing."""

    def test_every_occasion_key_maps_to_its_emotion(self):
        for key, (emotion, _triggers) in portraits.OCCASIONS.items():
            assert portraits.emotion_for(key) == emotion
        for key in portraits.EMOTIONS:
            assert portraits.emotion_for(key) == key

    def test_padding_around_a_key_is_the_same_key(self):
        assert portraits.emotion_for(" romance ") == "flustered"

    async def test_an_unknown_occasion_is_refused_before_the_database_is_touched(self):
        """No fixture here on purpose: the refusal has to come before the first read."""
        with pytest.raises(ValueError, match="unknown occasion 'porrtrait'"):
            await portraits.queue(5, "anyone", "porrtrait")
        with pytest.raises(ValueError, match="unknown occasion 'porrtrait'"):
            await portraits.lookup(5, "anyone", "porrtrait")

    async def test_a_typo_leaves_no_row(self, subject):
        with pytest.raises(ValueError, match="unknown occasion"):
            await portraits.queue(SCRATCH_SESSION, SUBJECT, "porrtrait")
        left = await Database.fetchval(
            "SELECT count(*) FROM maya_rp.character_assets WHERE session_id=$1", SCRATCH_SESSION)
        assert left == 0, "a refused key wrote a row anyway"

    def test_an_unknown_framing_is_refused(self):
        with pytest.raises(ValueError, match="unknown framing 'fullbody'"):
            portraits.build_prompt({"name": "X", "role": "review"}, "neutral", framing="fullbody")

    def test_an_unknown_emotion_is_refused(self):
        with pytest.raises(ValueError, match="unknown emotion 'smug'"):
            portraits.build_prompt({"name": "X", "role": "review"}, "smug")

    def test_every_framing_the_table_names_is_still_rendered(self):
        for key, table in portraits.FRAMING.items():
            prompt = portraits.build_prompt({"name": "X", "role": "review"}, "neutral", framing=key)
            assert table["clause"] in prompt, key


class TestTheInspectRead:
    """`/inspect` answered the neutral read whatever the scene was doing."""

    def test_the_portrait_default_is_a_read_the_table_has(self):
        """The derived path indexes INSPECT_READS with this key."""
        assert portraits.OCCASIONS["portrait"][0] in portraits.INSPECT_READS

    async def test_all_thirteen_reads_are_reachable(self, subject):
        assert len(portraits.INSPECT_READS) == 13
        for key, read in portraits.INSPECT_READS.items():
            answer = await portraits.inspect_line(SCRATCH_SESSION, SUBJECT, emotion=key)
            assert answer["found"] is True
            assert answer["emotion"] == key
            assert read in answer["hint"], key

    async def test_the_default_path_answers_the_neutral_read(self, subject):
        answer = await portraits.inspect_line(SCRATCH_SESSION, SUBJECT)
        assert answer["emotion"] == "neutral"
        assert portraits.INSPECT_READS["neutral"] in answer["hint"]

    async def test_an_unknown_emotion_is_refused(self):
        with pytest.raises(ValueError, match="unknown emotion 'smug'"):
            await portraits.inspect_line(5, "anyone", emotion="smug")

    async def test_a_register_lookup_that_fails_is_reported(self, subject, monkeypatch):
        """The handler answered `registers = []` with no line anywhere saying why."""
        from core import campaign, log

        async def gone(*_args, **_kwargs):
            raise RuntimeError("rules table gone")

        monkeypatch.setattr(campaign, "character_rules", gone)
        said: list[tuple[str, str]] = []
        monkeypatch.setattr(log, "warn", lambda module, message: said.append((module, message)))
        answer = await portraits.inspect_line(SCRATCH_SESSION, SUBJECT, emotion="battle")
        assert portraits.INSPECT_READS["battle"] in answer["hint"]
        assert said == [("portraits", f"registers unavailable for {SUBJECT}: rules table gone")]
