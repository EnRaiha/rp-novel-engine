#!/usr/bin/env python3
"""unified_recall.py — merged semantic recall across RP novel chunks + Maya Cortex memory.

Queries BOTH stores and merges by similarity:
  1. maya_rp.novel_chunks   (RP engine native, nomic 768-dim, local Ollama)
  2. maya_rag.unified       (Cortex professional, bge-m3 1024-dim)

Usage:
  python3 scripts/unified_recall.py "tabby the cat"           # both stores, merged
  python3 scripts/unified_recall.py "gate 7" --limit 6        # top-N
  python3 scripts/unified_recall.py "seraphina" --source novel  # only novel store
  python3 scripts/unified_recall.py "golden age" --source cortex # only cortex store
"""
import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.embed import RP_EMBED_MODEL, CORTEX_EMBED_MODEL, RP_EMBED_DIM, CORTEX_EMBED_DIM
from core.db import Database
import core.memory as mem


async def recall_rp_novel(query_vec: list[float], limit: int) -> list[dict]:
    """Query RP engine's native novel store (768-dim)."""
    vstr = "[" + ",".join(str(x) for x in query_vec) + "]"
    rows = await Database.fetch(
        "SELECT book, part, chapter, chunk_text, "
        "1 - (embedding <=> $1::vector(768)) AS sim "
        "FROM maya_rp.novel_chunks "
        "WHERE embedding IS NOT NULL AND chunk_text != '---' "
        "ORDER BY embedding <=> $1::vector(768) LIMIT $2",
        vstr, limit)
    return [{
        "source": "novel",
        "ref": f"Book {r['book']} | {r['part'] or '—'} | {r['chapter'] or '—'}",
        "text": r["chunk_text"],
        "sim": float(r["sim"]),
    } for r in rows]


async def recall_cortex(query_vec: list[float], limit: int) -> list[dict]:
    f"""Query Cortex unified store ({CORTEX_EMBED_DIM}-dim {CORTEX_EMBED_MODEL}). Same DB, maya user."""
    import pg8000
    host = os.environ.get("OC_PG_HOST", "100.65.243.60")
    port = int(os.environ.get("OC_PG_PORT", "5432"))
    user = os.environ.get("OC_PG_USER", "maya")
    password = os.environ.get("OC_PG_PASS", "")
    dbname = os.environ.get("OC_PG_DB", "maya_memory")

    conn = pg8000.connect(host=host, port=port, user=user, password=password, database=dbname)
    cur = conn.cursor()
    vstr = "[" + ",".join(str(x) for x in query_vec) + "]"
    cur.execute(
        """SELECT source_type, source_id, chunk_text,
                 1 - (embedding <=> %s::vector(1024)) AS sim
           FROM maya_rag.unified
           WHERE embedding IS NOT NULL AND verification_status != 'corrupt'
           ORDER BY embedding <=> %s::vector(1024) LIMIT %s""",
        (vstr, vstr, limit))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{
        "source": r[0],
        "ref": r[1],
        "text": r[2],
        "sim": float(r[3]),
    } for r in rows]


async def main(query: str, limit: int, source: str):
    await Database.init()

    if source in ("novel", "both"):
        novel_vec = await mem.embed_text(query)
        novel_results = await recall_rp_novel(novel_vec, limit)
    else:
        novel_results = []

    if source in ("cortex", "both"):
        # Cortex uses bge-m3 (1024-dim) — embed via search_memory's embed_text
        sys.path.insert(0, "/home/maya/scripts")
        from search_memory import embed_text as cortex_embed
        cortex_vec = cortex_embed(query)
        cortex_results = await recall_cortex(cortex_vec, limit)
    else:
        cortex_results = []

    merged = sorted(novel_results + cortex_results, key=lambda r: -r["sim"])
    merged = merged[:limit]

    print(f"\n=== UNIFIED RECALL: \"{query}\" ({len(merged)} results) ===\n")
    for r in merged:
        tag = "📖" if r["source"] == "novel" else "🧠"
        print(f"  {tag} [{r['source']}] {r['ref']} | sim {r['sim']:.3f}")
        snippet = r["text"][:180].replace("\n", " ")
        print(f"    {snippet}...\n")

    await Database.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--source", choices=["both", "novel", "cortex"], default="both")
    args = p.parse_args()
    asyncio.run(main(args.query, args.limit, args.source))
