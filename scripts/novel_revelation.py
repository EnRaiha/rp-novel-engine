#!/usr/bin/env python3
"""novel_revelation — how a compiled novel distributes what it reveals.

The craft rule is "drip-feed backstory across scenes". That is a claim about
distribution, so it can be measured rather than assumed: where the words sit, and
where the markers of looking backwards sit.

Two measures, and neither is a verdict:

  * **length** — words per scene, and the share the largest one holds. A scene
    holding an outsized share is a place where something was delivered at once.
  * **reach-back** — per scene, how often the prose refers to a time before the
    scene. A scene with a reach-back rate far above the others is where the past
    was handed over rather than shown.

Reads a compiled markdown novel. Writes nothing. Splits on `## ` headings, the
convention `scripts/compile_session_novel.py` produces.

    python3 scripts/novel_revelation.py adventures/tkg-arc1-restart/novel/the-sunrise.md
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# BM markers of reaching backwards. Deliberately short and literal: this counts
# what the prose says, and a longer list would start counting what it merely
# implies.
REACH_BACK = (
    "dahulu", "dulu", "sebelum", "masa lalu", "bertahun", "puluh tahun",
    "ketika dia masih", "waktu kecil", "asalnya", "pada mulanya", "pernah",
    "tahun lalu", "zaman", "sejarah",
)

SCENE = re.compile(r"^## +(.+)$", re.M)


def scenes(text: str) -> list[tuple[str, str]]:
    """Split on `## ` headings. Prose before the first heading is not a scene."""
    marks = [(m.start(), m.group(1).strip()) for m in SCENE.finditer(text)]
    out: list[tuple[str, str]] = []
    for index, (start, title) in enumerate(marks):
        end = marks[index + 1][0] if index + 1 < len(marks) else len(text)
        out.append((title, text[start:end]))
    return out


def words(body: str) -> int:
    return len(re.findall(r"[\w'’-]+", body, re.UNICODE))


def reach_back(body: str) -> int:
    low = body.lower()
    return sum(low.count(marker) for marker in REACH_BACK)


def report(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    rows = []
    for title, body in scenes(text):
        count = words(body)
        hits = reach_back(body)
        rows.append({
            "scene": title,
            "words": count,
            "reach_back": hits,
            "per_1k": round(hits * 1000 / count, 1) if count else 0.0,
        })
    total = sum(row["words"] for row in rows)
    largest = max(rows, key=lambda row: row["words"], default=None)
    reachy = sorted((row for row in rows if row["words"] >= 100),
                    key=lambda row: row["per_1k"], reverse=True)
    return {
        "file": str(path),
        "scenes": len(rows),
        "words": total,
        "rows": rows,
        "largest": largest,
        "largest_share": round(largest["words"] / total, 3) if largest and total else 0.0,
        "densest_reach_back": reachy[:3],
    }


def render(result: dict) -> str:
    lines = [f"{result['file']}", f"  {result['scenes']} scenes · {result['words']:,} words", ""]
    if result["largest"]:
        biggest = result["largest"]
        lines.append(f"  largest scene: {biggest['words']:,} words "
                     f"({result['largest_share'] * 100:.1f}% of the book) — {biggest['scene']}")
    lines.append("")
    lines.append(f"  {'words':>7} {'reach':>6} {'per 1k':>7}  scene")
    for row in sorted(result["rows"], key=lambda item: item["words"], reverse=True)[:12]:
        lines.append(f"  {row['words']:>7,} {row['reach_back']:>6} {row['per_1k']:>7.1f}  {row['scene'][:56]}")
    lines.append("")
    lines.append("  densest reach-back (scenes of 100 words or more):")
    for row in result["densest_reach_back"]:
        lines.append(f"    {row['per_1k']:>6.1f} per 1k — {row['scene'][:56]}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="How a compiled novel distributes what it reveals.")
    parser.add_argument("novel", type=Path, help="compiled markdown novel")
    args = parser.parse_args()
    if not args.novel.is_file():
        print(f"novel_revelation: no such file: {args.novel}", file=sys.stderr)
        return 2
    result = report(args.novel)
    if not result["scenes"]:
        print(f"novel_revelation: {args.novel} holds no `## ` scene headings", file=sys.stderr)
        return 1
    print(render(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
