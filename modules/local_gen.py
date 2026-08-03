#!/usr/bin/env python3
"""
Local Generation — offline prose generation via local Ollama models.

Primary use: pre-generate stream templates (intimacy expansions, environment,
combat) that the StreamInterceptor serves at runtime with zero latency and
zero cost. The main loop LLM never has to write explicit prose — it just
emits tags, and this module writes the stored templates offline.

Models:
  - huihui_ai/qwen3-abliterated:8b  (primary — 5.0GB, fits GTX 1060 6GB)
  - fredrezones55/Qwen3.5-Uncensored-HauhauCS-Aggressive:4b (fast fallback)
"""
from __future__ import annotations
import re
from typing import Any

import httpx

from core.db import Database
from core.log import info

OLLAMA_URL = "http://localhost:11434/api/generate"
PRIMARY_MODEL = "huihui_ai/qwen3-abliterated:8b"
FAST_MODEL = "fredrezones55/Qwen3.5-Uncensored-HauhauCS-Aggressive:4b"


def _strip_think(text: str) -> str:
    """Remove qwen3 /think blocks and artifacts from output."""
    text = re.sub(r"\s*/think\s*/?\s*", " ", text, flags=re.I)
    text = re.sub(r"\s*/\w+\s*", " ", text, flags=re.I)  # stray /tags
    return text.strip()


async def generate(
    prompt: str,
    model: str = PRIMARY_MODEL,
    max_tokens: int = 350,
    timeout: float = 300.0,
    temperature: float = 0.8,
) -> str:
    """Generate text via local Ollama. Returns stripped response."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(OLLAMA_URL, json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": {"num_predict": max_tokens, "temperature": temperature},
            "keep_alive": "10m",
        })
        resp.raise_for_status()
        data = resp.json()
        return _strip_think(data.get("response", ""))


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
        "trigger_tag_embed = EXCLUDED.trigger_tag_embed",
        trigger_tag, expanded_text, category, readable_hint,
        __import__("json").dumps(required_context or []), vstr)

    info("local_gen", f"Upserted template: {trigger_tag}")
    return {"trigger_tag": trigger_tag, "category": category}
