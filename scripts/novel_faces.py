#!/usr/bin/env python3
"""Illustrated edition of the novel: one portrait line per scene, from the manifest.

The manuscript is the record and stays untouched. This script produces a **derived**
edition that carries the faces, rebuilt on demand like the manifest itself:

    python3 scripts/novel_faces.py --stats
    python3 scripts/novel_faces.py

Rules, all deterministic:

- A scene is a line starting with `## `.
- A character claims a scene through the id form the novel already uses on first
  mention, `**Name (id NNN)**`. The tag is the contract; prose name matching is not
  attempted here, because the portrait plugin owns that job.
- One `neutral` portrait per character per scene, capped at `--cap` per scene so a
  crowd scene does not become a gallery.
- A character with no ready file is counted and reported, never silently dropped.

Nothing is generated and nothing is invented: a portrait that does not exist on disk
produces no image line.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from collections import Counter

VAULT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_NOVEL = VAULT / "adventures/tkg-arc1-restart/novel/the-sunrise.md"
DEFAULT_MANIFEST = VAULT / "adventures/tkg-arc1-restart/prototype/faces/manifest.json"
DEFAULT_OUT = VAULT / "adventures/tkg-arc1-restart/novel/the-sunrise-illustrated.md"
NEUTRAL = "neutral"
ID_TAG = re.compile(r"\(id (\d+)\)")
EMOTION_KIND = "emotion"


def load_manifest(path: pathlib.Path) -> dict[int, dict[str, str]]:
    """Read the JSON manifest into {character id: {key: relative path}} for ready files.

    @param path - the manifest produced by `face_manifest.py --format json`.
    @returns a mapping of character id to the keys that have a file on disk.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload["rows"] if isinstance(payload, dict) else payload
    ready: dict[int, dict[str, str]] = {}
    for row in rows:
        if row.get("kind") != EMOTION_KIND or row.get("status") != "ready":
            continue
        character = int(row["id"])
        ready.setdefault(character, {})[str(row["key"])] = str(row["path"])
    return ready


def scenes(text: str) -> list[tuple[str, list[str]]]:
    """Split the novel into scenes.

    @param text - the manuscript.
    @returns a list of (heading, body lines) for every `## ` section.
    """
    found: list[tuple[str, list[str]]] = []
    heading: str | None = None
    body: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if heading is not None:
                found.append((heading, body))
            heading = line[3:].strip()
            body = []
            continue
        if heading is not None:
            body.append(line)
    if heading is not None:
        found.append((heading, body))
    return found


def scene_faces(body: list[str], ready: dict[int, dict[str, str]], cap: int) -> tuple[list[tuple[int, str]], list[int]]:
    """Pick the faces for one scene.

    @param body - the scene's lines.
    @param ready - the manifest mapping.
    @param cap - the most faces a scene may carry.
    @returns (chosen [(id, path)], missing [ids]) in first-mention order.
    """
    order: list[int] = []
    for line in body:
        for match in ID_TAG.finditer(line):
            character = int(match.group(1))
            if character not in order:
                order.append(character)
    illustrated: list[tuple[int, str]] = []
    missing: list[int] = []
    for character in order:
        path = ready.get(character, {}).get(NEUTRAL)
        if path is None:
            missing.append(character)
            continue
        if len(illustrated) < cap:
            illustrated.append((character, path))
    return illustrated, missing


def render(novel: pathlib.Path, manifest: pathlib.Path, out: pathlib.Path, cap: int, stats_only: bool) -> int:
    text = novel.read_text(encoding="utf-8")
    ready = load_manifest(manifest)
    found = scenes(text)
    lines_out: list[str] = []
    scene_count = 0
    illustrated_scenes = 0
    face_count = 0
    missing_count = 0
    missing_chars: Counter[int] = Counter()

    for heading, body in found:
        scene_count += 1
        illustrated, missing = scene_faces(body, ready, cap)
        lines_out.append(f"## {heading}")
        if illustrated:
            illustrated_scenes += 1
            face_count += len(illustrated)
            names = ", ".join(f"id {character}" for character, _ in illustrated)
            lines_out.append("")
            for character, path in illustrated:
                lines_out.append(f"![id {character}](<{path}>)")
            lines_out.append("")
            lines_out.append(f"*Wajah scene ini: {names}.*")
        if missing:
            missing_count += len(missing)
            missing_chars.update(missing)
        lines_out.extend(body)

    print(f"scenes {scene_count} · illustrated {illustrated_scenes} · faces {face_count} · "
          f"characters without a neutral file {len(missing_chars)} ({missing_count} scene mentions)")
    if missing_chars:
        top = ", ".join(str(character) for character, _ in missing_chars.most_common(8))
        print(f"most often missing: {top}")
    if stats_only:
        return 0

    out.write_text("\n".join(lines_out), encoding="utf-8")
    print(f"wrote {out.relative_to(VAULT)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--novel", type=pathlib.Path, default=DEFAULT_NOVEL)
    parser.add_argument("--manifest", type=pathlib.Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    parser.add_argument("--cap", type=int, default=4)
    parser.add_argument("--stats", action="store_true")
    args = parser.parse_args()
    return render(args.novel, args.manifest, args.out, args.cap, args.stats)


if __name__ == "__main__":
    sys.exit(main())
