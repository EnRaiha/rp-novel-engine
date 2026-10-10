"""`--session` must reach the answer, not just the resolver.

Eleven commands added during the caller-less review derived the session again with
`take_session_flag(sys.argv)`. The flag is stripped in `__main__` before dispatch, so that call always
returned None and every command silently used the profile's session. `map stats --session=3` reported 0
while `get_system_stats(3)` reported 892 in the same second.

The resolved value is kept in `SID`, and the commands read it now. This test runs the real CLI as a
subprocess, because that is the only level at which the defect was visible: calling the module directly
was always correct.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _run(*args: str) -> str:
    env = {**os.environ, "DEEPSEEK_API_KEY": "test-key"}
    out = subprocess.run([sys.executable, "scripts/cli.py", *args], cwd=ROOT, capture_output=True,
                         text=True, env=env, timeout=120)
    return out.stdout + out.stderr


class TestTheFlagReachesTheAnswer:
    def test_a_session_with_a_world_reports_its_world(self):
        assert "total: 892" in _run("map", "stats", "--session=3")

    def test_the_space_form_works_too(self):
        assert "total: 892" in _run("map", "stats", "--session", "3")

    def test_the_pinned_session_still_reports_its_own_world(self):
        """Session 5's world is not seeded, so 0 is the correct answer for it."""
        assert "total: 0" in _run("map", "stats", "--session=5")

    def test_a_second_command_reads_the_flag_as_well(self):
        out = _run("wonders", "overview", "--session=3")
        assert "animals:" in out, out


class TestOneReaderForTheFlag:
    """`clear` read its own argv with a second reader that kept the first `--session`.

    `take_session_flag` keeps the last, so `clear --session=919 --session=918` cleared a different
    campaign than the one the process had resolved. The duplicate reader is gone; these pin the
    agreement between the reader `__main__` uses and the verb that used to disagree with it.
    """

    def test_the_reader_keeps_the_last_flag(self):
        from scripts.cli import take_session_flag

        explicit, rest = take_session_flag(["clear", "--session=919", "--session=918", "--yes"])
        assert explicit == "918"
        assert rest == ["clear", "--yes"]

    def test_the_reader_keeps_the_last_flag_across_both_forms(self):
        from scripts.cli import take_session_flag

        explicit, rest = take_session_flag(["--session", "919", "--session=918"])
        assert explicit == "918"
        assert rest == []

    def test_the_duplicate_reader_is_gone(self):
        import scripts.cli as cli

        assert not hasattr(cli, "_session_flag"), "two readers of one flag diverge again"

    def test_clear_agrees_with_the_process_reader(self, monkeypatch):
        """`clear` resolves through the reader `__main__` uses, so two flags give the last one.

        The resolver is replaced by a recorder, so no row is read and no campaign is touched. The
        old reader returned the first flag here, and 919 would reach the recorder.
        """
        import asyncio

        import scripts.cli as cli

        asked: list[str] = []
        refusal = RuntimeError("resolver stand-in: no row is read")

        def record(flag=None):
            asked.append(flag)
            raise refusal

        class _StubDatabase:
            async def init(self):
                return None

            async def close(self):
                return None

        monkeypatch.setattr(cli, "Database", _StubDatabase())
        monkeypatch.setattr("core.session.require_session", record)
        own = cli.sys.argv
        cli.sys.argv = ["cli.py", "clear", "--session=919", "--session=918"]
        try:
            with pytest.raises(SystemExit) as raised:
                asyncio.run(cli.cmd_clear())
        finally:
            cli.sys.argv = own

        assert raised.value.code == 2, "the recorder's refusal must leave through the session arm"
        assert asked == ["918"], f"clear resolved {asked}, not the last flag"
