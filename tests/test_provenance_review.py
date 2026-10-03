"""Module review: core/provenance.py.

ONE DEFECT FIXED, two reported, and the module is reachable.

FIXED. `current_value` returned None for a fact key the registry does not hold,
which is the same answer it gives for a fact whose session has no row. The two
mean different things and the only entry point that answers "why is X = Y" must
not answer "no value" for a key it never heard of. It refuses by name now, and
`why` resolves first so its own unknown-fact branch still returns the same dict
it always did (`error`, `current_value` None, empty lists) rather than raising
through the caller.

REPORTED, not changed, both because the file is not this module's.

- `scripts/kilo_bridge.py:435` calls `by_fact(sid, fact.lower().strip(), value)`
  with the raw request fact, while `why_cli` on the line above resolves the alias
  through FACT_REGISTRY. Ask for `credits` and the summary says "touching
  decisions: 2" while the `decisions` list beside it is empty, because
  `cabinet_decrees` holds the canonical key `treasury` and no row holds `credits`.
  `test_why_asks_by_fact_for_the_canonical_key` is the evidence that this module
  resolves it and the bridge does not. The fix is one call to `resolve` in the
  bridge, which belongs to the lead.
- `session_id or Config.SESSION_ID` in two places. `Config.SESSION_ID` resolves
  once at import, so a long-lived process answers about whichever session was
  active when it started; this is the drift `core.session.stale_process_default`
  describes and the 288-site accessor chapter on the King's list, not a local
  edit.

CHECKED AND CORRECT, so this row can say what was looked at: the source list in
the module docstring did not match the code (it named the unified
`decision_stream` view and `maya_rp.events` as sources of the fact path; the fact
path reads current-state tables and `cabinet_decrees`, and nothing resolves the
`event_ids` each decision carries), so the docstring is corrected rather than the
code. Every registry entry resolves to a session-scoped query. An alias cycle
returns None rather than looping. `game_day` reads `sessions` by id, which is the
session, and the other eight read `session_id=$1`. Live: `why` returns the right
value and the right touching decisions for `treasury`, `credits`, `mode`,
`queens`, `ships`, `bonds`, `game_day`, `alloys` and `fuel` on session 3, and
`why_cli` renders all of them without a None; that read wrote nothing.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from core import decision as decision_mod  # noqa: E402
from core import provenance  # noqa: E402

_NO_ROW = object()


def _patch_value(monkeypatch, row_value):
    """Answer every value query with one row, or with no row at all."""
    calls: list[tuple] = []

    async def fetchrow(sql, *args):
        calls.append((sql, args))
        return {"value": row_value} if row_value is not _NO_ROW else None

    monkeypatch.setattr(provenance.Database, "fetchrow", staticmethod(fetchrow))
    return calls


def _patch_decisions(monkeypatch, decisions, chains=None):
    """Capture the fact key `why` asks for, and answer with fixed rows."""
    seen: dict[str, object] = {}

    async def by_fact(session_id, fact_key, fact_value=None, limit=25):
        seen["session_id"] = session_id
        seen["fact_key"] = fact_key
        seen["limit"] = limit
        return decisions

    async def chain(session_id, decision_id, depth=20):
        return (chains or {}).get(decision_id, [])

    monkeypatch.setattr(decision_mod, "by_fact", by_fact)
    monkeypatch.setattr(decision_mod, "chain", chain)
    return seen


class TestTheFactKey:
    """A key the registry does not hold is refused; an empty value is not."""

    async def test_an_unknown_fact_is_refused_by_name(self, monkeypatch):
        _patch_value(monkeypatch, _NO_ROW)

        with pytest.raises(ValueError) as refused:
            await provenance.current_value("nonsense")

        assert "nonsense" in str(refused.value)
        assert "FACT_REGISTRY" in str(refused.value)

    async def test_a_known_fact_with_no_row_is_none_and_not_a_refusal(self, monkeypatch):
        _patch_value(monkeypatch, _NO_ROW)

        assert await provenance.current_value("treasury", 5) is None

    async def test_an_alias_resolves_to_the_canonical_entry(self):
        aliased = await provenance.resolve("credits")
        canonical = await provenance.resolve("treasury")

        assert aliased["fact"] == "treasury"
        assert aliased["sql"] == canonical["sql"]

    async def test_the_value_read_uses_the_registry_sql_and_the_named_session(self, monkeypatch):
        calls = _patch_value(monkeypatch, 7)

        assert await provenance.current_value("credits", 5) == 7
        sql, args = calls[0]
        assert args == (5,)
        assert sql == provenance.FACT_REGISTRY["treasury"]["sql"]

    async def test_an_alias_cycle_returns_none_rather_than_looping(self, monkeypatch):
        monkeypatch.setattr(provenance, "FACT_REGISTRY", {"a": {"alias": "b"}, "b": {"alias": "a"}})

        assert await provenance.resolve("a") is None


class TestTheRegistry:
    """Every entry reads a session, and every entry carries a source."""

    def test_every_entry_names_a_source_and_a_query(self):
        canonical = {k: v for k, v in provenance.FACT_REGISTRY.items() if "alias" not in v}

        assert canonical, "the registry is empty"
        for key, entry in canonical.items():
            assert entry["table"] and entry["column"], key
            assert entry["sql"], key

    def test_every_query_is_scoped_to_one_campaign(self):
        for key, entry in provenance.FACT_REGISTRY.items():
            if "alias" in entry:
                continue
            sql = entry["sql"]
            assert "session_id=$1" in sql or "maya_rp.sessions" in sql, f"{key} reads across campaigns: {sql}"

    def test_every_alias_points_at_a_key_that_exists(self):
        for key, entry in provenance.FACT_REGISTRY.items():
            if "alias" in entry:
                assert entry["alias"] in provenance.FACT_REGISTRY, key


class TestWhy:
    """The answer keeps its shape, and it asks for the canonical key."""

    async def test_an_unknown_fact_is_reported_rather_than_raised(self, monkeypatch):
        calls = _patch_value(monkeypatch, _NO_ROW)

        result = await provenance.why("nonsense", 5)

        assert result["error"] == "unknown fact 'nonsense'"
        assert result["current_value"] is None
        assert result["decisions"] == [] and result["chains"] == []
        assert calls == [], "an unknown fact is refused before any table is read"

    async def test_why_asks_by_fact_for_the_canonical_key(self, monkeypatch):
        _patch_value(monkeypatch, 123)
        seen = _patch_decisions(monkeypatch, [])

        result = await provenance.why("credits", 3)

        assert seen["fact_key"] == "treasury", "the alias reaches the decision lookup as the canonical key"
        assert seen["session_id"] == 3
        assert result["fact"] == "treasury"
        assert result["current_value"] == 123

    async def test_the_answer_carries_a_chain_per_decision_up_to_five(self, monkeypatch):
        _patch_value(monkeypatch, 1)
        rows = [
            {"id": n, "game_day": n, "actor": "Izzat", "decision_type": "economic", "title": f"D{n}"}
            for n in range(1, 8)
        ]
        _patch_decisions(monkeypatch, rows, chains={n: [{"id": n}] for n in range(1, 8)})

        result = await provenance.why("treasury", 3)

        assert result["decision_count"] == 7
        assert len(result["chains"]) == 5, "a chain is walked for at most five decisions"


class TestTheCli:
    """The rendering survives both shapes `why` returns."""

    async def _render(self, monkeypatch, result):
        async def fake_why(fact, session_id=None, limit=25):
            return result

        monkeypatch.setattr(provenance, "why", fake_why)
        return await provenance.why_cli("treasury", 3)

    async def test_a_known_fact_renders_its_decisions(self, monkeypatch):
        decision = {"id": 24, "game_day": 2195, "actor": "Izzat", "decision_type": "directive",
                    "title": "RS-2 GOVERNMENT EXECUTION"}
        result = {"fact": "treasury", "current_value": 729591047927, "decision_count": 1,
                  "decisions": [decision], "chains": [[decision]]}

        rendered = await self._render(monkeypatch, result)

        assert "PROVENANCE: treasury = 729591047927" in rendered
        assert "touching decisions: 1" in rendered
        assert "#24" in rendered and "chain:" in rendered

    async def test_an_unknown_fact_renders_without_a_decision_count(self, monkeypatch):
        result = {"fact": "nonsense", "current_value": None, "decisions": [],
                  "chains": [], "error": "unknown fact 'nonsense'"}

        rendered = await self._render(monkeypatch, result)

        assert "PROVENANCE: nonsense = None" in rendered
        assert "touching decisions: 0" in rendered


class TestReachability:
    """This module is on the live path: the bridge's `lineage` action is the caller."""

    def test_the_bridge_is_the_production_caller(self):
        bridge = (ROOT / "scripts/kilo_bridge.py").read_text(encoding="utf-8", errors="replace")

        assert "from core.provenance import why_cli" in bridge
        assert "why_cli(" in bridge
