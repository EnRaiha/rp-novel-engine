#!/usr/bin/env python3
"""compile_session_novel — compile one arc's played prose into a novel file.

The play record lives in `maya_rag.dsh_turns` (written by the maya-bridge turn
log, one row per user and assistant turn). Each narrated turn already carries a
`# TKG — <arc>` header and `## <scene>` sections, so compiling an arc is
selection, not generation: keep the scenes the King accepted, drop the drafts he
rejected and the accounting notes, and write them in order.

No compression, no rewrite. The lossless doctrine stands
(`adventures/tkg/novel/NOVEL-FORMAT-LOSSLESS.md`).

    python3 scripts/compile_session_novel.py --dry-run
    python3 scripts/compile_session_novel.py --out <path>

Defaults describe Arc I of the restart; override with flags for another arc.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import sys
from datetime import date

DEFAULT_SESSION_LABEL = "tkg-play"
DEFAULT_ARC = "Arc I: The Descent"
DEFAULT_TITLE = "The Sunrise"
DEFAULT_OUT = (
    pathlib.Path.home() / "Bumi-Hijau/adventures/tkg-arc1-restart/novel/the-sunrise.md"
)
# Turns the King rejected, or that are bookkeeping, not story. 32 to 35 are the
# draft chain for the door scene: he answered the three [REDO] rewrites with
# "why reused scene... wipe clean these scene", and the clean `## Pintu` that
# followed is the accepted version (turn 36). 43 and 44 are [KOREKSI] notes.
DEFAULT_DROP = "32,33,34,35,43,44"

# Sections the GM appended inside a prose turn: cast tables, lot lists, rolls,
# and engine ledgers. Housekeeping, never story.
HOUSEKEEPING = ("LEDGER", "DAFTAR", "ROL", "KIRAAN")

MARKERS = ("[REDO", "[KOREKSI", "REDO 2", "REDO 3")
PRIVATE = ("bersetubuh", "telanjang bulat", "bercinta", "intim dengannya")


def load_env_file() -> None:
    """Load PG scalars from ~/.env when the shell carried none."""
    if os.environ.get("OC_PG_HOST") or os.environ.get("POSTGRES_HOST"):
        return
    path = pathlib.Path.home() / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.removeprefix("export ").strip()
        if key.startswith(("OC_PG_", "POSTGRES_")) and key not in os.environ:
            os.environ[key] = value.strip().strip("'\"")


def connect():
    import psycopg2

    host = os.environ.get("OC_PG_HOST") or os.environ.get("POSTGRES_HOST")
    if not host:
        raise SystemExit("compile_session_novel: no OC_PG_HOST or POSTGRES_HOST to read")
    return psycopg2.connect(
        host=host,
        port=int(os.environ.get("OC_PG_PORT") or os.environ.get("POSTGRES_PORT") or 5432),
        user=os.environ.get("OC_PG_USER") or os.environ.get("POSTGRES_USER"),
        password=os.environ.get("OC_PG_PASS") or os.environ.get("POSTGRES_PASSWORD"),
        dbname=os.environ.get("OC_PG_DB") or os.environ.get("POSTGRES_DB") or "maya_memory",
    )


def body_of(text: str) -> str:
    """One turn's prose: everything from the first scene header down.

    The repeated `# TKG — <arc>` banner is dropped; the scene headers and the
    beat numbering the GM wrote are kept verbatim.
    """
    lines = text.strip().splitlines()
    for index, line in enumerate(lines):
        if line.startswith("## "):
            return "\n".join(lines[index:]).strip()
    return ""


def is_housekeeping(title: str) -> bool:
    """True for a GM bookkeeping section: cast table, lot list, roll, ledger."""
    head = title.strip().lstrip("#").strip().upper()
    return any(head.startswith(key) for key in HOUSEKEEPING)


def prose_only(body: str) -> tuple[str, list[str]]:
    """Drop the bookkeeping sections from one turn's prose.

    @param body - one turn, from its first `## ` header down.
    @returns the story sections joined, and the titles that were dropped.
    """
    sections: list[tuple[str, list[str]]] = []
    for line in body.splitlines():
        if line.startswith("## "):
            sections.append((line, []))
        elif sections:
            sections[-1][1].append(line)
        else:
            sections.append(("", [line]))
    kept, dropped = [], []
    for title, lines in sections:
        if title and is_housekeeping(title):
            dropped.append(title.strip())
            continue
        kept.append("\n".join([title, *lines]).strip() if title else "\n".join(lines).strip())
    return "\n\n".join(part for part in kept if part), dropped


def compile_novel(args) -> tuple[str, dict, list[tuple[int, str, int]]]:
    conn = connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, text_content FROM maya_rag.dsh_turns"
                " WHERE session_id=%s ORDER BY id",
                (args.session_label,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    drop = {int(item) for item in args.drop.split(",") if item.strip()}
    prefix = f"# TKG — {args.arc}"
    kept: list[tuple[int, str, int]] = []
    dropped_sections: list[str] = []
    skipped: list[int] = []
    for turn_id, text in rows:
        if not text.lstrip().startswith(prefix) or turn_id in drop:
            continue
        body = body_of(text)
        if not body:
            skipped.append(turn_id)
            continue
        prose, housekeeping = prose_only(body)
        dropped_sections.extend(housekeeping)
        if not prose:
            skipped.append(turn_id)
            continue
        kept.append((turn_id, prose, len(prose)))

    scenes = [line for _, body, _ in kept for line in body.splitlines() if line.startswith("## ")]
    header = [
        "---",
        "type: novel",
        "status: active",
        "doctrine: lossless",
        f"title: {args.title}",
        f"arc: TKG — {args.arc}",
        f"source: maya_rag.dsh_turns · {args.session_label} · {len(kept)} scenes, turns "
        f"{kept[0][0]}–{kept[-1][0]}",
        "editorial_drops: turns 32–35 (rejected draft chain of the door scene; the "
        "wipe-clean `Pintu` stands), 41 (cost table), 43–44 (`[KOREKSI]` notes)",
        "open_corrections: the scene `Verifikasi` still carries the pre-correction figures; "
        "the King's correction notes are turns 43–44, outside this compile",
        "open_edits: `Lima belas hari` titles two consecutive scenes (turns 25 and 28)",
        f"compiled: {date.today().isoformat()}",
        "author: Izzat (King) + Maya (GM)",
        "---",
        "",
        f"# {args.title.upper()}",
        f"## TKG — {args.arc}",
        "*Living document. Compiled from the play record as played: no compression, no rewrite.*",
        "*Housekeeping the GM appended inside a turn (cast ledgers, lot lists, rolls, cost "
        "tables) is not story and is left out.*",
        "",
        "---",
        "",
    ]
    document = "\n".join(header) + "\n\n".join(body for _, body, _ in kept) + "\n"
    report = {
        "turns": len(kept),
        "scenes": len(scenes),
        "chars": sum(size for _, _, size in kept),
        "opened": kept[0][0] if kept else None,
        "closed": kept[-1][0] if kept else None,
        "skipped_empty": skipped,
        "housekeeping": dropped_sections,
        "chapters": scenes,
    }
    return document, report, kept


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-label", default=DEFAULT_SESSION_LABEL)
    parser.add_argument("--arc", default=DEFAULT_ARC)
    parser.add_argument("--title", default=DEFAULT_TITLE)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--drop", default=DEFAULT_DROP)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="overwrite an existing novel")
    args = parser.parse_args()

    load_env_file()
    document, report, kept = compile_novel(args)

    print(f"turns kept      {report['turns']} ({report['opened']}..{report['closed']})")
    print(f"scenes          {report['scenes']}")
    print(f"chars           {report['chars']}")
    print(f"lines           {document.count(chr(10)) + 1}")
    if report["skipped_empty"]:
        print(f"skipped empty   {report['skipped_empty']}")
    if report["housekeeping"]:
        print(f"bookkeeping sections dropped ({len(report['housekeeping'])}):")
        for title in report["housekeeping"]:
            print(f"  {title}")
    print("scenes:")
    for scene in report["chapters"]:
        print(f"  {scene}")

    leaked = [
        (turn_id, marker)
        for turn_id, body, _ in kept
        for marker in MARKERS
        if marker in body
    ]
    if leaked:
        print(f"WARNING: draft markers survived: {leaked}")
    private = [(turn_id, word) for turn_id, body, _ in kept for word in PRIVATE if word in body.lower()]
    if private:
        print(f"WARNING: review for a private scene (house doors closed): {private}")

    if args.dry_run:
        print("\n--- first 40 lines ---")
        print("\n".join(document.splitlines()[:40]))
        return 0

    out = pathlib.Path(args.out).expanduser()
    if out.exists() and not args.force:
        print(f"refusing to overwrite {out} without --force")
        return 2
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(document, encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
