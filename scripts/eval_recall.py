#!/usr/bin/env python3
"""eval_recall.py — retrieval quality benchmark (added 2026-08-14).

Scores the RP novel-chunk retriever against gold Q→keywords pairs
(scripts/eval_pairs.json) using hit@k: a question passes if the top-k
retrieved chunks contain ALL expected keywords (case-insensitive).

Usage:
  python3 scripts/eval_recall.py            # default k=3, runs all pairs
  python3 scripts/eval_recall.py --k 5      # looser window
  python3 scripts/eval_recall.py --book 08  # filter by book

Requires the live DB (chunk_text) + Ollama embedding service for the
query-side embedding (same model the recall path uses: nomic-embed-text).
"""
from __future__ import annotations
import argparse, asyncio, json, os, re, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.db import Database
from core.log import info


async def run(k: int = 3, book: str | None = None, verbose: bool = True) -> dict:
    await Database.init()
    with open(os.path.join(os.path.dirname(__file__), "eval_pairs.json"), encoding="utf-8") as f:
        pairs = json.load(f)

    sys.path.insert(0, os.path.dirname(__file__))
    from rp_novel_recall import recall as novel_recall
    passed, total = 0, 0
    failures = []
    for pair in pairs:
        if book and pair["book"] != book:
            continue
        total += 1
        try:
            results = await novel_recall(pair["question"], book=pair["book"], limit=k)
        except Exception as e:
            if verbose:
                print(f"  ✗ {pair['question'][:60]} — ERROR {e}")
            failures.append({"q": pair["question"], "error": str(e)})
            continue
        # gather text from the k best chunks
        texts = []
        for r in results:
            if isinstance(r, dict):
                texts.append(r.get("chunk_text") or r.get("text") or "")
            else:
                texts.append(str(r))
        hay = " ".join(texts).lower()
        keywords = [k_.lower() for k_ in pair["keywords"]]
        hits = sum(1 for kw in keywords if kw in hay)
        ok = hits == len(keywords)
        if ok:
            passed += 1
        else:
            failures.append({"q": pair["question"], "hits": hits,
                             "of": len(keywords), "book": pair["book"]})
        if verbose:
            print(f"  {'✓' if ok else '✗'} ({hits}/{len(keywords)}) {pair['question'][:70]}")

    score = round(passed / total, 3) if total else 0.0
    print(f"\nrecall@{k}: {passed}/{total} = {score:.3f}")
    if failures and verbose:
        print(f"failures: {len(failures)}")
    await Database.close()
    return {"passed": passed, "total": total, "recall": score, "failures": failures}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--book", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    result = asyncio.run(run(args.k, args.book, verbose=not args.json))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
