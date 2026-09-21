#!/usr/bin/env python3
"""
Sync the Free Chat Pack — refresh wiki/rp-dev/canon copies + regenerate
source-onefile.md so a fresh session (or GLM Turbo) sees current state.

Copies (canonical -> wiki/rp-dev/canon/):
  skill, rp-current-session, setting-bible, progression, book-06,
  galaxy-beauties, erotic-playbook
Then regenerates source-onefile.md (all Python in one md).
Full src/ mirror sync is rsync (see integration-guide) — run:
  rsync -a --exclude='__pycache__' --exclude='*.pyc' rp-engine-py/{core,modules,scripts,migrations,tests,PLAN.md,pyproject.toml} wiki/rp-dev/src/
"""
import asyncio
import os
import sys
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.log import info

VAULT = Path("/home/maya/Bumi-Hijau")
ENGINE = VAULT / "rp-engine-py"
CANON_SRC = VAULT / "adventures/tkg"
CANON_DST = VAULT / "wiki/rp-dev/canon"

COPIES = [
    # The rp-engine skill moved from maya-skills to the Hermes skill tree; the
    # maya-skills copy was removed, so point at the canonical file that exists.
    (Path("/home/maya/.hermes/skills/maya/rp-engine/SKILL.md"), "rp-engine-skill.md"),
    (VAULT / "main/rp-current-session.md", "rp-current-session.md"),
    (CANON_SRC / "setting-bible.md", "setting-bible.md"),
    (CANON_SRC / "progression.md", "progression.md"),
    (CANON_SRC / "novel/book-06-operation-firework.md", "book-06-operation-firework.md"),
    (CANON_SRC / "character-sheets/galaxy-beauties.md", "galaxy-beauties.md"),
    (CANON_SRC / "reference/erotic-playbook.md", "erotic-playbook.md"),
]


def sync_canon() -> int:
    n = 0
    for src, name in COPIES:
        if not src.exists():
            info("sync_pack", f"SKIP (missing): {src}")
            continue
        shutil.copy2(src, CANON_DST / name)
        n += 1
    info("sync_pack", f"Canon copies refreshed: {n}")
    return n


def regen_onefile() -> int:
    """Regenerate wiki/rp-dev/source-onefile.md from live engine source."""
    dirs = [ENGINE / "core", ENGINE / "modules", ENGINE / "scripts", ENGINE / "tests"]
    py_files = sorted(f for d in dirs for f in d.glob("*.py"))
    py_files += sorted(ENGINE.glob("migrations/seed_*.py"))

    total_lines = sum(len(f.read_text().splitlines()) for f in py_files)
    out = [
        "# RP Engine — Full Python Source (One File)",
        "",
        f"*Consolidated for free-model consumption (GLM Turbo / Kimi / others). "
        f"Generated 2026-08-03 from rp-engine-py. {len(py_files)} .py files · {total_lines} lines. "
        f"Live source stays canonical.*",
        "",
        "> [!tip] How to use with a free model",
        "> This file is ~850KB — too large for a single paste on most free tiers. "
        "Paste **core/ + the target module** for focused work, or use the section headers in the TOC.",
        "",
        "## TOC",
        "",
    ]
    for d in dirs:
        for f in sorted(d.glob("*.py")):
            out.append(f"- `{f.relative_to(ENGINE)}` — {len(f.read_text().splitlines())}L")
    out.append("")
    for f in py_files:
        rel = f.relative_to(ENGINE)
        out += ["---", "", f"## `{rel}`", "", "```python",
                f.read_text(), "```", ""]

    dst = VAULT / "wiki/rp-dev/source-onefile.md"
    dst.write_text("\n".join(out))
    info("sync_pack", f"source-onefile regenerated: {len(py_files)} files / {total_lines} lines")
    return len(py_files)


async def main() -> None:
    dry = "--dry-run" in sys.argv
    if dry:
        print("DRY RUN — would copy:", len(COPIES), "canon files + regenerate one-file")
        return
    n = sync_canon()
    m = regen_onefile()
    print(f"✅ Sync complete: {n} canon files copied · one-file regenerated ({m} files)")
    print("   Full src/ mirror: rsync (see integration-guide §2 or run the command in the docstring)")


if __name__ == "__main__":
    asyncio.run(main())
