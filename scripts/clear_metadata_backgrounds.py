#!/usr/bin/env python3
"""REFUSES TO RUN. The string it was written to clear is a marker something depends on.

WHY THIS SCRIPT EXISTS AND WHY IT DOES NOT WORK.

Session 5's characters carry one of two things in `background`:

    Arc I: The Descent (The Sunrise) — dikompil dari play record, sesi 5     63 rows
    Description taken from the novel's cast ledger line on 2026-10-02 ...    (the same rows)

    Rika Voss rose through the ranks of the TKG fleet to command the
    Nusantara, then took the largest assignment of her career...            377 rows

The first looked like session metadata sitting in a content column, and on 2026-10-04 it was cleared to
NULL, with the values archived to `~/backups/rp-state/backgrounds/`. The full suite then failed two tests
in `tests/test_manifest_freshness.py`, and the reason is `scripts/face_manifest.py:106`:

    ARC1_PREFIX = "Arc I: The Descent (The Sunrise)"
    ...
    if str(row["background"] or "").startswith(ARC1_PREFIX):
        return "arc1-cast"

It is the ONLY signal that tiers a character `arc1-cast`. Clearing it reclassified 63 characters across 19
keys each — 1,197 manifest rows moved from `arc1-cast` to `import` or `other` — and drifted the committed
`manifest.json` and `MANIFEST.md` by 35,238 lines. The values were restored from the archive, both
artifacts were rebuilt, and the diff went back to the `generated_at` line alone.

SO THE STRING IS LOAD-BEARING AND THE COLUMN IS OVERLOADED. `background` means "this character's history"
for 377 rows and "this character came from Arc I" for 63, and nothing distinguishes them except which
value happens to be in the column. A real background cannot be told from a marker by reading it.

THE JOB THAT SHOULD COME FIRST: a column for the tier, so a background can be a background. That is a
migration plus a change to `tier_of` in the generator, and it is not a data cleanup. Until it exists, this
script refuses and exits 3.

    python3 scripts/clear_metadata_backgrounds.py --session 5
    → exits 3 with the reason, and writes nothing
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Restated rather than imported, so the guard cannot be disarmed by changing the generator.
ARC1_PREFIX = "Arc I: The Descent (The Sunrise)"

REASON = (
    "refusing to run: the value this script clears is a tier marker, not stray metadata.\n"
    "  scripts/face_manifest.py:106\n"
    "      if str(row['background'] or '').startswith(ARC1_PREFIX): return 'arc1-cast'\n"
    "Clearing it reclassified 63 characters across 1,197 manifest rows on 2026-10-04 and drifted\n"
    "manifest.json and MANIFEST.md by 35,238 lines. The values were restored from\n"
    "~/backups/rp-state/backgrounds/ and both artifacts rebuilt.\n"
    "\n"
    "The fix is a column for the tier so background can be a background: a migration plus a change\n"
    "to tier_of in scripts/face_manifest.py. Until that exists, this writes nothing on purpose."
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refuses: the metadata it targets is a marker face_manifest.py depends on.")
    parser.add_argument("--session", type=int, default=5)
    parser.add_argument("--apply", action="store_true", help="still refuses; the guard is not optional")
    args = parser.parse_args()

    print(f"session {args.session}: {REASON}")
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
