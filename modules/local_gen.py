#!/usr/bin/env python3
"""
Local Generation — prose generation via DeepSeek (sole-DS, 2026-08-15).

Primary use: pre-generate stream templates (intimacy expansions, environment,
combat) that the StreamInterceptor serves at runtime with zero latency and
zero cost. The main loop LLM never has to write explicit prose — it just
emits tags, and this module writes the stored templates offline.

Transport: DeepSeek API (core/deepseek_client.py). Formerly Ollama qwen
(huihui_ai/qwen3-abliterated:8b) — migrated 2026-08-15 under Izzat's
sole-DeepSeek decision. Ollama remains ONLY for embeddings (core/embed.py).
"""

from __future__ import annotations
import re
from typing import Any

from core.db import Database
from core.log import info, error
from core import deepseek_client as ds

PRIMARY_MODEL = ds.DEFAULT_MODEL
FAST_MODEL = ds.DEFAULT_MODEL


#: Artifact tokens the qwen3 build leaked into prose. The strip is this list, not a blanket
#: `/\w+`: the blanket form also ate ordinary writing out of every generated template — "24/7",
#: "he/she", "and/or" — and this module is the only writer of stream template text.
_ARTIFACT_TAGS = (
    "think", "thinking", "analysis", "reasoning", "response", "reply",
    "answer", "output", "assistant", "user", "system",
)


def _strip_think(text: str) -> str:
    """Remove qwen3 /think blocks and known stray artifacts from output."""
    # `\b` matters: without it `/thinking` matched the `/think` alternative, was replaced by a
    # single space, and left its tail behind as "ING" in the middle of the prose.
    text = re.sub(r"\s*/think\b\s*/?\s*", " ", text, flags=re.I)
    text = re.sub(r"\s*/(" + "|".join(_ARTIFACT_TAGS) + r")\b\s*", " ", text, flags=re.I)
    return text.strip()


async def generate(
    prompt: str,
    model: str = PRIMARY_MODEL,
    max_tokens: int = 350,
    timeout: float = 120.0,
    temperature: float = 0.8,
) -> str:
    """Generate text via DeepSeek (sole provider). Returns stripped response."""
    text = await ds.generate(
        prompt,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        timeout=timeout,
    )
    text = _strip_think(text)
    try:
        from modules.guardrails import check_generation

        gate = check_generation(text)
        if not gate.get("allowed"):
            return "[generation blocked: " + gate.get("reason", "guardrail") + "]"
    except Exception as e:  # noqa: BLE001 - reported below
        error("local-gen", f"generate: {e}")
    return text


async def generate_intimacy_template(
    position: str,
    target_desc: str = "",
    location: str = "heaven_pool",
    character: str = "she",
) -> str:
    """
    Generate a full intimacy expansion paragraph in the DS Register
    (sensory/metaphorical, no clinical terminology) for a position.
    Used to seed [SENSE: POSITION] stream templates.
    """
    prompt = (
        "Write a short literary paragraph (3-4 sentences) of sensual, romantic "
        "fiction for a private sci-fi novel. Sensory and metaphorical only — "
        "heat, breath, sound, light, water. No clinical terms, no mechanical "
        "anatomy. "
        f"Scene: the {position} position, at {location}, {character} "
        f"{target_desc}. End with an emotional beat."
    )
    return await generate(prompt)


async def upsert_template(
    trigger_tag: str,
    expanded_text: str,
    category: str = "intimacy",
    readable_hint: str = "",
    required_context: list[str] | None = None,
) -> dict[str, Any]:
    """Upsert a stream template + regenerate its semantic embedding."""
    if readable_hint:
        from core.memory import _embed

        vec = await _embed(readable_hint)
        vstr = "[" + ",".join(map(str, vec)) + "]"
    else:
        vstr = None

    await Database.execute(
        "INSERT INTO maya_rp.stream_templates "
        "(trigger_tag, expanded_text, category, readable_hint, required_context, trigger_tag_embed) "
        "VALUES ($1, $2, $3, $4, $5::jsonb, $6::vector) "
        "ON CONFLICT (trigger_tag) DO UPDATE SET "
        "expanded_text = EXCLUDED.expanded_text, "
        "category = EXCLUDED.category, "
        "readable_hint = EXCLUDED.readable_hint, "
        "required_context = EXCLUDED.required_context, "
        # A caller that supplies no `readable_hint` computed no vector, so EXCLUDED's is NULL.
        # Overwriting with it dropped the template out of the interceptor's semantic tier, which
        # reads `trigger_tag_embed` and skips every row where it is NULL.
        "trigger_tag_embed = COALESCE(EXCLUDED.trigger_tag_embed,"
        " stream_templates.trigger_tag_embed)",
        trigger_tag,
        expanded_text,
        category,
        readable_hint,
        __import__("json").dumps(required_context or []),
        vstr,
    )

    info("local_gen", f"Upserted template: {trigger_tag}")
    return {"trigger_tag": trigger_tag, "category": category}
