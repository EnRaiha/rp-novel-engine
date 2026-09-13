#!/usr/bin/env python3
"""
DeepSeek Client — sole LLM provider for the RP engine (Izzat decision 2026-08-15).

Sole-DS: all engine-side LLM generation goes through DeepSeek. Ollama remains
ONLY for embeddings (core/embed.py — nomic-embed-text) because DeepSeek has
no embedding API. This client is OpenAI-compatible (api.deepseek.com).

Pattern: minimal httpx async client. No langchain, no provider registry.
Mandatory timeouts + retry-once-before-first-token (fixes the Writingway
B3 bug class: requests.get with no timeout → indefinite hang).
"""

from __future__ import annotations
import os
import json
from typing import Any

import httpx

from core.log import info

DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "") or os.environ.get(
    "OPENAI_API_KEY", ""
)
DEFAULT_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro")
DEFAULT_MAX_TOKENS = 2048
DEFAULT_TEMPERATURE = 0.7
# deepseek-v4-pro is a reasoning model: without this flag, hidden reasoning
# consumes max_tokens before any content is emitted (verified live 2026-08-15:
# max_tokens=10 + thinking enabled → empty content; disabled → direct reply).
THINKING_DISABLED = {"type": "disabled"}
_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)


class DeepSeekError(Exception):
    """Raised when DeepSeek returns a non-2xx or the body is unusable."""


async def generate(
    prompt: str,
    system: str | None = None,
    model: str = DEFAULT_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
    timeout: float | None = None,
) -> str:
    """Single-shot text generation via DeepSeek chat completions.

    Retry-once policy: retry ONLY if the failure happened before any token
    was received (network error / 5xx / timeout on connect). Never retry a
    partial stream — that would duplicate prose.
    """
    if not DEEPSEEK_API_KEY:
        raise DeepSeekError("DEEPSEEK_API_KEY not set in environment")

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
        "thinking": THINKING_DISABLED,
    }

    timeout_cfg = httpx.Timeout(
        connect=10.0, read=timeout or 120.0, write=30.0, pool=10.0
    )
    async with httpx.AsyncClient(timeout=timeout_cfg) as client:
        resp = await _post_once(client, payload)
        if resp.status_code >= 500 or resp.status_code in (408, 429):
            # Retry once (idempotent-safe: no tokens emitted yet)
            info("deepseek", f"Retry after HTTP {resp.status_code}")
            resp = await _post_once(client, payload)
        resp.raise_for_status()
        try:
            data = resp.json()
        except json.JSONDecodeError as e:
            raise DeepSeekError(f"Non-JSON response: {e}") from e

    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as e:
        raise DeepSeekError(
            f"Unexpected DeepSeek payload: {data.get('error', data)}"
        ) from e


async def _post_once(
    client: httpx.AsyncClient, payload: dict[str, Any]
) -> httpx.Response:
    return await client.post(
        f"{DEEPSEEK_BASE_URL}/chat/completions",
        json=payload,
        headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
    )
