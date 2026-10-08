"""Both bridges answer with JSON on every failure path, never a traceback or a silent wrong session.

Pre-fix failures these pin:
- `ooc_bridge.handle` kept going when maintenance mode resolved no session: `direct` wrote to the
  stale `Config.SESSION_ID`, `slaves` queried session NULL, `portrait` raised TypeError.
- `kilo_bridge.handle` ran `Database.init()` and `resolve_session()` before its `try`, so a refused
  connection or an unresolvable session escaped as a traceback.
- `ooc_bridge.main` ran `Database.init()` before its `try`: an unreachable database printed a
  traceback and no JSON.
- `kilo_bridge` swallowed malformed params JSON and ran the action with `{}`.

Scratch session 900 only; sessions 3 and 5 are never written.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRATCH = 900


def _dead_db_run(script: str, args: list[str], stdin: str, tmp_path) -> subprocess.CompletedProcess:
    """Run a bridge script against a port nothing listens on."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("OC_PG_", "RP_SESSION"))}
    env.update({"OC_PG_HOST": "127.0.0.1", "OC_PG_PORT": "1",
                "DEEPSEEK_API_KEY": os.environ.get("DEEPSEEK_API_KEY", "test-key")})
    return subprocess.run([sys.executable, str(ROOT / "scripts" / script), *args], input=stdin,
                          capture_output=True, text=True, cwd=str(ROOT), env=env, timeout=120)


class TestOocBridgeMaintenanceWithoutSession:
    @pytest.fixture()
    async def scratch(self, monkeypatch, tmp_path):
        from core import session
        from core.config import Config
        from core.db import Database

        monkeypatch.setattr(session, "_maintenance_active", lambda: True)
        monkeypatch.setattr(session, "ACTIVE_ARC", tmp_path / "no-such-arc")
        monkeypatch.delenv("RP_SESSION", raising=False)
        monkeypatch.setattr(Config, "SESSION_ID", SCRATCH)
        await Database.init()
        await Database.execute("DELETE FROM maya_rp.ooc_directives WHERE session_id=$1", SCRATCH)
        yield
        await Database.execute("DELETE FROM maya_rp.ooc_directives WHERE session_id=$1", SCRATCH)
        await Database.close()

    async def test_direct_without_a_session_in_maintenance_refuses_and_writes_nothing(self, scratch):
        """Pre-fix `sid` was None, `add_directive(None, ...)` fell back to the stale
        `Config.SESSION_ID` and inserted a directive into a campaign nobody named."""
        from core.db import Database
        from scripts import ooc_bridge

        before = await Database.fetchval(
            "SELECT count(*) FROM maya_rp.ooc_directives WHERE session_id=$1", SCRATCH)
        reply = await ooc_bridge.handle({"call": "direct", "note": "x"})
        after = await Database.fetchval(
            "SELECT count(*) FROM maya_rp.ooc_directives WHERE session_id=$1", SCRATCH)
        assert reply["ok"] is False and "session_id" in reply["error"], reply
        assert after == before, "a directive landed on the stale default session"

    @pytest.mark.parametrize("call", ["state", "slaves", "portrait"])
    async def test_every_session_scoped_call_refuses_without_a_session(self, scratch, call):
        """Pre-fix `slaves` queried session NULL and `portrait` raised TypeError."""
        from scripts import ooc_bridge

        reply = await ooc_bridge.handle({"call": call})
        assert reply["ok"] is False and "session_id" in reply["error"], reply


class TestKiloBridgeAnswersInJson:
    async def test_an_unresolvable_session_answers_in_the_error_shape(self, monkeypatch):
        """Pre-fix `resolve_session` raised RuntimeError before the `try`: a traceback."""
        from scripts import kilo_bridge

        async def no_init():
            return None

        def refuse(_explicit=None):
            raise RuntimeError("no session resolved")

        monkeypatch.setattr(kilo_bridge.Database, "init", no_init)
        monkeypatch.setattr(kilo_bridge, "resolve_session", refuse)
        result = await kilo_bridge.handle("status", {})
        assert result["status"] == "error" and "no session resolved" in result["data"], result
        assert result["action"] == "status"

    async def test_a_failed_database_init_answers_in_the_error_shape(self, monkeypatch):
        """Pre-fix `Database.init()` sat before the `try`: a refused connection was a traceback."""
        from scripts import kilo_bridge

        async def broken_init():
            raise ConnectionRefusedError("db down")

        monkeypatch.setattr(kilo_bridge.Database, "init", broken_init)
        result = await kilo_bridge.handle("status", {})
        assert result["status"] == "error" and "db down" in result["data"], result

    async def test_maintenance_with_no_session_answers_in_the_error_shape(self, monkeypatch):
        """Pre-fix the action ran with `sid=None` and queried session NULL as if it were a session."""
        from scripts import kilo_bridge

        monkeypatch.setattr(kilo_bridge, "resolve_session", lambda explicit=None: None)
        reply = await kilo_bridge.handle("bonds", {})
        assert reply["status"] == "error" and "no session" in reply["data"], reply

    def test_malformed_params_json_is_an_error_not_an_empty_dict(self):
        """Pre-fix `except JSONDecodeError: pass` ran the action with `{}`."""
        from scripts import kilo_bridge

        params, problem = kilo_bridge.parse_params("{bad")
        assert params is None and "invalid params JSON" in problem
        assert kilo_bridge.parse_params('{"session": 900}') == ({"session": 900}, None)

    def test_the_script_rejects_malformed_params_before_touching_the_database(self, tmp_path):
        done = _dead_db_run("kilo_bridge.py", ["status", "{bad"], "", tmp_path)
        reply = json.loads(done.stdout.strip().splitlines()[-1])
        assert reply["status"] == "error" and "invalid params JSON" in reply["data"], reply
        assert done.returncode == 1


class TestOocBridgeMainWithUnreachableDatabase:
    async def test_a_refused_connection_still_ends_in_one_json_line(self, monkeypatch, capsys):
        """Pre-fix `Database.init()` ran before the `try`: the error escaped `main` with no JSON."""
        import io

        from core.db import Database
        from scripts import ooc_bridge

        async def refuse():
            raise ConnectionRefusedError("database unreachable")

        async def keep_the_shared_pool():
            return None

        monkeypatch.setattr(Database, "init", refuse)
        monkeypatch.setattr(Database, "close", keep_the_shared_pool)
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"call": "state", "session_id": SCRATCH})))
        code = await ooc_bridge.main()
        reply = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
        assert reply["ok"] is False and "ConnectionRefusedError" in reply["error"], reply
        assert code == 1


class TestOocBridgeMainReplyOutlivesTheMirrorFlush:
    """The memory-block refresh runs after the reply is printed; its failure cannot cost the reply."""

    @pytest.fixture()
    def quiet_pool(self, monkeypatch):
        import io

        from core.db import Database
        from scripts import ooc_bridge

        async def noop():
            return None

        monkeypatch.setattr(Database, "init", noop)
        monkeypatch.setattr(Database, "close", noop)
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"call": "state", "session_id": SCRATCH})))

        async def answer(_request):
            return {"ok": True}

        monkeypatch.setattr(ooc_bridge, "handle", answer)

    async def test_a_flush_that_raises_still_leaves_the_reply_on_stdout(self, quiet_pool, monkeypatch, capsys):
        """Pre-fix the flush ran in `finally` before `json.dump`: an exception it raised
        propagated out of `main` and the reply was never printed."""
        from scripts import ooc_bridge

        async def explode():
            raise RuntimeError("refresh blew up")

        monkeypatch.setattr(ooc_bridge, "_flush_context_mirror", explode)
        code = await ooc_bridge.main()
        lines = capsys.readouterr().out.strip().splitlines()
        assert lines == ['{"ok": true}'], lines
        assert code == 0

    async def test_the_reply_is_printed_before_the_flush_starts(self, quiet_pool, monkeypatch, capsys):
        """Pre-fix the flush ran first: at flush time stdout was still empty."""
        from scripts import ooc_bridge

        seen: list[str] = []

        async def record():
            seen.append(capsys.readouterr().out)

        monkeypatch.setattr(ooc_bridge, "_flush_context_mirror", record)
        await ooc_bridge.main()
        assert seen == ['{"ok": true}\n'], f"stdout at flush time: {seen!r}"

    async def test_the_pool_closes_after_the_flush(self, quiet_pool, monkeypatch):
        """The flush reads through the pool, so `Database.close` must come last."""
        from core.db import Database
        from scripts import ooc_bridge

        order: list[str] = []

        async def flush():
            order.append("flush")

        async def close():
            order.append("close")

        monkeypatch.setattr(ooc_bridge, "_flush_context_mirror", flush)
        monkeypatch.setattr(Database, "close", close)
        await ooc_bridge.main()
        assert order == ["flush", "close"], order

    @pytest.mark.parametrize("failure", ["import", "build"])
    async def test_the_real_flush_swallows_its_own_failures(self, monkeypatch, tmp_path, failure):
        """Pre-fix the `core.context` import sat outside the flush's `try`: an ImportError escaped."""
        import core
        from scripts import ooc_bridge

        monkeypatch.setattr(ooc_bridge, "_CONTEXT_PENDING", [(SCRATCH, str(tmp_path / "ctx.md"))])
        if failure == "import":
            monkeypatch.delattr(core, "context", raising=False)
            monkeypatch.setitem(sys.modules, "core.context", None)
        else:
            from core import context as context_layer

            async def broken(_session_id):
                raise RuntimeError("build failed")

            monkeypatch.setattr(context_layer, "build_context", broken)
        await ooc_bridge._flush_context_mirror()
        assert not (tmp_path / "ctx.md").exists(), "a failed refresh wrote a mirror file"
