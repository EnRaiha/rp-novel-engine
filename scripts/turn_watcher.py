#!/usr/bin/env python3
"""turn_watcher — read new turns, track what they declare, write no prose.

The King's instruction: "Ia perlu bekerja di process system dan hanya monitor, inject dan track."
Three jobs, and this is the first two. Injection is `core/context.py`, which now carries a `[TERMS]`
block fed by what this records, and reaches the GM through the bridge's context mirror.

    monitor  read `maya_rag.dsh_turns` for rows past a watermark
    track    run `core.scene_tracker.consume` for the `[SCENE]` line and `core.terms.record` for the
             obligation markers, then keep the watermark

THE TABLE MIXES TWO KINDS OF ROW AND THAT IS FINE. Every row has `role='assistant'` — 224 of them —
and the newest are a GM narrative turn at id 228 beside agent status messages at 227 and 226 ("Siap.
Arc II disalin, dan ingest jalan dengan bukti."). No filter is needed, because a status message
carries no `[SCENE]` line and no obligation marker, so both extractors return nothing and the pass
writes nothing. Self-filtering beats a heuristic that could drop a turn.

THE WATERMARK MOVES ONLY PAST A TURN THAT WAS PROCESSED, and a turn that raises stops the pass and is
reported. Advancing past it would lose it silently; retrying it forever would hide that it is stuck.
`--skip-failed` is how an operator says "I have seen this one, move on".

AND IT EXITS 3 WHEN SOMETHING FAILED, so `systemctl status` and the journal show it. Nothing it does
reaches back into the engine: a failure here cannot stop a turn, and the context block it feeds is
already written to report and return empty rather than raise.

    python3 scripts/turn_watcher.py --once                    # one pass, dry run
    python3 scripts/turn_watcher.py --once --apply            # one pass, writing
    python3 scripts/turn_watcher.py --watch --apply           # poll until stopped
    python3 scripts/turn_watcher.py --status                  # where the watermark stands
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import Config  # noqa: E402
from core.db import Database  # noqa: E402
from core.log import error, info, warn  # noqa: E402

WATERMARK = Path.home() / ".cache" / "rp-turn-watcher.json"
DEFAULT_LABEL = "tkg-play"


def read_watermark() -> dict:
    """The last turn id processed, or a fresh one. A corrupt file is reported, not fatal."""
    try:
        data = json.loads(WATERMARK.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("last_id"), int):
            return data
    except FileNotFoundError:
        pass
    except Exception as e:  # noqa: BLE001 - a bad watermark must not stop the watcher
        warn("turn-watcher", f"watermark unreadable ({e}); starting from the beginning")
    return {"last_id": 0, "processed": 0, "updated_at": None}


def write_watermark(state: dict) -> None:
    WATERMARK.parent.mkdir(parents=True, exist_ok=True)
    state = {**state, "updated_at": datetime.now(timezone.utc).isoformat()}
    tmp = WATERMARK.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1), encoding="utf-8")
    tmp.replace(WATERMARK)


async def new_turns(label: str, after: int, limit: int) -> list[dict]:
    """Turns past the watermark, oldest first. `id` is bigint and monotonic, so it is the cursor."""
    return [dict(r) for r in await Database.fetch(
        "SELECT id, role, text_content, created_at FROM maya_rag.dsh_turns"
        " WHERE session_id=$1 AND id > $2 ORDER BY id LIMIT $3",
        label, after, limit)]


async def process_one(session_id: int, turn: dict, *, write: bool) -> dict:
    """Track what one turn declares. Returns what was found, whether or not it was written."""
    from core import scene_tracker, terms

    text = turn.get("text_content") or ""
    scene = await scene_tracker.consume(session_id, text, write=write)
    obligations = await terms.record(session_id, turn_id=turn["id"], text=text) if write \
        else {"found": len(terms.extract(text)), "written": 0, "already": 0}
    return {
        "turn": turn["id"],
        "chars": len(text),
        "scene_declared": scene.get("declared") is not None,
        "scene_corrections": len(scene.get("corrections") or []),
        "scene_moved": scene.get("moved") is not None,
        "terms_found": obligations.get("found", 0),
        "terms_written": obligations.get("written", 0),
    }


async def once(*, session_id: int, label: str, apply: bool, limit: int,
               skip_failed: bool) -> int:
    """One pass. Returns the exit code: 0 always ran, 3 something could not be processed."""
    state = read_watermark()
    start = state["last_id"]
    turns = await new_turns(label, start, limit)
    if not turns:
        info("turn-watcher", f"no turns past id {start} in {label}")
        return 0

    processed, moved, terms_written = 0, 0, 0
    for turn in turns:
        try:
            result = await process_one(session_id, turn, write=apply)
        except Exception as e:  # noqa: BLE001 - reported; the pass stops so the id is not skipped
            error("turn-watcher", f"turn {turn['id']} could not be processed: {e}")
            if not skip_failed:
                print(f"  turn {turn['id']} FAILED: {e}")
                print(f"  watermark stays at {state['last_id']}; --skip-failed advances past it")
                return 3
            warn("turn-watcher", f"turn {turn['id']} skipped on request")
            state["last_id"] = turn["id"]
            continue
        processed += 1
        moved += 1 if result["scene_moved"] else 0
        terms_written += result["terms_written"]
        info("turn-watcher",
             f"turn {turn['id']}: {result['chars']} chars · scene "
             f"{'declared' if result['scene_declared'] else 'none'} · "
             f"{result['terms_found']} term(s) found, {result['terms_written']} new")
        state["last_id"] = turn["id"]
        if apply:
            write_watermark(state)

    state["processed"] = state.get("processed", 0) + processed
    if apply:
        write_watermark(state)
    what = "wrote" if apply else "would write"
    print(f"  {processed} turn(s) past id {start} · scene moved {moved} · {what} {terms_written} term(s)")
    if not apply:
        print("  dry run: nothing written, watermark unmoved")
    return 0


async def watch(*, session_id: int, label: str, apply: bool, limit: int, seconds: int) -> int:
    """Poll until stopped. Each pass is independent, so one bad turn cannot wedge the loop."""
    info("turn-watcher", f"watching {label} every {seconds}s; session {session_id}")
    while True:
        try:
            await once(session_id=session_id, label=label, apply=apply, limit=limit,
                       skip_failed=False)
        except Exception as e:  # noqa: BLE001 - a pass must never end the loop
            error("turn-watcher", f"pass failed: {e}")
        await asyncio.sleep(seconds)


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read new turns and track what they declare. Writes no prose.")
    parser.add_argument("--session", type=int, default=5, help="engine session id")
    parser.add_argument("--label", default=DEFAULT_LABEL, help="dsh_turns.session_id to read")
    parser.add_argument("--apply", action="store_true", help="write; the default is a dry run")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--skip-failed", action="store_true",
                        help="advance past a turn that raised, instead of stopping")
    parser.add_argument("--watch", action="store_true", help="poll until stopped")
    parser.add_argument("--seconds", type=int, default=60, help="poll interval with --watch")
    parser.add_argument("--status", action="store_true", help="print the watermark and exit")
    parser.add_argument("--reset", action="store_true", help="set the watermark back to 0")
    parser.add_argument("--once", action="store_true", help="one pass (the default)")
    args = parser.parse_args()

    if args.status:
        print(json.dumps(read_watermark(), indent=1))
        print(f"watermark file: {WATERMARK}")
        return 0
    if args.reset:
        write_watermark({"last_id": 0, "processed": 0})
        print("watermark reset to 0")
        return 0

    await Database.init()
    try:
        if args.watch:
            return await watch(session_id=args.session, label=args.label, apply=args.apply,
                               limit=args.limit, seconds=args.seconds)
        return await once(session_id=args.session, label=args.label, apply=args.apply,
                          limit=args.limit, skip_failed=args.skip_failed)
    finally:
        await Database.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
