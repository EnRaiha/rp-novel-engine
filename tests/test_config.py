"""Tests for core/config.py"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.config import Config
import pytest

class TestConfig:
    def test_dsn_set(self):
        assert Config.DSN is not None
        assert "rp_engine" in Config.DSN
        assert "maya_memory" in Config.DSN

    def test_session_id_follows_the_arc(self, tmp_path, monkeypatch):
        """The process default comes from the engine's single session source."""
        from core import session
        from core.config import _default_session

        monkeypatch.setattr(session, "ACTIVE_ARC", tmp_path / "active_arc")
        monkeypatch.delenv("RP_SESSION", raising=False)
        assert isinstance(Config.SESSION_ID, int)
        (tmp_path / "active_arc").write_text("5\n")
        assert _default_session() == 5
        (tmp_path / "active_arc").unlink()
        assert _default_session() == 3  # no arc file: the legacy TKG campaign

    def test_paths_exist(self):
        assert os.path.isdir(Config.ROOT)
        assert os.path.isdir(os.path.join(Config.ROOT, "modules"))
        assert os.path.isdir(os.path.join(Config.ROOT, "scripts"))
        assert os.path.isdir(os.path.join(Config.ROOT, "core"))

    def test_module_flags(self):
        assert len(Config.MODULES) >= 40
        for name, active in Config.MODULES.items():
            assert isinstance(name, str)
            assert isinstance(active, bool)

    def test_active_modules(self):
        active = Config.active_modules()
        assert len(active) >= 40
        assert "economy" in active

    def test_is_module_active(self):
        assert Config.is_module_active("economy") is True
        assert Config.is_module_active("nonexistent") is False

    def test_summary(self):
        s = Config.summary()
        assert "Session:" in s
        assert "TKG" in s
