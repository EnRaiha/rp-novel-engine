#!/usr/bin/env python3
"""
Interceptor benchmark gate — run before/after any interceptor change.

Measures:
  - Tier 1 exact:  µs/line (threshold: < 50 µs)
  - Pure cosine:   ms/query over cached vectors (threshold: < 1 ms)
  - Semantic path: ms/call (embed + match, hot) — reported, informational

Exits non-zero if a hard threshold fails (regression guard).
Usage: python3 scripts/bench_interceptor.py
"""
import asyncio
import os
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db import Database
from core.stream_interceptor import StreamInterceptor

HARD_LIMITS = {"exact_us": 50.0, "cosine_ms": 1.0}


async def main() -> int:
    await Database.init()
    si = StreamInterceptor()
    await si.load_cache()
    print(f"templates={len(si.template_cache)} vectors={len(si._tag_vectors)}")

    # Tier 1 exact
    line = "She squeezed the trigger. [HIT: RAILGUN_KINETIC] The squad advanced."
    n = 5000
    t0 = time.perf_counter()
    for _ in range(n):
        si.expand_line(line)
    exact_us = (time.perf_counter() - t0) / n * 1e6
    print(f"TIER1_EXACT: {exact_us:.1f} µs/line (limit < {HARD_LIMITS['exact_us']})")

    # Pure in-memory cosine (no embed)
    import numpy as np
    fake = np.zeros(768); fake[0] = 1.0
    n = 1000
    t0 = time.perf_counter()
    for _ in range(n):
        si._best_cosine(fake)
    cosine_ms = (time.perf_counter() - t0) / n * 1000
    print(f"COSINE: {cosine_ms:.4f} ms/query (limit < {HARD_LIMITS['cosine_ms']})")

    # Semantic path (embed + match) — informational, may cold-load
    t0 = time.perf_counter()
    hit = await si._semantic_swap("plasma bolt scorched the hull")
    sem_ms = (time.perf_counter() - t0) * 1000
    print(f"SEMANTIC_PATH: {sem_ms:.0f} ms/call hit={bool(hit)} (informational)")

    await Database.close()

    ok = exact_us < HARD_LIMITS["exact_us"] and cosine_ms < HARD_LIMITS["cosine_ms"]
    print(f"\n{'✅ PASS — interceptor performance within limits' if ok else '❌ FAIL — regression detected'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
