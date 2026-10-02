#!/usr/bin/env python3
"""Fill the cast's appearance from the novel's own ledger lines.

The manuscript keeps a dossier inside the prose: on first mention a named character gets
one line shaped `**Name (id NNN)**. Lelaki/perempuan. Asal. Umur. Fizikal. Niatnya: ...`.
This script reads those lines and writes the identity half into `description` and the
physical clause into `appearance`, so the portrait pass has something true to render from
instead of guessing.

    python3 scripts/cast_appearance.py --dry-run
    python3 scripts/cast_appearance.py

Rules:

- A row that already carries an appearance is never overwritten.
- The intent clause is dropped: intent is a reading Izzat takes in a scene, not a fact
  about a body, and it changes from page to page.
- A physical clause is only claimed when it actually describes a body. The marker list is
  deliberately narrow; where the novel says nothing physical, `appearance` stays empty and
  the row is reported, because an invented clause would make the render prompt lie.

A second extractor was built and then removed: one that mined every mention of a character
anywhere in the manuscript, not just the dossier line. It was measured against the live novel and
returned one candidate from thirty-one attempts, and that candidate was narration
("Kemudian orang tua B-088, yang membuka matanya..."). The novel names those people; it does not
describe their bodies. Mining was deleted rather than shipped, because a flaky extractor is worse
than no extractor: it would put a scene sentence into a render prompt and nobody would notice
until the portrait was wrong.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

VAULT = pathlib.Path(__file__).resolve().parents[2]
NOVEL = VAULT / "adventures/tkg-arc1-restart/novel/the-sunrise.md"
LEDGER = re.compile(r"\*\*(?P<name>[^*]+?) \(id (?P<id>\d+)\)\*\*[.:]\s*(?P<body>.+)")
INTENT_SPLIT = re.compile(r"\bNiat(?:nya)?\b", re.IGNORECASE)
# A clause is claimed only when it reads like a description of a body. The first version of
# this list claimed scene narration instead ("Dia bertugas di pintu tingkat lima..."), which
# would have put a paragraph of plot into an appearance field.
BODY_MARKERS = ("rambut", "kulit", "muka", "tangan", "mata", "kaki", "badan", "parut",
                "janggut", "kurus", "gemuk", "siku", "cangkuk", "tatu", "bekas luka")
AGE_MARKERS = ("tahun", "berumur", "umur ")
NARRATION_OPENERS = ("dia ", "mereka ", "kamu ", "aku ", "saya ", "ia ")
MAX_CLAUSE = 340


def ledger_lines(text: str) -> dict[int, tuple[str, str]]:
    """Pull every dossier line out of the manuscript.

    @param text - the manuscript.
    @returns {id: (name, identity half)} with the intent clause removed. A later line for
        the same id replaces an earlier one, because the later line is usually the fuller
        dossier.
    """
    found: dict[int, tuple[str, str]] = {}
    for match in LEDGER.finditer(text):
        body = match.group("body").strip()
        intent = INTENT_SPLIT.search(body)
        identity = body[: intent.start()].strip(" ,;.") if intent else body.strip()
        if not identity:
            continue
        found[int(match.group("id"))] = (" ".join(match.group("name").split()), identity)
    return found


def physical_clause(identity: str) -> str | None:
    """Return the clause that describes a body, or None when the line has none.

    Rejects narration on purpose: a sentence that opens with `Dia ...` is the scene talking,
    and it belongs in neither field.

    @param identity - the identity half of a dossier line.
    @returns the first clause carrying a body marker and no narration opener, else None.
    """
    bodies: list[str] = []
    ages: list[str] = []
    for clause in re.split(r"(?<=[.;])\s+", identity):
        text = clause.strip(" ,;.")
        if not text or len(text) > MAX_CLAUSE:
            continue
        lowered = text.lower()
        if lowered.startswith(NARRATION_OPENERS):
            continue
        if any(marker in lowered for marker in BODY_MARKERS):
            bodies.append(text)
        elif any(marker in lowered for marker in AGE_MARKERS):
            ages.append(text)
    # A body clause beats an age clause: "Dua puluh tujuh tahun." describes a year, while
    # "rambut hitam diikat rendah, kot kerja kelabu..." describes the person a render needs.
    if bodies:
        return max(bodies, key=len) + "."
    if ages:
        return ages[0] + "."
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--novel", type=pathlib.Path, default=NOVEL)
    args = parser.parse_args()

    import psycopg2

    env = pathlib.Path.home() / ".env"
    if env.is_file():
        import os
        for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, _, value = line.partition("=")
                key = key.removeprefix("export ").strip()
                if key.startswith(("OC_PG_", "POSTGRES_")) and key not in os.environ:
                    os.environ[key] = value.strip().strip("'\"")

    found = ledger_lines(args.novel.read_text(encoding="utf-8"))
    conn = psycopg2.connect(host=os.environ["OC_PG_HOST"], port=int(os.environ.get("OC_PG_PORT", 5432)),
                            user=os.environ["OC_PG_USER"], password=os.environ.get("OC_PG_PASS"),
                            dbname=os.environ.get("OC_PG_DB", "maya_memory"))
    cur = conn.cursor()
    filled = skipped = no_body = 0
    for character_id, (name, identity) in sorted(found.items()):
        cur.execute("SELECT name, COALESCE(appearance,''), COALESCE(description,'')"
                    " FROM maya_rp.characters WHERE id=%s", (character_id,))
        row = cur.fetchone()
        if row is None:
            continue
        if row[1] or row[2]:
            skipped += 1
            continue
        appearance = physical_clause(identity)
        if appearance is None:
            no_body += 1
        if args.dry_run:
            print(f"{character_id:>5} {name[:24]:<24} appearance={appearance!r}")
            continue
        cur.execute("""UPDATE maya_rp.characters SET description=%s,
                       appearance=COALESCE(%s, appearance),
                       background=COALESCE(background,'') || %s
                       WHERE id=%s""",
                    (identity, appearance,
                     f"\nDescription taken from the novel's cast ledger line on 2026-10-02"
                     f" (`the-sunrise.md`, id {character_id}).", character_id))
        filled += 1
    if not args.dry_run:
        conn.commit()
    print(f"dossier lines {len(found)} · filled {filled} · already present {skipped} · "
          f"no physical clause {no_body}")
    if args.dry_run:
        print("dry run: nothing written")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
