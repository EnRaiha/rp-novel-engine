"""Races in the infrastructure layer: state-file mirror, pool reconnect, guard cache, log roll.

Each test names the failure it pinned on the code before the fix.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import asyncpg
import pytest

from core import guard, log, ooc
from core.db import Database

ROOT = Path(__file__).resolve().parent.parent

#: One OS process per scratch session. `state` is stubbed (no DB rows) and sleeps so every process
#: sits between "loaded the list" and "replaced the file" at the same moment.
_WORKER = textwrap.dedent(
    """
    import asyncio, sys
    sys.path.insert(0, {root!r})
    from core import ooc

    async def fake_state(sid):
        await asyncio.sleep(0.15)
        return {{"deviation": sid, "roleplay_points": 1, "audits": 1, "findings": 0,
                "debuff": None, "arc_stage": "x", "updated_at": "2026-01-01T00:00:00+00:00"}}

    ooc.state = fake_state
    print(asyncio.run(ooc.mirror_state_file(int(sys.argv[1]))))
    """
).format(root=str(ROOT))

SCRATCH = list(range(901, 909))


def _canned(sid: int) -> dict:
    return {"deviation": sid, "roleplay_points": 1, "audits": 1, "findings": 0,
            "debuff": None, "arc_stage": "x", "updated_at": "2026-01-01T00:00:00+00:00"}


class TestMirrorStateFileAcrossProcesses:
    def test_eight_processes_keep_all_their_entries(self, tmp_path):
        """Pre-fix: the last os.replace dropped the others' entries and the shared `.tmp` name
        made the loser's replace raise FileNotFoundError, swallowed into None."""
        target = tmp_path / "tkg-state.json"
        env = {**os.environ, "OOC_STATE_FILE": str(target)}
        procs = [subprocess.Popen([sys.executable, "-c", _WORKER, str(s)], env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                 for s in SCRATCH]
        outs = [p.communicate(timeout=60) for p in procs]
        for (out, err), p in zip(outs, procs):
            assert p.returncode == 0, err
            assert out.strip() == str(target), f"a mirror returned None: {out!r} {err!r}"
        entries = json.loads(target.read_text())
        assert sorted(e["sessionId"] for e in entries) == SCRATCH, "entries were lost"
        stray = [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
        assert stray == [], f"temp files left behind: {stray}"


class TestMirrorStateFileInOneProcess:
    async def test_concurrent_tasks_keep_all_their_entries(self, tmp_path, monkeypatch):
        """Pre-fix: tasks interleaved at the awaited state read and overwrote each other."""
        target = tmp_path / "tkg-state.json"
        monkeypatch.setattr(ooc, "state_file_path", lambda: target)

        async def fake_state(sid):
            await asyncio.sleep(0.05)
            return _canned(sid)

        monkeypatch.setattr(ooc, "state", fake_state)
        results = await asyncio.gather(*(ooc.mirror_state_file(s) for s in SCRATCH))
        assert all(r == str(target) for r in results), results
        entries = json.loads(target.read_text())
        assert sorted(e["sessionId"] for e in entries) == SCRATCH
        assert not [p for p in tmp_path.iterdir() if p.name.endswith(".tmp")]

    async def test_a_dict_valued_file_is_kept_as_corrupt_not_wiped_silently(self, tmp_path, monkeypatch):
        """Pre-fix: valid JSON that is not a list dropped every entry with no log and no copy."""
        target = tmp_path / "tkg-state.json"
        target.write_text('{"sessionId": 7}')
        logged: list[str] = []
        monkeypatch.setattr(ooc, "state_file_path", lambda: target)
        monkeypatch.setattr(ooc, "error", lambda m, msg: logged.append(msg))

        async def fake_state(sid):
            return _canned(sid)

        monkeypatch.setattr(ooc, "state", fake_state)
        assert await ooc.mirror_state_file(901) == str(target)
        corrupt = tmp_path / "tkg-state.json.corrupt"
        assert corrupt.exists(), "no .corrupt copy of the unusable file"
        assert json.loads(corrupt.read_text()) == {"sessionId": 7}
        assert logged, "the rebuild was not logged"
        assert [e["sessionId"] for e in json.loads(target.read_text())] == [901]

    async def test_non_utf8_bytes_rebuild_instead_of_escaping(self, tmp_path, monkeypatch):
        """Pre-fix: UnicodeDecodeError was not JSONDecodeError, so the mirror returned None."""
        target = tmp_path / "tkg-state.json"
        target.write_bytes(b"\xff\xfe\x00bad")
        monkeypatch.setattr(ooc, "state_file_path", lambda: target)

        async def fake_state(sid):
            return _canned(sid)

        monkeypatch.setattr(ooc, "state", fake_state)
        assert await ooc.mirror_state_file(902) == str(target)
        assert (tmp_path / "tkg-state.json.corrupt").exists()

    def test_an_empty_env_value_is_unset(self, monkeypatch):
        """Pre-fix: `Path("")` is `.`, so the mirror targeted the working directory."""
        monkeypatch.setenv("OOC_STATE_FILE", "")
        assert ooc.state_file_path() == Path("~/.dsh/ooc/tkg-state.json").expanduser()


class _Conn:
    def __init__(self, fail_commit: bool = False):
        self.fail_commit = fail_commit

    async def fetch(self, *a):
        return []

    def transaction(self, **kw):
        conn = self

        class Tx:
            async def start(self):
                pass

            async def commit(self):
                raise RuntimeError("commit boom")

            async def rollback(self):
                raise asyncpg.exceptions.InterfaceError("transaction already finished")

        return Tx()


class _Acquire:
    def __init__(self, pool):
        self.pool = pool

    def __await__(self):
        return self._get().__await__()

    async def _get(self):
        return await self.pool.take()

    async def __aenter__(self):
        self.conn = await self.pool.take()
        return self.conn

    async def __aexit__(self, *exc):
        return False


class _Pool:
    def __init__(self, dead: bool):
        self.dead = dead
        self.terminated = False
        self.closed = False

    async def take(self):
        if self.dead:
            raise asyncpg.exceptions.InterfaceError("pool is closed")
        return _Conn()

    def acquire(self):
        return _Acquire(self)

    async def release(self, conn):
        pass

    def terminate(self):
        self.terminated = True

    async def close(self):
        self.closed = True


class TestPoolReconnect:
    async def test_concurrent_failures_create_exactly_one_pool(self, monkeypatch):
        """Pre-fix: each of N failing tasks did close() then init(); several saw pool None and each
        called create_pool, leaking all but one and closing pools others had just built."""
        created: list[_Pool] = []

        async def fake_create_pool(**kw):
            await asyncio.sleep(0.05)
            pool = _Pool(dead=False)
            created.append(pool)
            return pool

        from core import name_gen
        monkeypatch.setattr(asyncpg, "create_pool", fake_create_pool)
        monkeypatch.setattr(name_gen, "set_global_conn", lambda p: None)
        dead = _Pool(dead=True)
        monkeypatch.setattr(Database, "pool", dead)
        results = await asyncio.gather(*(Database.fetch("SELECT 1") for _ in range(6)))
        assert results == [[]] * 6
        assert len(created) == 1, f"{len(created)} pools created for one outage"
        assert Database.pool is created[0], "the surviving pool is not the one in use"
        assert dead.terminated, "the dead pool was not terminated"

    async def test_a_failed_commit_raises_the_original_error(self, monkeypatch):
        """Pre-fix: the except rolled back a finished transaction and the rollback error replaced
        the commit error."""
        monkeypatch.setattr(Database, "pool", _Pool(dead=False))
        with pytest.raises(RuntimeError, match="commit boom"):
            async with Database.transaction():
                pass


class TestGuardCache:
    async def test_concurrent_sessions_do_not_share_characters(self, monkeypatch):
        """Pre-fix: the shared cache was reset before the awaited load and filled by whichever
        load finished last, so session 1 held session 2's characters."""
        rows = {1: [{"id": 11, "name": "Ann", "status": "alive", "role": "r", "bond": 1}],
                2: [{"id": 22, "name": "Bob", "status": "dead", "role": "r", "bond": 1}]}

        async def fake_fetch(query, sid):
            await asyncio.sleep(0.05 if sid == 1 else 0.01)
            return rows[sid]

        monkeypatch.setattr(Database, "fetch", fake_fetch)
        guard.invalidate()
        got1, got2 = await asyncio.gather(guard._ensure(1), guard._ensure(2))
        assert set(got1) == {11}, f"session 1 holds {set(got1)}"
        assert set(got2) == {22}, f"session 2 holds {set(got2)}"


    async def test_the_cache_reloads_after_the_ttl(self, monkeypatch):
        """Pre-fix: the cache never expired, so a death written mid-run stayed invisible."""
        calls = {"n": 0}

        async def fake_fetch(query, sid):
            calls["n"] += 1
            return [{"id": 1, "name": "Ann", "status": "alive", "role": "r", "bond": calls["n"]}]

        monkeypatch.setattr(Database, "fetch", fake_fetch)
        guard.invalidate()
        await guard._ensure(1)
        await guard._ensure(1)
        assert calls["n"] == 1, "a fresh cache was reloaded"
        monkeypatch.setattr(guard, "_cache_at", time.monotonic() - guard._CACHE_TTL_S - 1)
        assert (await guard._ensure(1))[1]["bond"] == 2, "an expired cache was served"
        guard.invalidate()
        await guard._ensure(1)
        assert calls["n"] == 3, "invalidate() did not force a reload"


class TestDatedFileHandler:
    def test_a_failed_roll_does_not_raise_into_the_caller(self, tmp_path, monkeypatch):
        """Pre-fix: the OSError from the first record after midnight escaped warn()/info()."""
        handler = log._DatedFileHandler.__new__(log._DatedFileHandler)
        logging.Handler.__init__(handler)
        handler.baseFilename = str(tmp_path / "yesterday.log")
        handler.stream = None
        handled: list[logging.LogRecord] = []

        def boom():
            raise OSError("disk full")

        monkeypatch.setattr(handler, "_roll_to_today", boom)
        monkeypatch.setattr(handler, "handleError", handled.append)
        record = logging.LogRecord("rp", logging.INFO, __file__, 1, "msg", None, None)
        handler.emit(record)
        assert handled == [record], "the failure was not routed to handleError"
