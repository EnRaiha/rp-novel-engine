#!/usr/bin/env python3
"""Semantic Memory — search narrative by meaning via pgvector. GTX 1060 via Ollama = $0.00/inference."""
from __future__ import annotations
import httpx
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info

from core.embed import RP_EMBED_MODEL

EMBED_URL = "http://localhost:11434/api/embeddings"
EMBED_MODEL = RP_EMBED_MODEL

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

async def store_event(event_id: int, title: str, description: str, session_id: int = None):
    """Store event WITH vector embedding for semantic search."""
    text = f"{title}. {description}"
    try:
        vec = await _embed(text)
        vstr = "[" + ",".join(map(str, vec[:1536])) + "]"
        await Database.execute("UPDATE maya_rp.events SET embedding=$1::vector(768) WHERE id=$2", vstr, event_id)
    except Exception as e:
        info("memory", f"Embedding failed for event {event_id}: {e}")

async def recall(query: str, limit: int = 5, session_id: int = None) -> list[dict]:
    """Find semantically similar past events. 'Nethara getting hurt' finds the right scene."""
    if session_id is None: session_id = Config.SESSION_ID
    try:
        qv = await _embed(query)
        vstr = "[" + ",".join(map(str, qv[:1536])) + "]"
        rows = await Database.fetch(
            "SELECT id, title, description, happened_at, 1-(embedding <=> $1::vector(768)) AS sim "
            "FROM maya_rp.events WHERE session_id=$2 AND embedding IS NOT NULL "
            "ORDER BY embedding <=> $1::vector(768) LIMIT $3",
            vstr, session_id, limit)
        return [dict(r) for r in rows if r["sim"] and r["sim"] > 0.55]
    except Exception as e:
        info("memory", f"Recall failed: {e}")
        return []

async def store_and_recall(event_id: int, title: str, desc: str, query: str, session_id: int = None):
    """Store event, then immediately recall similar ones — for 'this reminds me of...' moments."""
    await store_event(event_id, title, desc, session_id)
    return await recall(query, 3, session_id)
