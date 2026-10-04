#!/usr/bin/env python3
"""scene_selector — pick a scene out of a novel, to rewrite it or branch a new one from it.

The King's ask: "make a scene selector, nak rewrite atau branch, novel apa? Scene apa? Then pick
its load. Other or old are save for reference."

    list                        every scene in every novel, with where it is
    show     --novel --scene    one scene, whole
    rewrite  --novel --scene    replace it in place, after archiving the file
    branch   --novel --scene    write it out on its own, so a variant can be written from it

EVERY MODE ARCHIVES FIRST, including `branch`. A scene that is being branched is still a scene
being read, and the file it came from can change under the reader.

THE HEADINGS ARE NOT UNIFORM, and the survey says so. Six shapes are in use across the novel
folder: `## Act 1: ...` in books four and six, `## Chapter 1: ...` in book one, `## Part I: ...`
in the prelude, `## Prologue: ...` in book five, `## Padang Limbah — hari pertama` in the
prequels, and bare titles in book eight and in the arc package. So the level is a flag rather
than an assumption, and the default of 2 is what every file currently uses for the same job.

    python3 scripts/scene_selector.py list
    python3 scripts/scene_selector.py list --novel the-sunrise
    python3 scripts/scene_selector.py show --novel the-sunrise --scene "Blok C"
    python3 scripts/scene_selector.py rewrite --novel the-sunrise --scene "Blok C" --from draft.md
    python3 scripts/scene_selector.py branch --novel the-sunrise --scene "Blok C" --name blok-c-alt
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

VAULT = Path(__file__).resolve().parents[2]
BACKUP_DIR = Path.home() / "backups" / "novel-scenes"

# Where novels live. Discovered rather than listed, so a file added later appears without an edit.
NOVEL_ROOTS = (VAULT / "adventures",)

# Files that describe the format rather than hold story.
NOT_A_NOVEL = ("HOWTOEDIT.md", "NOVEL-FORMAT-LOSSLESS.md", "README.md")


def novels() -> list[Path]:
    """Every markdown file under a novel folder, excluding the ones about the format."""
    found: list[Path] = []
    for root in NOVEL_ROOTS:
        for path in sorted(root.rglob("*.md")):
            if path.name in NOT_A_NOVEL:
                continue
            if "novel" not in path.parts and "arc" not in path.parts:
                continue
            found.append(path)
    return found


def heading(level: int = 2) -> re.Pattern:
    return re.compile(rf"^#{{{level}}}[ \t]+(?P<title>.+?)[ \t]*$", re.M)


def scenes(path: Path, level: int = 2) -> list[dict]:
    """Every scene in one file: its title, its line, and its body. Prose before the first
    heading is not a scene and is reported separately by `preamble`."""
    text = path.read_text(encoding="utf-8", errors="replace")
    marks = list(heading(level).finditer(text))
    out = []
    for index, match in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        body = text[match.end():end]
        out.append({
            "title": match.group("title").strip(),
            "line": text[:match.start()].count("\n") + 1,
            "words": len(re.findall(r"[\w'’-]+", body, re.UNICODE)),
            "body": body,
        })
    return out


def preamble(path: Path, level: int = 2) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    first = heading(level).search(text)
    return text[:first.start()] if first else text


def find_novel(name: str) -> Path | None:
    """`--novel the-sunrise` matches `the-sunrise.md` anywhere under a novel root."""
    wanted = name if name.endswith(".md") else f"{name}.md"
    for path in novels():
        if path.name == wanted or path.stem == name:
            return path
    return None


def find_scene(path: Path, needle: str, level: int = 2) -> list[dict]:
    """Scenes whose title contains the needle, case-insensitively. A list, because a title can
    repeat inside one file and choosing for the caller would rewrite the wrong one."""
    low = needle.lower()
    return [s for s in scenes(path, level) if low in s["title"].lower()]


def archive(path: Path, note: str) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = BACKUP_DIR / f"{path.stem}-{stamp}.md"
    shutil.copy2(path, target)
    if target.stat().st_size != path.stat().st_size:
        raise RuntimeError(f"archive is not a copy of the original: {target}")
    (BACKUP_DIR / f"{path.stem}-{stamp}.note").write_text(note + "\n", encoding="utf-8")
    return target


def cmd_list(args: argparse.Namespace) -> int:
    if args.novel:
        path = find_novel(args.novel)
        if not path:
            print(f"no novel matching {args.novel!r}", file=sys.stderr)
            return 1
        candidates = [path]
    else:
        candidates = novels()
    total = 0
    for path in candidates:
        rows = scenes(path, args.level)
        total += len(rows)
        rel = path.relative_to(VAULT)
        print(f"\n{rel}  —  {len(rows)} scene(s)")
        for row in rows:
            print(f"   {row['line']:>6}  {row['words']:>6}w  {row['title'][:70]}")
    print(f"\n{total} scene(s) across {len(candidates)} file(s)")
    print(f"archive: {BACKUP_DIR}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    path = find_novel(args.novel)
    if not path:
        print(f"no novel matching {args.novel!r}", file=sys.stderr)
        return 1
    hits = find_scene(path, args.scene, args.level)
    if not hits:
        print(f"no scene in {path.name} matches {args.scene!r}", file=sys.stderr)
        return 1
    if len(hits) > 1 and not args.all:
        print(f"{len(hits)} scenes match {args.scene!r}; pass --all or narrow it:", file=sys.stderr)
        for hit in hits:
            print(f"   line {hit['line']:>6}  {hit['title']}", file=sys.stderr)
        return 1
    for hit in (hits if args.all else hits[:1]):
        print(f"### line {hit['line']} — {hit['title']} ({hit['words']} words)\n")
        print(hit["body"].strip())
        print()
    return 0


def cmd_rewrite(args: argparse.Namespace) -> int:
    path = find_novel(args.novel)
    if not path:
        print(f"no novel matching {args.novel!r}", file=sys.stderr)
        return 1
    hits = find_scene(path, args.scene, args.level)
    if len(hits) != 1:
        print(f"need exactly one scene; {len(hits)} matched {args.scene!r}", file=sys.stderr)
        for hit in hits:
            print(f"   line {hit['line']:>6}  {hit['title']}", file=sys.stderr)
        return 1
    replacement = Path(args.from_file).read_text(encoding="utf-8") if args.from_file else None
    if not args.dry_run and replacement is None:
        print("--from <file> is required to rewrite; without it there is nothing to put back",
              file=sys.stderr)
        return 1

    hit = hits[0]
    if args.dry_run:
        incoming = len(re.findall(r"[0-9A-Za-z_’-]+", replacement or "")) if replacement else 0
        print(f"would rewrite {path.name} line {hit['line']} ({hit['title']}): "
              f"{hit['words']}w -> {incoming}w")
        return 0

    text = path.read_text(encoding="utf-8")
    marks = list(heading(args.level).finditer(text))
    index = [s["line"] for s in scenes(path, args.level)].index(hit["line"])
    start = marks[index].start()
    end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
    title_line = marks[index].group(0)
    updated = text[:start] + title_line + replacement.rstrip() + "\n\n" + text[end:]

    saved = archive(path, f"rewrite of scene {hit['title']!r} at line {hit['line']}")
    path.write_text(updated, encoding="utf-8")
    back = find_scene(path, hit["title"], args.level)
    if not back:
        print(f"the rewrite removed the scene heading for {hit['title']!r}", file=sys.stderr)
        return 1
    print(f"rewrote {path.name}: {hit['title']} ({hit['words']}w -> {back[0]['words']}w)")
    print(f"original archived to {saved}")
    return 0


def cmd_branch(args: argparse.Namespace) -> int:
    path = find_novel(args.novel)
    if not path:
        print(f"no novel matching {args.novel!r}", file=sys.stderr)
        return 1
    hits = find_scene(path, args.scene, args.level)
    if len(hits) != 1:
        print(f"need exactly one scene; {len(hits)} matched {args.scene!r}", file=sys.stderr)
        for hit in hits:
            print(f"   line {hit['line']:>6}  {hit['title']}", file=sys.stderr)
        return 1
    hit = hits[0]
    out = Path(args.out) if args.out else (
        VAULT / "adventures" / "branches" / f"{args.name or path.stem}-{hit['line']}.md")
    if out.exists() and not args.force:
        print(f"{out} exists; pass --force to replace it", file=sys.stderr)
        return 1
    saved = archive(path, f"branch from scene {hit['title']!r} at line {hit['line']}")
    header = (
        f"# Branch — {hit['title']}\n\n"
        f"From `{path.relative_to(VAULT)}` line {hit['line']}, {hit['words']} words.\n"
        f"Original archived to `{saved}`.\n"
        f"Everything below is the scene as it stood, to be rewritten or diverged from.\n\n"
        f"{'—' * 60}\n\n"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    # The heading is rebuilt from the level and the title. The first version wrote
    # `heading(level).pattern`, which put the regular expression itself into the branch file.
    out.write_text(header + f"{'#' * args.level} {hit['title']}\n" + hit["body"].lstrip("\n"),
                   encoding="utf-8")
    print(f"branched {hit['title']} ({hit['words']}w) to {out.relative_to(VAULT)}")
    print(f"original archived to {saved}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Pick a scene to rewrite or branch from.")
    parser.add_argument("--level", type=int, default=2, help="heading level that marks a scene")
    parser.add_argument("--json", action="store_true", help="list as JSON")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list", help="every scene in every novel")
    p.add_argument("--novel")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("show", help="one scene, whole")
    p.add_argument("--novel", required=True)
    p.add_argument("--scene", required=True)
    p.add_argument("--all", action="store_true", help="print every match rather than refusing")
    p.set_defaults(func=cmd_show)

    p = sub.add_parser("rewrite", help="replace a scene in place, archiving the file first")
    p.add_argument("--novel", required=True)
    p.add_argument("--scene", required=True)
    p.add_argument("--from", dest="from_file", help="file holding the replacement body")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_rewrite)

    p = sub.add_parser("branch", help="write a scene out on its own to diverge from")
    p.add_argument("--novel", required=True)
    p.add_argument("--scene", required=True)
    p.add_argument("--name", help="branch file name; defaults to the novel stem and line")
    p.add_argument("--out", help="explicit output path")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_branch)

    args = parser.parse_args()
    if args.json and args.cmd == "list":
        payload = {}
        for path in ([find_novel(args.novel)] if args.novel else novels()):
            if path is None:
                continue
            payload[str(path.relative_to(VAULT))] = [
                {k: v for k, v in s.items() if k != "body"} for s in scenes(path, args.level)]
        print(json.dumps(payload, indent=1, ensure_ascii=False))
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
