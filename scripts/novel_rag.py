#!/usr/bin/env python3
"""novel_rag — the campaign corpus, indexed for retrieval.

Sources: the chronicle (`maya_rp.events`), the cast (`characters` + their sheets),
the keyword lorebook, the story brief and arcs, and any chapters already written.
Keyword FTS works immediately; `--embed` adds bge-m3 vectors when the GPU is free,
which upgrades `--search` to hybrid (vector + keyword) ranking.

    python3 scripts/novel_rag.py --ingest
    python3 scripts/novel_rag.py --embed [--limit N]
    python3 scripts/novel_rag.py --search "the queen of the Marrow Fleet" [--limit 5]
    python3 scripts/novel_rag.py --stats
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import Config  # noqa: E402
from core.db import Database  # noqa: E402

OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = os.environ.get("MAYA_EMBED_MODEL", "bge-m3")
CHUNK_CHARS = 900
NOVEL_DIR = Path.home() / "Bumi-Hijau" / "adventures" / "tkg" / "novel"


def chunks_of(text: str) -> list[str]:
    """Split one source text into retrieval-sized pieces on paragraph breaks."""
    parts: list[str] = []
    buffer = ""
    for paragraph in [p.strip() for p in text.split("\n\n") if p.strip()]:
        if len(buffer) + len(paragraph) + 2 <= CHUNK_CHARS:
            buffer = f"{buffer}\n\n{paragraph}" if buffer else paragraph
        else:
            if buffer:
                parts.append(buffer)
            buffer = paragraph[:CHUNK_CHARS]
    if buffer:
        parts.append(buffer)
    return parts or ([text[:CHUNK_CHARS]] if text.strip() else [])


async def embed(text: str) -> str | None:
    payload = json.dumps({"model": EMBED_MODEL, "prompt": text[:4000]}).encode()
    try:
        request = urllib.request.Request(f"{OLLAMA}/api/embeddings", data=payload,
                                         headers={"Content-Type": "application/json"})
        vector = json.loads(urllib.request.urlopen(request, timeout=60).read()).get("embedding")
        return "[" + ",".join(f"{v:.6f}" for v in vector) + "]" if vector else None
    except Exception as error:
        print(f"embed failed: {error}", file=sys.stderr)
        return None


async def ingest(session: int) -> None:
    events = await Database.fetch(
        "SELECT id, happened_at, event_type, COALESCE(narrative_title, title) AS title,"
        " COALESCE(narrative_content, description) AS detail, importance"
        " FROM maya_rp.events WHERE session_id=$1 AND event_type <> 'policy' AND importance >= 3"
        " ORDER BY happened_at",
        session,
    )
    written = 0
    for row in events:
        stamp = row["happened_at"].strftime("%Y-%m-%d") if row["happened_at"] else ""
        text = f"{stamp} [{row['event_type']}] {' '.join(str(row['title'] or '').split())}"
        detail = " ".join(str(row["detail"] or "").split())
        if detail and detail not in text:
            text = f"{text}. {detail}"
        await Database.execute(
            "INSERT INTO maya_rag.novel_chunks (source, ref, chunk_index, text_content)"
            " VALUES ('event',$1,0,$2) ON CONFLICT (source, ref, chunk_index) DO UPDATE SET"
            " text_content=EXCLUDED.text_content",
            str(row["id"]),
            text[:CHUNK_CHARS],
        )
        written += 1

    characters = await Database.fetch(
        "SELECT id, name, role, archetype, character_type, bond, romance_stage, traits,"
        " appearance, description, current_outfit"
        " FROM maya_rp.characters WHERE session_id=$1 AND status IS DISTINCT FROM 'dead'",
        session,
    )
    for row in characters:
        traits = " ".join(str(row["traits"] or "").strip("[]").replace('"', "").split(","))
        for index, chunk in enumerate(chunks_of(
            "\n\n".join(part for part in (
                f"{row['name']} — {row['role'] or ''} ({row['archetype'] or ''})",
                f"Type {row['character_type'] or '—'}, bond {row['bond'] or 0}, {row['romance_stage'] or '—'}",
                f"Traits: {traits}" if traits else "",
                " ".join(str(row["appearance"] or row["description"] or "").split()),
                f"Outfit: {row['current_outfit']}" if row["current_outfit"] else "",
            ) if part)
        )):
            await Database.execute(
                "INSERT INTO maya_rag.novel_chunks (source, ref, chunk_index, text_content)"
                " VALUES ('character',$1,$2,$3) ON CONFLICT (source, ref, chunk_index) DO UPDATE SET"
                " text_content=EXCLUDED.text_content",
                row["name"],
                index,
                chunk,
            )
            written += 1

    lore = await Database.fetch(
        "SELECT title, content, keywords FROM maya_rp.ooc_lorebook WHERE enabled"
    )
    for row in lore:
        keywords = " ".join(row["keywords"] or [])
        for index, chunk in enumerate(chunks_of(f"{row['title']} (keywords: {keywords})\n\n{row['content']}")):
            await Database.execute(
                "INSERT INTO maya_rag.novel_chunks (source, ref, chunk_index, text_content)"
                " VALUES ('lore',$1,$2,$3) ON CONFLICT (source, ref, chunk_index) DO UPDATE SET"
                " text_content=EXCLUDED.text_content",
                row["title"],
                index,
                chunk,
            )
            written += 1

    text_files = [
        ("story", Path.home() / "Bumi-Hijau" / "adventures" / "tkg" / "story.md"),
        ("arc", Path.home() / "Bumi-Hijau" / "adventures" / "tkg" / "arcs" / "act-1.md"),
        ("arc", Path.home() / "Bumi-Hijau" / "adventures" / "tkg" / "arcs" / "act-2.md"),
        ("arc", Path.home() / "Bumi-Hijau" / "adventures" / "tkg" / "arcs" / "act-3.md"),
    ]
    for kind, path in text_files:
        if not path.is_file():
            continue
        for index, chunk in enumerate(chunks_of(path.read_text(encoding="utf-8", errors="replace"))):
            await Database.execute(
                "INSERT INTO maya_rag.novel_chunks (source, ref, chunk_index, text_content)"
                " VALUES ($1,$2,$3,$4) ON CONFLICT (source, ref, chunk_index) DO UPDATE SET"
                " text_content=EXCLUDED.text_content",
                kind,
                path.stem,
                index,
                chunk,
            )
            written += 1

    for path in sorted(NOVEL_DIR.glob("TKG-NOVEL-*.md")):
        for index, chunk in enumerate(chunks_of(path.read_text(encoding="utf-8", errors="replace"))):
            await Database.execute(
                "INSERT INTO maya_rag.novel_chunks (source, ref, chunk_index, text_content)"
                " VALUES ('chapter',$1,$2,$3) ON CONFLICT (source, ref, chunk_index) DO UPDATE SET"
                " text_content=EXCLUDED.text_content",
                path.name,
                index,
                chunk,
            )
            written += 1
    print(f"ingested {written} chunks (events {len(events)}, cast {len(characters)}, lore {len(lore)})")


async def embed_missing(limit: int) -> None:
    rows = await Database.fetch(
        "SELECT id, text_content FROM maya_rag.novel_chunks WHERE embedding IS NULL"
        " ORDER BY id LIMIT $1",
        limit,
    )
    done = 0
    for row in rows:
        vector = await embed(row["text_content"])
        if vector is None:
            break
        await Database.execute("UPDATE maya_rag.novel_chunks SET embedding=$2::vector WHERE id=$1", row["id"], vector)
        done += 1
    remaining = await Database.fetchval("SELECT count(*) FROM maya_rag.novel_chunks WHERE embedding IS NULL")
    print(f"embedded {done} chunks · still missing {remaining}")


async def search(query: str, limit: int, hybrid: bool) -> None:
    vector = await embed(query) if hybrid else None
    if vector is not None:
        rows = await Database.fetch(
            "SELECT source, ref, text_content, 1 - (embedding <=> $2::vector) AS score"
            " FROM maya_rag.novel_chunks WHERE embedding IS NOT NULL"
            " ORDER BY embedding <=> $2::vector LIMIT $3",
            query,
            vector,
            limit,
        )
    else:
        rows = await Database.fetch(
            "SELECT source, ref, text_content, ts_rank(fts, websearch_to_tsquery('english',$1)) AS score"
            " FROM maya_rag.novel_chunks WHERE fts @@ websearch_to_tsquery('english',$1)"
            " ORDER BY score DESC LIMIT $2",
            query,
            limit,
        )
    mode = "hybrid" if vector is not None else "keyword"
    print(f"{len(rows)} hits ({mode}) for {query!r}")
    for row in rows:
        print(f"  [{row['source']}:{row['ref']}] {row['score']:.3f}  {' '.join(row['text_content'].split())[:160]}")
    if not rows:
        return
    print(json.dumps([{"source": row["source"], "ref": row["ref"]} for row in rows]))


async def stats() -> None:
    rows = await Database.fetch(
        "SELECT source, count(*) AS n, count(embedding) AS embedded FROM maya_rag.novel_chunks"
        " GROUP BY source ORDER BY n DESC",
    )
    for row in rows:
        print(f"  {row['source']:10s} {row['n']:>6} chunks · {row['embedded']:>6} embedded")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Novel RAG: ingest, embed, search the campaign corpus")
    parser.add_argument("--session", type=int, default=Config.SESSION_ID)
    parser.add_argument("--ingest", action="store_true")
    parser.add_argument("--embed", action="store_true")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--search", default=None)
    parser.add_argument("--hybrid", action="store_true", default=True)
    parser.add_argument("--keyword-only", dest="hybrid", action="store_false")
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args()

    await Database.init()
    if args.ingest:
        await ingest(args.session)
    if args.embed:
        await embed_missing(args.limit)
    if args.search:
        await search(args.search, args.limit if args.limit != 500 else 5, args.hybrid)
    if args.stats or not (args.ingest or args.embed or args.search):
        await stats()
    await Database.close()
    return 0


if __name__ == "__main__":
    import asyncio

    raise SystemExit(asyncio.run(main()))
