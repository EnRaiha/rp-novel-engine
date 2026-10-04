#!/usr/bin/env python3
"""seed_character_injuries — the marks the story says these people carry.

`maya_rp.character_injuries` has a full schema — severity, body part, cause, a heal-by game day
and a scar roll — and `modules/physical_state.py` heals them on the tick. **It has never held a
row.** The story names two people who carry marks, so the mechanism has something to read.

BOTH ARE SCARS FROM BEFORE THE CAMPAIGN, and `status='scar'` is written directly rather than
`'active'` with a past heal date. The tick heals rows where `status='active'` and
`heal_by_game_day <= game day`; a scar that is already a scar is left alone, which is what a mark
from before the story should be. `received_game_day` is 0 for the same reason: it did not happen
on any day this engine counts.

WHAT THE SOURCE SAYS, per row:

  Ruslan Bakar (id 2981)  the novel: "Lelaki. Orang limbah generasi kelima, muka lebar dan tangan
                          penuh parut bakar." He is one of the twelve families in the great house,
                          which is where the scene is, so he is in the room.

  Ngesan Dorai (id 2963)  the novel: "Lelaki. Kacukan Koloni Dalam, hidung patah dua kali." One of
                          the twenty-six courting the inspector.

WHAT THIS DOES NOT WRITE, and the list is longer than the list above:

  * The gunshot rib. "satu, bekas tembakan di rusuk kiri, struktur bengkok ke dalam" is not a
    person: the passage is Izzat reading wreckage — "Setiap bangkai miring sedikit" — and a bent
    rib is a bent hull. Reading it as a wound would have put an injury on a character nobody named.
  * Izzat's hand. "Tangan yang dua hari lepas retak di celah ibu jari" then "Tiada keropeng. Tiada
    luka merah. Tiada parut." The Fountain closed it and the prose says so three ways. There is
    nothing to record and recording it would contradict the scene.
  * Two lung disease cases at Bukit Kaca, from turn 73: "Kabus relau. Dua kes paru-paru di Bukit
    Kaca. Sumayyah meminta penapis atau relau dipindahkan." They are active and they are unnamed.
    An injury belongs to a character, and these belong to a colony's working conditions, so they
    need a health field on the settlement rather than a person invented to carry them.

Dry run by default. `--apply` writes. A row that already exists for the same character and
description is left alone.

    python3 scripts/seed_character_injuries.py --session 5
    python3 scripts/seed_character_injuries.py --session 5 --apply
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.db import Database  # noqa: E402
from core.log import info, warn  # noqa: E402

# character name, description, severity, body part, cause, source
MARKS: tuple[tuple[str, str, str, str, str, str], ...] = (
    ("Ruslan Bakar", "Burn scars across both hands", "moderate", "hands", "furnace",
     "Turn 72, the novel: 'Lelaki. Orang limbah generasi kelima, muka lebar dan tangan penuh parut "
     "bakar.' A fifth-generation Limbah man, and the furnaces are what Limbah does."),
    ("Ngesan Dorai", "Nose broken twice", "moderate", "nose", "fight",
     "Turn 72, the novel: 'Lelaki. Kacukan Koloni Dalam, hidung patah dua kali.' Stated as a fact "
     "about his face, so both breaks are behind him."),
)


async def seed(session: int, *, write: bool) -> dict:
    result = {"created": [], "kept": [], "no_character": []}
    for name, desc, severity, body, cause, source in MARKS:
        who = await Database.fetchrow(
            "SELECT id, name FROM maya_rp.characters WHERE session_id=$1 AND name=$2", session, name)
        if not who:
            result["no_character"].append(name)
            warn("injuries", f"{name}: not in session {session}; skipped")
            continue
        existing = await Database.fetchrow(
            "SELECT id FROM maya_rp.character_injuries"
            " WHERE session_id=$1 AND character_id=$2 AND description=$3",
            session, who["id"], desc)
        if existing:
            result["kept"].append(name)
            info("injuries", f"{name}: already recorded as #{existing['id']}; left alone")
            continue
        if not write:
            result["created"].append(name)
            info("injuries", f"{name}: would record {desc!r} ({severity}, {body})  [{source[:60]}...]")
            continue
        new_id = await Database.fetchval(
            "INSERT INTO maya_rp.character_injuries"
            " (session_id, character_id, description, severity, body_part, cause,"
            "  received_game_day, heal_by_game_day, became_scar, status)"
            " VALUES ($1, $2, $3, $4, $5, $6, 0, 0, true, 'scar') RETURNING id",
            session, who["id"], desc, severity, body, cause)
        read_back = await Database.fetchrow(
            "SELECT status, became_scar FROM maya_rp.character_injuries WHERE id=$1", new_id)
        if not read_back or read_back["status"] != "scar":
            warn("injuries", f"{name}: write did not take; read back "
                             f"{dict(read_back) if read_back else None}")
            continue
        result["created"].append(name)
        info("injuries", f"{name}: recorded #{new_id} as a scar ({body}, {cause})")
    return result


async def main() -> int:
    parser = argparse.ArgumentParser(description="Record the marks the story says these people carry.")
    parser.add_argument("--session", type=int, default=5)
    parser.add_argument("--apply", action="store_true", help="write; the default is a dry run")
    args = parser.parse_args()

    await Database.init()
    try:
        result = await seed(args.session, write=args.apply)
    finally:
        await Database.close()

    verb = "recorded" if args.apply else "would record"
    print(f"{verb} {len(result['created'])} of {len(MARKS)} mark(s) in session {args.session}")
    if result["kept"]:
        print(f"left alone (already recorded): {', '.join(result['kept'])}")
    if result["no_character"]:
        print(f"SKIPPED (not in this session): {', '.join(result['no_character'])}")
    if not args.apply:
        print("dry run: nothing written")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
