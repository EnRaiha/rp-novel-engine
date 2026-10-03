"""Module review: core/deepseek_client.py.

THREE DEFECTS FIXED, all in the error contract this client is the only door to.

The module docstring states the retry policy: "retry ONLY if the failure
happened before any token was received (network error / 5xx / timeout on
connect)". Only the status-code half existed. A connection that never opened
raised straight out of `generate` — no retry, no DeepSeekError — so the most
common transient failure in the class the module was written to fix (the
Writingway B3 hang, requests with no timeout) was the one failure it did not
retry. `_RETRYABLE_TRANSPORT` is the pre-token class now: ConnectError,
ConnectTimeout, PoolTimeout. ReadTimeout and WriteTimeout are deliberately not in
it, because the request may have reached the server, and a retry there is the
duplicate prose the docstring forbids.

`data["choices"][0]["message"]["content"].strip()` raised AttributeError when
the content was null. The module catches KeyError, IndexError and TypeError as
"unusable body" and misses the one shape a null content produces, so a caller
that catches DeepSeekError as the provider fault saw a bare AttributeError
instead. Null and non-string content are refused as unusable bodies now.

A whitespace-only completion was returned as an empty string. The file documents
that shape as the symptom of the reasoning-token bug it disables with
`thinking: disabled` (`max_tokens=10` plus thinking → empty content, verified
live 2026-08-15), so an empty answer is a failure the caller had no way to see:
local_gen would hand blank prose back as narration. It raises now, naming the
model and the token budget.

Also fixed: a non-2xx raised `httpx.HTTPStatusError` from a class whose own
docstring says it is "raised when DeepSeek returns a non-2xx". The status error
is wrapped in DeepSeekError, with the status and the first 200 characters of the
body, so one exception type covers the provider fault as documented.

CHECKED AND CORRECT: the key check happens before any request; the payload
carries `stream: False` and the disabled thinking flag; the retry posts the same
payload object (idempotent-safe); a 400 is not retried; the non-JSON path raises
DeepSeekError. `timeout or 120.0` is on the added checklist's `X or default`
list and is left as it stands: a read timeout of 0 is not a value a caller
means, and the guard changes nothing for a real one.

No test here reaches the network: `_post_once` is patched in every one.
"""
from __future__ import annotations

import pathlib
import sys
from unittest.mock import Mock, patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402
import pytest  # noqa: E402

from core import deepseek_client as ds  # noqa: E402

URL = "https://api.deepseek.com/chat/completions"


@pytest.fixture
def keyed(monkeypatch):
    monkeypatch.setattr(ds, "DEEPSEEK_API_KEY", "test-key")


def _resp(status: int, body: dict):
    """httpx.Response, so raise_for_status() behaves as it does in production."""
    return httpx.Response(status, json=body, request=httpx.Request("POST", URL))


def _ok(text: str = "  Hello world!  "):
    return _resp(200, {"choices": [{"message": {"content": text}}]})


class TestTheRetryPolicy:
    """Retry once, and only for a failure that happened before any token."""

    async def test_a_connect_error_is_retried_once(self, keyed):
        with patch("core.deepseek_client._post_once") as post:
            post.side_effect = [httpx.ConnectError("connection refused"), _ok("retried")]
            text = await ds.generate("prompt")

        assert text == "retried"
        assert post.call_count == 2

    async def test_a_pool_timeout_is_retried_once(self, keyed):
        with patch("core.deepseek_client._post_once") as post:
            post.side_effect = [httpx.PoolTimeout("pool exhausted"), _ok("retried")]
            text = await ds.generate("prompt")

        assert text == "retried"
        assert post.call_count == 2

    async def test_a_connect_error_that_repeats_is_not_retried_forever(self, keyed):
        with patch("core.deepseek_client._post_once") as post:
            post.side_effect = [httpx.ConnectError("down"), httpx.ConnectError("still down")]
            with pytest.raises(httpx.ConnectError):
                await ds.generate("prompt")

        assert post.call_count == 2

    async def test_a_read_timeout_is_not_retried(self, keyed):
        with patch("core.deepseek_client._post_once") as post:
            post.side_effect = httpx.ReadTimeout("too slow")
            with pytest.raises(httpx.ReadTimeout):
                await ds.generate("prompt")

        assert post.call_count == 1, "the request may have reached the model; a retry duplicates prose"

    async def test_the_retryable_set_is_the_pre_token_class(self):
        assert httpx.ConnectError in ds._RETRYABLE_TRANSPORT
        assert httpx.ConnectTimeout in ds._RETRYABLE_TRANSPORT
        assert httpx.PoolTimeout in ds._RETRYABLE_TRANSPORT
        assert httpx.ReadTimeout not in ds._RETRYABLE_TRANSPORT
        assert httpx.WriteTimeout not in ds._RETRYABLE_TRANSPORT

    async def test_a_429_is_retried_and_a_400_is_not(self, keyed):
        with patch("core.deepseek_client._post_once") as post:
            post.side_effect = [_resp(429, {}), _ok("retried")]
            assert await ds.generate("prompt") == "retried"
            assert post.call_count == 2

        with patch("core.deepseek_client._post_once", return_value=_resp(400, {"error": "bad request"})) as post:
            with pytest.raises(ds.DeepSeekError):
                await ds.generate("prompt")
            assert post.call_count == 1

    async def test_the_retry_posts_the_same_payload(self, keyed):
        with patch("core.deepseek_client._post_once") as post:
            post.side_effect = [_resp(503, {}), _ok("retried")]
            await ds.generate("prompt")

        first, second = post.call_args_list[0][0][1], post.call_args_list[1][0][1]
        assert first == second
        assert first["stream"] is False
        assert first["thinking"] == {"type": "disabled"}


class TestTheBody:
    """An unusable body is a DeepSeekError, whichever shape it takes."""

    async def test_a_null_content_is_an_unusable_body(self, keyed):
        with patch("core.deepseek_client._post_once", return_value=_resp(200, {"choices": [{"message": {"content": None}}]})):
            with pytest.raises(ds.DeepSeekError) as refused:
                await ds.generate("prompt")

        assert "NoneType" in str(refused.value)

    async def test_an_empty_completion_is_refused(self, keyed):
        with patch("core.deepseek_client._post_once", return_value=_ok("   \n")):
            with pytest.raises(ds.DeepSeekError) as refused:
                await ds.generate("prompt", model="deepseek-v4-pro", max_tokens=10)

        message = str(refused.value)
        assert "Empty completion" in message
        assert "deepseek-v4-pro" in message and "max_tokens=10" in message, "the refusal names the budget"

    async def test_a_missing_choice_is_an_unusable_body(self, keyed):
        with patch("core.deepseek_client._post_once", return_value=_resp(200, {"choices": []})):
            with pytest.raises(ds.DeepSeekError):
                await ds.generate("prompt")

    async def test_a_non_json_body_is_a_deepseek_error(self, keyed):
        bad = httpx.Response(200, content=b"<html>nope</html>", request=httpx.Request("POST", URL))
        with patch("core.deepseek_client._post_once", return_value=bad):
            with pytest.raises(ds.DeepSeekError) as refused:
                await ds.generate("prompt")

        assert "Non-JSON" in str(refused.value)

    async def test_a_real_error_status_raises_the_clients_own_error(self, keyed):
        failed = _resp(503, {"error": "overloaded"})
        with patch("core.deepseek_client._post_once", return_value=failed) as post:
            with pytest.raises(ds.DeepSeekError) as refused:
                await ds.generate("prompt")

        assert "503" in str(refused.value)
        assert post.call_count == 2, "a 503 is retried before it is refused"

    async def test_a_good_body_is_stripped(self, keyed):
        with patch("core.deepseek_client._post_once", return_value=_ok()):
            assert await ds.generate("prompt") == "Hello world!"


class TestTheKey:
    """No key means no request."""

    async def test_a_missing_key_is_refused_before_any_request(self, monkeypatch):
        monkeypatch.setattr(ds, "DEEPSEEK_API_KEY", "")
        with patch("core.deepseek_client._post_once") as post:
            with pytest.raises(ds.DeepSeekError) as refused:
                await ds.generate("prompt")

        assert "DEEPSEEK_API_KEY" in str(refused.value)
        assert post.call_count == 0


class TestTheCallers:
    """Reachability: local_gen is the production caller, and it is the only one."""

    def test_local_gen_is_the_production_caller(self):
        source = (ROOT / "modules/local_gen.py").read_text(encoding="utf-8", errors="replace")
        assert "from core import deepseek_client as ds" in source
        assert "ds.generate(" in source
