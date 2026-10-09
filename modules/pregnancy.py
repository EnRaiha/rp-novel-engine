#!/usr/bin/env python3
"""Pregnancy Tracker — royal pregnancies, trimester progression, birth events.

Tracks mothers per session against game day. Each tick:
  - progresses trimester by elapsed time
  - flags 'due_soon' inside the final 30 days
  - fires a birth event when due_game_day passes
  - rolls a baby gender/name placeholder (name filled by narrative later)
"""
from __future__ import annotations
from core.db import Database
from core.config import Config
from core.log import info, error
from core.session import require_session

TRIMESTER_DAYS = [90, 180, 270]          # ends of trimester 1, 2, 3
DUE_SOON_WINDOW = 30                      # days before due → status 'due_soon'
BABY_NAMES = {
    "male": ["Ahmad", "Rayyan", "Danish", "Ibrahim", "Zafran", "Aqil", "Hariz", "Mikail"],
    "female": ["Aisyah", "Nur", "Sofea", "Hana", "Alya", "Zahra", "Inara", "Sarah"],
}


async def _game_day(session_id: int) -> int:
    return await Database.fetchval(
        "SELECT COALESCE(game_day, 1) FROM maya_rp.sessions WHERE id=$1", session_id
    ) or 1


async def register(session_id: int, mother_name: str, mother_id: int | None = None,
                   conceived_game_day: int | None = None, gestation_days: int = 270,
                   father_name: str = "King Izzat", notes: str = "") -> int:
    """Register a new pregnancy. Returns pregnancy id."""
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    if not str(mother_name or "").strip():
        raise ValueError(f"mother_name must be a non-empty string, got {mother_name!r}")
    if gestation_days < 1:
        raise ValueError(f"gestation_days must be at least 1, got {gestation_days}")
    gd = await _game_day(session_id)
    if conceived_game_day is None:
        conceived_game_day = gd
    due = conceived_game_day + gestation_days
    pid = await Database.fetchval(
        """INSERT INTO maya_rp.pregnancies
           (session_id, mother_id, mother_name, father_name, conceived_game_day,
            due_game_day, gestation_days, trimester, status, notes)
           VALUES ($1,$2,$3,$4,$5,$6,$7,1,'active',$8)
           RETURNING id""",
        session_id, mother_id, mother_name, father_name,
        conceived_game_day, due, gestation_days, notes,
    )
    info("pregnancy", f"Registered: {mother_name} due day {due}")
    return pid


async def status(session_id: int | None = None) -> list[dict]:
    """Full tracker report — every pregnancy for the session.

    Active and due_soon rows come first, then the births, each in due-day order.
    The progress fields used to be attached to `active` rows only, so a
    pregnancy lost its day count, ETA and percentage at exactly the moment it
    became `due_soon`.
    """
    session_id = require_session(session_id)
    gd = await _game_day(session_id)
    rows = await Database.fetch(
        """SELECT id, mother_name, father_name, conceived_game_day, due_game_day,
                  gestation_days, trimester, status, baby_name, baby_gender, notes,
                  birthed_game_day
           FROM maya_rp.pregnancies WHERE session_id=$1
           ORDER BY status = 'birthed', due_game_day ASC""",
        session_id,
    )
    out = []
    for r in rows:
        d = dict(r)
        if r["status"] in ("active", "due_soon"):
            days_pregnant = max(0, gd - r["conceived_game_day"])
            d["days_pregnant"] = days_pregnant
            d["days_to_due"] = max(0, r["due_game_day"] - gd)
            d["progress_pct"] = round(min(100, days_pregnant / max(1, r["gestation_days"]) * 100))
        out.append(d)
    return out


def _trimester_for(days_pregnant: int) -> int:
    for i, end in enumerate(TRIMESTER_DAYS, start=1):
        if days_pregnant < end:
            return i
    return 3


async def _roll_birth(session_id: int, gd: int, preg_id: int, mother_name: str) -> dict | None:
    """Deliver one pregnancy. Returns None when another tick already claimed it.

    The status claim and the birth event commit together: an error on the event
    leaves the pregnancy open for the next tick.
    """
    import random
    gender = random.choice(["male", "female"])
    name = random.choice(BABY_NAMES[gender])
    async with Database.transaction() as conn:
        claimed = await conn.fetchval(
            """UPDATE maya_rp.pregnancies
               SET status='birthed', baby_gender=$1, baby_name=$2, birthed_game_day=$3
               WHERE id=$4 AND session_id=$5 AND status IN ('active','due_soon')
               RETURNING id""",
            gender, name, gd, preg_id, session_id,
        )
        if claimed is None:
            return None
        await conn.execute(
            """INSERT INTO maya_rp.events (session_id, event_type, title, description, happened_at)
               VALUES ($1, 'birth', $2, $3, now())""",
            session_id,
            f"Birth — {mother_name}",
            f"{mother_name} gave birth to a {gender} child named {name} on game day {gd}.",
        )
    info("pregnancy", f"Birth: {mother_name} → {name} ({gender}), day {gd}")
    return {"mother": mother_name, "name": name, "gender": gender, "game_day": gd}


async def advance(session_id: int | None = None) -> dict:
    """Tick: progress trimesters, flag due_soon, fire births. Returns summary."""
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    gd = await _game_day(session_id)
    rows = await Database.fetch(
        """SELECT id, mother_name, conceived_game_day, due_game_day, gestation_days, trimester, status
           FROM maya_rp.pregnancies
           WHERE session_id=$1 AND status IN ('active','due_soon')""",
        session_id,
    )
    births = []
    errors = []
    updated = 0
    for r in rows:
        try:
            days_pregnant = max(0, gd - r["conceived_game_day"])
            new_status = r["status"]
            if gd >= r["due_game_day"]:
                birth = await _roll_birth(session_id, gd, r["id"], r["mother_name"])
                if birth is not None:
                    births.append(birth)
                continue
            if r["due_game_day"] - gd <= DUE_SOON_WINDOW:
                new_status = "due_soon"
            trimester = _trimester_for(days_pregnant)
            if trimester != r["trimester"] or new_status != r["status"]:
                tag = await Database.execute(
                    """UPDATE maya_rp.pregnancies SET trimester=$1, status=$2
                       WHERE id=$3 AND session_id=$4 AND status IN ('active','due_soon')""",
                    trimester, new_status, r["id"], session_id,
                )
                updated += int(tag.split()[-1])
        except Exception as e:
            error("pregnancy", f"pregnancy {r['id']} failed: {e}")
            errors.append({"id": r["id"], "error": str(e)})
    out = {"checked": len(rows), "updated": updated, "births": births}
    if errors:
        out["errors"] = errors
    return out


async def run_tick(session_id: int = None) -> dict:
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    try:
        result = await advance(session_id)
        info("pregnancy", f"Advanced: {result['checked']} tracked, {len(result['births'])} births")
        return result
    except Exception as e:
        error("pregnancy", f"tick error: {e}")
        return {"error": str(e)}
