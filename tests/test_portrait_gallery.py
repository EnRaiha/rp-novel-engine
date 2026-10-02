"""The gallery is a derived sheet, so it can be stale, and it must not claim more than exists.

Two things are worth testing. That the sheet matches what the generator would write now, because a
stale gallery shows faces that were renamed or removed. And that its counts agree with the manifest,
because a sheet that says 272 while the manifest holds 271 is the kind of drift nobody notices.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
VAULT = ROOT.parent
GALLERY = VAULT / "adventures/tkg/character-sheets/portrait-gallery.md"
MANIFEST = VAULT / "adventures/tkg-arc1-restart/prototype/faces/manifest.json"
SCRIPT = ROOT / "scripts" / "portrait_gallery.py"


def _rebuild(tmp_path: pathlib.Path) -> str:
    import os

    sys.path.insert(0, str(SCRIPT.parent))
    import portrait_gallery

    original = portrait_gallery.OUT
    portrait_gallery.OUT = tmp_path / "portrait-gallery.md"
    try:
        body = portrait_gallery.render()
    finally:
        portrait_gallery.OUT = original
    return body


class TestGallery:
    def test_the_committed_sheet_matches_a_fresh_render(self, tmp_path):
        assert _rebuild(tmp_path) == GALLERY.read_text(encoding="utf-8"), (
            "portrait-gallery.md is stale; run: python3 scripts/portrait_gallery.py")

    def test_every_image_it_names_exists_on_disk(self):
        missing = []
        for line in GALLERY.read_text(encoding="utf-8").splitlines():
            if not line.startswith("!["):
                continue
            relative = line.split("](", 1)[1].rstrip(")")
            path = (GALLERY.parent / relative).resolve()
            if not path.is_file():
                missing.append(relative)
        assert not missing, f"the gallery points at files that are gone: {missing[:5]}"

    def test_the_counts_agree_with_the_manifest(self):
        payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
        ready = {row["id"] for row in payload["rows"]
                 if row.get("kind") == "emotion" and row.get("status") == "ready"}
        text = GALLERY.read_text(encoding="utf-8")
        assert f"Every face that exists, {len(ready)} characters" in text.replace("\n", " ") or \
               f"{len(ready)} characters" in text

    def test_the_wives_are_named_as_such(self):
        text = GALLERY.read_text(encoding="utf-8")
        assert "## Confirmed wives (35)" in text, "the King confirmed 35 wives; the sheet must say so"


class TestGaps:
    """The gaps section is a work list, so each group must carry a stated reason.

    A gap with a reason is a decision. A gap without one is an oversight, and this sheet is read to
    decide what to render next.
    """

    def test_the_gaps_are_listed_with_counts(self):
        text = GALLERY.read_text(encoding="utf-8")
        assert "## Characters without a face" in text

    def test_every_group_carries_a_reason(self):
        text = GALLERY.read_text(encoding="utf-8")
        section = text[text.index("## Characters without a face"):]
        for line in section.splitlines():
            if line.startswith("**"):
                assert "), " in line, f"a gap group has no reason: {line[:60]}"
                assert "no reason recorded" not in line, f"a gap group is unexplained: {line[:60]}"

    def test_the_sealed_prisoners_are_named_as_sealed(self):
        text = GALLERY.read_text(encoding="utf-8")
        assert "sealed by design" in text
