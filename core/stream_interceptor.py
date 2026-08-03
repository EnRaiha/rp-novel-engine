#!/usr/bin/env python3
"""
Stream Interceptor — expands [CATEGORY: TAG] hints from the LLM into
full template text from PG before it reaches the terminal.

Narrative templating, not content rewriting:
  - The LLM emits a compact tag (4 tokens); the engine expands the stored
    description (consistent lore, token efficiency).
  - Unknown tags pass through untouched — the interceptor never alters
    text it does not own.
  - Categories: environment, combat, horror, intimacy, economy, diplomacy,
    science, exploration, social, system
    (table: maya_rp.stream_templates — editable without code changes).

Performance (2026-08-04 optimization pass):
  - Tier 1 exact: ~12 µs/line (regex + dict)
  - Tier 2 semantic: IN-MEMORY cosine over cached tag vectors (~0.1 ms after
    the single embed call) — previously 6,245 ms/call via PG HNSW round-trip.
  - Pre-filter gate + circuit breaker keep embed calls rare and stalls zero.
"""
import re
import time
from typing import AsyncGenerator, Any

from core.db import Database
from core.log import info

# Cosine-similarity threshold equivalent to the old PG cosine-distance 0.35
SEMANTIC_MIN_COSINE = 0.65
# Pre-filter bounds for hint-like lines
HINT_MIN_LEN = 8
HINT_MAX_LEN = 60
HINT_TERMINAL_PUNCT = ".!?;"
# Circuit breaker: consecutive embed failures disable tier 2 for the stream
BREAKER_LIMIT = 2


class StreamInterceptor:
    """Line-buffered tag expansion for async LLM token streams.

    Tiers:
      1. Exact regex match against cached templates (with {placeholder} interpolation)
      2. Semantic fallback: short hints embed once, match nearest cached vector in RAM

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
        # In-memory semantic index: list of (tag, normalized vector)
        self._tag_vectors: list[tuple[str, Any]] = []
        self._embed_cache: dict[str, list[float]] = {}
        self._semantic_disabled = False
        self._consecutive_failures = 0
        self.stats = {
            "lines_processed": 0,
            "exact_hits": 0,
            "semantic_attempts": 0,
            "semantic_hits": 0,
            "semantic_skipped": 0,
            "semantic_total_ms": 0.0,
            "breaker_engaged": False,
        }

    async def load_cache(self) -> None:
        """Load templates + tag vectors from PG into memory (idempotent)."""
        if self.cache_loaded:
            return
        rows = await Database.fetch(
            "SELECT trigger_tag, expanded_text, readable_hint, required_context, trigger_tag_embed "
            "FROM maya_rp.stream_templates")
        self.template_cache = {}
        self._tag_vectors = []
        for r in rows:
            tag = r["trigger_tag"]
            self.template_cache[tag] = {
                "expanded_text": r["expanded_text"],
                "readable_hint": r["readable_hint"],
                "required_context": r["required_context"] or [],
            }
            vec = r["trigger_tag_embed"]
            if vec is not None:
                self._tag_vectors.append((tag, self._normalize(vec)))
        self.cache_loaded = True
        info("interceptor", f"Loaded {len(self.template_cache)} templates "
                            f"({len(self._tag_vectors)} vectors for semantic tier).")

    # ── vector helpers ──────────────────────────────────────────

    @staticmethod
    def _normalize(vec: Any) -> Any:
        import numpy as np
        if isinstance(vec, str):
            import json
            vec = json.loads(vec)  # pgvector returns "[0.1, 0.2, ...]" as text
        v = np.asarray(vec, dtype=np.float64)
        n = np.linalg.norm(v)
        return v / n if n > 0 else v

    def _best_cosine(self, query: list[float]) -> tuple[str | None, float]:
        """In-memory cosine over cached tag vectors (0.1 ms scale)."""
        if not self._tag_vectors:
            return None, 0.0
        import numpy as np
        q = np.asarray(query, dtype=np.float64)
        qn = np.linalg.norm(q)
        if qn == 0:
            return None, 0.0
        q = q / qn
        best_tag, best_score = None, SEMANTIC_MIN_COSINE
        for tag, vec in self._tag_vectors:
            score = float(np.dot(q, vec))
            if score > best_score:
                best_tag, best_score = tag, score
        return best_tag, best_score

    @staticmethod
    def _is_hint_like(stripped: str) -> bool:
        """Pre-filter: only embed lines that look like semantic hints."""
        n = len(stripped)
        if n < HINT_MIN_LEN or n > HINT_MAX_LEN:
            return False
        if stripped[-1] in HINT_TERMINAL_PUNCT:
            return False
        if stripped.startswith(('"', "'", "The ", "A ", "She ", "He ", "They ")):
            return False  # dialogue/prose-openers, not hints
        return True

    # ── interpolation ────────────────────────────────────────────

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

    # ── semantic tier (in-memory) ────────────────────────────────

    async def _semantic_swap(self, line: str) -> str | None:
        """
        Tier 2 fallback: pre-filter → one embed call → in-memory cosine match.
        Circuit breaker: BREAKER_LIMIT consecutive failures disable tier 2.
        """
        stripped = line.strip()
        if not self._is_hint_like(stripped):
            self.stats["semantic_skipped"] += 1
            return None
        if self._semantic_disabled:
            return None
        if not self._tag_vectors:
            return None  # cache injected without vectors (unit tests) — no DB, no embed

        t0 = time.perf_counter()
        try:
            from core.memory import _embed
            vec = self._embed_cache.get(stripped)
            if vec is None:
                vec = await _embed(stripped)      # single Ollama call (keep_alive 30m)
                if len(self._embed_cache) < 256:  # bounded hint cache
                    self._embed_cache[stripped] = vec
            best_tag, best_score = self._best_cosine(vec)
            if best_tag is None:
                self._consecutive_failures = 0
                return None
            self.stats["semantic_hits"] += 1
            self._consecutive_failures = 0
            entry = self.template_cache[best_tag]
            info("interceptor", f"Semantic swap: '{stripped[:40]}' -> {best_tag} "
                                f"(cos {best_score:.3f})")
            return self._interpolate(entry["expanded_text"])
        except Exception as e:
            self._consecutive_failures += 1
            if self._consecutive_failures >= BREAKER_LIMIT:
                self._semantic_disabled = True
                self.stats["breaker_engaged"] = True
                info("interceptor", f"Circuit breaker engaged — tier 2 disabled for stream "
                                    f"({BREAKER_LIMIT} consecutive failures: {e})")
            else:
                info("interceptor", f"Semantic embed failed (passthrough): {e}")
            return None
        finally:
            self.stats["semantic_total_ms"] += (time.perf_counter() - t0) * 1000

    # ── stream processing ────────────────────────────────────────

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
        self.stats["lines_processed"] += 1

        # Tier 1 — exact regex + cache
        expanded = self.expand_line(line)
        if expanded != line or self.TAG_PATTERN.search(line):
            self.stats["exact_hits"] += 1
            yield expanded
            return

        # Tier 2 — semantic (pre-filtered inside _semantic_swap)
        stripped = line.strip()
        if 0 < len(stripped) < HINT_MAX_LEN:
            self.stats["semantic_attempts"] += 1
            swap = await self._semantic_swap(stripped)
            if swap is not None:
                yield swap
                return

        yield line
