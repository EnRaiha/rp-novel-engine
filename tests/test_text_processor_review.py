#!/usr/bin/env python3
"""Review of `core/text_processor.py`.

The module was reviewed once already — `2972ae41` made the phrasing deterministic by occurrence and
replaced `ds_register_delta`'s character comparison — and `tests/test_text_register.py` pins those
two. This file covers what that pass left behind.

One defect: the lexicon handled inflections in five entries and not in four. `\borgasm\b` left
`orgasms` standing, `\bbreasts\b` left `breast`, and `\bejaculat(ed|ing|es)?\b` let the noun
`ejaculation` through — the clinical vocabulary the block exists to remove, surviving its own pass in
the form a model is at least as likely to write. The pass runs on the prose boundary
(`core/stream_interceptor.py:171` calls `enforce_ds_register` on every expanded line), so the gap is
served to the player.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.text_processor import enforce_ds_register, register_report  # noqa: E402

CLINICAL = ("penis", "vagina", "breast", "nipple", "intercourse", "sex",
            "orgasm", "ejaculat", "thrust", "moan", "climax")


class TestEveryFormOfTheTermIsCaught:
    def test_the_plural_is_replaced_like_the_singular(self):
        for text in ("One orgasm, then another.", "Two orgasms later."):
            out = enforce_ds_register(text)
            assert "orgasm" not in out.lower(), (text, out)

    def test_the_noun_form_of_the_verb_is_replaced(self):
        out = enforce_ds_register("He spoke of the ejaculation.")
        assert "ejaculat" not in out.lower(), out

    def test_the_singular_anatomy_is_replaced_like_the_plural(self):
        for text in ("her breasts", "her breast", "each nipple", "his nipples"):
            out = enforce_ds_register(text)
            assert "breast" not in out.lower(), (text, out)
            assert "nipple" not in out.lower(), (text, out)

    def test_no_clinical_term_survives_any_of_its_forms(self):
        """The block's own contract, swept over the forms a model writes."""
        sample = ("He touched her breast and then her breasts. One orgasm followed, then two "
                  "orgasms. The ejaculation came. She felt a nipple stiffen, then both nipples. "
                  "They had intercourse. He thrust and she moaned at the climax.")
        out = enforce_ds_register(sample).lower()
        for term in CLINICAL:
            assert term not in out, f"{term!r} survived the register pass: {out}"


class TestThePassStaysWhatItWas:
    def test_the_same_input_gives_the_same_output(self):
        sample = "He thrust into her, she had an orgasm, then fade to black."
        assert enforce_ds_register(sample) == enforce_ds_register(sample)

    def test_the_second_pass_changes_nothing(self):
        """A replacement must not be a pattern of its own, or the prose drifts on every pass."""
        sample = "He thrust into her breasts, she had an orgasm, then fade to black."
        once = enforce_ds_register(sample)
        assert enforce_ds_register(once) == once, once

    def test_the_report_names_the_patterns_it_hit(self):
        counts = register_report("Two orgasms and a fade to black.")
        assert sum(counts.values()) >= 2, counts
        assert any("orgasm" in pattern for pattern in counts), counts
        assert any("fade to black" in pattern for pattern in counts), counts

    def test_clean_prose_is_untouched(self):
        text = "The pool glows warmly and the steam finds the ceiling."
        assert enforce_ds_register(text) == text
