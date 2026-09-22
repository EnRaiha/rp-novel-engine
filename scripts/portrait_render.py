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
from core.log import info  # noqa: E402

GENERATOR = Path.home() / "scripts" / "maya-generate"
MODEL = "Deliberate_v2.safetensors"


async def render_one(asset: dict, *, steps: int, dry_run: bool) -> bool:
    """Render one queued asset; returns True when the row is now ready."""
    name = asset["name"]
    emotion = portraits.OCCASIONS.get(asset["occasion"], (asset["occasion"], ()))[0]
    target = portraits.emotion_path(name, emotion)
    version, version_file = portraits.stage_version(name, emotion)
    target.parent.mkdir(parents=True, exist_ok=True)
    if dry_run:
        print(f"DRY  {name} [{asset['occasion']}] -> {version_file}")
        print(f"     prompt: {asset['prompt'][:160]}…")
        return False
    # The negative prompt lives in the ComfyUI workflow's node 7; the CLI takes
    # the positive text only.
    prompt = asset["prompt"] or ""
    result = subprocess.run(
        [sys.executable, str(GENERATOR), prompt, "-o", str(version_file), "--steps", str(steps)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not version_file.is_file():
        error = (result.stderr or result.stdout or "render failed").strip().splitlines()[-1:]
        await portraits.mark_failed(asset["id"], error[0] if error else "render failed")
        info("portraits", f"render failed for {name}/{asset['occasion']}: {error}")
        return False
    # The engine reads the live emotion image; the versioned file is the history.
    shutil.copyfile(version_file, target)
    portraits.set_live_version(name, emotion, version)
    await portraits.mark_ready(
        asset["id"], str(target), model=MODEL, seed=None, width=512, height=512
    )
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
    args = parser.parse_args()

    await Database.init()
    queue = await portraits.pending(args.session, args.limit, args.character, args.occasion)
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
