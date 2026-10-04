#!/usr/bin/env python3
"""A guard, not a cleanup: the Arc I marker in `background` is load-bearing.

On 2026-10-04 the marker was cleared as stray metadata. `scripts/face_manifest.py:106` reads it as the
only signal for the `arc1-cast` tier, so 63 characters were reclassified across 1,197 manifest rows and
the committed artifacts drifted by 35,238 lines. `tests/test_manifest_freshness.py` caught it. The values
were restored and the script now refuses to run.

These tests hold both halves: that the marker still decides the tier, and that nothing clears it. If a
tier column is ever added, the first test is the one that will fail, and it will say that the cleanup
became safe.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.face_manifest import ARC1_PREFIX, tier_of

ROOT = Path(__file__).resolve().parents[1]
CLEANUP = ROOT / "scripts" / "clear_metadata_backgrounds.py"

MARKER = f"{ARC1_PREFIX} — dikompil dari play record, sesi 5\nDescription taken from the novel's line."
PROSE = "Rika Voss rose through the ranks of the TKG fleet to command the Nusantara."


def _row(**over):
    row = {"id": 999999, "name": "Nobody At All", "traits": [], "background": None}
    row.update(over)
    return row


def test_the_marker_still_decides_the_arc1_cast_tier():
    """The pin. Clearing this value reclassifies the character, which is why the cleanup refuses."""
    assert tier_of(_row(background=MARKER), set()) == "arc1-cast"


def test_a_prose_background_does_not_earn_the_tier():
    assert tier_of(_row(background=PROSE), set()) == "other"


def test_an_absent_background_does_not_earn_the_tier():
    assert tier_of(_row(background=None), set()) == "other"


def test_clearing_the_marker_would_change_the_tier():
    """The demonstration the guard exists for, in one test rather than 35,238 diff lines."""
    with_marker = tier_of(_row(background=MARKER), set())
    without = tier_of(_row(background=None), set())

    assert with_marker == "arc1-cast"
    assert without == "other"
    assert with_marker != without, "if these ever match, the marker stopped mattering"


def test_a_wife_trait_still_wins_over_the_marker():
    """`tier_of` is first-match-wins, so the marker only decides for characters nothing else claims."""
    assert tier_of(_row(background=MARKER, traits=["confirmed-wife"]), set()) == "wife"


@pytest.mark.parametrize("flag", [[], ["--apply"]])
def test_the_cleanup_refuses_and_writes_nothing(flag):
    result = subprocess.run([sys.executable, str(CLEANUP), "--session", "5", *flag],
                            capture_output=True, text=True, cwd=str(ROOT), timeout=60)

    assert result.returncode == 3, result.stdout + result.stderr
    assert "tier marker" in result.stdout
    assert "face_manifest.py:106" in result.stdout


def test_the_refusal_names_where_the_marker_is_read():
    """A refusal that does not say why is an obstacle rather than a guard."""
    result = subprocess.run([sys.executable, str(CLEANUP), "--session", "5"],
                            capture_output=True, text=True, cwd=str(ROOT), timeout=60)

    assert "arc1-cast" in result.stdout
    assert "backups/rp-state/backgrounds" in result.stdout
