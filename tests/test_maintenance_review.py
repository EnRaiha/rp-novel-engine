#!/usr/bin/env python3
"""Review of `core/maintenance.py`.

GM MAYA maintenance is the operator's hand on two rules at once: the register guard stands down, and
a frozen campaign accepts writes again. Four defects, all on the paths that decide whether that hand
is still there:

1. `_read` caught every exception and returned `{}`, so a corrupt or unreadable state file read as
   "not armed". The guard resumed billing deviation and the frozen campaign refused writes again,
   and nothing on screen said why the override had gone.
2. `status()` ran `float(d.get("expires_at", 0))` unguarded, so a record holding a non-numeric
   expiry raised `ValueError` straight out of `active()`, which the register guard and the session
   resolver both call.
3. `disarm()` wrote over an unreadable record, replacing the file the operator could still have
   repaired with a dict built from nothing.
4. `arm()` accepted any `ttl`, so `gm_maint.py arm --ttl -5` armed a window that had already closed
   and printed `active: True`.

Every test here runs against its own temporary state directory. Without that fixture these tests
would write `~/.config/rp-engine/maintenance.json` and arm maintenance on the live engine.
"""
from __future__ import annotations

import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from core import maintenance  # noqa: E402


@pytest.fixture(autouse=True)
def state_dir(tmp_path, monkeypatch):
    """Its own `RP_MAINT_DIR`, so no test touches the operator's real state directory."""
    monkeypatch.setattr(maintenance, "STATE_DIR", tmp_path)
    monkeypatch.setattr(maintenance, "STATE_FILE", tmp_path / "maintenance.json")
    monkeypatch.setattr(maintenance, "PLAY_FLAG", tmp_path / "play.lock")
    return tmp_path


class TestACorruptRecordIsNotReadAsNotArmed:
    def test_a_missing_file_is_plainly_not_armed(self, state_dir):
        assert maintenance.status() == {"active": False}

    def test_a_corrupt_file_is_reported_rather_than_swallowed(self, state_dir):
        maintenance.STATE_FILE.write_text("{not json", encoding="utf-8")
        st = maintenance.status()
        assert st["active"] is False
        assert st.get("unreadable") is True, st
        assert "JSONDecodeError" in st["error"], st
        # Fail-safe direction, and the reason travels with it: `active()` is called every turn.
        assert maintenance.active() is False

    def test_an_armed_record_with_a_bad_expiry_answers_instead_of_raising(self, state_dir):
        maintenance.STATE_FILE.write_text(
            json.dumps({"active": True, "armed_by": "operator", "expires_at": "soon"}),
            encoding="utf-8")
        st = maintenance.status()
        assert st["active"] is False and st.get("unreadable") is True, st
        assert "'soon'" in st["error"], st
        # The record is left on disk for the operator rather than rewritten.
        assert json.loads(maintenance.STATE_FILE.read_text())["expires_at"] == "soon"

    def test_an_armed_record_survives_a_round_trip(self, state_dir):
        armed = maintenance.arm(maintenance.PHRASE, source="review", ttl=60)
        assert maintenance.status()["armed_by"] == "review"
        assert maintenance.active() is True
        assert armed["expires_at"] > time.time()


class TestDisarmDoesNotManufactureARecord:
    def test_disarm_refuses_to_write_over_an_unreadable_record(self, state_dir):
        maintenance.STATE_FILE.write_text("{not json", encoding="utf-8")
        out = maintenance.disarm("test")
        assert out["disarmed"] is False and out.get("unreadable") is True, out
        assert maintenance.STATE_FILE.read_text() == "{not json", (
            "the unreadable record was replaced by a dict built from nothing")

    def test_disarm_with_nothing_armed_writes_nothing(self, state_dir):
        out = maintenance.disarm("test")
        assert out == {"active": False, "disarmed": False, "reason": "nothing was armed"}, out
        assert not maintenance.STATE_FILE.exists()

    def test_arm_then_disarm_keeps_the_arm_record(self, state_dir):
        armed = maintenance.arm(maintenance.PHRASE, source="review", ttl=60)
        out = maintenance.disarm("review")
        assert out["armed_by"] == "review", out
        assert out["armed_at"] == armed["armed_at"], out
        assert out["expires_at"] == armed["expires_at"], out
        assert out["disarm_reason"] == "review" and out["disarmed_at"] >= out["armed_at"], out
        assert maintenance.active() is False


class TestTheWindowItArms:
    def test_a_non_positive_ttl_is_refused_by_name(self, state_dir):
        for ttl in (0, -5):
            with pytest.raises(ValueError) as exc:
                maintenance.arm(maintenance.PHRASE, source="test", ttl=ttl)
            assert "ttl" in str(exc.value) and str(ttl) in str(exc.value), exc.value
        # Nothing was written, so the operator's next `status` does not read a closed window.
        assert maintenance.status() == {"active": False}
        assert not maintenance.STATE_FILE.exists()

    def test_an_expired_window_reports_expiry_once(self, state_dir):
        armed = maintenance.arm(maintenance.PHRASE, source="test", ttl=60)
        armed["expires_at"] = time.time() - 1
        maintenance._write(armed)
        assert maintenance.status() == {"active": False, "expired": True}


class TestThePlayLockHasNoWriter:
    """The module's safety claim is "never armed while a play session is live".

    That refusal reads `PLAY_FLAG.exists()`, and nothing in `modules/`, `core/` or `scripts/` writes
    the flag: the only writer in the tree is `tests/test_session.py`. So the guard fires only if a
    human touches the file by hand, and the docstring describes a check the engine never arms.
    Pinned as current behaviour so the day someone wires it is the day this test fails, which is the
    signal that the pin can go.
    """

    def test_no_production_module_writes_the_play_flag(self):
        writers = []
        for folder in ("modules", "core", "scripts"):
            for path in sorted((ROOT / folder).glob("*.py")):
                if path.name == "maintenance.py":
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                if "play.lock" in text or "PLAY_FLAG" in text:
                    writers.append(str(path.relative_to(ROOT)))
        assert writers == [], (
            "a production writer for the play lock appeared; the refusal in arm() can now fire and"
            f" this pin should be replaced by a test of the path: {writers}")
