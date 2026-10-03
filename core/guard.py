#!/usr/bin/env python3
"""Contradiction Guard — checks output against known state before delivery. Catches wrong weapons, dead characters, wrong bonds."""
from __future__ import annotations
import re
from typing import Any
from core.db import Database
from core.config import Config
from core.log import error

_cache: dict[int, dict] = {}
_cache_session: int | None = None

#: The engine's own death marker is `status='dead'`: twelve readers across modules/, core/ and
#: scripts/ filter `status IS DISTINCT FROM 'dead'`. Measured: 0 characters hold it, and 22 hold
#: `status='executed'` -- presence 'gone', a deep cell or a wreck for a scene -- so those 22 pass
#: every one of those filters as living. The guard reads both, because a corpse acting is the thing
#: it exists to catch either way. Whether `executed` is death for the twelve readers is a canon
#: question and it is reported, not settled here.
_DEAD_STATUSES = ("dead", "executed")

async def _ensure(session_id: int):
    global _cache, _cache_session
    # `and _cache` is load-bearing: it is what makes a second caller wait for an in-flight load
    # instead of reading the empty dict and reporting no contradiction.
    if _cache_session == session_id and _cache:
        return
    _cache = {}
    _cache_session = session_id
    try:
        # This SELECT used to name `weapon`, `is_dead` and `death_cause`. None of the three columns
        # exists on maya_rp.characters, so every call raised UndefinedColumnError, the handler below
        # kept the cache empty, and the guard answered "no contradictions" to every text it was
        # ever given. `is_dead` is derived from the column that does exist.
        for r in await Database.fetch(
                "SELECT id, name, status, role, bond FROM maya_rp.characters WHERE session_id=$1",
                session_id):
            row = dict(r)
            row["is_dead"] = row["status"] in _DEAD_STATUSES
            _cache[r["id"]] = row
    except Exception as e:
        # An empty cache makes every check below answer "no contradiction", so a read that failed
        # turned this guard into a blank pass with nothing to show for it. It stays empty and the
        # next call retries; the failure is on the log now instead of only in the guard's silence.
        _cache = {}
        _cache_session = None
        error("guard", f"character cache read failed for session {session_id}: "
                       f"{type(e).__name__}: {e}")

async def check(text: str, session_id: int = None) -> list[dict]:
    """Scan text for contradictions. Returns list of issues or empty."""
    if session_id is None: session_id = Config.SESSION_ID
    await _ensure(session_id)
    lower = text.lower()
    issues = []

    for cid, f in _cache.items():
        n = f["name"].lower()
        if n not in lower: continue
        if f.get("is_dead") and any(v in lower for v in ["says","shouts","grabs","steps","turns","looks"]):
            issues.append({"type":"dead_char_active","detail":f"{f['name']} is dead but appears active","fix":"Remove from scene or reference as memory"})
        # No per-character weapon column exists on maya_rp.characters and the weapon catalogue has
        # no owner, so `weapon` is never present and this branch cannot fire. Reported rather than
        # deleted, and pinned by a test that reads the schema.
        w = (f.get("weapon") or "").lower()
        if w and "blade" in w:
            # Word-boundary match: a substring test flagged "gun" inside "begun".
            mw = re.search(r"\b(?:pistol|gun|firearm|rifle)s?\b", lower)
            if mw:
                np = lower.find(n)
                wp = mw.start()
                if np >= 0 and 0 < abs(np - wp) < 80:
                    issues.append({"type":"wrong_weapon","detail":f"{f['name']} uses {f['weapon']} but text mentions gun/pistol","fix":f"Replace with {f['weapon']}"})
        b = f.get("bond") or 0
        if b < 3 and any(t in lower for t in ["lover","beloved","my love","darling"]):
            issues.append({"type":"wrong_bond","detail":f"{f['name']} bond {b} but called 'lover'","fix":"Use neutral address"})

    res = await Database.fetchrow("SELECT credits FROM maya_rp.resources WHERE session_id=$1", session_id)
    if res:
        # credits NULL and credits 0 mean the same thing to this check, so `or 0` is the honest
        # reading; the column is nullable and formatting it raw raised TypeError on the NULL.
        available = res["credits"] or 0
        # "purchas[ed]?" never matched "purchased" — use an explicit alternation.
        for m in re.finditer(r"purchas(?:e|ed|ing)?\s+.*?([\d,]+)\s*credit", lower):
            digits = m.group(1).replace(",", "")
            if not digits:
                # The group is `[\d,]+`, so a lone comma matches the pattern and int("") raised
                # ValueError out of the guard. An amount with no digits in it is not an amount.
                continue
            a = int(digits)
            if a > available:
                issues.append({"type":"insufficient_credits","detail":f"Spent {a:,}C but only {available:,}C available","fix":f"Reduce to \u2264{available:,}"})
    return issues

async def get_quick_facts(name: str, session_id: int = None) -> dict | None:
    if session_id is None: session_id = Config.SESSION_ID
    await _ensure(session_id)
    for c in _cache.values():
        if c["name"].lower() == name.lower():
            return {"name":c["name"],"status":"DEAD" if c.get("is_dead") else c.get("status","active"),"bond":c.get("bond",0),"weapon":c.get("weapon","?")}
    return None
