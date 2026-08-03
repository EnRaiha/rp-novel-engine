#!/usr/bin/env python3
"""
Stream Interceptor — expands [CATEGORY: TAG] hints from the LLM into
full template text from PG before it reaches the terminal.

Narrative templating, not content rewriting:
  - The LLM emits a compact tag (4 tokens); the engine expands the stored
    description (consistent lore, token efficiency).
  - Unknown tags pass through untouched — the interceptor never alters
    text it does not own.
  - Categories: environment, combat, horror, intimacy, system
    (table: maya_rp.stream_templates — editable without code changes).
"""
import re
from typing import AsyncGenerator, Any

from core.db import Database
from core.log import info


class StreamInterceptor:
    """Line-buffered tag expansion for async LLM token streams.

    Tiers:
      1. Exact regex match against cached templates (with {placeholder} interpolation)
      2. Semantic fallback: short hints embed and match nearest template (HNSW)

    Live-state interpolation: pass ``context_state`` (dict of {key: value}) —
    templates with ``required_context`` keys get their {placeholders} filled;
    missing keys fall back to the raw template text.
    """

    TAG_PATTERN = re.compile(r"\[[A-Z_]+:\s?[A-Z_0-9]+\]")

    def __init__(self, cache: dict[str, dict] | None = None,
                 context_state: dict[str, Any] | None = None):
        self.template_cache = cache or {}
        self.cache_loaded = bool(cache)
        self.line_buffer = ""
        self.context_state = context_state or {}

    async def load_cache(self) -> None:
        """Load templates from PG into memory (idempotent)."""
        if self.cache_loaded:
            return
        rows = await Database.fetch(
            "SELECT trigger_tag, expanded_text, readable_hint, required_context "
            "FROM maya_rp.stream_templates")
        self.template_cache = {
            r["trigger_tag"]: {
                "expanded_text": r["expanded_text"],
                "readable_hint": r["readable_hint"],
                "required_context": r["required_context"] or [],
            }
            for r in rows
        }
        self.cache_loaded = True
        info("interceptor", f"Loaded {len(self.template_cache)} stream templates.")

    def _interpolate(self, raw_text: str) -> str:
        """Fill {placeholders} from context_state; missing keys stay literal."""
        if "{" not in raw_text:
            return raw_text

        class _SafeDict(dict):
            def __missing__(self, key):
                return "{" + key + "}"

        try:
            return raw_text.format_map(_SafeDict(self.context_state))
        except (ValueError, IndexError):
            return raw_text

    def expand_line(self, line: str) -> str:
        """Swap every known [CATEGORY: TAG] in a line with its template."""
        def repl(match: re.Match) -> str:
            entry = self.template_cache.get(match.group(0))
            if entry is None:
                return match.group(0)
            return self._interpolate(entry["expanded_text"])
        return self.TAG_PATTERN.sub(repl, line)

    def expand_text(self, text: str) -> str:
        """Sync convenience — expand all tags in a complete string."""
        return self.expand_line(text)

    async def _semantic_swap(self, line: str) -> str | None:
        """
        Tier 2 fallback: embed a short LLM hint and find the nearest
        template by cosine distance (pgvector HNSW). Fail-soft.
        """
        try:
            from core.memory import _embed
            vec = await _embed(line.strip())
            vstr = "[" + ",".join(map(str, vec)) + "]"
            row = await Database.fetchrow(
                "SELECT trigger_tag, expanded_text FROM maya_rp.stream_templates "
                "WHERE trigger_tag_embed IS NOT NULL "
                "AND trigger_tag_embed <=> $1::vector < 0.35 "
                "ORDER BY trigger_tag_embed <=> $1::vector LIMIT 1",
                vstr)
            if row:
                info("interceptor", f"Semantic swap: '{line.strip()[:40]}' -> {row['trigger_tag']}")
                return self._interpolate(row["expanded_text"])
        except Exception as e:
            info("interceptor", f"Semantic embed failed (passthrough): {e}")
        return None

    async def process_stream(self, token_generator: AsyncGenerator[str, None]) -> AsyncGenerator[str, None]:
        """Consume an async token stream, expanding completed lines."""
        await self.load_cache()

        async for token in token_generator:
            self.line_buffer += token
            if "\n" in self.line_buffer:
                lines = self.line_buffer.split("\n")
                for complete in lines[:-1]:
                    async for chunk in self._evaluate_line(complete + "\n"):
                        yield chunk
                self.line_buffer = lines[-1]

        if self.line_buffer:
            async for chunk in self._evaluate_line(self.line_buffer):
                yield chunk

    async def _evaluate_line(self, line: str) -> AsyncGenerator[str, None]:
        """Tier 1: exact tag match. Tier 2: semantic fallback for short hints."""
        # Tier 1 — exact regex + cache
        expanded = self.expand_line(line)
        if expanded != line or self.TAG_PATTERN.search(line):
            yield expanded
            return

        # Tier 2 — semantic: only for short hint-like lines (< 60 chars)
        stripped = line.strip()
        if 0 < len(stripped) < 60 and not stripped.endswith("."):
            swap = await self._semantic_swap(stripped)
            if swap is not None:
                yield swap
                return

        yield line
