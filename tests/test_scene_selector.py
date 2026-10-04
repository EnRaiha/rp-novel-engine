#!/usr/bin/env python3
"""The scene selector, on a fabricated vault so no real novel is touched.

Two of these are regressions for bugs found by running it: the branch file carried the regular
expression instead of the heading, and a dry-run rewrite without `--from` raised instead of
reporting.
"""
from __future__ import annotations

import argparse
import json
import pathlib

import pytest

from scripts import scene_selector as sel

NOVEL = """# A Novel

Front matter, before any scene. Not a scene.

## First Scene

Satu dua tiga empat lima.

## Second Scene

Enam tujuh lapan.

### A deeper heading

Not a scene at this level.
"""


@pytest.fixture
def vault(tmp_path, monkeypatch):
    """A vault with one novel and a backup folder, all inside tmp_path."""
    root = tmp_path / "adventures"
    (root / "novel" / "demo").mkdir(parents=True)
    path = root / "novel" / "demo" / "demo.md"
    path.write_text(NOVEL, encoding="utf-8")
    payload = tmp_path / "payload.md"
    payload.write_text("Ganti sepenuhnya.", encoding="utf-8")

    monkeypatch.setattr(sel, "VAULT", tmp_path)
    monkeypatch.setattr(sel, "NOVEL_ROOTS", (root,))
    monkeypatch.setattr(sel, "BACKUP_DIR", tmp_path / "backups")
    return {"root": root, "path": path, "payload": payload, "tmp": tmp_path}


def _ns(**kw):
    base = {"level": 2, "novel": "demo", "scene": None, "all": False, "json": False,
            "from_file": None, "dry_run": False, "name": None, "out": None, "force": False}
    base.update(kw)
    return argparse.Namespace(**base)


# ── reading ──────────────────────────────────────────────────────────────────

def test_scenes_split_on_the_level_heading(vault):
    rows = sel.scenes(vault["path"])

    assert [r["title"] for r in rows] == ["First Scene", "Second Scene"]


def test_a_scene_body_stops_at_the_next_heading(vault):
    rows = {r["title"]: r["body"] for r in sel.scenes(vault["path"])}

    assert "Satu dua tiga" in rows["First Scene"]
    assert "Enam tujuh" not in rows["First Scene"]
    assert "A deeper heading" in rows["Second Scene"], "a level-3 heading is inside the scene"


def test_the_preamble_is_not_a_scene(vault):
    body = sel.preamble(vault["path"])

    assert "Front matter" in body
    assert "First Scene" not in body


def test_words_are_counted_per_scene(vault):
    """A deeper heading's prose belongs to the scene it sits inside, so Second Scene counts it."""
    rows = {r["title"]: r["words"] for r in sel.scenes(vault["path"])}

    assert rows["First Scene"] == 5
    assert rows["Second Scene"] == 12, "the level-3 block is inside the level-2 scene"


def test_a_level_override_changes_what_counts_as_a_scene(vault):
    rows = sel.scenes(vault["path"], level=3)

    assert [r["title"] for r in rows] == ["A deeper heading"]


# ── finding ──────────────────────────────────────────────────────────────────

def test_a_novel_is_found_by_stem_or_by_file_name(vault):
    assert sel.find_novel("demo") == vault["path"]
    assert sel.find_novel("demo.md") == vault["path"]


def test_an_unknown_novel_finds_nothing(vault):
    assert sel.find_novel("nope") is None


def test_a_scene_search_returns_every_match(vault):
    """Returning one would let a repeated title rewrite the wrong scene."""
    rows = sel.scenes(vault["path"])
    assert sel.find_scene(vault["path"], "Scene") == rows
    assert len(sel.find_scene(vault["path"], "Scene")) == 2


def test_a_scene_search_is_case_insensitive(vault):
    assert len(sel.find_scene(vault["path"], "first scene")) == 1


# ── archiving ────────────────────────────────────────────────────────────────

def test_archiving_copies_the_file_and_writes_a_note(vault):
    saved = sel.archive(vault["path"], "a reason")

    assert saved.read_text(encoding="utf-8") == NOVEL
    assert saved.with_suffix(".note").read_text(encoding="utf-8").strip() == "a reason"


def test_archiving_twice_keeps_both(monkeypatch, vault):
    first = sel.archive(vault["path"], "one")

    class Later:
        pass

    # A second call in the same second would collide; the stamp carries the second, so force one.
    monkeypatch.setattr(sel, "datetime", type("D", (), {
        "now": staticmethod(lambda tz=None: type("N", (), {"strftime": lambda self, f: "29990101T000000Z"})())}))
    second = sel.archive(vault["path"], "two")

    assert first != second
    assert first.exists() and second.exists()


# ── branching ────────────────────────────────────────────────────────────────

def test_branch_writes_the_scene_with_a_real_heading(vault, capsys):
    """Regression: the first version wrote `heading(level).pattern` into the file, so the branch
    began with the regular expression instead of `## First Scene`."""
    code = sel.cmd_branch(_ns(scene="First Scene", name="alt"))

    assert code == 0
    written = next((vault["tmp"] / "adventures" / "branches").glob("alt-*.md"))
    text = written.read_text(encoding="utf-8")
    assert "## First Scene" in text
    assert "(?P<title>" not in text, "the branch file carries the pattern instead of the heading"
    assert "Satu dua tiga" in text


def test_branch_refuses_to_overwrite_without_force(vault):
    target = vault["tmp"] / "out.md"
    target.write_text("existing", encoding="utf-8")

    assert sel.cmd_branch(_ns(scene="First Scene", out=str(target))) == 1
    assert target.read_text(encoding="utf-8") == "existing"


def test_branch_archives_the_novel_it_read_from(vault, capsys):
    sel.cmd_branch(_ns(scene="First Scene", name="alt"))

    assert list((vault["tmp"] / "backups").glob("*.md")), "branching did not archive the source"


def test_branch_refuses_when_a_title_matches_twice(vault):
    assert sel.cmd_branch(_ns(scene="Scene", name="alt")) == 1


# ── rewriting ────────────────────────────────────────────────────────────────

def test_a_dry_run_rewrite_without_from_reports_instead_of_raising(vault, capsys):
    """Regression: `replacement` is None when --from is absent, and the first version built the
    new text before checking, so the dry run raised AttributeError."""
    assert sel.cmd_rewrite(_ns(scene="First Scene", dry_run=True)) == 0
    assert "would rewrite" in capsys.readouterr().out, "a dry run that says nothing is not a dry run"


def test_a_dry_run_writes_nothing(vault):
    sel.cmd_rewrite(_ns(scene="First Scene", dry_run=True, from_file=str(vault["payload"])))

    assert vault["path"].read_text(encoding="utf-8") == NOVEL


def test_a_rewrite_needs_a_replacement(vault):
    assert sel.cmd_rewrite(_ns(scene="First Scene")) == 1
    assert vault["path"].read_text(encoding="utf-8") == NOVEL


def test_a_rewrite_replaces_the_scene_and_keeps_the_rest(vault):
    code = sel.cmd_rewrite(_ns(scene="First Scene", from_file=str(vault["payload"])))

    assert code == 0
    text = vault["path"].read_text(encoding="utf-8")
    assert "## First Scene" in text, "the heading must survive the rewrite"
    assert "Ganti sepenuhnya." in text
    assert "Satu dua tiga" not in text
    assert "## Second Scene" in text and "Enam tujuh lapan." in text
    assert "Front matter" in text, "the preamble must survive"


def test_a_rewrite_archives_before_it_writes(vault):
    sel.cmd_rewrite(_ns(scene="First Scene", from_file=str(vault["payload"])))

    saved = list((vault["tmp"] / "backups").glob("*.md"))
    assert len(saved) == 1
    assert saved[0].read_text(encoding="utf-8") == NOVEL, "the archive is not the original"


# ── listing ──────────────────────────────────────────────────────────────────

def test_list_reports_every_novel_and_its_scenes(vault, capsys):
    assert sel.cmd_list(_ns()) == 0
    out = capsys.readouterr().out

    assert "demo.md" in out
    assert "First Scene" in out and "Second Scene" in out
    assert "2 scene(s) across 1 file(s)" in out
