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

ONE WATERMARK FILE PER SESSION AND LABEL. A turn id is global in `dsh_turns`, so a shared cursor makes
one session skip the turns another has already passed. The files sit beside `WATERMARK`:
`rp-turn-watcher.<session>.<label>.json`. The old shared file belongs to session 5 and `tkg-play`, the
CLI defaults, and that key reads it until its own file exists. The old file is never modified.

A CORRUPT WATERMARK REFUSES THE PASS. A missing file starts at 0. A file that cannot be read, or that
holds no non-negative integer `last_id`, raises `WatermarkCorrupt`: the pass logs it, exits 3 and
processes nothing, because starting at 0 replays the whole history through the tracker. Restore the
file, or run `--reset` to start at 0 on purpose.

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
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.db import Database  # noqa: E402
from core.log import error, info, warn  # noqa: E402
from core.session import _atomic_write  # noqa: E402

WATERMARK = Path.home() / ".cache" / "rp-turn-watcher.json"
DEFAULT_LABEL = "tkg-play"
# The shared file at `WATERMARK` was written with the CLI defaults: session 5, label `tkg-play`.
LEGACY_SESSION = 5

# The last freeze message reported, so a 60-second poll states a frozen campaign once.
_FREEZE_NOTICE = ""


class WatermarkCorrupt(RuntimeError):
    """A watermark file exists and holds no usable cursor. The pass must not start at 0."""


def watermark_path(session_id: int, label: str = DEFAULT_LABEL) -> Path:
    """The file that holds the cursor of one session and label.

    @param session_id - engine session id.
    @param label - `dsh_turns.session_id` value being read. It is percent-encoded, so no two labels share a file.
    @returns the path; the file may not exist.
    """
    return WATERMARK.with_name(
        f"{WATERMARK.stem}.{int(session_id)}.{quote(label, safe='')}{WATERMARK.suffix}")


def _source(session_id: int, label: str) -> Path | None:
    """The file to read the cursor from: its own, else the shared file for the session it belonged to."""
    own = watermark_path(session_id, label)
    if own.exists():
        return own
    if (session_id, label) == (LEGACY_SESSION, DEFAULT_LABEL) and WATERMARK.exists():
        return WATERMARK
    return None


def read_watermark(session_id: int, label: str = DEFAULT_LABEL) -> dict:
    """The last turn id processed for one session and label, or a fresh state when no file exists.

    @param session_id - engine session id.
    @param label - `dsh_turns.session_id` value being read.
    @returns state with `last_id`, `processed` and `updated_at`.
    @raises WatermarkCorrupt when a file exists and is unreadable, not a JSON object, or holds no
        non-negative integer `last_id`. Nothing is guessed: a guess of 0 replays every turn.
    """
    path = _source(session_id, label)
    if path is None:
        return {"last_id": 0, "processed": 0, "updated_at": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001 - any read or parse error is the same refusal
        raise WatermarkCorrupt(f"watermark {path} is unreadable ({type(e).__name__}: {e})") from e
    last_id = data.get("last_id") if isinstance(data, dict) else None
    if isinstance(last_id, bool) or not isinstance(last_id, int) or last_id < 0:
        raise WatermarkCorrupt(f"watermark {path} holds no non-negative integer last_id: {data!r:.200}")
    return data


def write_watermark(state: dict, session_id: int, label: str = DEFAULT_LABEL) -> None:
    """Store the cursor of one session and label through a temp file, so a crash leaves the old one."""
    path = watermark_path(session_id, label)
    path.parent.mkdir(parents=True, exist_ok=True)
    state = {**state, "session": int(session_id), "label": label,
             "updated_at": datetime.now(timezone.utc).isoformat()}
    _atomic_write(path, json.dumps(state, indent=1))


async def new_turns(label: str, after: int, limit: int) -> list[dict]:
    """Turns past the watermark, oldest first. `id` is bigint and monotonic, so it is the cursor."""
    return [dict(r) for r in await Database.fetch(
        "SELECT id, role, text_content, created_at FROM maya_rag.dsh_turns"
        " WHERE session_id=$1 AND id > $2 ORDER BY id LIMIT $3",
        label, after, limit)]


def _session_is_writable(session_id: int) -> bool:
    """Whether this watcher may write into `session_id`, reported once per state change.

    THE FREEZE DOOR WAS OPEN HERE AND THIS CLOSES IT. The watcher calls `scene_tracker` and `terms`
    directly, so it never passed `core/session.py` and never met `is_frozen`. Installed 2026-10-04,
    the freeze landed 2026-10-05 11:16, and the service kept running: the last write was 10:32 that
    morning, 44 minutes before, which is the only reason no frozen row was written. Turn 233 would
    have.

    A frozen campaign is read-only reference, so a pass over one writes nothing and says so once
    rather than every 60 seconds. The poll keeps running, so unfreezing resumes it without a restart.
    `is_frozen` is fail-closed: an unreadable list raises, and this treats that as not writable.
    """
    global _FREEZE_NOTICE
    from core.ooc import _maintenance_active
    from core.session import is_frozen

    try:
        frozen = is_frozen(session_id) and not _maintenance_active()
    except Exception as e:  # noqa: BLE001 - an unreadable freeze list must not fail open
        if _FREEZE_NOTICE != f"unreadable:{e}":
            _FREEZE_NOTICE = f"unreadable:{e}"
            warn("turn-watcher", f"the frozen list cannot be read ({e}); writing nothing")
        return False

    if frozen:
        if _FREEZE_NOTICE != "frozen":
            _FREEZE_NOTICE = "frozen"
            info("turn-watcher",
                 f"session {session_id} is frozen reference; the watcher writes nothing until it is"
                 " removed from frozen_sessions")
        return False

    if _FREEZE_NOTICE:
        _FREEZE_NOTICE = ""
        info("turn-watcher", f"session {session_id} is writable again; resuming")
    return True


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
    if apply and not _session_is_writable(session_id):
        return 0
    try:
        state = read_watermark(session_id, label)
    except WatermarkCorrupt as e:
        error("turn-watcher", f"{e}. Processing nothing.")
        print(f"  {e}")
        print(f"  restore it, or run --reset --session {session_id} --label {label} to start at 0")
        return 3
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
            write_watermark(state, session_id, label)

    state["processed"] = state.get("processed", 0) + processed
    if apply:
        write_watermark(state, session_id, label)
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
    parser.add_argument("--status", action="store_true",
                        help="print the watermark of --session and --label, then exit")
    parser.add_argument("--reset", action="store_true",
                        help="set the watermark of --session and --label to 0")
    parser.add_argument("--once", action="store_true", help="one pass (the default)")
    args = parser.parse_args()

    if args.status:
        try:
            print(json.dumps(read_watermark(args.session, args.label), indent=1))
        except WatermarkCorrupt as e:
            print(str(e))
            return 3
        print(f"watermark file: {_source(args.session, args.label) or watermark_path(args.session, args.label)}")
        return 0
    if args.reset:
        write_watermark({"last_id": 0, "processed": 0}, args.session, args.label)
        print(f"watermark for session {args.session}, label {args.label}, reset to 0")
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
