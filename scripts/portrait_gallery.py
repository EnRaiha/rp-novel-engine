#!/usr/bin/env python3
"""Write the readable gallery of every face that exists.

The chat shows a portrait when a turn names someone, which means a face is only ever seen by accident
of prose. This writes a sheet the King can open and read top to bottom: who has a face, which
emotions, and where the file sits. Nothing here is new data; it is the manifest, laid out for eyes.

    python3 scripts/portrait_gallery.py            # writes the sheet
    python3 scripts/portrait_gallery.py --check    # reports whether it is current
"""
from __future__ import annotations

import argparse
import json
import pathlib

VAULT = pathlib.Path(__file__).resolve().parents[2]
MANIFEST = VAULT / "adventures/tkg-arc1-restart/prototype/faces/manifest.json"
OUT = VAULT / "adventures/tkg/character-sheets/portrait-gallery.md"
PATH_PREFIX = "adventures/tkg/characters/"

#: Why a group has no face. A gap with a stated reason is a decision; a gap without one is an
#: oversight, and the difference matters when this sheet is read as a work list.
NO_FACE_REASON = {
    "arc1-cast": "the manuscript gives them no body text, so only the author can fill the basis",
    "import": "imported characters, out of scope under the faces-only ruling",
    "prisoner": "sealed by design: no portrait until the seal opens",
    "other": "no appearance basis recorded",
}
RELATIVE = "../characters/"


def collect() -> tuple[list[dict], list[dict], list[dict]]:
    """Who has a face, and who does not.

    @returns (wives, others, missing), the first two sorted by name with {name, id, faces}, and the
        third every character the manifest carries with no frame ready, as {name, id, tier, gaps}.
    """
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    faces: dict[int, dict] = {}
    for row in payload["rows"]:
        if row.get("kind") != "emotion" or row.get("status") != "ready" or not row.get("path"):
            continue
        path = str(row["path"])
        if not path.startswith(PATH_PREFIX):
            continue
        entry = faces.setdefault(int(row["id"]), {
            "id": int(row["id"]), "name": str(row["name"]), "wife": False, "faces": {},
        })
        entry["faces"][str(row["key"])] = path[len(PATH_PREFIX):]
        # The manifest already resolves the wife tier (it reads the confirmed-wife marker on the
        # session-5 row and falls back to the name join), so the sheet reads that verdict instead of
        # repeating the rule here.
        if row.get("tier") == "wife":
            entry["wife"] = True
    missing: dict[int, dict] = {}
    for row in payload["rows"]:
        if row.get("kind") != "emotion":
            continue
        if int(row["id"]) in faces:
            continue
        entry = missing.setdefault(int(row["id"]), {
            "id": int(row["id"]), "name": str(row["name"]), "tier": str(row.get("tier") or "other"),
            "gaps": 0,
        })
        if row.get("status") != "ready":
            entry["gaps"] += 1
    ordered = sorted(faces.values(), key=lambda row: row["name"])
    return ([row for row in ordered if row["wife"]],
            [row for row in ordered if not row["wife"]],
            sorted(missing.values(), key=lambda row: (row["tier"], row["name"])))


def render() -> str:
    wives, others, missing = collect()
    lines = [
        "# Portrait gallery",
        "",
        f"*Every face that exists, {len(wives) + len(others)} characters. Written by",
        "`rp-engine-py/scripts/portrait_gallery.py` from the face manifest. Do not edit by hand.*",
        "",
        "A character appears here when at least one frame is rendered. The chat attaches a face when a",
        "turn names the character, so this sheet is the only place to see them all at once.",
        "",
    ]
    for title, group in (("Confirmed wives", wives), ("Other characters with a face", others)):
        if not group:
            continue
        lines += [f"## {title} ({len(group)})", ""]
        for row in group:
            ordered = sorted(row["faces"], key=lambda key: (key != "neutral", key))
            lines.append(f"### {row['name']} (id {row['id']})")
            lines.append("")
            lines.append(f"{len(ordered)} frame(s): {', '.join(ordered)}")
            lines.append("")
            for key in ordered:
                lines.append(f"![{row['name']} — {key}]({RELATIVE}{row['faces'][key]})")
            lines.append("")
    if missing:
        by_tier: dict[str, list[dict]] = {}
        for row in missing:
            by_tier.setdefault(row["tier"], []).append(row)
        lines += [f"## Characters without a face ({len(missing)})", "",
                  "These are the gaps. A character moves out of this section when one frame is",
                  "rendered, and the tier says who they are to the story.", ""]
        for tier in sorted(by_tier):
            group = by_tier[tier]
            reason = NO_FACE_REASON.get(tier, "no reason recorded")
            lines.append(f"**{tier}** ({len(group)}), {reason}: "
                         + ", ".join(f"{row['name']} (id {row['id']})" for row in group[:40])
                         + (" …" if len(group) > 40 else ""))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    body = render()
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.is_file() else ""
        same = current == body
        print(f"portrait-gallery.md {'is current' if same else 'is stale'} ({len(body)} bytes)")
        return 0 if same else 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(body, encoding="utf-8")
    wives, others, missing = collect()
    print(f"wrote {OUT} ({len(wives)} wives, {len(others)} others with a face, "
          f"{len(missing)} without, {len(body)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
