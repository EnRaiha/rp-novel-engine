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
import asyncio
import os
import json
from typing import Any

import httpx

from core.log import info

# Public egress. Under the egress policy (outbound only over Tailscale) this must be overridden via
# DEEPSEEK_BASE_URL to a Tailscale proxy.
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
#: Pause before the single transport retry.
# Failures that happen before the request leaves: nothing was generated, so a retry is safe.
# A read or write timeout is not in this set: the request may have reached the server.
_RETRYABLE_TRANSPORT = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
)

_RETRY_SLEEP_S = 0.5
#: Backoff before the 408/429/5xx retry, and the ceiling for a server-sent Retry-After.
_STATUS_BACKOFF_S = 1.0
_RETRY_AFTER_CAP_S = 10.0


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
        # Retry only what failed before the request left: connect errors and a pool timeout. A read or
        # write timeout may have reached the model, and a retry would pay for and duplicate the prose.
        # Neither escapes as raw httpx: this class is the provider's error contract.
        try:
            resp = await _post_once(client, payload)
        except _RETRYABLE_TRANSPORT as exc:
            info("deepseek", f"Retry after {type(exc).__name__} before any token was sent")
            await asyncio.sleep(_RETRY_SLEEP_S)
            try:
                resp = await _post_once(client, payload)
            except httpx.HTTPError as exc2:
                raise DeepSeekError(f"DeepSeek transport failure: {type(exc2).__name__}: {exc2}") from exc2
        except httpx.HTTPError as exc:
            raise DeepSeekError(f"DeepSeek transport failure: {type(exc).__name__}: {exc}") from exc
        else:
            if resp.status_code >= 500 or resp.status_code in (408, 429):
                # Retry once (idempotent-safe: no tokens emitted yet), after a bounded backoff
                # so an overloaded or rate-limiting server is not hit again at once.
                delay = _retry_delay(resp)
                info("deepseek", f"Retry after HTTP {resp.status_code} in {delay:.1f}s")
                await asyncio.sleep(delay)
                try:
                    resp = await _post_once(client, payload)
                except httpx.HTTPError as exc2:
                    raise DeepSeekError(
                        f"DeepSeek transport failure: {type(exc2).__name__}: {exc2}") from exc2
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # This class documents itself as the error for a non-2xx; a raw
            # httpx exception from the sole provider client is not that contract.
            raise DeepSeekError(
                f"DeepSeek HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc
        try:
            data = resp.json()
        except json.JSONDecodeError as e:
            raise DeepSeekError(f"Non-JSON response: {e}") from e

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise DeepSeekError(
            f"Unexpected DeepSeek payload: {data.get('error', data)}"
        ) from e
    # A null or non-string content is an unusable body, not a crash: `.strip()`
    # on None raised AttributeError, which no caller catches as a provider fault.
    if not isinstance(content, str):
        raise DeepSeekError(f"Unexpected DeepSeek payload: content is {type(content).__name__}")
    if not content.strip():
        # Documented symptom of the reasoning-token bug this module disables:
        # an empty completion is a failure, and returning "" handed the caller
        # blank prose as if the model had written it.
        raise DeepSeekError(
            f"Empty completion for model {model} (max_tokens={max_tokens}); "
            "the model produced no content"
        )
    return content.strip()


def _retry_delay(resp: httpx.Response) -> float:
    """Seconds to wait before the status-code retry.

    @param resp: the failed response.
    @returns: Retry-After on a 429 when it parses as seconds, else the default; capped.
    """
    if resp.status_code == 429:
        try:
            return max(0.0, min(float(resp.headers.get("Retry-After", "")), _RETRY_AFTER_CAP_S))
        except (TypeError, ValueError):
            pass
    return _STATUS_BACKOFF_S


async def _post_once(
    client: httpx.AsyncClient, payload: dict[str, Any]
) -> httpx.Response:
    return await client.post(
        f"{DEEPSEEK_BASE_URL}/chat/completions",
        json=payload,
        headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
    )
