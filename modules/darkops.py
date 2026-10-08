#!/usr/bin/env python3
"""Dark Ops — Ported from Rust darkops.rs."""
from __future__ import annotations
import random
from core.db import Database
from core.session import require_session
from core.log import info

VALID_OPS = ["assassinate","sabotage","terror","planet_crack","enslave","purge","interrogate_hard"]
OP_COSTS = {"assassinate":(2000,5000,-40,10),"sabotage":(1000,2000,-20,5),"terror":(2000,1000,-30,15),
            "planet_crack":(10000,5000,-100,30),"enslave":(1000,500,-80,20),"purge":(5000,5000,-60,25),
            "interrogate_hard":(100,200,-10,5)}
MORALITY_COST = {"assassinate":-10,"sabotage":-5,"terror":-20,"planet_crack":-40,"enslave":-50,"purge":-60,"interrogate_hard":-10}

def _contains(text: str) -> str:
    """LIKE pattern matching `text` as a literal substring (pair with `ESCAPE '\\'`).

    @param text - user text.
    @returns the escaped `%text%` pattern.
    """
    return "%" + str(text).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _writable_session(session_id: int | None) -> int:
    """Resolve the session for one call and refuse a frozen campaign.

    @param session_id - caller's session; `None` resolves through `core.session.require_session`.
    @returns the resolved session id.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    from core.ooc import _refuse_frozen

    sid = session_id if session_id is not None else require_session(None)
    _refuse_frozen(sid)
    return sid


async def run_op(operation: str, target: str, session_id: int | None = None) -> dict:
    """Run one dark operation against a faction of this campaign.

    The target is resolved BEFORE anything is charged: a misspelled name used to
    match no faction, take the alloys and credits anyway, and report success.
    The operation is recorded now too — `list_darkops` reads `maya_rp.dark_ops`
    and nothing in the repo wrote to it, so the log door opened on an empty room.

    The cost is a guarded atomic charge in the same transaction as the faction, fear and log
    writes: the old read-then-debit let two concurrent calls both pass the check and drive the
    balance negative. The roll tests success first, then `exposed` in the top tail of the failing
    rolls; the old order reported the lowest rolls as exposure.

    @param operation - one of VALID_OPS.
    @param target - faction name fragment, matched literally.
    @param session_id - session; `None` resolves through `require_session`.
    @returns the outcome dict, or `{"error": ...}`.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    # An unknown operation writes nothing, so it is answered before the freeze check.
    if operation not in VALID_OPS: return {"error": f"Unknown: {operation}. Valid: {VALID_OPS}"}
    session_id = _writable_session(session_id)
    cost_a, cost_c, rep_delta, fear = OP_COSTS[operation]
    chance = 30 + random.randint(-10, 20)
    roll = random.randint(1, 100)
    if roll <= chance:
        outcome = "success"
    elif roll > 100 - chance // 5:
        outcome = "exposed"
    else:
        outcome = "failure"
    collat = random.randint(5, 50) if outcome == "success" else random.randint(20, 100) if outcome == "failure" else random.randint(50, 200)
    eff_rep = rep_delta if outcome == "success" else rep_delta // 2 if outcome == "failure" else rep_delta * 2
    morality = MORALITY_COST.get(operation, -5)

    async with Database.transaction() as conn:
        faction = await conn.fetchrow(
            "SELECT id, name FROM maya_rp.factions WHERE session_id=$1 "
            "AND LOWER(name) LIKE LOWER($2) ESCAPE '\\' ORDER BY id LIMIT 1",
            session_id, _contains(target))
        if not faction:
            return {"error": f"No faction matching '{target}' in session {session_id}"}
        charged = await conn.fetchrow(
            "UPDATE maya_rp.resources SET alloys=alloys-$1, credits=credits-$2, fear=COALESCE(fear,0)+$3 "
            "WHERE session_id=$4 AND alloys>=$1 AND credits>=$2 RETURNING alloys",
            cost_a, cost_c, fear, session_id)
        if charged is None:
            return {"error": f"Need {cost_a}a/{cost_c}c"}
        await conn.execute(
            "UPDATE maya_rp.factions SET reputation=GREATEST(reputation+$1,-100), "
            "fear_of_player=COALESCE(fear_of_player,0)+$2 WHERE id=$3 AND session_id=$4",
            eff_rep, fear, faction["id"], session_id)
        await conn.execute(
            "INSERT INTO maya_rp.dark_ops (session_id, target_type, target_name, operation, "
            "success_chance, collateral, reputation_delta, outcome, narrative, launched_at) "
            "VALUES ($1,'faction',$2,$3,$4,$5,$6,$7,$8,NOW())",
            session_id, faction["name"], operation, chance, collat, eff_rep, outcome,
            f"{operation} against {faction['name']}: {outcome}, collateral {collat}")
    info("darkops", f"{operation} → {target}: {outcome} (collat: {collat})")
    return {"operation": operation, "target": target, "outcome": outcome, "cost_alloys": cost_a, "cost_credits": cost_c, "rep_delta": eff_rep, "collateral": collat, "morality": morality}

async def list_darkops(session_id: int | None = None) -> list[dict]:
    if session_id is None: session_id = require_session(None)
    rows = await Database.fetch("SELECT operation, target_name, outcome, collateral, narrative FROM maya_rp.dark_ops WHERE session_id=$1 ORDER BY launched_at DESC LIMIT 15", session_id)
    return [dict(r) for r in rows]

async def run_tick(session_id: int = None) -> dict:
    """Report readiness. Resolves and guards the session like the writers.

    @param session_id - session; `None` resolves through `require_session`.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
    return {"status": "darkops_ready"}
