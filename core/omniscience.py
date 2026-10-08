#!/usr/bin/env python3
"""Omniscience — a character speaks in a scene they are recorded as not being in.

The rule: nobody acts on what they did not witness. The engine now knows where each character
is (`characters.scene_location`) and where the scene is (`player_context.location`), so one part
of that rule can be checked rather than trusted: **who speaks.**

Bahasa Melayu attributes speech regularly, measured on `the-sunrise.md`: `kata <Name>` 288 times,
`<Name> berkata` 120, and `katanya` 188 for the previous speaker.

    "ini tidak masuk," kata Ngozi.
    "tinggal di sini," kata Doyo, "kamu perlukan lebih daripada itu."
    Wulan berkata dengan lantang di dalam

So the names of the speakers can be read out of a turn. A speaker recorded at another location is
the finding.

WHAT THIS DOES NOT DO, AND MUST NOT. It does not move anybody. The same line can be a
recollection — `kata Doyo` inside someone telling what Doyo said a year ago — and this cannot
tell the two apart. A write based on that reading would put a person in a room because of a
sentence about the past, which is worse than the gap it was trying to close.

The correction already exists and it is the GM's: declare `masuk=<name>` in the `[SCENE]` line and
`core/scene_tracker.py` moves them, with the correction recorded. This module produces the
question. The tracker takes the answer.

    report = await check(5, turn_text)
    for f in report["findings"]:
        print(f["character"], "speaks but is recorded at", f["recorded_at"])
"""
from __future__ import annotations

import difflib
import re
from typing import Any

from core.config import Config
from core.db import Database

# `kata <Name>`, where Name is one or two capitalised words. The lookbehind keeps `katanya` and
# `dikatakan` from matching: both are followed by a lowercase continuation, and the name must start
# with a capital.
SAID = re.compile(r"(?<![\w-])kata ([A-Z][\w'-]*(?: [A-Z][\w'-]*)?)")
SPOKE = re.compile(r"(?<![\w-])([A-Z][\w'-]*(?: [A-Z][\w'-]*)?) berkata(?![\w-])")

# Forms of address rather than speakers. `kata Cikgu Izzat` names the person addressed in the
# surrounding dialogue as often as it names who spoke.
TITLES = ("Cikgu", "Tuan", "Puan", "Doktor", "Dr", "Kapten", "Ketua", "Hakim")


def resolve(name: str, roster: list[str]) -> str | None:
    """The roster name a spoken name refers to, or None when nothing fits.

    The prose uses short forms as often as full ones and the roster holds one name per person.
    Measured on `the-sunrise.md`: `Doyo` three times as often as `Doyo Kwarta`, and `Bregg` where
    the roster says `Marlon Bregg`. Exact match first, then whole-word containment, then a close
    match at a high cutoff because this is resolving a reference rather than guessing at a typo.

    Pure, so a test needs no database.
    """
    if name in roster:
        return name
    inside = [r for r in roster if re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", r)]
    if len(inside) == 1:
        return inside[0]
    if inside:
        return None  # more than one person answers to it, so this cannot choose
    close = difflib.get_close_matches(name, roster, n=1, cutoff=0.85)
    return close[0] if close else None


def resolve_speaker(said: str, roster: list[str]) -> str | None:
    """The roster name a captured speaker phrase refers to, retrying single words of a two-word capture.

    `SPOKE` takes an optional second capitalised word, so a sentence-initial word is captured as
    part of the name: "Lalu Wulan berkata" and "Kemudian Doyo berkata" came back as `Lalu Wulan`
    and `Kemudian Doyo`, resolved to nothing, and were reported not_in_roster for people the roster
    holds. When the whole phrase does not resolve, the last word is tried, then the first.

    @param said - the captured phrase, one or two words.
    @param roster - roster names.
    @returns the roster name, or None when no reading resolves.
    """
    whole = resolve(said, roster)
    if whole is not None:
        return whole
    words = said.split()
    if len(words) < 2:
        return None
    for word in (words[-1], words[0]):
        found = resolve(word, roster)
        if found is not None:
            return found
    return None


def speakers(text: str) -> list[str]:
    """Names attributed with speech in a turn, in the order they appear, without repeats.

    Pure: no database, no judgement about where anyone is. A name that appears only as part of a
    longer name is returned whole, because that is how the roster holds it.
    """
    found: list[str] = []
    for pattern in (SAID, SPOKE):
        for match in pattern.finditer(text or ""):
            name = match.group(1).strip()
            if not name or name.split()[0] in TITLES:
                continue
            if name not in found:
                found.append(name)
    return found


async def check(session_id: int | None = None, text: str = "") -> dict[str, Any]:
    """Who speaks in this turn, and whether the engine records them in this scene.

    A speaker the engine does not hold at all is reported separately. That is not an omniscience
    finding: it is a name the roster does not have, which is the import gate's question and the
    scene tracker's, not this one's.
    """
    if session_id is None:
        session_id = Config.SESSION_ID
    scene = await Database.fetchval(
        "SELECT location FROM maya_rp.player_context WHERE session_id=$1", session_id)
    roster = await Database.fetch(
        "SELECT name, scene_location FROM maya_rp.characters WHERE session_id=$1", session_id)
    where = {r["name"]: r["scene_location"] for r in roster}

    findings: list[dict[str, Any]] = []
    for said in speakers(text):
        name = resolve_speaker(said, list(where))
        if name is None:
            findings.append({"character": said, "kind": "not_in_roster", "said": said,
                             "recorded_at": None, "scene": scene})
            continue
        # `player_context.location` is NULL for every session, so comparing against it flagged every
        # speaker with a recorded location as elsewhere (scene=None). An unknown side is no evidence.
        if scene is None or where[name] is None or where[name] == scene:
            continue
        findings.append({"character": name, "kind": "speaks_elsewhere", "said": said,
                         "recorded_at": where[name], "scene": scene})
    return {
        "scene": scene,
        "speakers": speakers(text),
        "findings": findings,
        "checked": len(where),
        "note": "Nothing is moved. Declare masuk=<name> in the [SCENE] line and the scene tracker "
                "will move them, with the correction recorded.",
    }
