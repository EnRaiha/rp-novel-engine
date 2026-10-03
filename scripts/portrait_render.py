#!/usr/bin/env python3
"""Render queued character assets through ComfyUI (the portrait render queue).

Picks `maya_rp.character_assets` rows with `status='pending'`, renders each
through `~/scripts/maya-generate` (ComfyUI on the local GPU), writes the PNG to
the character's `emotions/<key>.png`, and records the result. A failure marks
the row `failed` with the error text — the prompt is never lost.

Usage:
    python3 scripts/portrait_render.py --session 3 [--limit N] [--dry-run] [--steps 14]
"""
from __future__ import annotations

import argparse
import asyncio
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import Config  # noqa: E402
from core.db import Database  # noqa: E402
from core import portraits  # noqa: E402
from core.log import info, warn  # noqa: E402

GENERATOR = Path.home() / "scripts" / "maya-generate"
MODEL = "Deliberate_v2.safetensors"

#: Composition for a render that is queued from the command line. The queued row already carries the
#: framing the prompt was built from; this only sets the default for a fresh queue.
DEFAULT_FRAMING = portraits.DEFAULT_FRAMING


async def render_one(asset: dict, *, steps: int, dry_run: bool) -> bool:
    """Render one queued asset; returns True when the row is now ready."""
    name = asset["name"]
    emotion = portraits.OCCASIONS.get(asset["occasion"], (asset["occasion"], ()))[0]
    target = portraits.emotion_path(name, emotion)
    # The dry-run check sits before anything touches the disk. It used to sit after stage_version and
    # mkdir, both of which write: `--dry-run` created emotions/versions/ and copied the current image into
    # it, so a flag whose whole purpose is to change nothing changed two things. The version number is a
    # product of the write, so the dry run prints the live target instead.
    if dry_run:
        print(f"DRY  {name} [{asset['occasion']}] -> {target}")
        print(f"     prompt: {asset['prompt'][:160]}…")
        return False
    version, version_file = portraits.stage_version(name, emotion)
    target.parent.mkdir(parents=True, exist_ok=True)
    # The negative prompt lives in the ComfyUI workflow's node 7; the CLI takes
    # the positive text only.
    prompt = asset["prompt"] or ""
    # The latent size comes from the framing this row was queued with, so the picture and the row
    # cannot disagree about what was rendered.
    framing = asset.get("framing") or DEFAULT_FRAMING
    frame = portraits.FRAMING.get(framing, portraits.FRAMING[DEFAULT_FRAMING])
    size = f"{frame['width']}x{frame['height']}"
    # One rule, one place. This used to recompute what `core/portraits.py` already computes, which is
    # the second copy of a rule and the reason a row could describe a semi prompt beside a photoreal
    # negative: the script and the queue built the same negative independently and disagreed.
    negative = portraits.negative_for(framing)
    result = subprocess.run(
        [sys.executable, str(GENERATOR), prompt, "-o", str(version_file), "--steps", str(steps),
         "--size", size, "--negative", negative],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not version_file.is_file():
        error = (result.stderr or result.stdout or "render failed").strip().splitlines()[-1:]
        recorded = await portraits.mark_failed(asset["id"], error[0] if error else "render failed",
                                               session_id=asset["session_id"])
        if not recorded:
            warn("portraits", f"asset {asset['id']} is not session {asset['session_id']};"
                              " the failure was not recorded")
        info("portraits", f"render failed for {name}/{asset['occasion']}: {error}")
        return False
    # The engine reads the live emotion image; the versioned file is the history.
    shutil.copyfile(version_file, target)
    portraits.set_live_version(name, emotion, version)
    recorded = await portraits.mark_ready(
        asset["id"], str(target), session_id=asset["session_id"], model=MODEL, seed=None,
        width=frame["width"], height=frame["height"],
    )
    if not recorded:
        # The image is on disk, but the row was not this session's to write. Report that rather
        # than counting a render the queue will not see.
        warn("portraits", f"asset {asset['id']} is not session {asset['session_id']};"
                          " the render was not recorded")
        return False
    info("portraits", f"rendered {name}/{asset['occasion']} -> v{version} {version_file.name} (live: {target.name})")
    return True


async def main() -> int:
    parser = argparse.ArgumentParser(description="Render queued character assets")
    parser.add_argument("--session", type=int, default=Config.SESSION_ID)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--character", default=None,
                        help="only this character (full-spectrum waves for one person)")
    parser.add_argument("--occasion", default=None,
                        help="only this occasion key (with --character: one frame test)")
    parser.add_argument("--steps", type=int, default=14)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--order", default="id", choices=tuple(portraits.QUEUE_ORDERS),
                        help="queue order: id (default, oldest queued first), bond, or name")
    args = parser.parse_args()

    await Database.init()
    queue = await portraits.pending(args.session, args.limit, args.character, args.occasion,
                                    order=args.order)
    if not queue:
        print(f"queue empty for session {args.session}")
        await Database.close()
        return 0
    print(f"{len(queue)} queued render(s), session {args.session}")
    done = 0
    for asset in queue:
        if await render_one(asset, steps=args.steps, dry_run=args.dry_run):
            done += 1
    await Database.close()
    print(f"rendered {done}/{len(queue)}" + (" (dry run)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
