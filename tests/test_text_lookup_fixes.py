"""Text-lookup and transport fixes: intent guardrails, name uniqueness, stream swaps, DeepSeek retry.

No test reaches the network or the database: `Database`, the embed call and httpx are faked.
"""
import re
import sys
import types
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from core import deepseek_client
from core.db import Database
from core.intent import PlayerIntent, validate_intent
from core.name_gen import NameGenerator
from core.stream_interceptor import StreamInterceptor


# ─── T1: intent guardrails ───────────────────────────────────────────────

class _FakeIntentDb:
    """Emulates Postgres on the three entity tables; records every SQL string."""

    def __init__(self, territory=(), factions=(), characters=(), credits=300):
        self.tables = {"territory": list(territory), "factions": list(factions),
                       "characters": list(characters)}
        self.credits = credits
        self.sql: list[str] = []

    @staticmethod
    def _like(pattern: str, value: str) -> bool:
        rx = "".join(".*" if c == "%" else "." if c == "_" else re.escape(c) for c in pattern)
        return re.fullmatch(rx, value, re.IGNORECASE | re.DOTALL) is not None

    async def fetchval(self, sql, *args):
        self.sql.append(sql)
        if "resources" in sql:
            return self.credits
        table = next((t for t in self.tables if f"maya_rp.{t}" in sql), None)
        if table is None:
            return None
        arg = args[1]
        if "strpos" in sql:
            hit = any(arg.lower() in row.lower() for row in self.tables[table])
        else:
            hit = any(self._like(arg, row) for row in self.tables[table])
        if not hit:
            return None
        return 1


class TestIntentTargetGuardrail:
    async def test_wildcard_target_is_rejected_as_nonexistent(self):
        """Pre-fix: target '%' became ILIKE '%%%' and matched every row, so a nonexistent target passed."""
        db = _FakeIntentDb(territory=["Sol"], factions=["Terran Union"], characters=["Mira"])
        with patch.object(Database, "fetchval", new=db.fetchval):
            for target in ("%", "_", "S_l", "%%"):
                ok, err, _ = await validate_intent(900, PlayerIntent(action_type="attack", target=target))
                assert not ok, f"wildcard target {target!r} passed the existence guardrail"
                assert "not found" in err

    async def test_target_sql_has_no_ilike_concatenation(self):
        """The query must carry the target as a plain value, with no pattern syntax built around it."""
        db = _FakeIntentDb(territory=["Sol"])
        with patch.object(Database, "fetchval", new=db.fetchval):
            await validate_intent(900, PlayerIntent(action_type="attack", target="Nowhere"))
        assert db.sql and all("ILIKE" not in q.upper() for q in db.sql), db.sql

    async def test_real_substring_target_still_passes(self):
        """The fix keeps substring, case-insensitive matching for honest targets."""
        db = _FakeIntentDb(territory=["Sol System"])
        with patch.object(Database, "fetchval", new=db.fetchval):
            ok, err, _ = await validate_intent(900, PlayerIntent(action_type="attack", target="sol"))
        assert ok, err


class TestIntentAmountGuardrail:
    async def test_move_amount_is_not_checked_against_credits(self):
        """Pre-fix: `move` with amount 500 (ships) and 300 credits failed as 'Insufficient credits'."""
        db = _FakeIntentDb(credits=300)
        with patch.object(Database, "fetchval", new=db.fetchval):
            ok, err, _ = await validate_intent(900, PlayerIntent(action_type="move", amount=500))
        assert ok, f"non-credit amount rejected: {err}"

    async def test_trade_over_credits_is_still_rejected(self):
        db = _FakeIntentDb(credits=300, factions=["Terran Union"])
        with patch.object(Database, "fetchval", new=db.fetchval):
            ok, err, _ = await validate_intent(
                900, PlayerIntent(action_type="trade", target="Terran", amount=500))
        assert not ok and "Insufficient credits" in err

    async def test_build_over_credits_is_still_rejected(self):
        db = _FakeIntentDb(credits=300)
        with patch.object(Database, "fetchval", new=db.fetchval):
            ok, err, _ = await validate_intent(900, PlayerIntent(action_type="build", amount=500))
        assert not ok and "Insufficient credits" in err


# ─── T2: name uniqueness ─────────────────────────────────────────────────

class _FakeNameConn:
    """Rows by exact lower-case match, as the fixed SQL asks; LIKE would be emulated as substring."""

    def __init__(self, names):
        self.names = list(names)
        self.sql: list[str] = []

    async def fetchrow(self, sql, arg):
        self.sql.append(sql)
        if "LIKE" in sql.upper():
            needle = arg.strip("%").lower()
            return (1,) if any(needle in n.lower() for n in self.names) else None
        wanted = set(arg) if isinstance(arg, (list, tuple)) else {arg}
        return (1,) if any(n.lower() in wanted for n in self.names) else None


class TestNameGenExists:
    async def test_single_name_is_not_rejected_by_a_longer_name(self):
        """Pre-fix: 'Amir' matched 'Samir Khan' as a substring, so single-name draws were refused."""
        gen = NameGenerator(_FakeNameConn(["Samir Khan"]))
        assert await gen._exists("Amir") is False

    async def test_prefixed_candidate_collides_with_canon_bare_name(self):
        """Pre-fix: 'TKG Ahmad Abdullah' did not match canon 'Ahmad Abdullah' (same name, different person)."""
        gen = NameGenerator(_FakeNameConn(["Ahmad Abdullah"]))
        assert await gen._exists("TKG Ahmad Abdullah", prefix="TKG") is True

    async def test_exact_match_is_case_insensitive(self):
        gen = NameGenerator(_FakeNameConn(["Ahmad Abdullah"]))
        assert await gen._exists("ahmad abdullah") is True

    async def test_sql_has_no_like(self):
        conn = _FakeNameConn([])
        await NameGenerator(conn)._exists("Rika_Voss%")
        assert conn.sql and all("LIKE" not in q.upper() for q in conn.sql), conn.sql

    async def test_wildcard_characters_do_not_match_other_names(self):
        gen = NameGenerator(_FakeNameConn(["Rika Voss"]))
        assert await gen._exists("Rika_Voss") is False
        assert await gen._exists("%") is False

    async def test_unique_name_passes_prefix_through(self):
        """The generator itself must hand its prefix to the check, or the bare-name rule never runs."""
        gen = NameGenerator(_FakeNameConn([]))
        seen = []
        orig = gen._exists

        async def spy(name, prefix=""):
            seen.append(prefix)
            return await orig(name, prefix)

        gen._exists = spy
        await gen.unique_name(prefix="TKG")
        assert seen and set(seen) == {"TKG"}


# ─── T3: stream interceptor ──────────────────────────────────────────────

def _interceptor():
    cache = {"[X: Y]": {"expanded_text": "TEMPLATE", "readable_hint": "", "required_context": []}}
    return StreamInterceptor(cache=cache)


class TestSemanticSwapFormatting:
    async def test_swap_keeps_the_trailing_newline(self):
        """Pre-fix: the swap was yielded bare, so the next paragraph was glued onto the template."""
        si = _interceptor()
        si._semantic_swap = AsyncMock(return_value="TEMPLATE")
        out = [c async for c in si._evaluate_line("dim corridor lights\n")]
        assert out == ["TEMPLATE\n"], out

    async def test_swap_without_newline_adds_none(self):
        si = _interceptor()
        si._semantic_swap = AsyncMock(return_value="TEMPLATE")
        out = [c async for c in si._evaluate_line("dim corridor lights")]
        assert out == ["TEMPLATE"], out

    async def test_swap_keeps_indentation(self):
        si = _interceptor()
        si._semantic_swap = AsyncMock(return_value="TEMPLATE")
        out = [c async for c in si._evaluate_line("    dim corridor lights\n")]
        assert out == ["    TEMPLATE\n"], out


class TestSemanticGate:
    @pytest.mark.parametrize("line", ["# Chapter heading text", "- a bullet item here",
                                      "* another bullet item", "> quoted line here"])
    def test_markdown_structure_is_never_hint_like(self, line):
        """Pre-fix: headings and bullets of 8-59 chars without terminal punctuation were embedded and swapped."""
        assert StreamInterceptor._is_hint_like(line) is False

    async def test_markdown_lines_pass_through_unswapped(self):
        si = _interceptor()
        si._semantic_swap = StreamInterceptor._semantic_swap.__get__(si)
        out = [c async for c in si._evaluate_line("- a bullet item here\n")]
        assert out == ["- a bullet item here\n"]

    async def test_middling_cosine_is_not_swapped(self):
        """Pre-fix: cosine 0.7 cleared the 0.65 floor and rewrote ordinary prose."""
        import numpy as np
        si = _interceptor()
        si._tag_vectors = [("[X: Y]", np.array([1.0, 0.0]))]
        vec = [0.7, (1 - 0.49) ** 0.5]  # unit vector, cosine 0.7 with the tag
        fake = types.SimpleNamespace(_embed=AsyncMock(return_value=vec))
        with patch.dict(sys.modules, {"core.memory": fake}):
            assert await si._semantic_swap("Captain Mira Voss") is None

    async def test_near_paraphrase_is_swapped(self):
        import numpy as np
        si = _interceptor()
        si._tag_vectors = [("[X: Y]", np.array([1.0, 0.0]))]
        vec = [0.95, (1 - 0.95 ** 2) ** 0.5]
        fake = types.SimpleNamespace(_embed=AsyncMock(return_value=vec))
        with patch.dict(sys.modules, {"core.memory": fake}):
            assert await si._semantic_swap("dim corridor lights") == "TEMPLATE"


class TestProcessStreamBuffer:
    async def test_stale_buffer_from_an_aborted_stream_is_dropped(self):
        """Pre-fix: a partial line left by an aborted stream was prefixed to the next stream's first line."""
        si = _interceptor()
        si.line_buffer = "stale"

        async def tokens():
            yield "hi\n"

        out = "".join([c async for c in si.process_stream(tokens())])
        assert out == "hi\n", out


# ─── T4: DeepSeek transport retry ────────────────────────────────────────

_REAL_CLIENT = httpx.AsyncClient


def _install(monkeypatch, handler):
    monkeypatch.setattr(deepseek_client, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(deepseek_client.asyncio, "sleep", AsyncMock())
    monkeypatch.setattr(
        deepseek_client.httpx, "AsyncClient",
        lambda **kw: _REAL_CLIENT(transport=httpx.MockTransport(handler), **{k: v for k, v in kw.items() if k == "timeout"}))


def _ok():
    return httpx.Response(200, json={"choices": [{"message": {"content": " hello "}}]})


class TestDeepSeekTransportRetry:
    async def test_a_read_timeout_is_wrapped_and_not_retried(self, monkeypatch):
        """Pre-fix: a ReadTimeout escaped as raw httpx. It stays unretried (the request may have
        reached the model and a retry would pay for and duplicate the prose) but is the provider error."""
        calls = []

        def handler(request):
            calls.append(1)
            raise httpx.ReadTimeout("slow", request=request)

        _install(monkeypatch, handler)
        with pytest.raises(deepseek_client.DeepSeekError) as raised:
            await deepseek_client.generate("hi")
        assert isinstance(raised.value.__cause__, httpx.ReadTimeout)
        assert len(calls) == 1, "a post-send fault is never retried"

    async def test_a_connect_error_is_retried_once_then_wrapped(self, monkeypatch):
        calls = []

        def handler(request):
            calls.append(1)
            raise httpx.ConnectError("down", request=request)

        _install(monkeypatch, handler)
        with pytest.raises(deepseek_client.DeepSeekError):
            await deepseek_client.generate("hi")
        assert len(calls) == 2, "exactly one retry before any token was sent"

    async def test_status_retry_backs_off_and_honors_retry_after(self, monkeypatch):
        calls = []

        def handler(request):
            calls.append(1)
            if len(calls) == 1:
                return httpx.Response(429, headers={"Retry-After": "3"})
            return _ok()

        _install(monkeypatch, handler)
        assert await deepseek_client.generate("hi") == "hello"
        deepseek_client.asyncio.sleep.assert_awaited_once_with(3.0)

    async def test_retry_after_is_capped(self, monkeypatch):
        def handler(request):
            return httpx.Response(429, headers={"Retry-After": "9999"}) if not handler.n else _ok()

        handler.n = 0

        def counting(request):
            r = handler(request)
            handler.n += 1
            return r

        _install(monkeypatch, counting)
        await deepseek_client.generate("hi")
        deepseek_client.asyncio.sleep.assert_awaited_once_with(deepseek_client._RETRY_AFTER_CAP_S)
