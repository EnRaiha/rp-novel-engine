"""Module review: core/state.py.

THREE DEFECTS FIXED, one of them writing to the frozen campaign.

The default session was the literal `3` on all three methods. Session 3 is the
frozen reference campaign — the one no reviewer may write to — so any caller that
named no session gathered a snapshot of the frozen arc, and `save_checkpoint()`
with no argument inserted a `story_checkpoints` row for it. The three live callers
all pass an id today, which is why nothing has surfaced; the default is a trap for
the next caller. `_resolve_session` goes through `core.session.resolve_session`,
which honours an explicit id, then `RP_SESSION`, then the active arc, then
maintenance, and refuses to guess. A maintenance resolve that names no session
raises with the wording `core/consequences.py` uses.

`save_checkpoint` picked a slot with `for n in (1, 2, 3): if n not in used`, and
`num` was initialised to 1, so once all three slots were taken the loop assigned
nothing and every later save claimed slot 1 again. Measured on the live table
before the fix: session 3 holds 395 rows numbered 1 against one each numbered 2
and 3; session 5 holds three numbered 1 against one each of 2 and 3. The three
slots now rotate: a free slot if there is one, otherwise the slot whose last use
is oldest. `last_used` comes from one grouped query instead of selecting every
row of the campaign.

`export_md` formatted four nullable columns with `:,` and `float(...)`, so a NULL
credit, alloy, fuel, population or tax rate raised TypeError out of a snapshot
that is supposed to be readable when the ledger is incomplete. A missing figure
renders as `n/a` and the rest of the snapshot still renders.

Also: the `except Exception: pass` around the ML importance gate swallowed the
reason the model was unavailable. It warns now, and the recency list stays the
answer, which is what the comment always claimed. Two unused imports (`json`,
`asyncio`) and two unused typing names are gone.

REPORTED, not changed. `story_checkpoints` has no unique constraint on
(session_id, checkpoint_number) — the primary key is on `id` alone, and the only
other constraint is a 1..3 check. So `ON CONFLICT DO NOTHING` can never fire and
the table grows by one row per save (402 rows today, 395 of them session 3 slot 1).
Making the slots real is a migration; the rotation above at least makes the
recorded number mean something. The `active` and `metadata` columns are read and
written by nothing in the repo: only this module touches the table at all.
"""
from __future__ import annotations

import datetime as dt
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from core import state as state_mod  # noqa: E402
from core.config import Config  # noqa: E402

D1 = dt.datetime(2026, 10, 1, 10, 0, 0)
D2 = dt.datetime(2026, 10, 2, 10, 0, 0)
D3 = dt.datetime(2026, 10, 3, 10, 0, 0)


class FakeDatabase:
    """Answers by the SQL it is handed. Records every session id it was given."""

    def __init__(self, *, slots=None, story=None, resources=None, territory=None):
        self.slots = slots or []
        self.story = story or []
        self.resources = resources
        self.territory = territory or []
        self.session_ids: list = []
        self.executed: list[tuple] = []
        self.fetched_sql: list[str] = []

    async def fetchrow(self, sql, *args):
        self.session_ids.append(args[0] if args else None)
        if "FROM resources" in sql:
            return self.resources
        if "FROM sessions" in sql:
            return {"id": args[0] if args else None, "game_day": 5}
        return None

    async def fetch(self, sql, *args):
        self.session_ids.append(args[0] if args else None)
        self.fetched_sql.append(sql)
        if "story_checkpoints" in sql:
            return self.slots
        if "FROM story_log" in sql:
            return self.story
        if "FROM territory" in sql:
            return self.territory
        return []

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        return "INSERT 0 1"


def _install(monkeypatch, fake, resolved=5):
    monkeypatch.setattr(state_mod.Database, "fetchrow", staticmethod(fake.fetchrow))
    monkeypatch.setattr(state_mod.Database, "fetch", staticmethod(fake.fetch))
    monkeypatch.setattr(state_mod.Database, "execute", staticmethod(fake.execute))
    monkeypatch.setattr("core.session.resolve_session", lambda explicit=None: resolved if explicit is None else explicit)
    return fake


class TestTheSession:
    """No session named resolves through core.session, and never to 3."""

    async def test_gather_names_the_resolved_session(self, monkeypatch):
        fake = _install(monkeypatch, FakeDatabase(), resolved=5)

        await state_mod.StateManager.gather()

        assert fake.session_ids, "gather read nothing"
        assert set(fake.session_ids) == {5}, f"a read used another campaign: {fake.session_ids}"
        assert 3 not in fake.session_ids

    async def test_a_named_session_wins_over_the_arc(self, monkeypatch):
        fake = _install(monkeypatch, FakeDatabase(), resolved=5)

        await state_mod.StateManager.gather(3)

        assert set(fake.session_ids) == {3}, "an explicit id is not overridden by the arc"

    async def test_a_maintenance_resolve_that_names_nothing_refuses(self, monkeypatch):
        _install(monkeypatch, FakeDatabase(), resolved=None)

        with pytest.raises(ValueError) as refused:
            await state_mod.StateManager.gather()

        assert "maintenance" in str(refused.value)

    async def test_save_checkpoint_writes_to_the_resolved_session(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Config, "BACKUP_DIR", str(tmp_path))
        fake = _install(monkeypatch, FakeDatabase(), resolved=5)

        path = await state_mod.StateManager.save_checkpoint(label="arc")

        assert fake.session_ids and set(fake.session_ids) == {5}
        assert fake.executed, "no checkpoint row was written"
        _, args = fake.executed[0]
        assert args[0] == 5, "the checkpoint row belongs to the resolved session"
        assert args[2] == "arc"
        assert pathlib.Path(path).parent == tmp_path
        assert pathlib.Path(path).read_text(encoding="utf-8")


class TestTheSlots:
    """Three slots: a free one if there is one, otherwise the oldest."""

    async def test_a_free_slot_is_taken_when_one_exists(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Config, "BACKUP_DIR", str(tmp_path))
        fake = _install(monkeypatch, FakeDatabase(slots=[{"checkpoint_number": 1, "last_used": D3}]))

        path = await state_mod.StateManager.save_checkpoint(5)

        assert pathlib.Path(path).name.startswith("checkpoint_2_")
        assert fake.executed[0][1][1] == 2

    async def test_all_three_taken_reuses_the_oldest_slot(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Config, "BACKUP_DIR", str(tmp_path))
        slots = [
            {"checkpoint_number": 1, "last_used": D3},
            {"checkpoint_number": 2, "last_used": D1},
            {"checkpoint_number": 3, "last_used": D2},
        ]
        fake = _install(monkeypatch, FakeDatabase(slots=slots))

        path = await state_mod.StateManager.save_checkpoint(5)

        assert pathlib.Path(path).name.startswith("checkpoint_2_"), "the least recently used slot is reused"
        assert fake.executed[0][1][1] == 2

    async def test_a_slot_with_no_timestamp_is_the_oldest_not_a_crash(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Config, "BACKUP_DIR", str(tmp_path))
        slots = [
            {"checkpoint_number": 1, "last_used": D3},
            {"checkpoint_number": 2, "last_used": None},
            {"checkpoint_number": 3, "last_used": D2},
        ]
        _install(monkeypatch, FakeDatabase(slots=slots))

        path = await state_mod.StateManager.save_checkpoint(5)

        assert pathlib.Path(path).name.startswith("checkpoint_2_")

    async def test_the_slot_query_reads_one_grouped_row_per_slot(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Config, "BACKUP_DIR", str(tmp_path))
        fake = _install(monkeypatch, FakeDatabase(slots=[{"checkpoint_number": 1, "last_used": D1}]))

        await state_mod.StateManager.save_checkpoint(5)

        assert any("GROUP BY checkpoint_number" in sql for sql in fake.fetched_sql), \
            "the slot choice reads grouped rows, not every row of the campaign"


class TestTheSnapshot:
    """The snapshot renders when a figure is missing, and says so."""

    async def test_a_missing_resource_row_renders_no_section(self, monkeypatch):
        _install(monkeypatch, FakeDatabase())

        rendered = await state_mod.StateManager.export_md(5)

        assert "Session 5" in rendered
        assert "## Resources" not in rendered

    async def test_a_null_figure_renders_as_not_available(self, monkeypatch):
        fake = FakeDatabase(resources={"credits": None, "alloys": None, "fuel": None})
        _install(monkeypatch, fake)

        rendered = await state_mod.StateManager.export_md(5)

        assert "## Resources" in rendered
        assert "Credits: n/a" in rendered and "Alloys: n/a" in rendered

    async def test_a_real_figure_keeps_its_thousands_separators(self, monkeypatch):
        fake = FakeDatabase(resources={"credits": 729591047927, "alloys": 88276465, "fuel": 12716089})
        _install(monkeypatch, fake)

        rendered = await state_mod.StateManager.export_md(5)

        assert "Credits: 729,591,047,927" in rendered

    async def test_a_null_tax_rate_does_not_crash_the_territory_line(self, monkeypatch):
        fake = FakeDatabase(territory=[{"system_name": "Kedah", "population": None,
                                        "tax_rate": None, "development_level": 1, "crisis_level": 0}])
        _install(monkeypatch, fake)

        rendered = await state_mod.StateManager.export_md(5)

        assert "Kedah" in rendered and "Pop n/a" in rendered and "Tax n/a" in rendered

    async def test_a_story_row_without_a_timestamp_still_renders(self, monkeypatch):
        fake = FakeDatabase(story=[{"happened_at": None, "category": "x", "title": "A beat",
                                    "content": "", "importance": 1}])
        _install(monkeypatch, fake)

        rendered = await state_mod.StateManager.export_md(5)

        assert "A beat" in rendered


class TestTheMlGate:
    """A failed importance model is logged, and the recency list stays."""

    async def test_a_model_failure_is_reported(self, monkeypatch):
        warnings: list[str] = []
        monkeypatch.setattr(state_mod, "warn", lambda module, message: warnings.append(message))
        fake = FakeDatabase(story=[{"happened_at": D1, "category": "x", "title": "beat",
                                    "content": "", "importance": 1, "event_type": "x"}])
        _install(monkeypatch, fake)

        def boom(event):
            raise RuntimeError("model not trained")

        import core.decision_models as dm
        monkeypatch.setattr(dm, "predict_event_importance", boom)

        gathered = await state_mod.StateManager.gather(5)

        assert warnings and "model not trained" in warnings[0]
        assert [dict(r)["title"] for r in gathered["story"]] == ["beat"], "the recency list stays authoritative"


class TestTheDeadImports:
    """The module no longer carries imports it never uses."""

    def test_json_and_asyncio_are_not_imported(self):
        source = (ROOT / "core/state.py").read_text(encoding="utf-8")
        assert "import json" not in source
        assert "import asyncio" not in source
