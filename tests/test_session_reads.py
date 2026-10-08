"""Readers resolve the session per call, not from the import-time `Config.SESSION_ID`.

`Config.SESSION_ID` is fixed when `core.config` is imported. The kilo bridge serves the DSH plugin
for hours, so every reader that fell back to it kept answering for the session current at start.
Scratch sessions 900-999 only; nothing here writes a row.
"""
from __future__ import annotations

import pytest

from core import guard, session
from core.config import Config
from core.db import Database

STALE = 901
LIVE = 902


@pytest.fixture
def stale_default(monkeypatch, tmp_path):
    """Import-time default 901, the live arc 902 via RP_SESSION, no arc file, maintenance off."""
    monkeypatch.setattr(Config, "SESSION_ID", STALE)
    monkeypatch.setenv("RP_SESSION", str(LIVE))
    monkeypatch.setattr(session, "ACTIVE_ARC", tmp_path / "no_active_arc")
    monkeypatch.setattr(session, "_maintenance_active", lambda: False)


@pytest.fixture
def unresolved(monkeypatch, tmp_path):
    """Nothing resolves: no RP_SESSION, no arc file."""
    monkeypatch.delenv("RP_SESSION", raising=False)
    monkeypatch.setattr(session, "ACTIVE_ARC", tmp_path / "no_active_arc")


class TestRequireSession:
    async def test_it_refuses_when_nothing_resolves(self, unresolved, monkeypatch):
        """Pre-fix: no `require_session`; callers fell back to the stale import-time default."""
        monkeypatch.setattr(session, "_maintenance_active", lambda: False)
        with pytest.raises(RuntimeError, match="no session resolved"):
            session.require_session()

    async def test_it_raises_the_maintenance_error_when_maintenance_resolves_none(
            self, unresolved, monkeypatch):
        monkeypatch.setattr(session, "_maintenance_active", lambda: True)
        with pytest.raises(RuntimeError, match="maintenance mode resolves no session"):
            session.require_session()

    async def test_explicit_wins_over_the_environment(self, stale_default):
        assert session.require_session(903) == 903, "explicit id must win"


class TestGuardResolvesPerCall:
    async def test_check_scans_the_resolved_session_not_the_import_default(
            self, stale_default, monkeypatch):
        """Pre-fix: check() passed Config.SESSION_ID (901) to _ensure while RP_SESSION said 902."""
        seen = []

        async def fake_ensure(sid):
            seen.append(sid)

        async def fake_fetchrow(*args, **kwargs):
            return None

        monkeypatch.setattr(guard, "_ensure", fake_ensure)
        monkeypatch.setattr(Database, "fetchrow", fake_fetchrow)
        monkeypatch.setattr(guard, "_cache", {})

        await guard.check("x")

        assert seen == [LIVE], f"guard scanned {seen}, expected [{LIVE}]"

    async def test_check_returns_nothing_under_maintenance_and_scans_no_session(
            self, unresolved, monkeypatch):
        """Pre-fix: maintenance fell through to Config.SESSION_ID and scanned a guessed session."""
        monkeypatch.setattr(session, "_maintenance_active", lambda: True)
        seen = []

        async def fake_ensure(sid):
            seen.append(sid)

        monkeypatch.setattr(guard, "_ensure", fake_ensure)

        assert await guard.check("x") == []
        assert await guard.get_quick_facts("x") is None
        assert seen == [], f"maintenance scanned {seen}"


class TestCharQueryResolvesPerCall:
    async def test_every_territory_query_uses_the_resolved_session(self, stale_default, monkeypatch):
        """Pre-fix: the name path mixed `sid` (sectors) with Config.SESSION_ID (territory, fuzzy)."""
        from scripts import char_query

        calls = []

        async def fake_fetch(sql, *params):
            calls.append((sql, params))
            if "FROM maya_rp.territory WHERE session_id=$1" in sql and "LIKE" not in sql:
                return [{"system_name": "Kestrel"}]
            return []

        monkeypatch.setattr(Database, "fetch", fake_fetch)

        await char_query.resolve_loc("kestrl")

        assert calls, "no query reached the database"
        for sql, params in calls:
            assert LIVE in params, f"query ran without session {LIVE}: {params}"
            assert STALE not in params, f"query used the stale default: {params}"

    async def test_ship_and_character_loaders_use_the_resolved_session(
            self, stale_default, monkeypatch):
        from scripts import char_query

        calls = []

        async def fake_fetch(sql, *params):
            calls.append(params)
            return []

        monkeypatch.setattr(Database, "fetch", fake_fetch)

        await char_query.resolve_ship("nothing")
        await char_query._load_characters()

        assert calls and all(p[0] == LIVE for p in calls), f"params: {calls}"

    async def test_maintenance_raises_instead_of_falling_back(self, unresolved, monkeypatch):
        """Pre-fix: `resolve_session(None) or Config.SESSION_ID` returned the stale default."""
        from scripts import char_query

        monkeypatch.setattr(session, "_maintenance_active", lambda: True)
        monkeypatch.setattr(Config, "SESSION_ID", STALE)
        with pytest.raises(RuntimeError, match="maintenance mode resolves no session"):
            char_query._call_session()


class _FakeConn:
    def __init__(self, seen):
        self.seen = seen

    async def fetchval(self, sql, *params):
        return 7

    async def fetchrow(self, sql, *params):
        self.seen.append(params)
        return {"id": params[0], "name": "n", "status": "s", "game_day": 1}


class _FakePool:
    def __init__(self, seen):
        self.conn = _FakeConn(seen)

    def acquire(self):
        conn = self.conn

        class _Ctx:
            async def __aenter__(self_inner):
                return conn

            async def __aexit__(self_inner, *exc):
                return False

        return _Ctx()


class TestDatabaseStatusResolvesPerCall:
    async def test_status_reports_the_resolved_session(self, stale_default, monkeypatch):
        """Pre-fix: status() queried Config.SESSION_ID (901)."""
        seen = []
        pool = _FakePool(seen)

        async def fake_pool():
            return pool

        monkeypatch.setattr(Database, "_ensure_pool", fake_pool)

        out = await Database.status()

        assert seen == [(LIVE,)], f"status queried {seen}"
        assert out["session"]["id"] == LIVE

    async def test_status_reports_an_error_instead_of_failing_when_unresolved(
            self, unresolved, monkeypatch):
        monkeypatch.setattr(session, "_maintenance_active", lambda: False)
        seen = []

        async def fake_pool():
            return _FakePool(seen)

        monkeypatch.setattr(Database, "_ensure_pool", fake_pool)

        out = await Database.status()

        assert out["connected"] is True
        assert out["session"] is None and "error" in out, out
        assert seen == [], "no session row should be queried"


class TestBuildContextResolvesPerCall:
    async def test_default_path_uses_rp_session_not_config(self, stale_default, monkeypatch):
        """Pre-fix: build_context(None) used Config.SESSION_ID (901)."""
        from core import context, ooc

        seen = []

        class _Stop(Exception):
            pass

        async def fake_state(sid):
            seen.append(sid)
            raise _Stop

        monkeypatch.setattr(ooc, "state", fake_state)

        with pytest.raises(_Stop):
            await context.build_context()

        assert seen == [LIVE], f"build_context resolved {seen}, expected [{LIVE}]"
