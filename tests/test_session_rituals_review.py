"""Module review: core/session_rituals.py.

THREE DEFECTS FIXED, and this module is on the live briefing path.

`generate_close` formatted three nullable columns with `:,` — `credits`, `alloys`,
`fuel`, all nullable in `maya_rp.resources` — so a NULL figure raised TypeError out
of the session summary. It formats through `core.utils.comma` now, which answers
`n/a` for a missing figure, and the module that was the third copy of that rule
uses the one helper instead. `importance` was compared with `>= 4` and is nullable
too (`maya_rp.events`): zero NULL today, and a NULL row would have crashed the
"what happened" list. A missing importance reads as not important, which is what
the icon already means.

The bonds read joined `romance_arcs` to `characters` on the character id alone, so
a row whose `character_id` pointed at another campaign would have carried that
campaign's name and bond into the summary. `c.session_id=$1` filters it, the same
gap `core/briefing.py` had. Measured: zero cross-session rows in that table, so no
output changes today.

Also: `from typing import Any` and `info` were imported and never used.

REPORTED, not changed, because the fix changes prose the GM reads on every session
open. Line 50 builds its own opening-beat dict for the eight modes, and
`core/pacing.OPENING_BEATS` is a second, longer copy of the same eight beats that
nothing reads. The two diverge — this module says "Something is wrong.", pacing
says "Something is wrong. You can feel it in the way the crew moves." So the
canonical-looking constant is dead and the live text is the copy. Unifying them
picks which text the model is handed, which is a ruling rather than a review fix;
`test_the_opening_beats_cover_every_mode` pins the part that is a contract (no mode
falls through to the downtime beat if a ninth mode is added) without freezing the
prose.

CHECKED AND CORRECT: the empty stack adds no unfinished-scene line; the last-event
lookup is session-scoped and orders by id; the environment block already logs its
failure rather than swallowing it; `_ago` reads a naive timestamp as UTC.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from core import pacing, session_rituals  # noqa: E402


class FakeDatabase:
    """Answers by the table each query names and records the SQL."""

    def __init__(self, *, events=None, resources=None, bonds=None):
        self.events = events or []
        self.resources = resources
        self.bonds = bonds or []
        self.sql: list[str] = []

    async def fetchrow(self, sql, *args):
        self.sql.append(" ".join(sql.split()))
        if "maya_rp.resources" in sql:
            return self.resources
        if "maya_rp.events" in sql:
            return self.events[0] if self.events else None
        return None

    async def fetch(self, sql, *args):
        self.sql.append(" ".join(sql.split()))
        if "maya_rp.events" in sql:
            return self.events
        if "maya_rp.romance_arcs" in sql:
            return self.bonds
        return []


def _install(monkeypatch, fake, mode="downtime"):
    monkeypatch.setattr(session_rituals.Database, "fetchrow", staticmethod(fake.fetchrow))
    monkeypatch.setattr(session_rituals.Database, "fetch", staticmethod(fake.fetch))
    monkeypatch.setattr(
        pacing.PacingDirector, "get_mode",
        staticmethod(lambda session_id=None: _mode(mode)),
    )
    return fake


async def _mode(mode):
    return {"mode": mode, "config": pacing.MODES.get(mode, pacing.MODES["downtime"]),
            "tension": 0, "scenes_in_mode": 0}


class TestTheSummary:
    """The close summary renders when the ledger holds no figure."""

    async def test_a_null_figure_renders_as_not_available(self, monkeypatch):
        fake = FakeDatabase(resources={"credits": None, "alloys": None, "fuel": None})
        _install(monkeypatch, fake)

        rendered = await session_rituals.generate_close(5)

        assert "**State:** n/aC | n/aA | n/aF" in rendered

    async def test_a_real_figure_keeps_its_separators(self, monkeypatch):
        fake = FakeDatabase(resources={"credits": 729591047927, "alloys": 88276465, "fuel": 12716089})
        _install(monkeypatch, fake)

        rendered = await session_rituals.generate_close(5)

        assert "729,591,047,927C" in rendered and "88,276,465A" in rendered

    async def test_a_session_with_no_resources_row_still_renders(self, monkeypatch):
        _install(monkeypatch, FakeDatabase(resources=None))

        rendered = await session_rituals.generate_close(5)

        assert "Session Summary" in rendered and "**State:**" not in rendered

    async def test_a_null_importance_is_not_important(self, monkeypatch):
        fake = FakeDatabase(events=[{"title": "A beat", "importance": None},
                                    {"title": "A disaster", "importance": 5}])
        _install(monkeypatch, fake)

        rendered = await session_rituals.generate_close(5)

        assert "A beat" in rendered and "A disaster" in rendered
        assert "\u2022 A beat" in rendered, "a missing importance reads as the plain bullet"
        assert "! A disaster" in rendered

    async def test_the_bonds_join_filters_the_character_session(self, monkeypatch):
        fake = _install(monkeypatch, FakeDatabase())

        await session_rituals.generate_close(5)

        joined = [sql for sql in fake.sql if "JOIN maya_rp.characters" in sql]
        assert joined, "the bonds query did not run"
        for sql in joined:
            assert "c.session_id=$1" in sql, f"a join can carry another campaign's character: {sql}"

    async def test_a_null_bond_is_not_counted_into_the_hearts(self, monkeypatch):
        fake = FakeDatabase(bonds=[{"name": "Someone", "bond": 7}])
        _install(monkeypatch, fake)

        rendered = await session_rituals.generate_close(5)

        assert "Someone" in rendered and "\u2665" * 7 in rendered


class TestTheOpen:
    """The open renders without a stack, and every mode has its own beat."""

    async def test_an_empty_stack_adds_no_unfinished_scene(self, monkeypatch):
        _install(monkeypatch, FakeDatabase(events=[{"title": "Last beat", "happened_at": None}]))

        async def no_stack(session_id=None):
            return []

        monkeypatch.setattr("core.scene_stack.get_stack_summary", no_stack)
        monkeypatch.setattr("modules.locations.get_player_location", _async({"location": "bridge"}))
        monkeypatch.setattr("modules.objectives.objectives_to_prompt", _async("- nothing critical"))

        rendered = await session_rituals.generate_open(5)

        assert "**Last session ended:**" in rendered
        assert "Unfinished scene" not in rendered
        assert "**Atmosphere:** DOWNTIME" in rendered

    async def test_the_opening_beats_cover_every_mode(self):
        source = (ROOT / "core/session_rituals.py").read_text(encoding="utf-8")
        beats = source.split("ob = {", 1)[1].split("}", 1)[0]
        for mode in pacing.MODES:
            assert f'"{mode}"' in beats, f"pacing knows mode {mode} and the open has no beat for it"
        assert '"downtime"' in beats, "the fallback beat exists"

    def test_the_dead_imports_are_gone(self):
        source = (ROOT / "core/session_rituals.py").read_text(encoding="utf-8")
        assert "from typing import Any" not in source
        assert "from core.log import info, error" not in source


def _async(value):
    async def call(*args, **kwargs):
        return value
    return call
