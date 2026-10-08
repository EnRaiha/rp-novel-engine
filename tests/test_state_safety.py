#!/usr/bin/env python3
"""Safety of the session/maintenance state files and `State.save_checkpoint`.

Four defects:

1. `session.frozen()` returned `set()` on ANY read error, so an unreadable `frozen_sessions`
   (permissions, bad encoding, a directory) made every session read as writable and the frozen
   guard let a write into session 3.
2. `set_active_arc` / `set_frozen` wrote through a fixed `.tmp` name, so concurrent writers
   raced on one temp file.
3. `maintenance.status()` wrote `active: False` back on expiry with no lock; an operator `arm()`
   landing between its read and write was silently overwritten. `_write` shared the fixed-tmp
   race, and `_read` handed non-dict JSON (`[]`, `null`) to `d.get`, raising AttributeError.
4. `StateManager.save_checkpoint` wrote a row and file for frozen sessions, never created
   `BACKUP_DIR`, and named files at one-second resolution so two saves collided.

Every test runs against a tmp_path state directory; no test arms the live engine. Scratch
session ids come from the 900-999 range; sessions 3 and 5 are never written.
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402

from core import maintenance, session  # noqa: E402
from core.config import Config  # noqa: E402
from core.db import Database  # noqa: E402
from core.ooc import _refuse_frozen  # noqa: E402
from core.state import StateManager  # noqa: E402


@pytest.fixture(autouse=True)
def state_dir(tmp_path, monkeypatch):
    """Point every state path at tmp_path so nothing touches ~/.config/rp-engine."""
    monkeypatch.setattr(maintenance, "STATE_DIR", tmp_path)
    monkeypatch.setattr(maintenance, "STATE_FILE", tmp_path / "maintenance.json")
    monkeypatch.setattr(maintenance, "PLAY_FLAG", tmp_path / "play.lock")
    monkeypatch.setattr(session, "STATE_DIR", tmp_path)
    monkeypatch.setattr(session, "ACTIVE_ARC", tmp_path / "active_arc")
    monkeypatch.setattr(session, "FROZEN", tmp_path / "frozen_sessions")
    monkeypatch.delenv("RP_SESSION", raising=False)
    return tmp_path


class TestAnUnreadableFrozenListFailsClosed:
    def test_a_directory_in_place_of_the_file_refuses_writes(self, state_dir):
        """Pre-fix: read_text raised IsADirectoryError, frozen() returned set(), the write passed."""
        session.FROZEN.mkdir()
        with pytest.raises(PermissionError, match="frozen_sessions"):
            _refuse_frozen(3)
        with pytest.raises(session.FrozenListUnreadable):
            session.is_frozen(3)

    @pytest.mark.skipif(os.geteuid() == 0, reason="root reads a chmod 000 file")
    def test_a_file_without_read_permission_refuses_writes(self, state_dir):
        """Pre-fix: PermissionError was swallowed and every session read as writable."""
        session.FROZEN.write_text("3\n")
        session.FROZEN.chmod(0)
        try:
            with pytest.raises(PermissionError):
                _refuse_frozen(3)
        finally:
            session.FROZEN.chmod(0o600)

    def test_undecodable_bytes_refuse_writes(self, state_dir):
        session.FROZEN.write_bytes(b"\xff\xfe3\n")
        with pytest.raises(session.FrozenListUnreadable):
            session.is_frozen(3)

    def test_armed_maintenance_lets_the_operator_through(self, state_dir):
        session.FROZEN.mkdir()
        maintenance.arm(maintenance.PHRASE, source="test")
        assert session.is_frozen(3) is False
        _refuse_frozen(3)

    def test_a_missing_file_still_means_nothing_is_frozen(self, state_dir):
        assert session.frozen() == set()
        assert session.is_frozen(3) is False
        _refuse_frozen(3)

    def test_the_stale_default_note_survives_an_unreadable_list(self, state_dir, monkeypatch):
        session.FROZEN.mkdir()
        session.set_active_arc(5)
        assert "unreadable" in session.stale_process_default(current=3)


class TestStateFilesUseUniqueTempNames:
    def test_set_active_arc_never_uses_the_fixed_tmp_name(self, state_dir, monkeypatch):
        """Pre-fix: both writers used `active_arc.tmp`."""
        sources = []
        real = os.replace
        monkeypatch.setattr(os, "replace", lambda src, dst: (sources.append(str(src)), real(src, dst))[1])
        session.set_active_arc(5)
        session.set_active_arc(7)
        assert sources, "set_active_arc did not go through os.replace"
        assert all(not s.endswith("active_arc.tmp") for s in sources), sources
        assert len(set(sources)) == len(sources), f"temp name reused: {sources}"
        assert session.active_arc() == 7
        assert sorted(p.name for p in state_dir.iterdir()) == ["active_arc"], list(state_dir.iterdir())

    def test_set_frozen_leaves_no_stray_tmp_files(self, state_dir):
        session.set_frozen([3])
        session.set_frozen([3, 9])
        assert session.frozen() == {3, 9}
        assert sorted(p.name for p in state_dir.iterdir()) == ["frozen_sessions"]

    def test_maintenance_write_never_uses_the_fixed_tmp_name(self, state_dir, monkeypatch):
        sources = []
        real = os.replace
        monkeypatch.setattr(os, "replace", lambda src, dst: (sources.append(str(src)), real(src, dst))[1])
        maintenance.arm(maintenance.PHRASE, source="test")
        assert sources and all(not s.endswith("maintenance.tmp") for s in sources), sources
        assert sorted(p.name for p in state_dir.iterdir()) == ["maintenance.json"]


class TestStatusDoesNotWrite:
    def _expired(self):
        rec = maintenance.arm(maintenance.PHRASE, source="test", ttl=60)
        rec["expires_at"] = time.time() - 1
        maintenance._write(rec)

    def test_an_expired_record_is_left_byte_identical(self, state_dir):
        """Pre-fix: status() rewrote the file with active=false and an expired_at stamp."""
        self._expired()
        before = maintenance.STATE_FILE.read_bytes()
        assert maintenance.status() == {"active": False, "expired": True}
        assert maintenance.STATE_FILE.read_bytes() == before

    def test_an_arm_after_expiry_is_not_overwritten_by_status(self, state_dir):
        self._expired()
        maintenance.arm(maintenance.PHRASE, source="operator")
        assert maintenance.status()["active"] is True
        assert maintenance.active() is True
        assert json.loads(maintenance.STATE_FILE.read_text())["active"] is True

    def test_arm_replaces_an_expired_record_cleanly(self, state_dir):
        self._expired()
        rec = maintenance.arm(maintenance.PHRASE, source="operator")
        assert "expired_at" not in json.loads(maintenance.STATE_FILE.read_text())
        assert rec["active"] is True

    @pytest.mark.parametrize("payload", ["[]", "null", "3", '"x"'])
    def test_non_object_json_reads_as_unreadable(self, state_dir, payload):
        """Pre-fix: `[].get` raised AttributeError out of active()."""
        maintenance.STATE_FILE.write_text(payload)
        assert "_unreadable" in maintenance._read()
        st = maintenance.status()
        assert st["active"] is False and st.get("unreadable") is True, st
        assert maintenance.active() is False


class TestSaveCheckpointSafety:
    @pytest.mark.asyncio
    async def test_a_frozen_session_is_refused_with_no_file_and_no_row(
            self, scratch_session, state_dir, monkeypatch):
        """Pre-fix: a checkpoint row and file were written for any session, frozen or not."""
        backup = state_dir / "backups"
        monkeypatch.setattr(Config, "BACKUP_DIR", str(backup))
        monkeypatch.setattr(session, "is_frozen", lambda sid: True)
        await Database.init()
        try:
            with pytest.raises(PermissionError, match="frozen"):
                await StateManager.save_checkpoint(scratch_session, "x")
            assert not backup.exists() or not list(backup.iterdir()), "a file was written"
            rows = await Database.fetch(
                "SELECT 1 FROM story_checkpoints WHERE session_id=$1", scratch_session)
            assert rows == [], "a row was written"
        finally:
            await Database.execute("DELETE FROM story_checkpoints WHERE session_id=$1", scratch_session)

    @pytest.mark.asyncio
    async def test_a_missing_backup_dir_is_created_and_same_second_saves_stay_distinct(
            self, scratch_session, state_dir, monkeypatch):
        """Pre-fix: FileNotFoundError on the missing dir; second-resolution names collided."""
        backup = state_dir / "nested" / "backups"
        monkeypatch.setattr(Config, "BACKUP_DIR", str(backup))
        await Database.init()
        # `story_checkpoints.session_id` is a foreign key into `sessions`.
        await Database.execute(
            "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1,'State safety scratch','active')"
            " ON CONFLICT (id) DO NOTHING", scratch_session)
        try:
            first = await StateManager.save_checkpoint(scratch_session, "a")
            second = await StateManager.save_checkpoint(scratch_session, "b")
            assert first != second, "two saves produced one path"
            assert len(list(backup.iterdir())) == 2, list(backup.iterdir())
        finally:
            await Database.execute("DELETE FROM story_checkpoints WHERE session_id=$1", scratch_session)
            await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", scratch_session)
