#!/usr/bin/env python3
"""Review of `core/guard.py`.

Two defects:

1. `_ensure` caught every exception, emptied the cache and said nothing. Every check in `check()`
   walks that cache, so a read that failed turned the contradiction guard into a blank pass: the
   report came back "no contradictions" and the only difference was in a module nobody was watching.
2. The credits block read `res["credits"]` twice, once through `or 0` and once raw. `credits` is
   nullable, so the raw read formatted None and raised `TypeError`. The amount group is `[\\d,]+`,
   so a lone comma matched the pattern and `int("")` raised `ValueError` out of the guard.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import Database  # noqa: E402
from core import guard  # noqa: E402


class TestTheGuardDoesNotPassInSilence:
    async def test_a_failed_read_is_reported_and_the_next_call_retries(self, monkeypatch):
        """An empty cache means "no contradictions". A failed read must not look like that."""
        await Database.init()
        logged: list[tuple[str, str]] = []
        calls = {"n": 0}
        real_fetch = Database.fetch

        async def flaky(*a, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("connection reset by peer")
            return await real_fetch(*a, **kw)

        guard._cache, guard._cache_session = {}, None
        monkeypatch.setattr(guard, "error", lambda module, msg: logged.append((module, msg)))
        monkeypatch.setattr(Database, "fetch", flaky)
        try:
            await guard._ensure(3)
            assert guard._cache == {} and guard._cache_session is None, "a failed load was kept"
            assert logged and logged[0][0] == "guard", logged
            assert "connection reset by peer" in logged[0][1], logged

            # The retry: the failure clears the session key, so the next call loads for real.
            await guard._ensure(3)
            assert calls["n"] >= 2, "the failed load was not retried"
            assert guard._cache, "the retry loaded nothing"
        finally:
            guard._cache, guard._cache_session = {}, None
            await Database.close()


class TestTheCreditsReadAnswersInsteadOfRaising:
    async def _scratch_row(self, session_id: int, credits):
        """A resources row for a scratch session, removed by session id afterwards."""
        made_session = await Database.fetchval(
            "SELECT 1 FROM maya_rp.sessions WHERE id=$1", session_id) is None
        if made_session:
            await Database.execute(
                "INSERT INTO maya_rp.sessions (id, name) VALUES ($1, $2)",
                session_id, f"scratch-guard-{session_id}")
        made_row = await Database.fetchval(
            "SELECT 1 FROM maya_rp.resources WHERE session_id=$1", session_id) is None
        if made_row:
            await Database.execute(
                "INSERT INTO maya_rp.resources (session_id, credits) VALUES ($1, $2)",
                session_id, credits)
        return made_session, made_row

    async def _drop(self, session_id: int, made_session: bool, made_row: bool) -> None:
        if made_row:
            await Database.execute(
                "DELETE FROM maya_rp.resources WHERE session_id=$1", session_id)
        if made_session:
            await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", session_id)

    async def test_a_comma_with_no_digits_is_not_an_amount(self, scratch_session):
        await Database.init()
        made = (False, False)
        try:
            made = await self._scratch_row(scratch_session, 10)
            guard._cache, guard._cache_session = {}, None
            issues = await guard.check("the crew purchased , credit somewhere", scratch_session)
            assert issues == [], issues
        finally:
            await self._drop(scratch_session, *made)
            guard._cache, guard._cache_session = {}, None
            await Database.close()

    async def test_a_null_credits_column_reports_zero_available(self, scratch_session):
        """`credits` is nullable, and the message formatted the raw column."""
        await Database.init()
        made = (False, False)
        try:
            made = await self._scratch_row(scratch_session, None)
            guard._cache, guard._cache_session = {}, None
            issues = await guard.check("they purchased 500 credits of ore", scratch_session)
            assert [i["type"] for i in issues] == ["insufficient_credits"], issues
            assert "0C available" in issues[0]["detail"], issues[0]
        finally:
            await self._drop(scratch_session, *made)
            guard._cache, guard._cache_session = {}, None
            await Database.close()


class TestTheCacheCanLoadAtAll:
    """The defect that hid every other one.

    `_ensure` selected `weapon`, `is_dead` and `death_cause` from `maya_rp.characters`. None of the
    three columns exists, so every call raised `UndefinedColumnError`, the handler kept the cache
    empty, and the guard answered "no contradictions" for its whole life. The first thing it ever
    logged was this review's own fix.
    """

    async def test_the_columns_it_names_do_not_exist_and_the_cache_still_fills(self):
        await Database.init()
        try:
            guard._cache, guard._cache_session = {}, None
            present = {c["column_name"] for c in await Database.fetch(
                "SELECT column_name FROM information_schema.columns"
                " WHERE table_schema='maya_rp' AND table_name='characters'")}
            for column in ("weapon", "is_dead", "death_cause"):
                assert column not in present, (
                    f"characters now carries {column}, so the guard can read a dead character and"
                    " a weapon again; this pin should become a test of them")

            expected = await Database.fetchval(
                "SELECT count(*) FROM maya_rp.characters WHERE session_id=3")
            await guard._ensure(3)
            assert len(guard._cache) == expected > 0, (
                f"cache holds {len(guard._cache)} of {expected}")
        finally:
            guard._cache, guard._cache_session = {}, None
            await Database.close()

    async def test_a_dead_character_acting_is_reported(self, scratch_session):
        """End to end: a corpse named in the prose with an active verb."""
        await Database.init()
        made_session = False
        made_rows: list[int] = []
        try:
            made_session = await Database.fetchval(
                "SELECT 1 FROM maya_rp.sessions WHERE id=$1", scratch_session) is None
            if made_session:
                await Database.execute(
                    "INSERT INTO maya_rp.sessions (id, name) VALUES ($1, $2)",
                    scratch_session, f"scratch-guard-{scratch_session}")
            for name, status in (("Review Corpse", "dead"), ("Review Executed", "executed")):
                made_rows.append(await Database.fetchval(
                    "INSERT INTO maya_rp.characters (session_id, name, status) VALUES ($1, $2, $3)"
                    " RETURNING id", scratch_session, name, status))

            guard._cache, guard._cache_session = {}, None
            issues = await guard.check(
                "Review Corpse says hello. Review Executed shouts back.", scratch_session)
            kinds = {(i["type"], i["detail"].split(" is dead")[0]) for i in issues}
            assert ("dead_char_active", "Review Corpse") in kinds, issues
            assert ("dead_char_active", "Review Executed") in kinds, issues
        finally:
            for row_id in made_rows:
                await Database.execute("DELETE FROM maya_rp.characters WHERE id=$1", row_id)
            left = await Database.fetchval(
                "SELECT count(*) FROM maya_rp.characters WHERE session_id=$1", scratch_session)
            if made_session:
                await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", scratch_session)
            guard._cache, guard._cache_session = {}, None
            await Database.close()
            print(f"cleanup: scratch {scratch_session} characters left = {left}")
            assert left == 0

    async def test_a_low_bond_character_called_lover_is_reported(self, scratch_session):
        await Database.init()
        made_session = False
        row_id = None
        try:
            made_session = await Database.fetchval(
                "SELECT 1 FROM maya_rp.sessions WHERE id=$1", scratch_session) is None
            if made_session:
                await Database.execute(
                    "INSERT INTO maya_rp.sessions (id, name) VALUES ($1, $2)",
                    scratch_session, f"scratch-guard-{scratch_session}")
            row_id = await Database.fetchval(
                "INSERT INTO maya_rp.characters (session_id, name, status, bond)"
                " VALUES ($1, 'Review Stranger', 'active', 0) RETURNING id", scratch_session)

            guard._cache, guard._cache_session = {}, None
            issues = await guard.check("Review Stranger, my love, come here.", scratch_session)
            assert [i["type"] for i in issues] == ["wrong_bond"], issues
            facts = await guard.get_quick_facts("Review Stranger", scratch_session)
            assert facts == {"name": "Review Stranger", "status": "active", "bond": 0,
                             "weapon": "?"}, facts
        finally:
            if row_id is not None:
                await Database.execute("DELETE FROM maya_rp.characters WHERE id=$1", row_id)
            if made_session:
                await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", scratch_session)
            guard._cache, guard._cache_session = {}, None
            await Database.close()


class TestTheCacheIsScopedToItsSession:
    async def test_the_cache_holds_the_named_session_only(self):
        """Read-only: the `session_id` in the query is what keeps two campaigns apart."""
        await Database.init()
        try:
            guard._cache, guard._cache_session = {}, None
            for session_id in (3, 5):
                expected = await Database.fetchval(
                    "SELECT count(*) FROM maya_rp.characters WHERE session_id=$1", session_id)
                await guard._ensure(session_id)
                assert len(guard._cache) == expected, (
                    f"session {session_id}: cache holds {len(guard._cache)} of {expected}")
        finally:
            guard._cache, guard._cache_session = {}, None
            await Database.close()

    async def test_quick_facts_answers_for_a_known_name_and_refuses_an_unknown_one(self):
        await Database.init()
        try:
            guard._cache, guard._cache_session = {}, None
            name = await Database.fetchval(
                "SELECT name FROM maya_rp.characters WHERE session_id=3 ORDER BY id LIMIT 1")
            facts = await guard.get_quick_facts(name, 3)
            assert facts is not None and facts["name"] == name, facts
            assert await guard.get_quick_facts("no such character, review fixture", 3) is None
        finally:
            guard._cache, guard._cache_session = {}, None
            await Database.close()
