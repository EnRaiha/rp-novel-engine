#!/usr/bin/env python3
"""Seed the pre-letter state for TKG Arc I, once, with the tick stopped.

Why this exists
---------------
Session 5 (`TKG — Arc I: The Sunrise`) is meant to resume at the state before `Tiga surat`
(turn 75 of `maya_rag.dsh_turns`, label `tkg-play`). The engine does not hold that state: it holds
a shell written into by the test suite and by the tick, and on 2026-10-03 the tick opened a
`fuel_zero` collapse against it (`Dead in the Water`, story_arcs 117) because the resources row
carries fuel 0 and population 0 against a story with 29,600 people in three settlements.

So the state has to be set once, deliberately, and only while nothing else is writing.

Two rules this script will not break
------------------------------------
1. **It refuses to guess a number.** `--population` has a documented default (29,600, from the
   record's beat 14). `--credits`, `--fuel` and `--alloys` have NO default: the record does not
   state them, and an invented treasury is exactly how the collapse above happened. Pass them.
2. **It refuses to run while the tick can write.** It requires GM MAYA maintenance to be armed,
   because the tick honours it (`scripts/orchestrator.py`) and the retry path makes a lost race
   expensive. Use `--force` only if you have stopped the tick another way.

It deletes nothing. The row it replaces is copied to the archive directory first, and the rows it
marks are marked, not removed.

Usage
-----
    python3 scripts/seed_preletter_state.py --dry-run
    python3 scripts/seed_preletter_state.py --credits N --fuel N --alloys N --apply

Verify afterwards with the read-back the script prints.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from core.db import Database  # noqa: E402

SESSION = 5

#: Documented in the record, section C beat 14: Garden 16,200 + Bukit Kaca 5,400 + Pesisir Panjang
#: 5,600 + orbit 2,400. It sums, and it is what the story says on the day before the letter.
#: The record also flags it as possibly an estimate, which is why it is a default and not a fact.
POPULATION_FROM_RECORD = 29600

ARCHIVE = pathlib.Path.home() / "backups/rp-state/preletter"

#: Rows this engine wrote while testing, not while playing. Marked, never deleted.
POLLUTION_EVENT_TYPES = ("resources:add",)


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--population", type=int, default=POPULATION_FROM_RECORD,
                    help=f"default {POPULATION_FROM_RECORD}, from the record's beat 14")
    ap.add_argument("--credits", type=int, required=True, help="no default: the record does not state it")
    ap.add_argument("--fuel", type=int, required=True, help="no default: the record does not state it")
    ap.add_argument("--alloys", type=int, default=None,
                    help="optional. alloys is NOT a collapse condition, so the script leaves it alone \
unless you pass it")
    ap.add_argument("--apply", action="store_true", help="write. Without it, nothing changes")
    ap.add_argument("--dry-run", action="store_true", help="print what would change and stop")
    ap.add_argument("--force", action="store_true",
                    help="run even when maintenance is not armed; only if the tick is stopped by other means")
    a = ap.parse_args()

    await Database.init()
    try:
        from core import maintenance
        if not maintenance.active() and not a.force:
            print("REFUSED: GM MAYA maintenance is not armed, so the tick may write under this.")
            print("         Arm it first:  python3 scripts/gm_maint.py arm --ttl 3600 <phrase>")
            print("         Or, if the tick is stopped another way:  --force")
            return 2

        now = await Database.fetchrow(
            "SELECT credits, alloys, fuel, population, aggregate_morale, crew_pool"
            " FROM maya_rp.resources WHERE session_id=$1", SESSION)
        if now is None:
            print(f"REFUSED: session {SESSION} has no resources row. Nothing to correct.")
            return 2

        # Only the columns given are touched. credits, fuel and population are the three collapse
        # conditions this row fails today; alloys is not one, so leaving it alone is better than
        # requiring a number the record does not state for a column nothing checks.
        target = {"credits": a.credits, "fuel": a.fuel, "population": a.population}
        if a.alloys is not None:
            target["alloys"] = a.alloys

        print(f"\nSESSION {SESSION} — resources")
        print(f"{'column':14} {'now':>14} {'after':>14}")
        for col, want in target.items():
            mark = "" if now[col] == want else "   <- changes"
            print(f"{col:14} {now[col]!s:>14} {want!s:>14}{mark}")

        events = await Database.fetchval(
            "SELECT count(*) FROM maya_rp.events WHERE session_id=$1 AND event_type = ANY($2::text[])",
            SESSION, list(POLLUTION_EVENT_TYPES))
        arcs = await Database.fetchval(
            "SELECT count(*) FROM maya_rp.story_arcs WHERE session_id=$1 AND started_at::date = CURRENT_DATE",
            SESSION)
        print(f"\nrows this engine wrote while testing, to be MARKED not deleted:")
        print(f"  events, event_type in {POLLUTION_EVENT_TYPES}: {events}")
        print(f"  story_arcs created today:                          {arcs}")

        if a.dry_run or not a.apply:
            print("\nDRY RUN. Nothing changed. Re-run with --apply to write.")
            return 0

        ARCHIVE.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = ARCHIVE / f"session{SESSION}-resources-{stamp}.json"
        backup.write_text(json.dumps({
            "taken_at": stamp,
            "why": "pre-letter seed; the row this engine left behind after test and tick writes",
            "row": {k: (str(v) if v is not None else None) for k, v in dict(now).items()},
            "target": target,
        }, indent=2))
        size = backup.stat().st_size
        if size < 40:
            print(f"STOPPED: the archive at {backup} is {size} bytes. Refusing to write over a bad backup.")
            return 1
        print(f"\narchived the current row -> {backup} ({size} bytes)")

        # Column names come from the fixed dict above, never from argv, so the f-string cannot carry an
        # injected identifier; the values are bound.
        assignments = ", ".join(f"{col}=${i + 1}" for i, col in enumerate(target))
        await Database.execute(
            f"UPDATE maya_rp.resources SET {assignments} WHERE session_id=${len(target) + 1}",
            *target.values(), SESSION)

        read_back = await Database.fetchrow(
            "SELECT credits, alloys, fuel, population FROM maya_rp.resources WHERE session_id=$1", SESSION)
        print("read back:", {k: read_back[k] for k in ("credits", "alloys", "fuel", "population")})
        drifted = {k: read_back[k] for k, v in target.items() if read_back[k] != v}
        if drifted:
            print(f"NOT CLEAN: {drifted} did not take. Something is writing to this row.")
            return 1

        # MARK, never delete. The events carry tags already (["bus","resources:add"]), so the mark is one
        # more tag on the same array; the arcs have no CHECK constraint on status, so the mark is a status
        # value that says what it is rather than a deletion. Arc 117 is closed by this: the collapse it
        # records came from fuel 0 on a row this engine left wrong, not from the story.
        marked = await Database.execute(
            # jsonb_build_array rather than a quoted literal: no nested quotes to escape, and the tag
            # is a parameter the driver binds instead of a string this file has to get right twice.
            "UPDATE maya_rp.events SET tags = tags || jsonb_build_array($3::text)"
            " WHERE session_id=$1 AND event_type = ANY($2::text[])"
            " AND NOT (tags @> jsonb_build_array($3::text))",
            SESSION, list(POLLUTION_EVENT_TYPES), "noncanon:test-write")
        closed = await Database.execute(
            "UPDATE maya_rp.story_arcs SET status='noncanon:engine-write'"
            " WHERE session_id=$1 AND started_at::date = CURRENT_DATE"
            " AND status <> 'noncanon:engine-write'", SESSION)
        print(f"marked {marked} event rows and {closed} arc rows as non-canon (nothing deleted)")

        live = await Database.fetchval(
            "SELECT count(*) FROM maya_rp.story_arcs WHERE session_id=$1 AND status='active'", SESSION)
        print(f"active arcs left for session {SESSION}: {live}")

        from modules.collapse import check_for_collapse
        state = await check_for_collapse(SESSION, dry_run=True)
        print("check_for_collapse(dry_run) ->", "stable" if state is None else state.get("title"))
        if state is not None:
            print(f"STILL COLLAPSING on {state.get('type')}. That condition is not fixed by this seed.")
            return 1
        print("\nSEEDED. The pre-letter state is set and no collapse condition fires.")
        return 0
    finally:
        await Database.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
