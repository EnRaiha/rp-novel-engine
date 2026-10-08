#!/usr/bin/env python3
"""Scene tracker — read what the turn says happened, check it against the engine, correct it.

The engine feeds state in. This reads the other direction: the prose declares what moved,
and the declaration is validated against the engine before anything is written. A name the
engine does not hold is corrected to the nearest one it does, and the correction is reported
rather than applied in silence.

THE DECLARATION, one line at the end of a turn:

    [SCENE] lokasi=rumah_agung_sayap_timur | masuk=Ersya Ardani | keluar=Boyet | masa=petang

Four fields, and no numbers. Credits, fuel, population and crew are the engine's, and a
declaration that restated them would be a second source of truth for the thing this exists
to check.

    lokasi   a maya_rp.location_catalog.name. Where the scene is now.
    masuk    characters who entered. Comma separated.
    keluar   characters who left. Comma separated. They are set to no location.
    masa     subuh, pagi, tengah hari, petang, malam.

Correction uses `difflib.get_close_matches`, so a misspelling lands on the engine's name
rather than creating a new one. A field the parser does not know is checked against the field
names and reported as a probable typo instead of being ignored.
"""
from __future__ import annotations

import difflib
import re
from typing import Any

from core.db import Database
from core.log import info, warn
from core.session import require_session

BLOCK = re.compile(r"^[ \t]*\[SCENE\][ \t]*(?P<body>[^\n]*)$", re.M)
FIELDS = ("lokasi", "masuk", "keluar", "masa")
TIMES = ("subuh", "pagi", "tengah hari", "petang", "malam")
CUTOFF = 0.6

# What a declaration writes when it means "nobody". The first live turn used `keluar=-`, and the
# reader treated the dash as a character name and warned that `-` is not in session 5. A placeholder
# is not a person, so it is dropped at the parse rather than reported as a miss.
EMPTY_MARKERS = frozenset({"-", "--", "—", "–", "none", "nobody", "tiada", "kosong", "(none)"})


def parse(text: str) -> dict[str, Any] | None:
    """The declaration in a turn, or None when the turn carries none.

    Pure: no database, no correction. A repeated field keeps the last value, which is what a
    reader would do.
    """
    match = None
    for found in BLOCK.finditer(text or ""):
        match = found
    if match is None:
        return None
    decl: dict[str, Any] = {"unknown_fields": [], "raw": match.group(0).strip()}
    for chunk in match.group("body").split("|"):
        if "=" not in chunk:
            continue
        key, _, value = chunk.partition("=")
        key = key.strip().lower()
        value = value.strip()
        if key in ("masuk", "keluar"):
            decl[key] = [name.strip() for name in re.split(r"[,;]", value)
                         if name.strip() and name.strip() not in EMPTY_MARKERS]
        elif key in ("lokasi", "masa"):
            decl[key] = value or None
        elif key:
            decl["unknown_fields"].append(key)
    return decl


def render(decl: dict[str, Any]) -> str:
    """The declaration back as a line. Pure, so a test can read what would be written."""
    parts = []
    if decl.get("lokasi"):
        parts.append(f"lokasi={decl['lokasi']}")
    for key in ("masuk", "keluar"):
        names = decl.get(key) or []
        if names:
            parts.append(f"{key}={', '.join(names)}")
    if decl.get("masa"):
        parts.append(f"masa={decl['masa']}")
    return "[SCENE] " + " | ".join(parts) if parts else "[SCENE]"


def _nearest(value: str, options: list[str]) -> str | None:
    hit = difflib.get_close_matches(value, options, n=1, cutoff=CUTOFF)
    return hit[0] if hit else None


async def resolve(session_id: int | None, decl: dict[str, Any]) -> dict[str, Any]:
    """Check a declaration against the engine and correct what is close enough.

    Nothing is written. Every correction is recorded with the value it replaced, so a reader
    can see what the prose said and what the engine made of it.

    A name that is not close to anything is dropped, not invented: a character the engine does
    not hold cannot be placed, and creating one from a turn would put a person into the campaign
    because of a typo.
    """
    # `Config.SESSION_ID` is fixed at import; a long-lived process kept resolving against the
    # session that was current at start. An explicit id wins as given.
    session_id = require_session(session_id)
    corrections: list[dict[str, str]] = []
    resolved: dict[str, Any] = {"masuk": [], "keluar": [], "lokasi": None, "masa": None}

    catalogue = [r["name"] for r in await Database.fetch("SELECT name FROM maya_rp.location_catalog")]
    roster = [r["name"] for r in await Database.fetch(
        "SELECT name FROM maya_rp.characters WHERE session_id=$1", session_id)]

    lokasi = decl.get("lokasi")
    if lokasi:
        if lokasi in catalogue:
            resolved["lokasi"] = lokasi
        else:
            fixed = _nearest(lokasi, catalogue)
            if fixed:
                corrections.append({"field": "lokasi", "said": lokasi, "used": fixed})
                resolved["lokasi"] = fixed
            else:
                corrections.append({"field": "lokasi", "said": lokasi, "used": ""})
                warn("scene-tracker", f"{lokasi!r} is not in location_catalog and is not close to "
                                      "anything there; the scene location is left as it was")

    for key in ("masuk", "keluar"):
        for name in decl.get(key) or []:
            if name in roster:
                resolved[key].append(name)
                continue
            fixed = _nearest(name, roster)
            if fixed:
                corrections.append({"field": key, "said": name, "used": fixed})
                resolved[key].append(fixed)
            else:
                corrections.append({"field": key, "said": name, "used": ""})
                warn("scene-tracker", f"{name!r} is not in session {session_id} and is not close to "
                                      "anyone there; not placed")

    masa = decl.get("masa")
    if masa:
        if masa in TIMES:
            resolved["masa"] = masa
        else:
            fixed = _nearest(masa, list(TIMES))
            if fixed:
                corrections.append({"field": "masa", "said": masa, "used": fixed})
                resolved["masa"] = fixed

    for key in decl.get("unknown_fields") or []:
        fixed = _nearest(key, list(FIELDS))
        corrections.append({"field": key, "said": key,
                            "used": fixed or "", "kind": "unknown_field"})
        if fixed:
            warn("scene-tracker", f"unknown field {key!r} in the declaration; did you mean {fixed!r}?")

    # A name cannot enter and leave at once. Entering wins, because the scene it just joined is
    # the one the turn is about, and a reader would resolve it that way.
    both = set(resolved["masuk"]) & set(resolved["keluar"])
    if both:
        resolved["keluar"] = [n for n in resolved["keluar"] if n not in both]
        for name in sorted(both):
            corrections.append({"field": "keluar", "said": name, "used": "",
                                "kind": "entered_and_left"})

    return {"declared": decl, "resolved": resolved, "corrections": corrections}


async def apply_declaration(session_id: int | None, resolved: dict[str, Any]) -> dict[str, Any]:
    """Write a resolved declaration in one transaction. Returns what moved, with a read-back per write.

    Every statement goes through the yielded connection, so a failure midway leaves neither a
    moved scene with unmoved characters nor the reverse. The scene location and the entrants
    used to commit one autocommit at a time.

    `masuk` without `lokasi` leaves the entrant's `scene_location` as it was. The update bound
    `lokasi` unconditionally, so `masuk=Ersya` alone wrote NULL over the location of the person
    who had just entered. Skipping is the smaller correct move: the declaration named nobody's
    place, so it changes nobody's place.

    @param session_id - explicit id wins; None resolves the arc now.
    @param resolved - the `resolved` half of `resolve()`.
    @returns {"location", "entered", "left"}.
    """
    session_id = require_session(session_id)
    moved: dict[str, Any] = {"location": None, "entered": [], "left": []}

    lokasi = resolved.get("lokasi")
    async with Database.transaction() as conn:
        if lokasi:
            await conn.execute(
                "INSERT INTO maya_rp.player_context (session_id, location, updated_at) VALUES ($1, $2, NOW())"
                " ON CONFLICT (session_id) DO UPDATE SET location=$2, updated_at=NOW()",
                session_id, lokasi)
            moved["location"] = await conn.fetchval(
                "SELECT location FROM maya_rp.player_context WHERE session_id=$1", session_id)

    # NO PLAYER-CHARACTER MOVE HAPPENS HERE, AND A FIRST ATTEMPT AT ONE WAS REVERTED.
    #
    # `player_context.location` and `characters.scene_location` describe different things: the scene
    # and a person. The instinct was to keep them in step by moving the row behind the player, so
    # this function moved `WHERE controlled_by='gm'`. That column is not the player. Measured on
    # session 5 it holds **63 rows**, ids 2931 to 2993, every one `character_type='supporting'` and
    # `bond 0`: the Arc I supporting cast, the same block the `arc1-cast` marker exists for. The
    # update put all 63 into the town hall, 52 of which had no recorded location at all before it.
    #
    # They were restored to NULL and the twelve known values were reapplied. There is no column that
    # says which character is the player's, so `apply_declaration` moves exactly the names the
    # declaration names and nothing else. A declaration that wants the player's own row moved lists
    # him in `masuk` like anybody else.

        for name in resolved.get("masuk") or []:
            if lokasi:
                await conn.execute(
                    "UPDATE maya_rp.characters SET scene_location=$1 WHERE session_id=$2 AND name=$3",
                    lokasi, session_id, name)
            moved["entered"].append(name)

        for name in resolved.get("keluar") or []:
            await conn.execute(
                "UPDATE maya_rp.characters SET scene_location=NULL WHERE session_id=$1 AND name=$2",
                session_id, name)
            moved["left"].append(name)

    return moved


async def consume(session_id: int | None, text: str, *, write: bool = True) -> dict[str, Any]:
    """The whole pass over one turn: parse, check, correct, and optionally write.

    @param write - False validates and reports without touching state, which is what a preview
        or a dry run wants.
    """
    decl = parse(text)
    if decl is None:
        warn("scene-tracker", "the turn carries no [SCENE] declaration; nothing was checked")
        return {"declared": None, "resolved": None, "corrections": [], "moved": None}

    result = await resolve(session_id, decl)
    result["moved"] = await apply_declaration(session_id, result["resolved"]) if write else None
    for c in result["corrections"]:
        info("scene-tracker", f"corrected {c['field']}: said {c['said']!r}, used {c.get('used')!r}")
    return result
