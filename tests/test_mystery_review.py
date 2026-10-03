"""Mystery review: what reading `modules/mystery.py` in full turned up.

Three defects. Nothing here writes to session 3, and every row this file creates in session 5 is
removed in a `finally`.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from core.db import Database  # noqa: E402
from modules import mystery  # noqa: E402

SESSION = 5


async def _case(session_id=SESSION, template="generic", title="review case"):
    return await Database.fetchval(
        "INSERT INTO maya_rp.investigations (session_id, title, template_name, difficulty, status) "
        "VALUES ($1, $2, $3, 5, 'active') RETURNING id",
        session_id, title, template)


async def _drop(inv_id):
    await Database.execute("DELETE FROM maya_rp.clues WHERE investigation_id = $1", inv_id)
    await Database.execute("DELETE FROM maya_rp.investigation_log WHERE investigation_id = $1", inv_id)
    await Database.execute("DELETE FROM maya_rp.investigations WHERE id = $1", inv_id)


class TestTheRedHerring:
    async def test_a_red_herring_cannot_be_filed_against_another_campaign(self):
        """`add_clue` grew this check; its sibling kept inserting for any investigation id."""
        await Database.init()
        case = await _case(session_id=3, title="review case s3")
        try:
            out = await mystery.generate_red_herring(SESSION, case)
            assert "belongs to session 3" in out.get("error", ""), out
            count = await Database.fetchval(
                "SELECT COUNT(*) FROM maya_rp.clues WHERE investigation_id = $1", case)
            assert count == 0, "a red herring landed in another campaign's case"
        finally:
            await _drop(case)
            await Database.close()

    async def test_a_red_herring_for_a_case_that_does_not_exist_is_refused(self):
        await Database.init()
        try:
            out = await mystery.generate_red_herring(SESSION, 999999999)
            assert "does not exist" in out.get("error", ""), out
        finally:
            await Database.close()

    async def test_a_red_herring_in_its_own_case_is_written_and_not_counted(self):
        await Database.init()
        case = await _case()
        try:
            out = await mystery.generate_red_herring(SESSION, case)
            assert out["clue_id"], out
            found = await Database.fetchval(
                "SELECT clues_found FROM maya_rp.investigations WHERE id = $1", case)
            assert found == 0, "a red herring counted as progress"
            source = await Database.fetchval(
                "SELECT source FROM maya_rp.clues WHERE id = $1", out["clue_id"])
            assert source == mystery.RED_HERRING_SOURCE
        finally:
            await _drop(case)
            await Database.close()


class TestTheClueLinks:
    async def test_a_link_to_a_clue_that_does_not_exist_is_refused(self):
        await Database.init()
        case = await _case()
        try:
            out = await mystery.add_clue(SESSION, case, "a clue", connects_to=999999999)
            assert "does not exist" in out.get("error", ""), out
            count = await Database.fetchval(
                "SELECT COUNT(*) FROM maya_rp.clues WHERE investigation_id = $1", case)
            assert count == 0, "the clue was written before its link was checked"
        finally:
            await _drop(case)
            await Database.close()

    async def test_a_link_across_cases_is_refused(self):
        await Database.init()
        first = await _case(title="review case one")
        second = await _case(title="review case two")
        try:
            clue = await mystery.add_clue(SESSION, first, "clue in the first case")
            out = await mystery.add_clue(SESSION, second, "clue in the second",
                                         connects_to=clue["clue_id"])
            assert "belongs to investigation" in out.get("error", ""), out
        finally:
            await _drop(first)
            await _drop(second)
            await Database.close()

    async def test_a_link_inside_one_case_is_written(self):
        await Database.init()
        case = await _case()
        try:
            first = await mystery.add_clue(SESSION, case, "first")
            second = await mystery.add_clue(SESSION, case, "second",
                                            connects_to=first["clue_id"])
            linked = await Database.fetchval(
                "SELECT connects_to_clue FROM maya_rp.clues WHERE id = $1", second["clue_id"])
            assert linked == first["clue_id"], linked
        finally:
            await _drop(case)
            await Database.close()


class TestTheDeduction:
    async def test_the_clue_count_excludes_red_herrings(self):
        await Database.init()
        case = await _case()
        try:
            for n in range(3):
                await mystery.add_clue(SESSION, case, f"clue {n}")
            await mystery.generate_red_herring(SESSION, case)
            out = await mystery.deduce(SESSION, case)
            assert out["clues_found"] == 3, out
            assert out["success"] is True, out
            assert out["threshold"] == mystery.DEFAULT_THRESHOLD, out
        finally:
            await _drop(case)
            await Database.close()

    async def test_a_solved_case_records_its_solve(self):
        await Database.init()
        case = await _case()
        try:
            for n in range(4):
                await mystery.add_clue(SESSION, case, f"clue {n}")
            await mystery.deduce(SESSION, case, "the butler")
            row = await Database.fetchrow(
                "SELECT status, solved_at, summary, deductions_made FROM maya_rp.investigations"
                " WHERE id = $1", case)
            assert row["status"] == "solved", dict(row)
            assert row["solved_at"] is not None
            assert row["summary"] == "the butler"
            assert row["deductions_made"] == 1
        finally:
            await _drop(case)
            await Database.close()

    async def test_a_case_from_another_campaign_is_refused(self):
        await Database.init()
        case = await _case(session_id=3, title="review case s3")
        try:
            out = await mystery.deduce(SESSION, case)
            assert "not found in session 5" in out.get("error", ""), out
        finally:
            await _drop(case)
            await Database.close()


class TestTheTick:
    async def test_a_failing_tick_is_logged_as_a_fault(self, monkeypatch):
        seen = []

        async def boom(*args, **kwargs):
            raise RuntimeError("investigation query died")

        monkeypatch.setattr(mystery.Database, "fetch", boom)
        monkeypatch.setattr(mystery, "error", lambda module, message: seen.append(message))
        out = await mystery.run_tick(SESSION)
        assert "investigation query died" in out["error"], out
        assert seen, "a failing tick returned a dict and said nothing at fault level"

    async def test_an_empty_tick_answers_with_its_counts(self):
        await Database.init()
        try:
            out = await mystery.run_tick(SESSION)
            assert out == {"active": 0, "decayed": 0}, out
        finally:
            await Database.close()
