"""Module review: core/briefing.py.

FIVE DEFECTS FIXED, one finding reported, and the module has NO CALLER.

REACHABILITY, first, because it changes how the rest reads. Nothing imports
`core.briefing`. `scripts/cli.py:1710` defines its own `cmd_briefing`, and that
one calls `core.master_briefing.generate`, which is the briefing the engine
actually uses. So this module is the earlier briefing engine, superseded and dead:
its defects cannot be reached today. They are fixed anyway, because the file is a
soundness hazard the day someone wires it, and the tests here are the only thing
that exercises it. Whether it is wired or retired is a decision for the King, so
the last test pins the caller-less status and fails the day a caller appears.

THE FIVE, all the same family: a value that is absent read as a value that is not.

- `generate_briefing` fetched the session row and indexed it without checking for
  None, so an unknown session id raised `TypeError: 'NoneType' object is not
  subscriptable`. It refuses by name now, with the wording `core/consequences.py`
  already uses for the same condition.
- `game_day = s["game_day"] or 1` read a clock at day zero as day one. The column
  is nullable, so the intent was "NULL means unset", and `or` also swallowed a
  real 0. Split into an explicit None check.
- The three resource comparisons (`r["fuel"] < 500_000` and its two siblings)
  raised TypeError on a NULL figure. `credits`, `alloys` and `fuel` are all
  nullable. A NULL figure is a figure the ledger does not hold, so the briefing
  does not claim the treasury is low on it, and the three copies of the rule are
  one table now.
- `briefing_to_prompt` sliced `c.get('description','?')[:80]`. asyncpg returns
  NULL as None, and `dict.get` defaults only on an absent key, so a hook with no
  description crashed the whole prompt render. `bond` was compared with `>=`
  before a NULL check, which crashes for the same reason. Both are None-safe now,
  and every optional field that used to render the literal text "None" renders
  the module's own `?` instead.
- Two joins (`romance_arcs` and `character_memories` onto `characters`) filtered
  the arc's session and not the character's, so a row pointing across campaigns
  would have carried another campaign's character into the briefing. Measured
  today: zero cross-session rows in either table, so this changes no output.

CHECKED AND CORRECT: every other query carries `session_id=$1` (asserted by test);
a session with no `resources` row yields no pressure alerts rather than a crash;
`character_memories.content` is NOT NULL, so the `[:60]` slice is safe; the
leave-flag file is guarded by `exists()`.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from core import briefing  # noqa: E402


class FakeDatabase:
    """Answers the ten queries by the table each one names. No writes, no pool."""

    def __init__(self, *, session=None, loc=None, resources=None, rows=None):
        self.session = session
        self.loc = loc
        self.resources = resources
        self.rows = rows or {}
        self.queries: list[str] = []

    async def init(self):
        return None

    async def close(self):
        return None

    async def fetchrow(self, sql, *args):
        self.queries.append(sql)
        if "maya_rp.sessions" in sql:
            return self.session
        if "maya_rp.player_context" in sql:
            return self.loc
        if "maya_rp.resources" in sql:
            return self.resources
        return None

    async def fetch(self, sql, *args):
        self.queries.append(sql)
        for table, value in self.rows.items():
            if f"maya_rp.{table}" in sql:
                return value
        return []


def _install(monkeypatch, fake):
    monkeypatch.setattr(briefing.Database, "init", staticmethod(fake.init))
    monkeypatch.setattr(briefing.Database, "close", staticmethod(fake.close))
    monkeypatch.setattr(briefing.Database, "fetchrow", staticmethod(fake.fetchrow))
    monkeypatch.setattr(briefing.Database, "fetch", staticmethod(fake.fetch))
    return fake


def _session(game_day, name="TKG", status="active"):
    return {"name": name, "status": status, "game_day": game_day}


class TestTheSessionRow:
    """A session that does not exist is refused; a clock at zero is day zero."""

    async def test_an_unknown_session_is_refused_by_name(self, monkeypatch):
        _install(monkeypatch, FakeDatabase(session=None))

        with pytest.raises(ValueError) as refused:
            await briefing.generate_briefing(9999)

        assert "9999" in str(refused.value)
        assert "no such row" in str(refused.value)

    async def test_a_clock_at_zero_is_day_zero(self, monkeypatch):
        _install(monkeypatch, FakeDatabase(session=_session(0)))

        generated = await briefing.generate_briefing(5)

        assert generated["session"].startswith("Day 0,")

    async def test_a_null_clock_is_day_one(self, monkeypatch):
        _install(monkeypatch, FakeDatabase(session=_session(None)))

        generated = await briefing.generate_briefing(5)

        assert generated["session"].startswith("Day 1,")

    async def test_a_missing_session_row_stops_before_anything_else_is_read(self, monkeypatch):
        fake = _install(monkeypatch, FakeDatabase(session=None))

        with pytest.raises(ValueError):
            await briefing.generate_briefing(9999)

        assert len(fake.queries) == 1, "the refusal happens on the session read, not after five more"


class TestTheTreasury:
    """A missing figure is not a low figure, and the three rules are one table."""

    async def test_a_null_figure_is_not_a_low_treasury(self, monkeypatch):
        row = {"credits": None, "alloys": None, "fuel": None}
        _install(monkeypatch, FakeDatabase(session=_session(5), resources=row))

        generated = await briefing.generate_briefing(5)

        assert generated["resource_pressure"] == []

    async def test_the_thresholds_the_module_names(self, monkeypatch):
        row = {"credits": 199_999, "alloys": 100_000, "fuel": 499_999}
        _install(monkeypatch, FakeDatabase(session=_session(5), resources=row))

        generated = await briefing.generate_briefing(5)

        assert generated["resource_pressure"] == ["FUEL LOW", "CREDITS LOW"]

    async def test_a_full_treasury_raises_no_alert(self, monkeypatch):
        row = {"credits": 200_000, "alloys": 100_000, "fuel": 500_000}
        _install(monkeypatch, FakeDatabase(session=_session(5), resources=row))

        generated = await briefing.generate_briefing(5)

        assert generated["resource_pressure"] == []

    async def test_a_session_with_no_resources_row_raises_no_alert(self, monkeypatch):
        _install(monkeypatch, FakeDatabase(session=_session(5), resources=None))

        generated = await briefing.generate_briefing(5)

        assert generated["resource_pressure"] == []


class TestTheQueries:
    """Every read that is about a campaign names the campaign."""

    async def test_every_scoped_query_names_the_session(self, monkeypatch):
        rows = {
            "narrative_hooks": [],
            "characters": [],
            "romance_arcs": [],
            "events": [],
            "choices": [],
            "character_memories": [],
            "wars": [],
        }
        fake = _install(monkeypatch, FakeDatabase(session=_session(5), rows=rows))

        await briefing.generate_briefing(5)

        scoped = [sql for sql in fake.queries if "maya_rp.sessions" not in sql]
        assert len(scoped) == 9, f"expected nine scoped reads, saw {len(scoped)}"
        for sql in scoped:
            assert "session_id=$1" in sql, f"a read does not name its session: {sql}"

    async def test_the_two_joins_filter_the_character_session_too(self, monkeypatch):
        rows = {"romance_arcs": [], "characters": [], "character_memories": []}
        fake = _install(monkeypatch, FakeDatabase(session=_session(5), rows=rows))

        await briefing.generate_briefing(5)

        joined = [sql for sql in fake.queries if "JOIN maya_rp.characters" in sql]
        assert len(joined) == 2
        for sql in joined:
            assert "c.session_id=$1" in sql, f"a join can carry another campaign's character: {sql}"


class TestThePrompt:
    """The renderer survives an absent optional field and never prints None."""

    def _briefing_with_nulls(self):
        return {
            "session": "Day 1, active — TKG",
            "crises": [{"title": None, "description": None, "status": "active"}],
            "location": "bridge",
            "present": [{"name": "Someone", "bond": None, "role": None}],
            "companion_states": [{"name": None, "arc_stage": None, "saturation_pct": None}],
            "resource_pressure": [],
            "recent_beats": [],
            "pending_choices": [{"id": 1, "title": None, "description": ""}],
            "overdue_memories": [],
            "wars": [{"opponent_faction": None, "phase": None, "status": "active", "casus_belli": None}],
            "leave_mode": "NONE",
            "rp_tone": "English",
        }

    def test_a_null_in_every_optional_field_still_renders(self):
        rendered = briefing.briefing_to_prompt(self._briefing_with_nulls())

        assert "### ACTIVE CRISES" in rendered and "### ACTIVE WARS" in rendered
        assert "None" not in rendered, "an absent field reached the prompt as the word None"
        assert "?" in rendered

    def test_the_bond_icons_are_driven_by_a_number(self):
        low = self._briefing_with_nulls()
        low["present"] = [{"name": "A", "bond": 8, "role": "spouse"}]
        high = self._briefing_with_nulls()
        high["present"] = [{"name": "A", "bond": 0, "role": "spouse"}]

        assert "\u2665" in briefing.briefing_to_prompt(low)
        assert "\u00b7" in briefing.briefing_to_prompt(high)

    async def test_the_generator_supplies_every_key_the_prompt_reads(self, monkeypatch):
        _install(monkeypatch, FakeDatabase(session=_session(5)))

        generated = await briefing.generate_briefing(5)

        for key in (
            "session", "crises", "location", "present", "companion_states",
            "resource_pressure", "pending_choices", "overdue_memories", "wars",
            "leave_mode", "rp_tone",
        ):
            assert key in generated, f"the prompt reads {key} and the generator never sets it"


class TestReachability:
    """This module is superseded by core/master_briefing. Pinned, not decided here."""

    def test_no_production_module_imports_this_one(self):
        sources = sorted((ROOT / "scripts").glob("*.py")) + sorted((ROOT / "modules").glob("*.py"))
        callers = [
            path.relative_to(ROOT).as_posix()
            for path in sources
            if "core.briefing" in path.read_text(encoding="utf-8", errors="replace")
            or "import briefing" in path.read_text(encoding="utf-8", errors="replace")
        ]

        assert callers == [], (
            "core/briefing.py has acquired a caller. This module is the earlier briefing engine and "
            "core/master_briefing.generate is the one the CLI and kilo_bridge use; decide whether the "
            f"second briefing is wired on purpose before removing this pin. Callers: {callers}"
        )
