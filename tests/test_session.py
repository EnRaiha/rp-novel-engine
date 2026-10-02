"""Tests for core/session.py and core/maintenance.py — the session source of truth.

The engine no longer guesses a session, so the resolver precedence and its two
escape hatches (the arc file, GM MAYA maintenance) are load-bearing. Everything
here runs against a temporary state directory; the live arc is never touched.
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402

from core import maintenance, session  # noqa: E402


@pytest.fixture()
def state_dir(tmp_path, monkeypatch):
    """Redirect both modules at a temporary directory, restore afterwards."""
    monkeypatch.setattr(maintenance, "STATE_DIR", tmp_path)
    monkeypatch.setattr(maintenance, "STATE_FILE", tmp_path / "maintenance.json")
    monkeypatch.setattr(maintenance, "PLAY_FLAG", tmp_path / "play.lock")
    monkeypatch.setattr(session, "ACTIVE_ARC", tmp_path / "active_arc")
    monkeypatch.setattr(session, "FROZEN", tmp_path / "frozen_sessions")
    monkeypatch.delenv("RP_SESSION", raising=False)
    return tmp_path


class TestResolver:
    """Precedence: explicit, env, arc, then maintenance. Never a guess."""

    def test_refuses_when_nothing_resolves(self, state_dir):
        with pytest.raises(RuntimeError):
            session.resolve_session()

    def test_explicit_id_wins(self, state_dir):
        session.set_active_arc(5)
        assert session.resolve_session(7) == 7

    def test_env_beats_arc(self, state_dir, monkeypatch):
        session.set_active_arc(5)
        monkeypatch.setenv("RP_SESSION", "9")
        assert session.resolve_session() == 9

    def test_arc_is_the_default(self, state_dir):
        session.set_active_arc(5)
        assert session.resolve_session() == 5

    def test_zero_and_blank_are_unset(self, state_dir):
        """The harness sends 0 for 'no session'; that must fall through, not target 0."""
        session.set_active_arc(5)
        assert session.resolve_session(0) == 5
        assert session.resolve_session("0") == 5
        assert session.resolve_session("") == 5
        assert session.resolve_session(None) == 5

    def test_maintenance_resolves_none_without_arc(self, state_dir):
        maintenance.arm(maintenance.PHRASE, source="test")
        assert session.resolve_session() is None

    def test_mode_label_reports_maintenance(self, state_dir):
        assert session.mode_label() == "play"
        maintenance.arm(maintenance.PHRASE, source="test")
        assert session.mode_label() == "GM MAYA maintenance"


class TestFrozen:
    """A frozen campaign stays readable and stops accepting writes."""

    def test_round_trip(self, state_dir):
        assert session.frozen() == set()
        session.set_frozen([3])
        assert session.frozen() == {3}
        assert session.is_frozen(3)
        assert not session.is_frozen(5)

    def test_reads_tolerates_separators_and_junk(self, state_dir):
        session.FROZEN.write_text("3, 7\n\nnope 9\n")
        assert session.frozen() == {3, 7, 9}

    def test_missing_file_is_empty(self, state_dir):
        assert session.frozen() == set()

    def test_refuse_frozen_blocks_a_write(self, state_dir):
        from core import ooc

        session.set_frozen([3])
        with pytest.raises(ooc.FrozenSession):
            ooc._refuse_frozen(3)
        ooc._refuse_frozen(5)  # unfrozen: no raise

    def test_maintenance_is_the_only_way_in(self, state_dir):
        from core import ooc

        session.set_frozen([3])
        maintenance.arm(maintenance.PHRASE, source="test")
        ooc._refuse_frozen(3)  # armed: the operator may repair a frozen campaign


class TestMaintenance:
    """GM MAYA: the operator phrase, the play lock, and the TTL."""

    def test_phrase_gate(self, state_dir):
        with pytest.raises(PermissionError):
            maintenance.arm("gm maya")
        with pytest.raises(PermissionError):
            maintenance.arm("open sesame")

    def test_arm_status_disarm(self, state_dir):
        assert maintenance.status() == {"active": False}
        maintenance.arm(maintenance.PHRASE, source="test", ttl=60)
        assert maintenance.active()
        assert maintenance.status()["armed_by"] == "test"
        maintenance.disarm("test")
        assert not maintenance.active()

    def test_refuses_while_a_play_session_is_live(self, state_dir):
        maintenance.PLAY_FLAG.write_text("live\n")
        assert maintenance.play_is_live()
        with pytest.raises(RuntimeError):
            maintenance.arm(maintenance.PHRASE, source="test")
        maintenance.arm(maintenance.PHRASE, source="test", force=True)

    def test_expiry_closes_the_window(self, state_dir):
        state = maintenance.arm(maintenance.PHRASE, source="test", ttl=60)
        state["expires_at"] = time.time() - 1
        maintenance._write(state)
        assert maintenance.status() == {"active": False, "expired": True}

    def test_audit_stands_down_while_armed(self, state_dir):
        """The register guard is what maintenance mode buys."""
        from core.ooc import LAYER_DIALOGUE, OocRule, audit_text

        rule = OocRule("modern-slip", "modern_phrasing", "re:(okay|hey)", 4, LAYER_DIALOGUE)
        text = 'She shrugs. "Okay, proceed."'
        assert audit_text(text, [rule], LAYER_DIALOGUE), "expected a finding outside maintenance"
        maintenance.arm(maintenance.PHRASE, source="test")
        assert audit_text(text, [rule], LAYER_DIALOGUE) == []
        maintenance.disarm("test")
        assert audit_text(text, [rule], LAYER_DIALOGUE)
