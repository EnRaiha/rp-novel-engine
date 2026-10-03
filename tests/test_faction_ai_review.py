"""faction_ai review: what reading `modules/faction_ai.py` in full turned up.

One defect: the tick reported its caught exception at INFO. The docstring, the doctrine table and the
decision log all held up under the checklist.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from core.db import Database  # noqa: E402
from modules import faction_ai  # noqa: E402

SESSION = 5


class TestTheFactionTick:
    async def test_the_tick_answers_with_its_counts(self):
        await Database.init()
        try:
            out = await faction_ai.run_tick(SESSION)
            assert set(out) == {"factions", "decisions"}, out
            assert out["decisions"] == 0, out  # session 5 has no pirate factions
            assert out["factions"] == 5, out
        finally:
            await Database.close()

    async def test_a_failing_tick_is_logged_as_a_fault(self, monkeypatch):
        seen = []

        async def boom(*args, **kwargs):
            raise RuntimeError("faction query died")

        monkeypatch.setattr(faction_ai.Database, "fetch", boom)
        monkeypatch.setattr(faction_ai, "error", lambda module, message: seen.append(message))
        out = await faction_ai.run_tick(SESSION)
        assert "faction query died" in out["error"], out
        assert seen, "a failing tick returned a dict and said nothing at fault level"


class TestTheDoctrine:
    def test_an_unknown_group_falls_back_to_the_wild_doctrine(self):
        assert faction_ai._doctrine("nobody") == faction_ai._doctrine("free")

    def test_each_group_has_its_own_shape(self):
        free = faction_ai._doctrine("free")
        sponsor = faction_ai._doctrine("sponsor")
        hired = faction_ai._doctrine("hired")
        assert free[4] > hired[4] > sponsor[4], (free, sponsor, hired)
        assert hired[2] > sponsor[2] > free[2], (free, sponsor, hired)
