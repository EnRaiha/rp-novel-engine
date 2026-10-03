#!/usr/bin/env python3
"""Review of `core/player_profile.py`.

Three defects, and one measurement that reframes the module.

**`maya_rp.player_action_log` holds 0 rows**, and `record` has no caller anywhere: the only callers
of this module are `get_profile`, in `core/master_briefing.py:66`, `modules/themes.py:36` and
`scripts/cli.py:1854`. So every player-style report the engine has ever produced is built from an
empty table and answers `balanced`. That is the caller-less class again, and wiring `record` into a
play path changes what the engine reports, so it is reported and pinned rather than wired here.

1. `record` classified with `kw in lower`, a **substring** test: "skill" counted as cruelty ("kill"),
   "ideal" as diplomacy ("deal"), "household" as romance ("hold"), "breakfast" as cruelty ("break")
   and "research" as exploration **and** building ("search" + "research"). `core/guard.py` already
   learned this one, in its own comment: a substring test flagged "gun" inside "begun". The keywords
   are matched on word boundaries now.
2. `get_profile` did `total = sum(...) or 1` and then reported that `total`, so a session with no
   recorded actions claimed `"total": 1`. The fallback is the divisor, and with no rows nothing
   divides; the report carries the real sum now.
3. The preferred companion is read with `ORDER BY ra.nights_shared DESC`, and Postgres sorts NULLs
   first in DESC, so a row with no count outranks every companion with one. Measured: 0 of the 49
   live rows hold NULL, so it is latent; NULLS LAST keeps it that way.

Reported, not changed: `modules/ideology.py:62` recomputes the same category distribution from the
same table, which is the rule in this module written a second time.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from core.db import Database  # noqa: E402
from core import player_profile  # noqa: E402


async def _ids(session_id: int) -> set[int]:
    rows = await Database.fetch(
        "SELECT id FROM maya_rp.player_action_log WHERE session_id=$1", session_id)
    return {int(r["id"]) for r in rows}


@pytest.fixture(autouse=True)
async def _scratch_session_row(scratch_session):
    """`player_action_log.session_id` is a foreign key into `sessions`."""
    await Database.init()
    before = await _ids(scratch_session)
    made = await Database.fetchval(
        "SELECT 1 FROM maya_rp.sessions WHERE id=$1", scratch_session) is None
    if made:
        await Database.execute(
            "INSERT INTO maya_rp.sessions (id, name) VALUES ($1, $2)",
            scratch_session, f"scratch-profile-{scratch_session}")
    try:
        yield
    finally:
        created = (await _ids(scratch_session)) - before
        if created:
            await Database.execute(
                "DELETE FROM maya_rp.player_action_log WHERE id = ANY($1::int[])",
                sorted(created))
        left = await Database.fetchval(
            "SELECT count(*) FROM maya_rp.player_action_log WHERE session_id=$1", scratch_session)
        print(f"cleanup: scratch {scratch_session} action rows left = {left}")
        if made:
            await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", scratch_session)
        assert left == 0, "the scratch session kept a row this test did not create"


class TestTheClassificationCountsWordsNotLetters:
    async def test_unrelated_words_score_nothing(self, scratch_session):
        """skill/kill, ideal/deal, household/hold, breakfast/break: none of them is an action."""
        await Database.init()
        try:
            await player_profile.record(
                "My skill at breakfast was ideal for the household.", scratch_session)
            assert await _ids(scratch_session) == set(), (
                "a sentence with no action in it was classified as an action")
        finally:
            await Database.close()

    async def test_a_longer_word_does_not_match_its_shorter_keyword(self, scratch_session):
        """`research` is a `building` keyword and must not also score `exploration` through `search`."""
        await Database.init()
        try:
            await player_profile.record("Research the drive.", scratch_session)
            rows = await Database.fetch(
                "SELECT action_category, count FROM maya_rp.player_action_log WHERE session_id=$1",
                scratch_session)
            scored = {r["action_category"]: r["count"] for r in rows}
            assert scored == {"building": 1}, scored
        finally:
            await Database.close()

    async def test_real_actions_still_score(self, scratch_session):
        await Database.init()
        try:
            await player_profile.record(
                "Kill the scout, then build a ship and research a drive.", scratch_session)
            rows = await Database.fetch(
                "SELECT action_category, count FROM maya_rp.player_action_log"
                " WHERE session_id=$1 ORDER BY action_category", scratch_session)
            scored = {r["action_category"]: r["count"] for r in rows}
            assert scored.get("combat") == 1, scored     # kill is a combat keyword
            assert scored.get("building") == 2, scored   # build, research
            assert scored.get("cruelty") is None, scored
        finally:
            await Database.close()

    async def test_a_word_that_is_two_categories_is_counted_in_both(self, scratch_session):
        """`search` sits in exploration and its longer form in building; the boundary keeps them apart."""
        await Database.init()
        try:
            await player_profile.record("Scan the ruin and search the wreck.", scratch_session)
            rows = await Database.fetch(
                "SELECT action_category, count FROM maya_rp.player_action_log WHERE session_id=$1",
                scratch_session)
            scored = {r["action_category"]: r["count"] for r in rows}
            assert scored == {"exploration": 2}, scored
        finally:
            await Database.close()


class TestTheProfileItReports:
    async def test_a_session_with_nothing_recorded_reports_zero(self, scratch_session):
        """`or 1` was the divisor and the reported total, so an empty log claimed one action."""
        await Database.init()
        try:
            assert await _ids(scratch_session) == set()
            prof = await player_profile.get_profile(scratch_session)
            assert prof["total"] == 0, prof
            assert prof["distribution"] == {}, prof
            assert prof["style"] == "balanced", prof
            assert prof["preferred_companion"] is None, prof
            assert prof["advice"] == player_profile.STYLE_ADVICE["balanced"], prof
        finally:
            await Database.close()

    async def test_the_style_follows_the_distribution(self, scratch_session):
        await Database.init()
        try:
            for category, count in (("combat", 6), ("diplomacy", 4)):
                await Database.execute(
                    "INSERT INTO maya_rp.player_action_log (session_id, action_category, count,"
                    " raw_input) VALUES ($1, $2, $3, 'review fixture')",
                    scratch_session, category, count)
            prof = await player_profile.get_profile(scratch_session)
            assert prof["total"] == 10, prof
            assert prof["distribution"] == {"combat": 60, "diplomacy": 40}, prof
            assert prof["style"] == "warlord", prof
            assert prof["advice"] == player_profile.STYLE_ADVICE["warlord"], prof
        finally:
            await Database.close()


    async def test_the_preferred_companion_is_the_one_with_the_most_nights(self, scratch_session):
        """`ORDER BY nights_shared DESC` sorts NULLs first, so a blank row took the slot."""
        await Database.init()
        made_arcs: list[int] = []
        made_chars: list[int] = []
        try:
            dated = await Database.fetchval(
                "INSERT INTO maya_rp.characters (session_id, name, status) VALUES ($1, $2, 'active')"
                " RETURNING id", scratch_session, "Review Dated")
            blank = await Database.fetchval(
                "INSERT INTO maya_rp.characters (session_id, name, status) VALUES ($1, $2, 'active')"
                " RETURNING id", scratch_session, "Review Blank")
            made_chars = [int(dated), int(blank)]
            made_arcs = [
                int(await Database.fetchval(
                    "INSERT INTO maya_rp.romance_arcs (session_id, character_id, nights_shared)"
                    " VALUES ($1, $2, 5) RETURNING id", scratch_session, dated)),
                int(await Database.fetchval(
                    "INSERT INTO maya_rp.romance_arcs (session_id, character_id, nights_shared)"
                    " VALUES ($1, $2, NULL) RETURNING id", scratch_session, blank)),
            ]
            prof = await player_profile.get_profile(scratch_session)
            assert prof["preferred_companion"] == "Review Dated", prof
        finally:
            for arc_id in made_arcs:
                await Database.execute("DELETE FROM maya_rp.romance_arcs WHERE id=$1", arc_id)
            for char_id in made_chars:
                await Database.execute("DELETE FROM maya_rp.characters WHERE id=$1", char_id)
            left = await Database.fetchval(
                "SELECT count(*) FROM maya_rp.characters WHERE session_id=$1", scratch_session)
            print(f"cleanup: scratch {scratch_session} characters left = {left}")
            assert left == 0
            await Database.close()


class TestRecordHasNoCaller:
    def test_no_production_module_calls_record(self):
        """Pins why the log is empty: nothing in the engine records a player action.

        The day a play path calls it, this test fails and the pin should be replaced by tests of
        that path. Measured while reviewing: `player_action_log` holds 0 rows.
        """
        users = []
        for folder in ("modules", "core", "scripts"):
            for path in sorted((ROOT / folder).glob("*.py")):
                if path.name == "player_profile.py":
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
                if "player_profile import record" in text or "player_profile.record" in text:
                    users.append(str(path.relative_to(ROOT)))
        assert users == [], f"record now has a caller; test the path instead: {users}"
