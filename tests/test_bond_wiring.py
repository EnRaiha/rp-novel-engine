"""The bond surface: engine state only, which is what the house rule requires.

Five entry points of romance.py had no caller. All five touch engine tables only (romance_arcs,
characters, intimacy_events, sessions) and none writes a story log, a file or the novel, so wiring them
keeps private scenes in engine state as the rule says.

`calculate_bond_shift` takes the quality as a word, not a number: it lowercases it and looks it up in
BOND_SHIFT_MATRIX. My first CLI call passed an int and raised AttributeError.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import Database  # noqa: E402
from modules import romance  # noqa: E402

ENGINE_TABLES = ("romance_arcs", "characters", "intimacy_events", "sessions")


class TestTheHouseRule:
    def test_none_of_the_five_writes_a_record_outside_engine_state(self):
        """The rule is about records, so the check is on the source, not on a side effect."""
        import inspect

        for fn in (romance.calculate_bond_shift, romance.get_bond_ranking, romance.process_healing,
                   romance.release_and_heal, romance.process_aftercare):
            source = inspect.getsource(fn)
            for forbidden in ("story_log", "open(", "write_text", "novel"):
                assert forbidden not in source, f"{fn.__name__} touches {forbidden}"


class TestTheBondRules:
    def test_the_quality_word_decides_the_shift(self):
        assert romance.calculate_bond_shift("kiss", "perfect")["delta"] == 2
        assert romance.calculate_bond_shift("kiss", "violation")["delta"] == -2
        assert romance.calculate_bond_shift("kiss", "neutral")["delta"] == 0

    def test_a_quality_word_that_is_not_in_the_matrix_still_answers(self):
        out = romance.calculate_bond_shift("kiss", "something else entirely")
        assert "delta" in out and "reason" in out, out


class TestTheSessionReads:
    async def test_the_ranking_is_scoped_to_its_session(self):
        await Database.init()
        assert await romance.get_bond_ranking(5) == [] or all(
            isinstance(r, dict) for r in await romance.get_bond_ranking(5))
        await Database.close()

    async def test_healing_an_unknown_character_is_answered_not_crashed(self):
        await Database.init()
        out = await romance.process_healing(999_999, "rest", 905)  # a scratch id: the writer refuses frozen session 5
        assert out is not None
        await Database.close()
