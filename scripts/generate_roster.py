#!/usr/bin/env python3
"""Roster page — every character with sheet, emotions and play-guide status (M23).

A player-facing page (never sent to the model): who exists, how close they are,
which preset images are ready, and whether their voice/intro/play-guide fields
have been written yet.

Usage: python3 scripts/generate_roster.py --session 3 [--out FILE]
"""
from __future__ import annotations

import argparse
import asyncio
import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import Config  # noqa: E402
from core.db import Database  # noqa: E402
from core import persona, portraits  # noqa: E402

DEFAULT_OUT = Path("/home/maya/Bumi-Hijau/wiki/rp-dev/canon/assets/roster.html")


def card(row: dict, assets: dict[str, str], fields: dict[str, bool], play_guide: str) -> str:
    name = html.escape(row["name"])
    slug = portraits.slugify(row["name"])
    rel = f"/characters/{slug}"
    emotions_files = sorted({portraits.OCCASIONS.get(key, (key, ()))[0] for key in assets})
    thumbs = " ".join(
        f'<img src="/characters/{slug}/emotions/{html.escape(key)}.png" alt="{html.escape(key)}" title="{html.escape(key)}">'
        for key in emotions_files
    )
    emotions = thumbs or "—"
    flags = " ".join(key for key, present in fields.items() if present) or "—"
    notes = html.escape(play_guide[:220]) if play_guide else "—"
    return f"""      <article class="card">
        <h3>{name}</h3>
        <p class="meta">{html.escape(row.get('role') or '—')} · bond {row.get('bond') or 0}
           · {html.escape(row.get('romance_stage') or '—')}</p>
        <p class="meta">images: {html.escape(emotions)}</p>
        <p class="meta">fields: {html.escape(flags)}</p>
        <p class="notes">{notes}</p>
        <p class="links"><a href="{rel}/sheet.md">sheet.md</a>
           <a href="{rel}/emotions/">emotions/</a></p>
      </article>"""


async def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the roster page")
    parser.add_argument("--session", type=int, default=Config.SESSION_ID)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    await Database.init()
    rows = await Database.fetch(
        "SELECT id, name, role, bond, romance_stage FROM maya_rp.characters"
        " WHERE session_id=$1 AND status IS DISTINCT FROM 'dead'"
        " ORDER BY COALESCE(bond,0) DESC, id",
        args.session,
    )
    asset_rows = await Database.fetch(
        "SELECT c.name, a.occasion FROM maya_rp.character_assets a"
        " JOIN maya_rp.characters c ON c.id=a.character_id WHERE a.status='ready'",
    )
    await Database.close()

    by_name: dict[str, dict[str, str]] = {}
    for row in asset_rows:
        by_name.setdefault(row["name"], {})[row["occasion"]] = row["occasion"]

    cards = []
    for row in rows:
        row = dict(row)
        slug = portraits.slugify(row["name"])
        root = portraits.character_dir(row["name"])
        fields = {field: (root / f"{field}.md").is_file() for field in persona.FIELDS}
        play_guide = (root / "play-guide.md")
        notes = play_guide.read_text(encoding="utf-8").strip() if play_guide.is_file() else ""
        cards.append(card(row, by_name.get(row["name"], {}), fields, notes.splitlines()[-1] if notes else ""))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>TKG — Roster</title>
<style>
 body{{background:#0a0a0f;color:#e0dff0;font-family:Inter,system-ui,sans-serif;margin:2rem}}
 h1{{font-weight:700}} .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}}
 .card{{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.08);border-radius:14px;padding:14px}}
 .card h3{{margin:0 0 6px;color:#c4b5fd}} .meta{{margin:2px 0;font-size:12px;color:#8b8aa8}}
 .notes{{font-size:12px;color:#6b6a8a}} .links a{{color:#7dd3fc;font-size:12px;margin-right:10px}}
 .card img{{height:54px;border-radius:6px;margin-right:6px}}
</style></head><body>
<h1>TKG — Roster</h1>
<p class="meta">{len(cards)} characters · player only · never sent to the model</p>
<div class="grid">
{chr(10).join(cards)}
</div></body></html>
""", encoding="utf-8")
    print(f"roster: {len(cards)} characters -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
