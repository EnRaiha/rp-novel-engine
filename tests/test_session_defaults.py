"""The process default session, and the two ways it can point somewhere nobody chose.

`Config.SESSION_ID` is resolved once, at import. That is fine for a short-lived command and wrong for
a long-lived one: the bridge or the MCP server that started while the arc was session 3 keeps writing
to session 3 after the arc moves to 5, and session 3 is the frozen reference.

The other way is a silent fallback. When the resolver fails, the config falls back to the legacy TKG
campaign, which is exactly the frozen session. So the failure has to say so out loud.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class TestStaleProcessDefault:
    def test_a_stale_default_names_the_drift(self):
        from core.session import stale_process_default

        # 3 is the legacy session the engine used before the arc moved.
        message = stale_process_default(3)
        assert message is not None, "a process stuck on the old session must be told"
        assert "session 3" in message and "frozen" in message

    def test_a_matching_default_says_nothing(self):
        from core.config import Config
        from core.session import stale_process_default

        assert stale_process_default(int(Config.SESSION_ID)) is None

    def test_the_config_default_matches_the_resolver(self):
        """The two must not disagree today, or every count below is meaningless."""
        from core.config import Config
        from core.session import resolve_session

        assert int(Config.SESSION_ID) == int(resolve_session())


class TestFallbackAnnouncesItself:
    def test_the_fallback_warns_on_stderr(self, monkeypatch, capsys):
        import importlib

        import core.config as config

        monkeypatch.setattr(sys, "path", sys.path)
        # Make the resolver fail the way a missing arc file does, then rebuild the default.
        monkeypatch.setenv("RP_SESSION", "")
        monkeypatch.setattr("core.session.active_arc", lambda: None)
        monkeypatch.setattr("core.session._maintenance_active", lambda: False)
        monkeypatch.setattr(config, "SESSION_FALLBACK_USED", False)
        session = config._default_session()
        captured = capsys.readouterr()
        assert session == 3, "the fallback is the legacy campaign"
        assert "FROZEN" in captured.err, "a silent fallback is a write to a session nobody chose"
        assert config.SESSION_FALLBACK_USED is True
        importlib.reload(config)
