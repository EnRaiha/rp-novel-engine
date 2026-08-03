"""Tests for modules/local_gen.py — local abliterated generation helpers."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from modules.local_gen import _strip_think
import pytest


class TestStripThink:
    def test_removes_think_blocks(self):
        assert _strip_think("OK /think") == "OK"
        assert _strip_think("Fine /think but slow") == "Fine but slow"

    def test_removes_stray_tags(self):
        assert _strip_think("Yes /assistant") == "Yes"

    def test_clean_text_untouched(self):
        assert _strip_think("The pool glows warmly.") == "The pool glows warmly."

    def test_case_insensitive(self):
        assert _strip_think("ok /THINK") == "ok"
