"""One suite at a time against the live campaign database.

Four reviewers run pytest concurrently against the same `maya_rp` database, and every failure set
changed between runs: crew_system, celestial, prison, weapon_upgrade and dry_run_safety failed in
different combinations, and each of them passed together in isolation. One teammate measured it
directly — 38 of 38 pass alone, and 1053-1055 pass in a clean worktree with only his change, with the
remaining one to three failures always belonging to another module.

The cause is not the tests being wrong. It is two processes writing session-scoped rows at once, the same
race that made `test_ooc.py` fail before its scratch session was derived from the process id.

A suite that reports different failures each run teaches the team to ignore failures, which is worse than
a slow suite. This fixture takes an exclusive lock for the whole session, so a second concurrent run waits
its turn instead of interleaving.

Set RP_TEST_NO_LOCK=1 to skip the lock deliberately. If a run dies while holding it, the lock is released
by the kernel when the process exits; there is no stale lock to clear.
"""
from __future__ import annotations

import fcntl
import os
import pathlib
import time

import pytest

LOCK_PATH = pathlib.Path(os.environ.get("RP_TEST_LOCK", "/tmp/rp-engine-pytest.lock"))


@pytest.fixture(scope="session", autouse=True)
def _one_suite_at_a_time():
    if os.environ.get("RP_TEST_NO_LOCK") == "1":
        yield
        return
    handle = LOCK_PATH.open("w")
    start = time.monotonic()
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print(f"\nwaiting for the other pytest run to finish ({LOCK_PATH})")
        fcntl.flock(handle, fcntl.LOCK_EX)
        waited = time.monotonic() - start
        print(f"lock acquired after {waited:.0f}s; another run was using the database")
    try:
        yield
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()
