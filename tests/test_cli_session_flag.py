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
