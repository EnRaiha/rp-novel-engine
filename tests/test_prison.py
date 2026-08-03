"""Tests for modules/prison.py — uses mock DB"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from modules.prison import (
    _random_name, SECURITY_MULTIPLIERS, INTIMACY_PATHS,
    INTERROGATION_TIERS, CONVERSION_PATHS, ESCAPE_COUNTERMEASURES
)
import pytest

class TestPrisonConstants:
    def test_security_multipliers(self):
        assert SECURITY_MULTIPLIERS["maximum"] == 0.2
        assert SECURITY_MULTIPLIERS["isolated"] == 0.05

    def test_interrogation_tiers(self):
        for tier in ("standard", "enhanced", "brutal"):
            assert tier in INTERROGATION_TIERS
        assert INTERROGATION_TIERS["brutal"]["moral_cost"] == 8

    def test_intimacy_paths(self):
        assert "fear" in INTIMACY_PATHS
        assert "seduction" in INTIMACY_PATHS
        assert "stockholm" in INTIMACY_PATHS
        for path in INTIMACY_PATHS.values():
            assert "risk" in path
            assert "intimacy_style" in path

    def test_conversion_paths(self):
        for path in ("stockholm", "persuasion", "broken"):
            assert path in CONVERSION_PATHS

    def test_escape_countermeasures(self):
        assert len(ESCAPE_COUNTERMEASURES) >= 5
        names = [m["name"] for m in ESCAPE_COUNTERMEASURES]
        assert "cell_inspection" in names

    def test_random_name(self):
        name = _random_name()
        assert isinstance(name, str)
        assert len(name) > 2
