#!/usr/bin/env python3
"""seed_arc1_beats — the scripted beats of Arc I: The Descent.

The engine's milestones are per-session rows; a relived arc needs its own set or
the gates show empty. These are the novel's first-arc landmarks turned into
beats, tagged `general` so any persona sees them, and spread across the three
arc stages. They are **offers**: `required` stays false so the story may follow
the novel or diverge.

Idempotent: upserted by (session, name).

    python3 scripts/seed_arc1_beats.py --session 5 --dry-run
    python3 scripts/seed_arc1_beats.py --session 5
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.db import Database  # noqa: E402

# (name, trait, stage, required, rpp_reward, latch_ruleset)
BEATS: tuple[tuple[str, str, str, bool, int, str | None], ...] = (
    # ── lockdown — day one, nothing to his name ───────────────────────────────
    ("land-first-day", "general", "lockdown", False, 5, None),
    ("land-first-work", "general", "lockdown", False, 5, None),
    ("land-first-witness", "general", "lockdown", False, 8, None),
    ("land-first-name", "general", "lockdown", False, 5, None),
    # ── selective — a foothold, a name, a reason to stay ─────────────────────
    ("foot-first-hull", "general", "selective", False, 10, None),
    ("foot-first-ally", "general", "selective", False, 10, None),
    ("foot-first-ledger", "general", "selective", False, 10, None),
    ("foot-vessel-contained", "general", "selective", False, 12, None),
    # ── confrontation — the trust against someone he loves ───────────────────
    ("test-good-name", "general", "confrontation", False, 15, None),
    ("test-worship", "general", "confrontation", False, 15, None),
    ("test-the-rule", "general", "confrontation", False, 20, None),
)

# The King persona's register beats, carried over from the original arc.
PERSONA_BEATS: tuple[tuple[str, str, str, bool, int, str | None], ...] = (
    ("aloof-receive-without-answering", "aloof", "lockdown", False, 5, None),
    ("mentor-lay-the-burden", "mentor", "lockdown", False, 5, None),
    ("tyrant-pronounce-punishment", "tyrant", "lockdown", False, 5, None),
    ("general-order-the-withdrawal", "general", "lockdown", False, 5, None),
)


async def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Arc I beats for a session")
    parser.add_argument("--session", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--with-persona-beats", action="store_true",
                        help="also seed the King persona's register beats (aloof/mentor/tyrant)")
    args = parser.parse_args()

    await Database.init()
    session = await Database.fetchrow("SELECT id, name FROM maya_rp.sessions WHERE id=$1", args.session)
    if session is None:
        print(f"no session {args.session}")
        return 1
    print(f"session {args.session}: {session['name']}")
    if args.dry_run:
        for name, trait, stage, required, rpp, _ in BEATS:
            print(f"  would seed {name} [{stage}/{trait}] rpp {rpp} required={required}")
        await Database.close()
        return 0

    beats = BEATS + (PERSONA_BEATS if args.with_persona_beats else ())
    seeded = 0
    for name, trait, stage, required, rpp, latch in beats:
        await Database.execute(
            "INSERT INTO maya_rp.ooc_milestones"
            " (session_id, name, trait, stage, required, rpp_reward, latch_ruleset)"
            " VALUES ($1,$2,$3,$4,$5,$6,$7)"
            " ON CONFLICT (session_id, name) DO UPDATE SET"
            " stage=EXCLUDED.stage, trait=EXCLUDED.trait, rpp_reward=EXCLUDED.rpp_reward",
            args.session, name, trait, stage, required, rpp, latch)
        seeded += 1
    total = await Database.fetchval(
        "SELECT count(*) FROM maya_rp.ooc_milestones WHERE session_id=$1", args.session)
    print(f"seeded {seeded} beats for session {args.session} (total {total})")
    await Database.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
