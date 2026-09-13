#!/usr/bin/env python3
"""Tests for core/deepseek_client.py — sole-DS provider client (2026-08-15).

pytest-asyncio style (pyproject: asyncio_mode = "auto").
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import Mock, patch

from core import deepseek_client as ds


def _resp(status: int, body: dict):
    """Plain Mock — the client calls resp.status_code (attr) and resp.json()
    (sync, httpx-style). AsyncMock would make .json() a coroutine."""
    r = Mock()
    r.status_code = status
    r.json.return_value = body
    return r


@pytest.fixture
def ds_key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")


async def test_generate_success(ds_key):
    with patch(
        "core.deepseek_client._post_once",
        return_value=_resp(
            200, {"choices": [{"message": {"content": "  Hello world!  "}}]}
        ),
    ):
        text = await ds.generate("prompt")
    assert text == "Hello world!"


async def test_generate_system_prompt(ds_key):
    with patch(
        "core.deepseek_client._post_once",
        return_value=_resp(200, {"choices": [{"message": {"content": "ok"}}]}),
    ) as mock_post:
        await ds.generate("prompt", system="be concise")
        payload = mock_post.call_args[0][1]
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][1]["role"] == "user"
    assert payload["messages"][1]["content"] == "prompt"


async def test_retry_on_5xx_before_first_token(ds_key):
    """Retry-once only for pre-token failures (idempotent-safe)."""
    with patch("core.deepseek_client._post_once") as mock_post:
        mock_post.side_effect = [
            _resp(500, {}),
            _resp(200, {"choices": [{"message": {"content": "retried"}}]}),
        ]
        text = await ds.generate("prompt")
    assert text == "retried"
    assert mock_post.call_count == 2


async def test_no_retry_on_400(ds_key):
    with patch(
        "core.deepseek_client._post_once", return_value=_resp(400, {})
    ) as mock_post:
        with pytest.raises(Exception):
            await ds.generate("prompt")
    assert mock_post.call_count == 1


async def test_missing_key_raises(monkeypatch):
    """Module-level DEEPSEEK_API_KEY is captured at import; patch it directly."""
    monkeypatch.setattr(ds, "DEEPSEEK_API_KEY", "")
    with pytest.raises(ds.DeepSeekError):
        await ds.generate("prompt")


async def test_malformed_payload_raises(ds_key):
    with patch(
        "core.deepseek_client._post_once",
        return_value=_resp(200, {"error": "no choices"}),
    ):
        with pytest.raises(ds.DeepSeekError):
            await ds.generate("prompt")
