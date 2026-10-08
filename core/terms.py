#!/usr/bin/env python3
"""Terms — what a character asked of Izzat and what was agreed, quoted from the turn that said it.

WHERE THE GAP IS. `characters` carries six columns for feeling and the engine has eight more tables
for relationships and romance. None holds what a character ASKED FOR. A character can be furious for
forty turns and the engine cannot say why. Turn 75 shows the cost: Zulaikha Nadira answers the
proposal with two terms, demoting the first promise to an intention because it cannot be measured and
adding a condition to the second. Nothing recorded either.

THE ENGINE FINDS THE PASSAGE. IT DOES NOT INTERPRET IT.

`extract` scans paragraphs for the markers Bahasa Melayu uses to introduce an obligation, and returns
the paragraph verbatim with a `kind` label. The label comes from the marker, not from reading the
sentence: `Perkara satu` is a `syarat` because that is what the phrase introduces, not because the
engine understood the clause. A paraphrase of an obligation is a second version of it, and the two
drift. The quote does not.

SPEAKER IS BEST EFFORT AND SAYS SO. A `### N. Name` heading above the passage wins, because that is
how `compile_session_novel.py` and the play record structure a turn. Failing that, `kata Name` inside
the paragraph. Failing both, None, which is honest rather than guessed.

    python3 -c "from core.terms import extract; import json; \\
                print(json.dumps(extract(open('turn.md').read()), indent=1, ensure_ascii=False))"
"""
from __future__ import annotations

import re
from typing import Any

from core.session import require_session
from core.db import Database
from core.log import info

# Marker, then the kind it introduces. Longest first, because `perjanjian` contains `janji` and
# `persetujuan` contains `setuju`: checking the short form first would mislabel both.
#
# `saya akan` AND `kamu akan` WERE HERE AND ARE GONE. They were in the first version and they are
# ordinary future tense, not obligation: run over the real play record they produced 110 of 116
# matches and almost all were noise — "Saya akan bayar dengan kerja", "Saya akan kembali," katanya,
# "Kamu akan tinggal di sini sampai berapa lama?" The markers below are the ones that introduce a
# commitment rather than describe what happens next.
MARKERS: tuple[tuple[str, str], ...] = (
    ("perjanjian", "perjanjian"),
    ("aku boleh janjikan", "janji"),
    ("aku minta kamu", "janji"),
    ("aku meminta kamu", "janji"),
    ("aku janji", "janji"),
    ("saya bersetuju", "persetujuan"),
    ("aku bersetuju", "persetujuan"),
    ("aku setuju", "persetujuan"),
    ("dengan syarat", "syarat"),
    ("satu tambahan", "syarat"),
    ("perkara satu", "syarat"),
    ("perkara dua", "syarat"),
    ("perkara tiga", "syarat"),
    ("ini satu perjanjian", "perjanjian"),
)

SECTION = re.compile(r"^#{2,4}[ \t]+(?:\d+\.)?[ \t]*(?P<name>[^\n]+)$", re.M)
SAID = re.compile(r"(?<![\w-])kata ([A-Z][\w'-]*(?: [A-Z][\w'-]*)?)")

# A paragraph is the unit. The play record writes one clause per paragraph inside emphasis, so a
# term's sentence and its reasoning stay together and neither bleeds into the next clause.
MAX_QUOTE = 900


def paragraphs(text: str) -> list[tuple[int, str]]:
    """Non-empty paragraphs with the offset they start at. Pure."""
    out: list[tuple[int, str]] = []
    for match in re.finditer(r"(?:^|\n)([^\n](?:[^\n]|\n(?!\n))*)", text or ""):
        start = match.start(1)
        body = match.group(1)
        # A heading directly above its text (no blank line) joined the paragraph, which then began
        # with '#' and `_kind` dropped it: a real obligation vanished. Leading heading lines are
        # their own paragraphs.
        while body.lstrip().startswith("#") and "\n" in body:
            head, body = body.split("\n", 1)
            start += len(head) + 1
            if head.strip():
                out.append((start - len(head) - 1 + (len(head) - len(head.lstrip())), head.strip()))
        stripped = body.strip()
        if stripped:
            out.append((start + (len(body) - len(body.lstrip())), stripped))
    return out


def speaker_before(text: str, offset: int) -> str | None:
    """The nearest `### N. Name` heading above an offset, cleaned of its numbering. Pure."""
    name = None
    for match in SECTION.finditer(text or ""):
        if match.start() > offset:
            break
        name = match.group("name").strip()
    return name or None


def _kind(paragraph: str) -> str | None:
    """The kind a paragraph introduces, or None.

    TABLE ROWS AND HEADINGS ARE SKIPPED. Run over the real turns, three of seventeen matches were
    table cells that happened to contain a marker — `| Calon | Asas | Minat (dadu) | Harga sanggup
    bayar |` and two like it, from the ledger tables the record uses. A row is not a sentence
    somebody said, and a heading introduces nothing by itself.
    """
    stripped = paragraph.lstrip()
    if stripped.startswith("|") or stripped.startswith("#"):
        return None
    low = paragraph.lower()
    for marker, kind in MARKERS:
        if marker in low:
            return kind
    return None


def extract(text: str) -> list[dict[str, Any]]:
    """Every paragraph that introduces an obligation, verbatim, with its kind and speaker.

    Pure: no database, no interpretation beyond the marker. A paragraph matching two markers takes
    the first in `MARKERS` order, which is why the longest phrases are checked first.
    """
    found: list[dict[str, Any]] = []
    for offset, body in paragraphs(text):
        kind = _kind(body)
        if kind is None:
            continue
        speaker = speaker_before(text, offset)
        if not speaker:
            said = SAID.search(body)
            speaker = said.group(1).strip() if said else None
        quote = body if len(body) <= MAX_QUOTE else body[:MAX_QUOTE].rstrip() + "…"
        found.append({"kind": kind, "speaker": speaker, "quote": quote})
    return found


async def record(session_id: int | None = None, turn_id: int | None = None,
                 text: str = "") -> dict[str, Any]:
    """Store the terms a turn states. Idempotent: the same passage in the same turn is one row.

    A SPEAKER THAT IS NOT A CHARACTER IS BLANKED. `speaker_before` takes the nearest heading, and
    the play record heads sections with things that are not people: run over the real turns it
    returned `Harga`, `Ejen di tanjakan`, `Mahar`, `Tanda` and `Yang dia pilih`. A term attributed to
    a price is worse than one attributed to nobody, so the name is checked against the roster here,
    where the database is available, and set to None when it does not resolve.
    """
    if session_id is None:
        session_id = require_session(None)
    terms = extract(text)
    roster = {r["name"] for r in await Database.fetch(
        "SELECT name FROM maya_rp.characters WHERE session_id=$1", session_id)}
    known = roster | {n for n in roster if " " in n}  # exact names only; the roster is authoritative

    written, already, unnamed = 0, 0, 0
    for term in terms:
        speaker = term["speaker"]
        if speaker and speaker not in known:
            unnamed += 1
            speaker = None
        tag = await Database.execute(
            "INSERT INTO maya_rp.terms (session_id, turn_id, speaker, kind, quote)"
            " VALUES ($1, $2, $3, $4, $5)"
            " ON CONFLICT (session_id, COALESCE(turn_id, 0), md5(quote)) DO NOTHING",
            session_id, turn_id, speaker, term["kind"], term["quote"])
        if tag.rsplit(" ", 1)[-1] == "1":
            written += 1
        else:
            already += 1
    if written:
        info("terms", f"turn {turn_id}: recorded {written} term(s), {already} already held, "
                      f"{unnamed} heading(s) were not people")
    return {"found": len(terms), "written": written, "already": already,
            "speakers_blanked": unnamed, "terms": terms}


async def open_terms(session_id: int | None = None) -> list[dict]:
    """Every open term for a session, oldest first. This is what gets injected."""
    if session_id is None:
        session_id = require_session(None)
    return [dict(r) for r in await Database.fetch(
        "SELECT id, turn_id, speaker, kind, quote FROM maya_rp.terms"
        " WHERE session_id=$1 AND status='open' ORDER BY id", session_id)]


async def render(session_id: int | None = None) -> str:
    """The open terms as a block for the turn's context, or an empty string when there are none."""
    rows = await open_terms(session_id)
    if not rows:
        return ""
    lines = ["## TERMA YANG BERDIRI", ""]
    for row in rows:
        who = row["speaker"] or "tiada penutur"
        lines.append(f"- **{row['kind']}** · {who} · giliran {row['turn_id']}: {row['quote']}")
    return "\n".join(lines)


async def lines(session_id: int | None = None, *, limit: int = 8, width: int = 240) -> list[str]:
    """The open terms as one line each, for the `[TERMS]` block in the turn's context.

    The quote is collapsed to single spaces and capped, because this goes into a prompt. A term
    longer than `width` keeps its beginning and ends with an ellipsis rather than being dropped: an
    obligation that is silently absent is worse than one that is visibly shortened.
    """
    rows = await open_terms(session_id)
    out: list[str] = []
    for row in rows[:limit]:
        quote = " ".join((row["quote"] or "").split())
        if len(quote) > width:
            quote = quote[:width].rstrip() + "…"
        who = row["speaker"] or "tiada penutur"
        out.append(f"- {row['kind']} · {who} · giliran {row['turn_id']}: {quote}")
    return out
