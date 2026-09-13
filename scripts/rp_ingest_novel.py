#!/usr/bin/env python3
"""rp_ingest_novel.py — Ingest lossless novel files into maya_rp.novel_chunks.

RP-engine native: uses core.memory's embed path (local Ollama, 768-dim)
so retrieval works with the same engine. Chunks carry book/part/chapter
metadata for filtered recall.

Usage:
  python3 scripts/rp_ingest_novel.py            # ingest all books
  python3 scripts/rp_ingest_novel.py --book 8   # ingest one book only
"""
import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.db import Database
from core.log import info

import core.memory as mem

NOVEL_DIR = "/home/maya/Bumi-Hijau/adventures/tkg/novel"
# Paragraph-boundary chunking (2026-08-14): fixed 40-line chunks split
# mid-thought; chunks now respect paragraph integrity with 1-paragraph
# overlap so context spans chunk seams.
TARGET_CHUNK_CHARS = 2600
OVERLAP_PARAGRAPHS = 1
SKIP_FILES = {"HOWTOEDIT.md", "NOVEL-FORMAT-LOSSLESS.md"}

BOOK_RE = re.compile(r"book-(\d+)-")
PART_RE = re.compile(r"^###\s+PART\s+[IVXLC]+|^##\s+PART\s+[IVXLC]+", re.IGNORECASE)
CHAPTER_RE = re.compile(r"^####\s+Chapter|^###\s+Chapter|^##\s+Chapter", re.IGNORECASE)


def chunk_file(path: str) -> list[dict]:
    """Split a book into paragraph-aligned chunks with overlap."""
    with open(path, encoding="utf-8") as f:
        lines = f.readlines()

    # Build paragraphs with part/chapter context
    paragraphs = []  # {"part", "chapter", "text"}
    current_part = ""
    current_chapter = ""
    buf: list[str] = []

    def flush_para():
        nonlocal buf
        text = "".join(buf).strip()
        if text:
            paragraphs.append({"part": current_part, "chapter": current_chapter,
                               "text": text})
        buf = []

    for line in lines:
        if PART_RE.match(line):
            flush_para()
            current_part = line.strip().strip('#').strip()
            continue
        if CHAPTER_RE.match(line):
            flush_para()
            current_chapter = line.strip().strip('#').strip()
            continue
        if line.strip() == "":
            flush_para()
            continue
        buf.append(line)
    flush_para()

    # Pack paragraphs into ~TARGET_CHUNK_CHARS chunks, overlap at seams
    chunks: list[dict] = []
    acc: list[dict] = []
    acc_len = 0
    for p in paragraphs:
        plen = len(p["text"])
        if acc and acc_len + plen > TARGET_CHUNK_CHARS:
            chunks.append({
                "part": acc[0]["part"],
                "chapter": acc[0]["chapter"],
                "text": "\n\n".join(x["text"] for x in acc),
            })
            acc = acc[-OVERLAP_PARAGRAPHS:] if OVERLAP_PARAGRAPHS else []
            acc_len = sum(len(x["text"]) for x in acc)
        acc.append(p)
        acc_len += plen
    if acc:
        chunks.append({
            "part": acc[0]["part"],
            "chapter": acc[0]["chapter"],
            "text": "\n\n".join(x["text"] for x in acc),
        })
    return chunks


async def ingest(book_filter: int | None = None):
    await Database.init()
    books = sorted(f for f in os.listdir(NOVEL_DIR) if f.endswith(".md") and f not in SKIP_FILES)
    total = 0

    for fname in books:
        m = BOOK_RE.match(fname)
        if book_filter is not None and (not m or int(m.group(1)) != book_filter):
            continue
        fpath = os.path.join(NOVEL_DIR, fname)
        chunks = chunk_file(fpath)
        book = m.group(1) if m else fname
        print(f"[novel] Book {book}: {len(chunks)} chunks", flush=True)
        # clear stale chunks first — chunking changed (2026-08-14), so old
        # indexes would otherwise linger as duplicates
        await Database.execute("DELETE FROM maya_rp.novel_chunks WHERE book=$1", book)

        for idx, c in enumerate(chunks):
            try:
                vec = await mem.embed_text(c["text"])
                vstr = "[" + ",".join(str(x) for x in vec) + "]"
                await Database.execute(
                    """INSERT INTO maya_rp.novel_chunks
                       (session_id, book, part, chapter, chunk_index, chunk_text, embedding, created_at)
                       VALUES ($1, $2, $3, $4, $5, $6, $7::vector(768), NOW())
                       ON CONFLICT (book, chunk_index)
                       DO UPDATE SET part=EXCLUDED.part, chapter=EXCLUDED.chapter,
                                     chunk_text=EXCLUDED.chunk_text, embedding=EXCLUDED.embedding,
                                     created_at=NOW()""",
                    3, book, c["part"], c["chapter"], idx, c["text"], vstr,
                )
                total += 1
            except Exception as e:
                print(f"  [novel] ERROR Book {book} chunk {idx}: {e}", flush=True)

    print(f"\n✅ RP novel ingest complete: {total} chunks embedded (local Ollama 768-dim).")
    await Database.close()


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--book", type=int, default=None)
    args = p.parse_args()
    asyncio.run(ingest(args.book))
