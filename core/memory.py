#!/usr/bin/env python3
"""Semantic Memory — search narrative by meaning via pgvector. GTX 1060 via Ollama = $0.00/inference."""
from __future__ import annotations
import httpx
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info, warn

from core.embed import RP_EMBED_MODEL

EMBED_URL = "http://localhost:11434/api/embeddings"
EMBED_MODEL = RP_EMBED_MODEL
#: `maya_rp.events.embedding` is `vector(768)` and `core/embed.py` records nomic-embed-text as the
#: 768-dim RP model. The old literal builder sliced the vector with `vec[:1536]`, which is a no-op at
#: this dimension and would have written a silently truncated vector at any other, so the length is
#: checked by name instead.
EMBED_DIM = 768


def _vector_literal(vec: list[float]) -> str:
    """The pgvector literal for an embedding, refusing a vector the column cannot hold."""
    if len(vec) != EMBED_DIM:
        raise ValueError(
            f"embedding has {len(vec)} dimensions, maya_rp.events.embedding holds {EMBED_DIM}"
            f" (EMBED_MODEL={EMBED_MODEL!r})")
    return "[" + ",".join(map(str, vec)) + "]"

import asyncio
_OLLAMA_LOCK = asyncio.Lock()  # one Ollama job at a time on the 1060 (2026-08-14)

async def _embed(text: str, keep_alive: str = "30m") -> list[float]:
    """Generate embedding via local Ollama on GTX 1060. ~50ms per call when hot.

    keep_alive 30m: keeps nomic-embed-text resident so the interceptor's
    semantic tier never pays cold-load latency (contends with 8B generator).
    """
    async with _OLLAMA_LOCK:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(EMBED_URL, json={
                "model": EMBED_MODEL, "prompt": text, "keep_alive": keep_alive})
            return resp.json()["embedding"]

# Public alias — used by wiki_ingest.py, kilo_bridge.py, and any external script
embed_text = _embed

async def store_event(event_id: int, title: str, description: str, session_id: int = None) -> bool:
    """Store event WITH vector embedding for semantic search.

    Returns True when the vector was written. `session_id` used to be accepted and never read, and
    the UPDATE matched on the id alone, so a caller naming the wrong campaign still had the vector
    written onto that campaign's row. The write names its session now and says when it matched
    nothing.
    """
    if session_id is None:
        session_id = Config.SESSION_ID
    text = f"{title}. {description}"
    try:
        vec = await _embed(text)
        status = await Database.execute(
            "UPDATE maya_rp.events SET embedding=$1::vector(768) WHERE id=$2 AND session_id=$3",
            _vector_literal(vec), event_id, session_id)
        stored = status.split()[-1] == "1"
        if not stored:
            warn("memory", f"event {event_id} is not in session {session_id}: no vector stored")
        return stored
    except Exception as e:
        # Was `info`, which is why a failing embed path read as noise rather than as a fault: it is
        # the difference between "memory has nothing to say" and "memory cannot hear".
        warn("memory", f"Embedding failed for event {event_id}: {e}")
        return False

async def recall(query: str, limit: int = 5, session_id: int = None) -> list[dict]:
    """Find semantically similar past events. 'Nethara getting hurt' finds the right scene."""
    if session_id is None: session_id = Config.SESSION_ID
    try:
        qv = await _embed(query)
        rows = await Database.fetch(
            "SELECT id, title, description, happened_at, 1-(embedding <=> $1::vector(768)) AS sim "
            "FROM maya_rp.events WHERE session_id=$2 AND embedding IS NOT NULL "
            "ORDER BY embedding <=> $1::vector(768) LIMIT $3",
            _vector_literal(qv), session_id, limit)
        return [dict(r) for r in rows if r["sim"] and r["sim"] > 0.55]
    except Exception as e:
        warn("memory", f"Recall failed: {e}")
        return []

async def store_and_recall(event_id: int, title: str, desc: str, query: str, session_id: int = None):
    """Store event, then immediately recall similar ones — for 'this reminds me of...' moments."""
    await store_event(event_id, title, desc, session_id)
    return await recall(query, 3, session_id)
