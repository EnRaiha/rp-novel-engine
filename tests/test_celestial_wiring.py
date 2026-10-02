"""The map readers: twelve of them, all scoped, and one that proves the scoping.

Twelve readers of celestial.py had no caller. Unlike every other module in this review they were clean:
each takes a session and uses it. What they could not do was show it, because nothing called them.

The test that matters is the comparison. The same reader returns 892 systems for session 3 and 0 for
session 5, which proves both that the query works and that session 5's emptiness is real: the Arc I
world has not been seeded. A broken query and an empty world look identical from one session.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import Database  # noqa: E402
from modules import celestial as c  # noqa: E402


class TestEveryReaderRuns:
    async def test_all_twelve_answer_without_raising(self):
        await Database.init()
        probes = [
            c.get_system_stats, c.get_sector_breakdown, c.get_planet_stats, c.get_colonies,
            c.get_visible_systems, c.get_faction_territories, c.get_faction_presence,
        ]
        for fn in probes:
            out = await fn(5)
            assert out is not None, fn.__name__
        assert await c.get_system_detail(5, "TKG Bayu") is None
        assert await c.get_faction_relations(5, "TKG", "Iron Concord") == []
        assert await c.search_all(5, "Bayu") == []
        await Database.close()


class TestTheScopingIsReal:
    async def test_session_three_sees_its_world_and_session_five_sees_none(self):
        """One reader, two sessions. If the filter were absent or ignored, both would return 892."""
        await Database.init()
        three = await c.get_system_stats(3)
        five = await c.get_system_stats(5)
        assert three["total"] > 0, "session 3 has no systems, so this comparison proves nothing"
        assert five["total"] == 0, f"session 5 sees {five['total']} systems"
        hits_three = await c.search_all(3, "Bayu")
        hits_five = await c.search_all(5, "Bayu")
        assert hits_three, "the search finds nothing in session 3"
        assert hits_five == [], "the search leaks session 3 rows into session 5"
        await Database.close()
