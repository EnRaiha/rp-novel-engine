#!/usr/bin/env python3
"""novel_revelation — the two measures, held still.

Pure functions over compiled markdown, so these need no database and no session.
"""
from __future__ import annotations

from pathlib import Path

from scripts.novel_revelation import reach_back, report, scenes, words

NOVEL = """# TKG — Arc I

Prose before any heading is not a scene.

## Pertama

Dia datang dari Limbah dahulu, dan bertahun dia menunggu.

## Kedua

Kapal itu berlepas.
"""


def test_prose_before_the_first_heading_is_not_a_scene():
    found = scenes(NOVEL)

    assert [title for title, _ in found] == ["Pertama", "Kedua"]


def test_a_scene_body_stops_at_the_next_heading():
    found = dict(scenes(NOVEL))

    assert "bertahun" in found["Pertama"]
    assert "berlepas" not in found["Pertama"], "a scene must not swallow the next one"
    assert "berlepas" in found["Kedua"]


def test_words_counts_words_not_punctuation():
    assert words("Kapal itu berlepas.") == 3
    assert words("") == 0


def test_reach_back_counts_each_marker():
    assert reach_back("Dia datang dari Limbah dahulu") == 1
    assert reach_back("bertahun dia menunggu, dahulu, sebelum itu") == 3
    assert reach_back("Kapal itu berlepas") == 0


def test_report_names_the_largest_scene_and_its_share(tmp_path: Path):
    path = tmp_path / "n.md"
    path.write_text(NOVEL, encoding="utf-8")

    result = report(path)

    assert result["scenes"] == 2
    assert result["largest"]["scene"] == "Pertama"
    assert 0 < result["largest_share"] < 1


def test_a_scene_too_short_to_judge_is_not_named_densest(tmp_path: Path):
    """Reach-back per 1,000 words is unstable on a scene of a few words, so the
    densest list skips them rather than reporting a rate built on nothing."""
    path = tmp_path / "n.md"
    path.write_text("## Tiny\n\ndahulu\n\n## Long\n\n" + ("kapal " * 400) + "\n", encoding="utf-8")

    result = report(path)

    assert [row["scene"] for row in result["densest_reach_back"]] == ["Long"]
