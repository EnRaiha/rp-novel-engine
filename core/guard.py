#!/usr/bin/env python3
"""Contradiction Guard — checks output against known state before delivery. Catches wrong weapons, dead characters, wrong bonds."""
from __future__ import annotations
import re
from typing import Any
from core.db import Database
from core.config import Config

_cache: dict[int, dict] = {}
_cache_session: int | None = None

async def _ensure(session_id: int):
    global _cache, _cache_session
    if _cache_session == session_id and _cache:
        return
    _cache = {}
    _cache_session = session_id
    try:
        for r in await Database.fetch("SELECT id, name, status, role, weapon, bond, is_dead, death_cause FROM maya_rp.characters WHERE session_id=$1", session_id):
            _cache[r["id"]] = dict(r)
    except Exception:
        _cache = {}
        _cache_session = None

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
        # "purchas[ed]?" never matched "purchased" — use an explicit alternation.
        for m in re.finditer(r"purchas(?:e|ed|ing)?\s+.*?([\d,]+)\s*credit", lower):
            a = int(m.group(1).replace(",",""))
            if a > (res["credits"] or 0):
                issues.append({"type":"insufficient_credits","detail":f"Spent {a:,}C but only {res['credits']:,}C available","fix":f"Reduce to \u2264{res['credits']:,}"})
    return issues

async def get_quick_facts(name: str, session_id: int = None) -> dict | None:
    if session_id is None: session_id = Config.SESSION_ID
    await _ensure(session_id)
    for c in _cache.values():
        if c["name"].lower() == name.lower():
            return {"name":c["name"],"status":"DEAD" if c.get("is_dead") else c.get("status","active"),"bond":c.get("bond",0),"weapon":c.get("weapon","?")}
    return None
