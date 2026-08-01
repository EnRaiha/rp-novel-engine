"""Tests for modules/pregnancy.py — pure logic, no DB."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from modules.pregnancy import _trimester_for, DUE_SOON_WINDOW, BABY_NAMES
import pytest


class TestPregnancyTracker:
    def test_trimester_1(self):
        assert _trimester_for(0) == 1
        assert _trimester_for(89) == 1

    def test_trimester_2(self):
        assert _trimester_for(90) == 2
        assert _trimester_for(179) == 2

    def test_trimester_3(self):
        assert _trimester_for(180) == 3
        assert _trimester_for(269) == 3

    def test_due_soon_window_positive(self):
        assert DUE_SOON_WINDOW == 30

    def test_baby_names_cover_both_genders(self):
        assert "male" in BABY_NAMES and "female" in BABY_NAMES
        assert len(BABY_NAMES["male"]) > 0
        assert len(BABY_NAMES["female"]) > 0
