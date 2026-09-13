#!/usr/bin/env python3
"""rp_novel_recall.py — semantic recall across lossless novel chunks (RP engine native).

Usage:
  python3 scripts/rp_novel_recall.py "tabby the cat"            # semantic search all books
  python3 scripts/rp_novel_recall.py "gate 7" --book 8          # filter to one book
  python3 scripts/rp_novel_recall.py "seraphina" --limit 3      # top-N
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import httpx
from core.db import Database
import core.memory as mem


async def _recall_impl(query: str, book: str | None = None, limit: int = 5):
    await Database.init()
    vec = await mem.embed_text(query)
    vstr = "[" + ",".join(str(x) for x in vec) + "]"

    if book:
        rows = await Database.fetch(
            "SELECT book, part, chapter, chunk_index, chunk_text, "
            "1 - (embedding <=> $1::vector(768)) AS sim "
            "FROM maya_rp.novel_chunks "
            "WHERE book = $2::text AND embedding IS NOT NULL "
            "ORDER BY embedding <=> $1::vector(768) LIMIT $3",
            vstr,
            book,
            limit,
        )
    else:
        rows = await Database.fetch(
            "SELECT book, part, chapter, chunk_index, chunk_text, "
            "1 - (embedding <=> $1::vector(768)) AS sim "
            "FROM maya_rp.novel_chunks "
            "WHERE embedding IS NOT NULL AND chunk_text != '---' "
            "ORDER BY embedding <=> $1::vector(768) LIMIT $2",
            vstr,
            limit,
        )
    await Database.close()
    return [dict(r) for r in rows]


async def recall(query: str, book: str | None = None, limit: int = 5):
    """Novel chunk recall (CLI path — prints results to stdout).

    Bridge consumers MUST use recall_pure() instead: recall() prints, which
    corrupts kilo_bridge's JSON contract. (2026-08-15 split.)
    """
    try:
        rows = await _recall_impl(query, book, limit)
    except httpx.HTTPError as e:
        return [
            {
                "error": f"Ollama embedding unavailable ({e.__class__.__name__}) — "
                "check local Ollama on :11434; recall skipped"
            }
        ]
    except Exception as e:
        return [{"error": f"recall failed: {e}"}]

    print(f'\n=== NOVEL RECALL: "{query}" ===\n')
    for r in rows:
        print(
            f"  [Book {r['book']} | {r['part'] or '—'} | {r['chapter'] or '—'} | sim {r['sim']:.3f}]"
        )
        snippet = r["chunk_text"][:200].replace("\n", " ")
        print(f"    {snippet}...\n")
    return rows


async def recall_pure(
    query: str, book: str | None = None, limit: int = 5
) -> list[dict]:
    """Bridge-safe recall: returns data ONLY (no stdout prints).

    rp_novel_recall.recall() prints to stdout — which corrupts the JSON
    contract of kilo_bridge (lore_pack/novel_recall). Bridge consumers must
    use this. CLI keeps using recall(). (2026-08-15 fix.)
    """
    try:
        return await _recall_impl(query, book, limit)
    except httpx.HTTPError as e:
        return [
            {
                "error": f"Ollama embedding unavailable ({e.__class__.__name__}) — "
                "check local Ollama on :11434; recall skipped"
            }
        ]
    except Exception as e:
        return [{"error": f"recall failed: {e}"}]


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("query")
    p.add_argument("--book", default=None)
    p.add_argument("--limit", type=int, default=5)
    args = p.parse_args()
    asyncio.run(recall(args.query, args.book, args.limit))
