#!/usr/bin/env python3
"""galaxy_beauties_list — merge the 50-name catalog with the campaign database.

Reads `adventures/tkg/character-sheets/galaxy-beauties.md` (hidden catalog:
groups and entries) and cross-references every name with `maya_rp.characters`
(bond, stage, spouse flag, `beauty_standard`) plus rendered portraits, then
writes `wiki/rp-dev/GALAXY-BEAUTIES-LIST-<date>.md`.

    python3 scripts/galaxy_beauties_list.py [--out PATH]
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import Config  # noqa: E402
from core.db import Database  # noqa: E402

CATALOG = Path.home() / "Bumi-Hijau" / "adventures" / "tkg" / "character-sheets" / "galaxy-beauties.md"
DEFAULT_OUT = Path.home() / "Bumi-Hijau" / "wiki" / "rp-dev" / "GALAXY-BEAUTIES-LIST-2026-09-22.md"


def parse_catalog(path: Path) -> list[dict[str, str]]:
    """Groups and entries from the catalog markdown."""
    entries: list[dict[str, str]] = []
    group = ""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("## "):
            group = line[3:].strip()
        elif line.startswith("### "):
            body = line[4:].strip()
            match = re.match(r"(\d+)\.\s*([^—]+)(?:—\s*(.*))?$", body)
            if match:
                entries.append({
                    "number": match.group(1),
                    "name": match.group(2).strip(),
                    "title": (match.group(3) or "").strip(),
                    "group": group,
                })
    return entries


async def lookup(session: int, name: str) -> dict | None:
    """The character row for a catalog name, exact then prefix."""
    for pattern in (name, f"{name}%"):
        row = await Database.fetchrow(
            "SELECT id, name, role, archetype, bond, romance_stage, is_spouse, status,"
            " beauty_standard, presence,"
            " (SELECT count(*) FROM maya_rp.character_assets a"
            "  WHERE a.character_id = c.id AND a.status='ready') AS portraits"
            " FROM maya_rp.characters c WHERE session_id=$1 AND name ILIKE $2"
            " ORDER BY COALESCE(bond,0) DESC LIMIT 1",
            session, pattern,
        )
        if row:
            return dict(row)
    return None


async def main() -> int:
    parser = argparse.ArgumentParser(description="Merge the galaxy-beauties catalog with the DB")
    parser.add_argument("--session", type=int, default=Config.SESSION_ID)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    catalog = parse_catalog(CATALOG)
    await Database.init()
    flagged = [dict(row) for row in await Database.fetch(
        "SELECT name, role, bond, romance_stage, is_spouse,"
        " (SELECT count(*) FROM maya_rp.character_assets a WHERE a.character_id=c.id AND a.status='ready') AS portraits"
        " FROM maya_rp.characters c WHERE session_id=$1 AND beauty_standard IS TRUE"
        " ORDER BY COALESCE(bond,0) DESC, name", args.session)]

    # A comprehension with `await` builds an async generator; resolve the
    # catalog names with an explicit loop instead.
    resolved: dict[str, dict | None] = {}
    for entry in catalog:
        resolved[entry["name"]] = await lookup(args.session, entry["name"])
    present = sum(1 for row in resolved.values() if row)

    lines = [
        "# 50 Galaxy-Crushing Beauties — list (2026-09-22)",
        "",
        "> Hidden, protected, elusive. Merged from the catalog "
        "(`adventures/tkg/character-sheets/galaxy-beauties.md`) and the campaign database "
        "(`maya_rp.characters`, flag `beauty_standard`). Status as of this date.",
        "",
        f"Catalog entries: **{len(catalog)}** · database-flagged: **{len(flagged)}** · "
        f"catalog names present in the database: **{present}**",
        "",
    ]
    group = ""
    for entry in catalog:
        if entry["group"] != group:
            group = entry["group"]
            lines += ["", f"## {group}", ""]
        row = resolved[entry["name"]]
        if row:
            spouse = "spouse" if row["is_spouse"] else (row["romance_stage"] or "—")
            star = "★" if row["beauty_standard"] else "·"
            lines.append(
                f"- {star} **{entry['number']}. {row['name']}** — {entry['title'] or row['role'] or '—'} · "
                f"bond {row['bond'] or 0} · {spouse} · {row['status']} · {row['portraits']}🖼 · id {row['id']}"
            )
        else:
            lines.append(f"- ○ **{entry['number']}. {entry['name']}** — {entry['title'] or '—'} · not in the database yet")

    lines += ["", "## Flagged in the database, not in the catalog", ""]
    names = {entry["name"].lower() for entry in catalog}
    extras = [row for row in flagged if row["name"].split(" (")[0].lower() not in names
              and not any(row["name"].lower().startswith(n) for n in names)]
    for row in extras:
        spouse = "spouse" if row["is_spouse"] else (row["romance_stage"] or "—")
        lines.append(f"- ★ **{row['name']}** — {row['role'] or '—'} · bond {row['bond'] or 0} · {spouse} · {row['portraits']}🖼")
    lines += ["", "★ = flagged `beauty_standard` · ○ = catalog-only (no row yet) · 🖼 = rendered portraits", ""]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    await Database.close()
    print(f"{len(catalog)} catalog entries · {len(flagged)} flagged · extras {len(extras)} → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
