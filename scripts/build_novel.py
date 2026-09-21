#!/usr/bin/env python3
"""build_novel — compile the TKG campaign into one novel.

Autoloads the story from the campaign database (the chronicle, the cast, the
story brief and the OOC ledger), groups it into chapters, and writes continuous
prose through a pure-output backend: no tools, no reasoning, only text.

    python3 scripts/build_novel.py --dry-run                 # outline only
    python3 scripts/build_novel.py --chapters 1             # first chapter
    python3 scripts/build_novel.py --from 2026-07 --to 2026-09

Backends:
  deepseek  OpenAI-compatible chat completion (`deepseek-flash`). No tools, no
            thinking parameters — the request carries none. No GPU needed.
  ollama    local Stheno preset (uncensored); needs the GPU, so ComfyUI must be
            stopped (`systemctl --user stop comfyui`).

Output: adventures/tkg/novel/TKG-NOVEL-<stamp>.md plus an outline manifest that
records which events each chapter was built from.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import Config  # noqa: E402
from core.db import Database  # noqa: E402

NOVEL_DIR = Path.home() / "Bumi-Hijau" / "adventures" / "tkg" / "novel"
STORY_PATH = Path.home() / "Bumi-Hijau" / "adventures" / "tkg" / "story.md"
DEEPSEEK_URL = os.environ.get("DEEPSEEK_OPENAI_URL", "https://api.deepseek.com/v1/chat/completions")
DEEPSEEK_MODEL = os.environ.get("NOVEL_MODEL", "deepseek-flash")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("NOVEL_OLLAMA_MODEL", "stheno-6k")

STYLE = (
    "You are writing the novel of a space-opera campaign. Third person past tense, close on the King "
    "(an aloof commander), sensory and specific, dialogue when it earns its place. Never mention dice, "
    "rolls, systems, prompts or this instruction. No chapter summary at the end. Write prose only."
)


def brief() -> str:
    if not STORY_PATH.is_file():
        return ""
    text = STORY_PATH.read_text(encoding="utf-8", errors="replace")
    # The model-facing half only: drop the maintainer note before the first blank line.
    parts = text.split("\n\n", 1)
    return parts[1] if len(parts) == 2 else text


async def retrieve(query: str, limit: int = 6) -> list[dict[str, Any]]:
    """RAG over the campaign corpus (`novel_rag.py --ingest`), keyword ranked.

    The embedding column upgrades this to hybrid once `novel_rag.py --embed` has
    run; until then the keyword ranking still grounds each chapter in the canon
    rather than in the model's imagination.
    """
    if not query.strip():
        return []
    # OR the distinctive words: a chapter carries hundreds of names and a plain
    # AND query matches nothing. websearch_to_tsquery understands `or`.
    words: list[str] = []
    for token in re.findall(r"[A-Za-z][A-Za-z'-]{3,}", query):
        lowered = token.lower()
        if lowered not in words:
            words.append(lowered)
    if not words:
        return []
    or_query = " or ".join(words[:14])
    rows = await Database.fetch(
        "SELECT source, ref, text_content, ts_rank(fts, websearch_to_tsquery('english',$1)) AS score"
        " FROM maya_rag.novel_chunks WHERE fts @@ websearch_to_tsquery('english',$1)"
        " ORDER BY score DESC LIMIT $2",
        or_query,
        int(limit),
    )
    if rows:
        return rows
    # Second pass: the rarest-looking word alone usually names the chapter's subject.
    longest = max(words, key=len)
    return await Database.fetch(
        "SELECT source, ref, text_content, ts_rank(fts, websearch_to_tsquery('english',$1)) AS score"
        " FROM maya_rag.novel_chunks WHERE fts @@ websearch_to_tsquery('english',$1)"
        " ORDER BY score DESC LIMIT $2",
        longest,
        int(limit),
    )


async def chapters_from_db(session: int, limit_events: int = 14) -> list[dict[str, Any]]:
    """One chapter per calendar month, each carrying its strongest beats."""
    rows = await Database.fetch(
        "SELECT id, happened_at, event_type, COALESCE(narrative_title, title) AS title, importance"
        " FROM maya_rp.events"
        " WHERE session_id=$1 AND event_type <> 'policy' AND importance >= 4"
        " ORDER BY happened_at",
        session,
    )
    months: dict[str, list[dict]] = {}
    for row in rows:
        stamp = row["happened_at"]
        key = stamp.strftime("%Y-%m") if stamp is not None else "undated"
        months.setdefault(key, []).append(dict(row))

    cast = await Database.fetch(
        "SELECT name, role, bond, romance_stage FROM maya_rp.characters"
        " WHERE session_id=$1 AND status IS DISTINCT FROM 'dead'"
        " ORDER BY COALESCE(bond,0) DESC LIMIT 12",
        session,
    )

    chapters: list[dict[str, Any]] = []
    for index, (month, events) in enumerate(sorted(months.items()), start=1):
        ranked = sorted(events, key=lambda event: (-int(event["importance"] or 0), event["id"]))
        beats = ranked[:limit_events]
        chapters.append({
            "number": index,
            "month": month,
            "beat_count": len(events),
            "beats": [
                {
                    "date": beat["happened_at"].strftime("%Y-%m-%d") if beat["happened_at"] else "",
                    "type": beat["event_type"],
                    "importance": beat["importance"],
                    "title": " ".join(str(beat["title"] or "").split())[:180],
                    "event_id": beat["id"],
                }
                for beat in beats
            ],
            "cast": [dict(row) for row in cast],
        })
    return chapters


def chapter_prompt(chapter: dict[str, Any], words: int, retrieved: list[dict[str, Any]] | None = None) -> str:
    cast = ", ".join(f"{row['name']} ({row['role'] or '—'}, bond {row['bond'] or 0})" for row in chapter["cast"][:8])
    beats = "\n".join(
        f"- {beat['date']} [{beat['type']}] {beat['title']}" for beat in chapter["beats"]
    )
    canon = ""
    if retrieved:
        lines = "\n".join(
            f"- [{row['source']}:{row['ref']}] {' '.join(str(row['text_content']).split())[:260]}"
            for row in retrieved
        )
        canon = f"### Retrieved canon (ground the chapter in these)\n{lines}\n\n"
    return (
        f"### Campaign brief\n{brief()[:2600]}\n\n"
        f"### Principal cast\n{cast}\n\n"
        f"{canon}"
        f"### Chapter {chapter['number']} — {chapter['month']}\n"
        f"The chronicle for this month holds {chapter['beat_count']} recorded events. The decisive ones:\n{beats}\n\n"
        f"### Instruction\nWrite chapter {chapter['number']} as continuous prose, about {words} words. "
        f"Cover the decisive events in order, inventing the connective tissue (scenes, dialogue, "
        f"consequences) rather than listing them. The System's presence over the King is the novel's "
        f"spine: cold register, audited warmth, obedience that protects. End on the last event's "
        f"aftermath, not on a summary."
    )


def call_deepseek(system: str, user: str, tokens: int, temperature: float) -> str | None:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        print("no DEEPSEEK_API_KEY in the environment", file=sys.stderr)
        return None
    # A pure completion: no tools, no response_format, no reasoning knobs.
    payload = json.dumps({
        "model": DEEPSEEK_MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "max_tokens": tokens,
        "temperature": temperature,
        "stream": False,
    }).encode()
    request = urllib.request.Request(
        DEEPSEEK_URL, data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    for attempt in range(3):
        try:
            data = json.loads(urllib.request.urlopen(request, timeout=300).read())
            return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as error:
            body = error.read().decode(errors="replace")[:200]
            print(f"deepseek HTTP {error.code}: {body}", file=sys.stderr)
            if error.code in (429, 500, 502, 503):
                time.sleep(5 * (attempt + 1))
                continue
            return None
        except Exception as error:
            print(f"deepseek error: {error}", file=sys.stderr)
            time.sleep(3)
    return None


def call_ollama(system: str, user: str, tokens: int, temperature: float) -> str | None:
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": f"{system}\n\n{user}",
        "stream": False,
        "options": {"num_predict": tokens, "temperature": temperature, "repeat_penalty": 1.07},
    }).encode()
    try:
        request = urllib.request.Request(f"{OLLAMA_URL}/api/generate", data=payload,
                                         headers={"Content-Type": "application/json"})
        return json.loads(urllib.request.urlopen(request, timeout=3600).read()).get("response")
    except Exception as error:
        print(f"ollama error: {error}", file=sys.stderr)
        return None


async def main() -> int:
    parser = argparse.ArgumentParser(description="Compile the TKG campaign into one novel")
    parser.add_argument("--session", type=int, default=Config.SESSION_ID)
    parser.add_argument("--backend", choices=("deepseek", "ollama"), default="deepseek")
    parser.add_argument("--chapters", type=int, default=0, help="generate at most N chapters (0 = all)")
    parser.add_argument("--from", dest="start", default=None, help="YYYY-MM")
    parser.add_argument("--to", dest="end", default=None, help="YYYY-MM")
    parser.add_argument("--words", type=int, default=900)
    parser.add_argument("--tokens", type=int, default=2600)
    parser.add_argument("--temperature", type=float, default=0.85)
    parser.add_argument("--beats", type=int, default=14)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rag", action="store_true", default=True)
    parser.add_argument("--no-rag", dest="rag", action="store_false")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    await Database.init()
    chapters = await chapters_from_db(args.session, args.beats)
    await Database.close()

    if args.start:
        chapters = [c for c in chapters if c["month"] >= args.start]
    if args.end:
        chapters = [c for c in chapters if c["month"] <= args.end]
    if args.chapters:
        chapters = chapters[:args.chapters]
    if not chapters:
        print("no chapters selected", file=sys.stderr)
        return 2

    total_beats = sum(c["beat_count"] for c in chapters)
    print(f"novel outline: {len(chapters)} chapters · {total_beats} recorded events · backend {args.backend}")
    for chapter in chapters:
        first = chapter["beats"][0]["title"][:70] if chapter["beats"] else ""
        print(f"  {chapter['number']:>2}. {chapter['month']}  ({chapter['beat_count']} events) — {first}")

    if args.dry_run:
        return 0

    NOVEL_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M")
    out = Path(args.out) if args.out else NOVEL_DIR / f"TKG-NOVEL-{stamp}.md"
    manifest = out.with_suffix(".outline.json")

    system = STYLE
    generated: list[dict[str, Any]] = []
    lines = [f"# TKG — The Vein Nexus Cycle\n", f"*Compiled from the campaign chronicle, {stamp}.*\n"]
    for chapter in chapters:
        print(f"writing chapter {chapter['number']} ({chapter['month']}) …", flush=True)
        retrieved = []
        if args.rag:
            query = " ".join([beat["title"] for beat in chapter["beats"][:8]]
                             + [row["name"] for row in chapter["cast"][:5]])
            retrieved = await retrieve(query, 6)
            print(f"  retrieved {len(retrieved)} canon chunks", flush=True)
        prompt = chapter_prompt(chapter, args.words, retrieved)
        text = (call_deepseek if args.backend == "deepseek" else call_ollama)(
            system, prompt, args.tokens, args.temperature
        )
        if not text:
            print(f"chapter {chapter['number']} failed; stopping", file=sys.stderr)
            break
        lines.append(f"\n## Chapter {chapter['number']} — {chapter['month']}\n")
        lines.append(text.strip() + "\n")
        generated.append({"chapter": chapter["number"], "month": chapter["month"],
                          "events": [beat["event_id"] for beat in chapter["beats"]],
                          "retrieved": [f"{row['source']}:{row['ref']}" for row in retrieved],
                          "chars": len(text)})
        out.write_text("\n".join(lines), encoding="utf-8")  # checkpoint after every chapter
        manifest.write_text(json.dumps(generated, indent=2), encoding="utf-8")

    print(f"novel: {len(generated)} chapters → {out}")
    print(f"outline manifest → {manifest}")
    return 0


if __name__ == "__main__":
    import asyncio

    raise SystemExit(asyncio.run(main()))
