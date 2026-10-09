"""Tests for the R1 bounds in core/ooc.py: refused backtracking shapes and the audit text cap.

The compile tests never run a refused pattern against text: on the old guard `((a+))+b` on 40 `a`
characters runs for hours. Two tests read the database and one writes scratch rows (ids 900-999).
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core import ooc  # noqa: E402
from core.config import Config  # noqa: E402
from core.db import Database  # noqa: E402
from core.ooc import LAYER_BOTH, OocRule, compile_rule  # noqa: E402

REFUSED = [
    r"((a+))+b",
    r"(a|aa)+b",
    r"(a|a)+b",
    r"(a?){26}a{26}",
    r".*.*.*.*x",
    r"(.*)(.*)(.*)(.*)x",
    r"t.*h.*#",
    r"\w+\w+x",
    r"a{100,}",
    r"(a+)+b",
    r"(\w+\s?)+$",
]

ORDINARY = [
    "re:voice (crack|cracks|breaks|breaking)",
    r"re:(\d{1,3}\.){3}\d{1,3}",
    r"re:she (looks|looked)\s+away",
    "re:foo.*bar",
    "re:(ab|cd)+e",
    "plain phrase",
]


def _rule(pattern: str, rule_id: str = "t-rule", delta: int = 4) -> OocRule:
    return OocRule(rule_id, "modern_phrasing", pattern, delta, LAYER_BOTH)


@pytest.mark.parametrize("pattern", REFUSED)
def test_a_backtracking_shape_is_refused(pattern):
    with pytest.raises(ValueError, match="unbounded backtracking"):
        compile_rule(_rule("re:" + pattern))


@pytest.mark.parametrize("pattern", ORDINARY)
def test_an_ordinary_pattern_still_compiles(pattern):
    assert compile_rule(_rule(pattern)).pattern


def test_a_refused_rule_is_inert_and_reported_once(monkeypatch):
    messages: list[tuple[str, str]] = []
    monkeypatch.setattr(ooc, "_BROKEN_RULES", set())
    monkeypatch.setattr(ooc, "_maintenance_active", lambda: False)
    monkeypatch.setattr(ooc, "error", lambda module, msg: messages.append((module, msg)))
    rule = _rule("re:((a+))+b", rule_id="redos-bad")
    assert ooc.audit_text("zzzz", [rule]) == []
    assert ooc.audit_text("zzzz", [rule]) == []
    assert len(messages) == 1
    assert "redos-bad" in messages[0][1]


async def test_every_seeded_regex_rule_still_compiles():
    await Database.init()
    try:
        rows = await Database.fetch("SELECT id, pattern FROM maya_rp.ooc_rules WHERE is_regex")
    finally:
        await Database.close()
    assert rows
    for row in rows:
        assert compile_rule(OocRule(row["id"], "x", row["pattern"], 1, LAYER_BOTH, is_regex=True)), row["id"]


SCRATCH_STATE = {"arc_stage": "lockdown", "deviation": 0, "roleplay_points": 0}


async def _preview(monkeypatch, text, rules=()):
    """Run a preview audit with every read stubbed. Return the result and the `warn` messages."""
    messages: list[str] = []

    async def state(_sid):
        return dict(SCRATCH_STATE)

    async def effective_rules(*_args, **_kwargs):
        return list(rules)

    async def no_findings(*_args, **_kwargs):
        return []

    async def no_exemptions(*_args, **_kwargs):
        return {}

    monkeypatch.setattr(ooc, "_session_key", lambda _sid: 901)
    monkeypatch.setattr(ooc, "_maintenance_active", lambda: False)
    monkeypatch.setattr(ooc, "state", state)
    monkeypatch.setattr(ooc, "effective_rules", effective_rules)
    monkeypatch.setattr(ooc, "knowledge_findings", no_findings)
    monkeypatch.setattr(ooc, "live_exemptions", no_exemptions)
    monkeypatch.setattr(ooc, "warn", lambda module, msg: messages.append(msg))
    result = await ooc.audit(text, 901, preview=True)
    return result, messages


async def test_a_preview_audit_reports_how_much_was_cut(monkeypatch):
    result, messages = await _preview(monkeypatch, "a" * (ooc.MAX_AUDIT_CHARS + 50))
    assert result["truncated_chars"] == 50
    assert len(messages) == 1
    assert "50" in messages[0]


async def test_a_preview_audit_at_the_cap_reports_nothing(monkeypatch):
    result, messages = await _preview(monkeypatch, "a" * ooc.MAX_AUDIT_CHARS)
    assert result["truncated_chars"] == 0
    assert messages == []


async def test_a_slip_past_the_cap_is_not_found_and_the_result_says_so(monkeypatch):
    rule = OocRule("cut-slip", "modern_phrasing", "wanna", 4, LAYER_BOTH)
    filler = "x " * (ooc.MAX_AUDIT_CHARS // 2)
    late, _ = await _preview(monkeypatch, filler + "wanna", [rule])
    assert late["findings"] == []
    assert late["truncated_chars"] == 5
    early, _ = await _preview(monkeypatch, "wanna " + filler, [rule])
    assert [f["rule_id"] for f in early["findings"]] == ["cut-slip"]
    assert early["truncated_chars"] == 6


async def test_the_stored_audit_reports_the_cut_too(scratch_session, monkeypatch):
    monkeypatch.setattr(Config, "SESSION_ID", scratch_session)
    await Database.init()
    try:
        result = await ooc.audit("a" * (ooc.MAX_AUDIT_CHARS + 7), scratch_session)
        assert result["session_id"] == scratch_session
        assert result["truncated_chars"] == 7
    finally:
        await Database.close()
