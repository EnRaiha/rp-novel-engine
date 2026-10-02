"""The register pass: deterministic, counted, and reached from the prose boundary.

`core/text_processor.py` had no production caller, and while reviewing it for a caller two defects
turned up that no caller would have survived. `random.choice` decided the phrasing, so the same input
produced different canon prose every run. And `ds_register_delta` compared the two strings character
by character, which returns -1 whenever a replacement changes the length — which almost all of them
do. It counted nothing, ever.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.text_processor import ds_register_delta, enforce_ds_register, register_report  # noqa: E402
from core.stream_interceptor import StreamInterceptor  # noqa: E402

SAMPLE = "He thrust into her, she had an orgasm, then fade to black."


class TestDeterminism:
    def test_the_same_input_gives_the_same_output_twice(self):
        assert enforce_ds_register(SAMPLE) == enforce_ds_register(SAMPLE)

    def test_repeated_occurrences_vary_within_one_pass(self):
        out = enforce_ds_register("orgasm. orgasm. orgasm.")
        assert len({part for part in out.split(". ") if part}) > 1, "every occurrence got the same words"


class TestCounting:
    def test_the_delta_counts_substitutions_not_characters(self):
        # The old body returned -1 here, because `sex` -> `the union` changes the length.
        assert ds_register_delta("sex", enforce_ds_register("sex")) == 1

    def test_the_report_names_each_pattern(self):
        counts = register_report(SAMPLE)
        assert sum(counts.values()) >= 3, counts
        assert any("fade to black" in pattern for pattern in counts)

    def test_clean_text_counts_zero(self):
        assert ds_register_delta("She waited at the rail.", "unchanged") == 0


class TestWiring:
    def test_the_prose_boundary_holds_the_register(self):
        out = StreamInterceptor().expand_text(SAMPLE)
        assert "GM Note" in out, "the boundary does not apply the register pass"
        assert "fade to black" not in out
        assert "thrust" not in out

    def test_the_boundary_still_expands(self):
        # A string with no tags must survive the added pass unchanged apart from the register.
        text = "Grey light on the dock."
        assert StreamInterceptor().expand_text(text) == text
