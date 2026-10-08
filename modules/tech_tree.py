#!/usr/bin/env python3
"""Tech Tree — Ported from Rust tech_tree.rs. Tech view, labs, assign scientists, research tick."""
from __future__ import annotations
import json
from typing import Any
from core.db import Database
from core.log import error, info
from core.session import require_session


class _Refuse(Exception):
    """Carries an error answer out of a transaction so every write in it rolls back."""

    def __init__(self, out: dict):
        super().__init__(out.get("error", ""))
        self.out = out


def _contains(text: str) -> str:
    """LIKE pattern matching `text` as a literal substring (pair with `ESCAPE '\\'`).

    A bare `%` or `_` in a name matched every row, so `build_lab("%")` put a lab on an arbitrary colony.

    @param text - user text.
    @returns the escaped `%text%` pattern.
    """
    return "%" + str(text).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _tag_count(tag) -> int:
    """Row count of an asyncpg command tag such as `UPDATE 1`; 0 when unreadable."""
    try:
        return int(str(tag).split()[-1])
    except (ValueError, IndexError):
        return 0

async def view_tech(session_id: int | None = None) -> list[dict]:
    """List this campaign's technologies.

    @param session_id - session key; the active session when None.
    @returns one dict per technology, ordered by field and tier.
    """
    session_id = require_session(session_id)
    rows = await Database.fetch(
        "SELECT id, name, field, tier, researched, research_progress, prerequisites, unlocks "
        "FROM maya_rp.technologies WHERE session_id=$1 ORDER BY field, tier", session_id)
    return [dict(r) for r in rows]

async def tech_info(tech_name: str, session_id: int | None = None) -> dict | None:
    """Find one technology by name fragment.

    @param tech_name - literal substring; `%` and `_` match themselves.
    @param session_id - session key; the active session when None.
    @returns the technology row, or None.
    """
    session_id = require_session(session_id)
    row = await Database.fetchrow(
        "SELECT id, name, field, tier, researched, research_progress, prerequisites, unlocks "
        "FROM maya_rp.technologies WHERE session_id=$1 AND LOWER(name) LIKE LOWER($2) ESCAPE '\\' LIMIT 1",
        session_id, _contains(tech_name))
    return dict(row) if row else None

async def build_lab(colony: str, name: str, field: str, session_id: int | None = None) -> dict:
    """Build a research lab on a colony for 2000 credits.

    The charge and the lab row commit together. The charge used to land first, so a lab insert that
    raised kept the credits.

    @param colony - literal colony name fragment.
    @param name - lab name.
    @param field - research field.
    @param session_id - session key; the active session when None.
    @returns the lab, or {"error": ...}.
    @raises FrozenSession when the campaign is frozen reference data.
    """
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    col = await Database.fetchrow(
        "SELECT id, name FROM maya_rp.colonies WHERE session_id=$1 AND LOWER(name) LIKE LOWER($2) ESCAPE '\\' LIMIT 1",
        session_id, _contains(colony))
    if not col: return {"error": f"Colony '{colony}' not found"}
    try:
        async with Database.transaction() as conn:
            # Guarded charge: two builds racing on 2000 credits cannot both pass a read-then-write check.
            tag = await conn.execute(
                "UPDATE maya_rp.resources SET credits=credits-2000 WHERE session_id=$1 AND credits>=2000",
                session_id)
            if _tag_count(tag) == 0:
                raise _Refuse({"error": "Need 2000 credits"})
            lab_id = await conn.fetchval(
                "INSERT INTO maya_rp.research_labs (colony_id, name, research_field) VALUES ($1,$2,$3) RETURNING id",
                col["id"], name, field)
    except _Refuse as refused:
        return refused.out
    info("tech_tree", f"Built lab '{name}' on {col['name']}")
    return {"lab_id": lab_id, "name": name, "colony": col["name"], "field": field}

async def assign_scientist(character: str, lab_id: int, specialty: str, session_id: int | None = None) -> dict:
    """Put a character in one of this campaign's labs.

    @param character - literal character name fragment.
    @param lab_id - lab id; it must belong to this campaign through its colony.
    @param specialty - scientist specialty.
    @param session_id - session key; the active session when None.
    @returns the assignment, or {"error": ...}.
    @raises FrozenSession when the campaign is frozen reference data.
    """
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    char = await Database.fetchrow(
        "SELECT id, name FROM maya_rp.characters WHERE session_id=$1 AND LOWER(name) LIKE LOWER($2) ESCAPE '\\' LIMIT 1",
        session_id, _contains(character))
    if not char: return {"error": f"Character '{character}' not found"}
    lab = await Database.fetchval(
        # `research_labs` carries no session_id: ownership runs through the colony that hosts it.
        # The bare id check let one campaign put its scientist in another campaign's lab.
        "SELECT rl.id FROM maya_rp.research_labs rl "
        "JOIN maya_rp.colonies col ON rl.colony_id = col.id AND col.session_id=$2 "
        "WHERE rl.id=$1",
        lab_id, session_id)
    if not lab: return {"error": f"Lab #{lab_id} not found in session {session_id}"}
    await Database.execute(
        "INSERT INTO maya_rp.scientist_assignments (character_id, lab_id, specialty, bonus) VALUES ($1,$2,$3,0.25) ON CONFLICT DO NOTHING",
        char["id"], lab_id, specialty)
    return {"character": char["name"], "lab_id": lab_id, "specialty": specialty, "bonus": 0.25}

async def list_labs(session_id: int | None = None) -> list[dict]:
    """List the labs on this campaign's colonies.

    @param session_id - session key; the active session when None.
    @returns one dict per lab and assignment.
    """
    session_id = require_session(session_id)
    rows = await Database.fetch(
        "SELECT rl.id, rl.name, rl.level, rl.research_field, rl.research_rate, "
        "c.name AS scientist, sa.specialty, sa.bonus "
        "FROM maya_rp.research_labs rl "
        "JOIN maya_rp.colonies col ON rl.colony_id = col.id AND col.session_id=$1 "
        "LEFT JOIN maya_rp.scientist_assignments sa ON sa.lab_id=rl.id "
        "LEFT JOIN maya_rp.characters c ON c.id=sa.character_id "
        "ORDER BY rl.id", session_id)
    return [dict(r) for r in rows]

async def run_tick(session_id: int | None = None) -> dict:
    """Advance every in-progress technology that the treasury can pay for.

    Each technology commits alone: a guarded charge and the progress write share one transaction, so
    an unpayable or failing technology leaves the treasury untouched. The charge used to land before
    the progress UPDATE, which bound a float to the integer column `research_progress` and raised
    after the money was gone. Resources were also read once, so the third technology was checked
    against a balance that the first two had already spent.

    @param session_id - session key; the active session when None.
    @returns {"active", "completed"}, the idle shape when nothing is in progress, or {"error": ...}
        after logging at error level when the tick raises.
    @raises FrozenSession when the campaign is frozen reference data.
    """
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    try:
        active = await Database.fetch(
            "SELECT id, name, field, tier, research_progress FROM maya_rp.technologies "
            "WHERE session_id=$1 AND researched=false AND research_progress>0 AND research_progress<100 "
            "ORDER BY research_progress ASC", session_id)
        res = await Database.fetchrow("SELECT alloys, credits, tech_score FROM maya_rp.resources WHERE session_id=$1", session_id)
        if not active or not res:
            # Same keys as the full answer: a caller reading `completed` got a KeyError on exactly
            # the session with nothing in progress.
            return {"active": 0, "completed": 0, "active_projects": 0}

        total_rate = await Database.fetchval(
            "SELECT COALESCE(SUM(rl.research_rate + COALESCE(sa.bonus,0.0)),0.0) FROM maya_rp.research_labs rl "
            "JOIN maya_rp.colonies col ON rl.colony_id=col.id AND col.session_id=$1 "
            "LEFT JOIN maya_rp.scientist_assignments sa ON sa.lab_id=rl.id", session_id) or 0
        # research_rate is numeric and arrives as Decimal; Decimal + float raises TypeError.
        base = max(1, min(30, (res["tech_score"] or 0) / 5))
        edu_mult = 1.0  # simplified
        total = (base + float(total_rate)) * edu_mult
        # research_progress is an integer column: asyncpg rejects a float bind.
        gain = int(round(10 + total))
        completed = 0
        for t in active:
            cost = (t["tier"] or 1) * 500
            half = cost // 2
            try:
                async with Database.transaction() as conn:
                    charged = await conn.execute(
                        "UPDATE maya_rp.resources SET alloys=alloys-$1, credits=credits-$2 "
                        "WHERE session_id=$3 AND alloys>=$1 AND credits>=$2", cost, half, session_id)
                    if _tag_count(charged) == 0:
                        continue
                    row = await conn.fetchrow(
                        "UPDATE maya_rp.technologies SET research_progress=LEAST(100, research_progress+$1), "
                        "researched=(research_progress+$1>=100) "
                        "WHERE id=$2 AND session_id=$3 AND researched=false RETURNING researched",
                        gain, t["id"], session_id)
                    if row is None:
                        # Researched or removed since the read: the raise rolls the charge back.
                        raise _Refuse({"error": f"technology {t['id']} is no longer researchable"})
                    if row["researched"]:
                        await conn.execute(
                            "UPDATE maya_rp.resources SET tech_score=tech_score+1 WHERE session_id=$1", session_id)
                        completed += 1
            except _Refuse as refused:
                info("tech_tree", f"tick skipped: {refused.out['error']}")
        info("tech_tree", f"Tick: {len(active)} active, {completed} completed")
        return {"active": len(active), "completed": completed}
    except Exception as e:
        error("tech_tree", f"tick failed for session {session_id}: {e}")
        return {"error": str(e)}
