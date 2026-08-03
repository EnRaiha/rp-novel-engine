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
from typing import AsyncGenerator

from core.db import Database
from core.log import info


class StreamInterceptor:
    """Line-buffered tag expansion for async LLM token streams."""

    TAG_PATTERN = re.compile(r"\[[A-Z_]+:\s?[A-Z_0-9]+\]")

    def __init__(self, cache: dict[str, str] | None = None):
        self.template_cache = cache or {}
        self.cache_loaded = bool(cache)
        self.line_buffer = ""

    async def load_cache(self) -> None:
        """Load templates from PG into memory (idempotent)."""
        if self.cache_loaded:
            return
        rows = await Database.fetch(
            "SELECT trigger_tag, expanded_text FROM maya_rp.stream_templates")
        self.template_cache = {r["trigger_tag"]: r["expanded_text"] for r in rows}
        self.cache_loaded = True
        info("interceptor", f"Loaded {len(self.template_cache)} stream templates.")

    def expand_line(self, line: str) -> str:
        """Swap every known [CATEGORY: TAG] in a line with its template."""
        def repl(match: re.Match) -> str:
            return self.template_cache.get(match.group(0), match.group(0))
        return self.TAG_PATTERN.sub(repl, line)

    def expand_text(self, text: str) -> str:
        """Sync convenience — expand all tags in a complete string."""
        return self.expand_line(text)

    async def process_stream(self, token_generator: AsyncGenerator[str, None]) -> AsyncGenerator[str, None]:
        """Consume an async token stream, expanding completed lines."""
        await self.load_cache()

        async for token in token_generator:
            self.line_buffer += token
            if "\n" in self.line_buffer:
                lines = self.line_buffer.split("\n")
                for complete in lines[:-1]:
                    yield self.expand_line(complete + "\n")
                self.line_buffer = lines[-1]

        if self.line_buffer:
            yield self.expand_line(self.line_buffer)
