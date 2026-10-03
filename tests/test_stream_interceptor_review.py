"""Module review: core/stream_interceptor.py.

ONE DEFECT FIXED, and three findings reported.

`_semantic_swap` wrote an embed failure and the circuit breaker's engagement through `info`. A failing
embed is what disables tier 2 for the whole stream, so it is a fault, not a note: the council review
made exactly this call on `run_tick` and it was accepted. Both lines are `warn` now, and the tests
assert that a failure reaches `warn` and does not reach `info`.

REACHABILITY. Nothing on the turn path expands a tag. `StreamInterceptor` appears in `modules/
local_gen.py` only in a docstring, and its one caller in scripts/ is `cli.py stream`, whose own
docstring calls it a demo over a hand-written mock token list. `expand_text`, the boundary that runs
`enforce_ds_register` on the finished prose, has no caller outside tests. So the register pass the
module documents as this boundary is not on the live path. Wiring it is a decision about where the
harness expands tags, not a review fix.

REPORTED, not changed.

`required_context` is selected from the table, stored in the cache, and never consulted: nothing
gates a template on the scene it needs. All 47 rows carry an empty requirement today, so it costs
nothing. It also arrives as the *text* asyncpg hands back for jsonb, not a list, so the first reader
that iterates it will walk "[" and "]" rather than nothing.

The tier 2 gate in `_evaluate_line` is `0 < len(stripped) < HINT_MAX_LEN`, while the pre-filter it
feeds accepts `n == HINT_MAX_LEN`. A hint of exactly 60 characters never reaches the semantic tier.
Moving the boundary would let one more line swap canon prose, so it is reported rather than moved.

CHECKED AND CORRECT, so the row says what was looked at: `stream_templates` carries no `session_id`,
so the unscoped read is right; all 47 `trigger_tag` values match `TAG_PATTERN`, so no template is
unreachable from the parser; an unknown tag passes through untouched; a missing placeholder stays
literal; and the cosine match is deterministic (strict `>` against the threshold, so ties keep the
first cached tag).

The one database test reads the live table and writes nothing.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import Database  # noqa: E402
from core import stream_interceptor as si  # noqa: E402
from core.stream_interceptor import StreamInterceptor  # noqa: E402

BRIDGE = "[ENV: BRIDGE]"


def _interceptor(**kwargs) -> StreamInterceptor:
    """An interceptor with an injected cache, so no test reaches the database by accident."""
    cache = kwargs.pop("cache", {BRIDGE: {"expanded_text": "The bridge hums.",
                                          "readable_hint": "bridge",
                                          "required_context": []}})
    return StreamInterceptor(cache=cache, **kwargs)


def _vec(values):
    import numpy as np
    return np.asarray(values, dtype=float)


class TestAFailureIsNotANote:
    """A failing embed is what disables tier 2, and it was logged at info."""

    async def test_an_embed_failure_reaches_warn(self, monkeypatch):
        warned: list[tuple[str, str]] = []
        noted: list[tuple[str, str]] = []
        interceptor = _interceptor()
        interceptor._tag_vectors = [(BRIDGE, _vec([1.0, 0.0]))]

        async def broken(_text):
            raise RuntimeError("ollama down")

        monkeypatch.setattr("core.memory._embed", broken)
        # The module binds `warn` at import, so the module's own name is what has to be replaced.
        monkeypatch.setattr(si, "warn", lambda module, message: warned.append((module, message)))
        monkeypatch.setattr(si, "info", lambda module, message: noted.append((module, message)))
        assert await interceptor._semantic_swap("the corridor is dark") is None
        assert warned and warned[0][0] == "interceptor" and "ollama down" in warned[0][1], warned
        assert not noted, "a fault must not read as routine"

    async def test_the_breaker_engages_on_the_second_failure_and_says_so(self, monkeypatch):
        warned: list[str] = []
        interceptor = _interceptor()
        interceptor._tag_vectors = [(BRIDGE, _vec([1.0, 0.0]))]

        async def broken(_text):
            raise RuntimeError("ollama down")

        monkeypatch.setattr("core.memory._embed", broken)
        monkeypatch.setattr(si, "warn", lambda module, message: warned.append(message))
        await interceptor._semantic_swap("the corridor is dark")
        await interceptor._semantic_swap("the corridor is dark again")
        assert interceptor._semantic_disabled is True
        assert interceptor.stats["breaker_engaged"] is True
        assert any("Circuit breaker engaged" in message for message in warned), warned


class TestTheTiersTheModuleClaims:
    def test_an_unknown_tag_passes_through_untouched(self):
        interceptor = _interceptor()
        line = "She waits by the [ENV: NOWHERE] hatch.\n"
        assert interceptor.expand_line(line) == line

    def test_a_known_tag_expands_and_fills_its_placeholders(self):
        interceptor = _interceptor(
            cache={"[ENV: BRIDGE]": {"expanded_text": "The {name} bridge hums.",
                                     "readable_hint": "bridge", "required_context": []}},
            context_state={"name": "Iron"},
        )
        assert interceptor.expand_line(f"Step onto {BRIDGE}\n") == "Step onto The Iron bridge hums.\n"

    def test_a_placeholder_with_no_value_stays_literal(self):
        interceptor = _interceptor(
            cache={"[ENV: BRIDGE]": {"expanded_text": "The {name} bridge hums.",
                                     "readable_hint": "bridge", "required_context": []}},
        )
        assert "[ENV: BRIDGE]" not in interceptor.expand_line(BRIDGE)
        assert "{name}" in interceptor.expand_line(BRIDGE)

    async def test_a_stream_with_no_tags_is_yielded_unchanged(self):
        interceptor = _interceptor()

        async def tokens():
            for token in ("She waits. ", "The hatch ", "is cold.\n", "Nothing moves.\n"):
                yield token

        chunks = [chunk async for chunk in interceptor.process_stream(tokens())]
        assert "".join(chunks) == "She waits. The hatch is cold.\nNothing moves.\n"
        assert interceptor.stats["lines_processed"] == 2

    async def test_a_tag_split_across_tokens_is_expanded_once_the_line_completes(self):
        interceptor = _interceptor()

        async def tokens():
            for token in ("He steps onto ", "[ENV: ", "BRIDGE]", " and waits.\n"):
                yield token

        chunks = [chunk async for chunk in interceptor.process_stream(tokens())]
        assert "".join(chunks) == "He steps onto The bridge hums. and waits.\n"
        assert interceptor.stats["exact_hits"] == 1


class TestTheTemplatesInTheTable:
    """The data side of the parser, read-only."""

    async def test_the_table_carries_no_session(self):
        await Database.init()
        column = await Database.fetchval(
            "SELECT count(*) FROM information_schema.columns WHERE table_schema='maya_rp'"
            " AND table_name='stream_templates' AND column_name='session_id'")
        await Database.close()
        assert column == 0, "an unscoped read is right only while this stays zero"

    async def test_every_trigger_tag_can_be_matched_by_the_parser(self):
        await Database.init()
        tags = [row["trigger_tag"] for row in
                await Database.fetch("SELECT trigger_tag FROM maya_rp.stream_templates")]
        await Database.close()
        assert tags, "the table is the module's data"
        unreachable = [tag for tag in tags if not StreamInterceptor.TAG_PATTERN.fullmatch(tag)]
        assert unreachable == [], "these tags exist and no turn can ever expand them"
