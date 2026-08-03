"""Tests for Erotic Playbook integration (2026-08-03) — positions ladder,
d100 roll modifiers, Watcher's Curse, Wife-Breaks-Door, sensory packets."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from modules.romance import (
    POSITIONS, TIERS, INTIMACY_TRAITS, WATCHERS_CURSE_TRAITS,
    _get_trait_modifier, generate_sensory_packet, _trait_keys,
    detect_intent,
)
from core.text_processor import enforce_ds_register
import pytest


class TestPositionLadder:
    def test_ladder_tiers(self):
        assert POSITIONS["peck"]["tier"] == "ember"
        assert POSITIONS["sandwich"]["tier"] == "flame"
        for p in ("doggy", "missionary", "piledriver", "pool_deck"):
            assert POSITIONS[p]["tier"] == "inferno"

    def test_ladder_modifiers(self):
        assert POSITIONS["peck"]["modifier"] == 0
        assert POSITIONS["sandwich"]["modifier"] == 5
        assert POSITIONS["doggy"]["modifier"] == 10
        assert POSITIONS["missionary"]["modifier"] == 20
        assert POSITIONS["piledriver"]["modifier"] == 30
        assert POSITIONS["pool_deck"]["modifier"] == 15

    def test_vow_and_breaker_flags(self):
        assert POSITIONS["missionary"]["vow_position"] is True
        assert POSITIONS["piledriver"]["breaks_watcher"] is True
        assert POSITIONS["pool_deck"]["breaks_watcher"] is True
        assert POSITIONS["doggy"]["breaks_watcher"] is False


class TestWatchersCurse:
    def test_curse_penalty_without_breaker(self):
        mod, narrative = _get_trait_modifier(["scientist", "overthinking"], "doggy")
        assert mod == -40
        assert "watches herself" in narrative

    def test_curse_breaker_bonus(self):
        mod, narrative = _get_trait_modifier(["scientist"], "piledriver")
        assert mod == 20
        assert "Gravity must defeat" in narrative

    def test_curse_pool_deck_breaker(self):
        mod, _ = _get_trait_modifier(["analytical"], "pool_deck")
        assert mod == 20

    def test_curse_traits_constant(self):
        assert "scientist" in WATCHERS_CURSE_TRAITS
        assert "analytical" in WATCHERS_CURSE_TRAITS


class TestIntimacyTraits:
    def test_century_denied_always_breaks(self):
        mod, _ = _get_trait_modifier(["immortal", "ancient"], "missionary")
        assert mod == 30

    def test_warriors_wall_penalty(self):
        mod, _ = _get_trait_modifier(["soldier"], "doggy")
        assert mod == -20

    def test_warriors_wall_missionary_breaks(self):
        mod, _ = _get_trait_modifier(["stoic"], "missionary")
        assert mod == 15

    def test_devotion_mastery(self):
        mod, _ = _get_trait_modifier(["wife", "devoted"], "doggy")
        assert mod == 50

    def test_trait_keys_mapping(self):
        keys = _trait_keys(["scientist", "immortal"])
        assert "watchers_curse" in keys and "century_denied" in keys


class TestSensoryPacket:
    def test_packet_structure(self):
        pkt = generate_sensory_packet("piledriver", True, ["scientist"], "heaven_pool")
        assert "environment" in pkt and "sensory" in pkt
        assert "emotional_beat" in pkt and "instruction" in pkt
        assert pkt["environment"]["lighting"] == "starfield wall, fusion-fed glow, steam"

    def test_position_normalization(self):
        pkt = generate_sensory_packet("pool deck", False, [], "forge")
        assert pkt["sensory"]["sight"]  # pool_deck lexicon resolved
        assert pkt["environment"]["mood"] == "raw power"

    def test_watcher_fail_beat(self):
        pkt = generate_sensory_packet("doggy", False, ["scientist"])
        assert "watches herself" in pkt["emotional_beat"]

    def test_century_pass_beat(self):
        pkt = generate_sensory_packet("missionary", True, ["immortal"])
        assert "century of cold" in pkt["emotional_beat"]

    def test_instruction_no_clinical(self):
        pkt = generate_sensory_packet("peck", True, [])
        assert "clinical" in pkt["instruction"]


class TestIntentExtension:
    def test_peck_ember(self):
        assert detect_intent("I peck her cheek")["intensity"] == "ember"

    def test_sandwich_flame(self):
        assert detect_intent("Let us sandwich him between us")["intensity"] == "flame"

    def test_piledriver_inferno(self):
        r = detect_intent("Piledriver her, then missionary")
        assert r["detected"] is True and r["intensity"] == "inferno"


class TestTextProcessor:
    def test_clinical_replaced(self):
        out = enforce_ds_register("He thrust into her, she had an orgasm, then fade to black.")
        assert "orgasm" not in out
        assert "thrust" not in out
        assert "GM Note" in out

    def test_clean_text_untouched(self):
        out = enforce_ds_register("The pool glows. Steam rises. She laughs.")
        assert out == "The pool glows. Steam rises. She laughs."
