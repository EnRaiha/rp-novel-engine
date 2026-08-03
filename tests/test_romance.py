"""Tests for modules/romance.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from modules.romance import (
    detect_intent, check_threshold, check_jealousy_logic,
    calculate_saturation_state, calculate_pursuit, get_milestones,
    get_crossed_thresholds, generate_scene, TIERS, VOICE_PROFILES
)
import pytest

class TestRomanceEngine:
    def test_detect_intent_ember(self):
        result = detect_intent("I want to flirt with Nethara")
        assert result["detected"] is True
        assert result["companion"] == "Nethara"

    def test_detect_intent_inferno(self):
        result = detect_intent("I want to take you and claim you, Nethara")
        assert result["detected"] is True

    def test_detect_no_intent(self):
        result = detect_intent("What is the status of the fleet?")
        assert result["detected"] is False

    def test_check_threshold_allowed(self):
        result = check_threshold(7, "kiss")
        assert result["allowed"] is True
        assert result["tier"] == "flame"

    def test_check_threshold_denied(self):
        result = check_threshold(3, "kiss")
        assert result["allowed"] is False

    def test_jealousy_strong(self):
        companions = [{"name": "Melano", "bond": 7}]
        result = check_jealousy_logic("Nethara", 9, companions)
        assert result is not None
        assert result["intensity"] == "strong"

    def test_jealousy_none(self):
        companions = [{"name": "Melano", "bond": 2}]
        result = check_jealousy_logic("Nethara", 3, companions)
        assert result is None

    def test_saturation_states(self):
        assert calculate_saturation_state(90)["state"] == "glutted"
        assert calculate_saturation_state(50)["state"] == "balanced"
        assert calculate_saturation_state(10)["state"] == "starved"

    def test_pursuit_ratio(self):
        result = calculate_pursuit(1, 10, 50)
        assert result["pursuit_stage"] == "they_chase"

    def test_milestones(self):
        ms = get_milestones(4, 8)
        assert "flirt_unlocked" in ms
        assert "kiss_unlocked" in ms

    def test_voice_profiles(self):
        for name in ("Nethara", "Melano", "Valia"):
            assert name in VOICE_PROFILES
            assert VOICE_PROFILES[name]["marker"] in ("!", "...", "*")

    def test_tiers(self):
        for tier in ("ember", "flame", "inferno"):
            assert tier in TIERS
