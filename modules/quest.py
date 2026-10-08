#!/usr/bin/env python3
"""Quest — Ported from Rust quest.rs."""
from __future__ import annotations
import random
from core.db import Database
from core.log import info
from core.session import require_session

# Exactly the values `quests_quest_type_check` accepts, minus the ones with no generator flavour
# (companion, interrogation, dark, cosmic). 'science', 'delivery' and 'defense' violated the CHECK,
# so three draws in seven raised after the roll.
QUEST_TYPES = ["combat","exploration","diplomacy","trade","research","territory"]


class _Refuse(Exception):
    """Carries an error answer out of a transaction so every write in it rolls back."""

    def __init__(self, out: dict):
        super().__init__(out.get("error", ""))
        self.out = out


def _tag_count(tag) -> int:
    """Row count of an asyncpg command tag such as `UPDATE 1`; 0 when unreadable."""
    try:
        return int(str(tag).split()[-1])
    except (ValueError, IndexError):
        return 0


async def generate(session_id: int | None = None) -> dict:
    """Create one random active quest.

    @param session_id - session key; the active session when None.
    @returns {"id", "name", "type", "rewards"}.
    @raises FrozenSession when the campaign is frozen reference data.
    """
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    qtype = random.choice(QUEST_TYPES)
    name = f"{random.choice(['Operation','Mission','Task','Contract','Expedition'])} {random.choice(['Starfall','Ironhold','Shadowmere','Dawnbreak','Voidgate'])}"
    rewards = {"alloys": random.randint(500, 5000), "credits": random.randint(1000, 10000)}
    qid = await Database.fetchval(
        "INSERT INTO maya_rp.quests (session_id, title, quest_type, description, reward_alloy, reward_credit, status) "
        "VALUES ($1,$2,$3,$4,$5,$6,'active') RETURNING id",
        session_id, name, qtype, f"A {qtype} quest", rewards["alloys"], rewards["credits"])
    return {"id": qid, "name": name, "type": qtype, "rewards": rewards}

async def complete(quest_id: int, session_id: int | None = None) -> dict:
    """Pay out one quest exactly once.

    The claim `UPDATE ... SET status='completed' WHERE status='active' RETURNING` runs first, so two
    concurrent calls cannot both see 'active' and both pay: the second claims zero rows. The claim and
    the credit share one transaction, so a session with no `resources` row (session 5 has none) rolls
    the claim back and the quest stays open.

    @param quest_id - quest id.
    @param session_id - session key; the active session when None.
    @returns {"completed", "alloys", "credits"} or {"error": ...}.
    @raises FrozenSession when the campaign is frozen reference data.
    """
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    try:
        async with Database.transaction() as conn:
            # quests spells the rewards reward_alloy / reward_credit (singular).
            q = await conn.fetchrow(
                "UPDATE maya_rp.quests SET status='completed' "
                "WHERE id=$1 AND session_id=$2 AND status='active' "
                "RETURNING reward_alloy, reward_credit", quest_id, session_id)
            if q is None:
                row = await conn.fetchrow(
                    "SELECT status FROM maya_rp.quests WHERE id=$1 AND session_id=$2", quest_id, session_id)
                if row is None:
                    raise _Refuse({"error": "Quest not found"})
                raise _Refuse({"error": f"Quest {quest_id} is {row['status']}, not active — no reward paid"})
            tag = await conn.execute(
                "UPDATE maya_rp.resources SET alloys=alloys+$1, credits=credits+$2 WHERE session_id=$3",
                q["reward_alloy"] or 0, q["reward_credit"] or 0, session_id)
            if _tag_count(tag) == 0:
                info("quest", f"session {session_id} has no resources row — quest {quest_id} NOT paid")
                raise _Refuse({"error": f"No treasury row for session {session_id} — quest left open"})
    except _Refuse as refused:
        return refused.out
    return {"completed": True, "alloys": q["reward_alloy"], "credits": q["reward_credit"]}

async def run_tick(session_id: int | None = None) -> dict:
    """Report readiness; quests have no per-tick work.

    @raises FrozenSession when the campaign is frozen reference data.
    """
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    return {"status": "quest_ready"}
