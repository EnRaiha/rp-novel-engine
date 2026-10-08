#!/usr/bin/env python3
"""Guardrails — Ported from Rust guardrail.rs. Content safety checks, moral boundaries."""
from __future__ import annotations
import re
import unicodedata
from core.db import Database
from core.session import require_session
from core.log import info

# The blocked terms are snake_case keys, so the haystack is closed up before the
# match: an action written "mind control" walked straight past a literal "_"
# compare and was allowed. Same list, one definition, not rebuilt per call.
BLOCKED_WORDS = ("mind_control", "permanent_harm", "irreversible_damage",
                 "slavery_of_children")

_ACTION_GAP_RE = re.compile(r"[\s\-]+")


def _fold(text) -> str:
    """NFKC-fold, drop invisible format characters, lowercase.

    Fullwidth letters ("ｕｎｄｅｒａｇｅ") and zero-width characters ("under\u200bage") walked past a
    literal compare. NFKC maps the first to ASCII; category Cf holds the second.

    @param text - any value; `None` reads as "".
    @returns the folded string.
    """
    raw = str(text if text is not None else "")
    folded = unicodedata.normalize("NFKC", raw)
    return "".join(c for c in folded if unicodedata.category(c) != "Cf").lower()


def _normalize_action(action) -> str:
    """Fold, then close the gaps: spaces and hyphens become underscores.

    `check_generation` uses `_normalize_text` instead: closing the gaps with underscores there
    would turn prose into snake_case keys.
    """
    return _ACTION_GAP_RE.sub("_", _fold(action))


_TEXT_GAP_RE = re.compile(r"[\s\-_]+")


def _normalize_text(text) -> str:
    """Fold, then collapse runs of whitespace, hyphens and underscores to one space.

    @param text - generated prose; `None` reads as "".
    @returns text where "non-consensual", "non_consensual" and "non   consensual" are all
        "non consensual".
    """
    return _TEXT_GAP_RE.sub(" ", _fold(text)).strip()


async def check_action(action: str, context: dict | None = None) -> dict:
    """Gate one proposed action.

    `context` is accepted and unused: the check is stateless, so there is no
    session to scope. The CLI passes {"session_id": sid} for a future rule.
    """
    lower = _normalize_action(action)
    for w in BLOCKED_WORDS:
        if w in lower:
            return {"allowed": False, "reason": f"Blocked by guardrail: {w}"}
    return {"allowed": True, "reason": "Passes all guardrails"}

# Labels keep the original spelling: the reason string names the rule that matched.
GEN_BLOCKED = ["underage", "minor_in_", "non-consensual", "child abuse"]

# Patterns run on `_normalize_text` output, where every gap is one space. Each one is a superset
# of the literal term it replaces: "non-consensual" alone missed "non consensual", "nonconsensual"
# and "non_consensual", and "underage" missed "under-age" and "under age".
_GEN_PATTERNS = (
    ("underage", re.compile(r"underage|\bunder age\b")),
    ("non-consensual", re.compile(r"non ?consensual")),
    ("child abuse", re.compile(r"child ?abuse|\babus(?:e|ed|es|ing) (?:of )?(?:a |the |that |this )?child(?:ren)?\b")),
)

# "minor_in_" is a snake_case key. It only matches before the gaps are collapsed, and collapsing
# turns it into "minor in", which is ordinary prose ("a minor in engineering"). It is checked on
# the folded text with its underscores intact, so the block stays and the false positive does not appear.
_GEN_RAW = (("minor_in_", "minor_in_"),)


def check_generation(text: str) -> dict:
    """Gate local-model prose before it reaches the GM (qwen-abliterated
    has no built-in guardrails).

    @param text - generated prose; `None` passes.
    @returns `{allowed, reason}`; the reason names the rule that matched.
    """
    folded = _fold(text)
    for label, literal in _GEN_RAW:
        if literal in folded:
            return {"allowed": False, "reason": f"Blocked by generation guardrail: {label}"}
    low = _normalize_text(text)
    for label, pattern in _GEN_PATTERNS:
        if pattern.search(low):
            return {"allowed": False, "reason": f"Blocked by generation guardrail: {label}"}
    return {"allowed": True, "reason": "Passes generation guardrails"}

async def run_tick(session_id: int = None) -> dict:
    """@raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed."""
    from core.ooc import _refuse_frozen

    session_id = require_session(session_id)
    _refuse_frozen(session_id)
    return {"status": "guardrails_ready"}
