#!/usr/bin/env python3
"""
narration_sync.py — reconciliation between NARRATION day and ENGINE day.

Narration is the master clock: when a story time-skip moves the narrative to day N,
the ENGINE must be rolled forward to match. Ships, babies, builds, and economy all
land on the SAME clock — no more silent siap.

Usage:
  python3 scripts/narration_sync.py <target_day> [--dry-run] [--no-builds] [--no-collapse] [--no-preg]

Flow:
  1. Read current engine sessions.game_day
  2. delta = target_day - engine_day (must be >= 0)
  3. Checkpoint before any mutation (safety)
  4. Run roll100 for `delta` days (economy + builds + pregnancies + collapse in one pass)
  5. Verify: engine day == target day; report ships/babies/builds that silently completed
"""
from __future__ import annotations
import os
import asyncio, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import Config
from core.db import Database


SID = Config.SESSION_ID


async def main() -> None:
    argv = sys.argv[1:]
    dry = "--dry-run" in argv
    try:
        target = int(next(a for a in argv if a.isdigit()))
    except StopIteration:
        print("Usage: narration_sync.py <target_day> [--dry-run] [--no-builds] [--no-collapse] [--no-preg]")
        return

    await Database.init()
    cur = await Database.fetchval("SELECT game_day FROM maya_rp.sessions WHERE id=$1", SID) or 1
    delta = target - cur

    print(f"NARRATION SYNC  ({'DRY RUN' if dry else 'LIVE'})")
    print(f"  engine day : {cur}")
    print(f"  narrative  : {target}")
    print(f"  delta      : {delta} days {'(already synced)' if delta <= 0 else ''}")

    if delta <= 0:
        print("No forward drift — engine already at/after narrative day.")
        await Database.close()
        return

    # Safety: checkpoint BEFORE any mutation (non-dry)
    if not dry:
        from core.state import StateManager  # type: ignore
        try:
            fp = await StateManager.save_checkpoint(SID, f"pre-narration-sync-day-{target}")
            print(f"  checkpoint : {fp}")
        except Exception as e:
            print(f"  checkpoint FAILED ({e}) — aborting, no mutation done")
            await Database.close()
            return

    # Delegate the actual roll to roll100.main() — single source of truth for skips
    from scripts.roll100 import main as roll100_main
    # Construct argv to re-run roll100 with the delta, preserving flags
    roll_argv = [sys.argv[0], str(delta)]
    for flag in ("--dry-run", "--no-builds", "--no-collapse", "--no-sarang", "--no-preg", "--rates"):
        if flag in argv:
            i = argv.index(flag)
            roll_argv.append(flag)
            if flag == "--rates" and i + 1 < len(argv):
                roll_argv.append(argv[i + 1])
    sys.argv = roll_argv
    await roll100_main()

    # Verify
    new_day = await Database.fetchval("SELECT game_day FROM maya_rp.sessions WHERE id=$1", SID) or 1
    print(f"\nVERIFY: engine day {cur} → {new_day} (target {target})  {'✅ SYNCED' if new_day == target else f'⚠️ off by {target - new_day}'}")
    await Database.close()


if __name__ == "__main__":
    asyncio.run(main())