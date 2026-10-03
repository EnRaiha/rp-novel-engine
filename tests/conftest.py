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
import pytest_asyncio

#: Four tests in tests/test_deepseek_client.py fail without an API key, and the key's absence is not a
#: defect: it is how the module reports a missing key. Three reviewers reported those four as failures in
#: their suite lines and one of them spent a round deciding whether they were his. A dummy value here makes
#: the suite self-contained, so a red line means a real defect and every reviewer's line counts the same
#: things. Tests that need a real key should skip on a placeholder rather than fail.
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key")

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

#: Session ids reserved for test scratch work. 900-999 sits above the live arc (5) and the frozen
#: reference (3), and below nothing that matters, so a test can write freely inside its own slot.
SCRATCH_BASE = 900


@pytest_asyncio.fixture
async def scratch_session() -> int:
    """A session id no other test process is using.

    Fifty-six files write to session 5, which is the live arc, and that is why the suite needs a session
    lock: two runs sharing one session delete each other's rows. A test that asks for this fixture gets its
    own slot instead, so it can run beside another process rather than queueing behind it.

    Use it for anything that inserts, updates or deletes. Read-only tests can keep naming the arc they are
    reading, because reading a campaign is not what collides.

        async def test_something(scratch_session):
            await Database.init()
            await Database.execute("INSERT INTO maya_rp.x (session_id, ...) VALUES ($1, ...)",
                                   scratch_session, ...)

    The fixture deletes that session's rows afterwards, and it discovers them rather than assuming: it reads
    every `maya_rp` table that has a `session_id` column and deletes this session's rows from each. That is
    the contract a test author needs to rely on.

    It said that before it did it. The first version ended at `yield session_id`, so a generator with no code
    after its yield performed no teardown at all, while the docstring told eleven test files they could skip
    their own `finally`. A false contract in a cleanup helper is worse than no helper, because it is the
    helper that stops the author writing the cleanup themselves, and it was named as the remedy for the very
    hazard that destroyed the live arc's resources row.
    """
    import os

    session_id = SCRATCH_BASE + (os.getpid() % 100)
    yield session_id

    from core.db import Database

    try:
        tables = await Database.fetch(
            "SELECT table_name FROM information_schema.columns"
            " WHERE table_schema = 'maya_rp' AND column_name = 'session_id'")
    except Exception:
        return
    for row in tables:
        try:
            await Database.execute(
                f'DELETE FROM maya_rp."{row["table_name"]}" WHERE session_id = $1', session_id)
        except Exception:
            # A table with a session_id column that refuses the delete (a view, a foreign key, a permission)
            # is reported rather than swallowed, because a silent failure here is the defect this file just
            # had. The test author still owns rows the fixture could not remove.
            print(f"scratch_session: could not clear {row['table_name']}")
