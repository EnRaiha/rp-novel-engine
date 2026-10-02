#!/usr/bin/env python3
"""What the portrait work would cost, in both orders, without rendering or queueing.

Two plans are on the table and the King has not picked one:

- **Wives first** (his standing order, D1): the 35 spouses of frozen session 3 have 575 ready
  frames, and the outstanding work is the emotions they are missing.
- **Arc I first** (recommended, because the live manuscript names 63 characters that have no
  face at all): neutral frames built from the `appearance` prose the novel already carries.

This script prints both, with the prompt each Arc I character would get, and writes nothing.

    python3 scripts/portrait_plan.py
    python3 scripts/portrait_plan.py --sample 3
"""
from __future__ import annotations

import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from core import portraits  # noqa: E402
from core.db import Database  # noqa: E402

EMOTION_KEYS = [key for key in portraits.EMOTIONS if key not in portraits.NO_HAIR_CLAUSE]
ARC1_RANGE = (2931, 2993)


async def wives_plan() -> None:
    """The wife order: what the 35 spouses are still missing."""
    rows = await Database.fetch(
        """SELECT c.id, c.name FROM maya_rp.characters c
           WHERE c.session_id = 3 AND COALESCE(c.is_spouse, false) ORDER BY c.id""")
    total_missing = 0
    fully_done = 0
    for row in rows:
        missing = [key for key in EMOTION_KEYS
                   if not portraits.emotion_path(row["name"], key, row["id"]).is_file()]
        total_missing += len(missing)
        if not missing:
            fully_done += 1
        print(f"  {row['name'][:30]:<30} ready {len(EMOTION_KEYS) - len(missing)}/{len(EMOTION_KEYS)}"
              + (f"  missing: {', '.join(missing[:4])}" if missing else "  complete"))
    print(f"wives {len(rows)} · complete {fully_done} · renders outstanding {total_missing}")


async def arc1_plan(sample: int) -> None:
    """The Arc I order: the cast the live manuscript actually names."""
    rows = await Database.fetch(
        """SELECT id, name, role, traits::text, appearance, description
           FROM maya_rp.characters
           WHERE session_id = 5 AND id BETWEEN $1 AND $2 ORDER BY id""",
        ARC1_RANGE[0], ARC1_RANGE[1])
    has_appearance = has_description = empty = 0
    prompts: list[tuple[str, str]] = []
    for row in rows:
        character = dict(row)
        if (row["appearance"] or "").strip():
            has_appearance += 1
        elif (row["description"] or "").strip():
            has_description += 1
        else:
            empty += 1
        if len(prompts) < sample:
            prompt = portraits.build_prompt(character, "neutral")
            prompts.append((row["name"], prompt))
    print(f"arc1 {len(rows)} characters · appearance {has_appearance} · description only "
          f"{has_description} · nothing {empty}")
    for name, prompt in prompts:
        print(f"  {name}: {len(prompt)} chars")
        print(f"    {prompt[:160]}...")
    renderable = has_appearance + has_description
    print(f"renderable now: {renderable} · need appearance written first: {empty}")
    if empty:
        print("  the empty ones would render as the same generic face, which is worse than no face")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=2)
    args = parser.parse_args()
    await Database.init()
    print("plan A: wives first (standing order D1)")
    await wives_plan()
    print()
    print("plan B: Arc I first (the manuscript has no faces without it)")
    await arc1_plan(args.sample)
    print()
    print("nothing rendered, nothing queued")
    return 0


if __name__ == "__main__":
    import asyncio

    sys.exit(asyncio.run(main()))
