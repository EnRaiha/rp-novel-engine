#!/usr/bin/env python3
"""Adventures — Ported from Rust adventure.rs."""
from __future__ import annotations
import random
from core.db import Database
from core.log import info
from core.session import require_session

ENCOUNTER_TYPES = ["merchant","pirate","derelict","anomaly","distress","trade_fleet","refugee","ambush","signal","artifact"]

#: The outcomes `resolve` understands. Anything else is refused rather than
#: reported as a resolved encounter that paid nothing.
OUTCOMES = ("success", "failure")


def _writable_session(session_id: int | None) -> int:
    """Resolve the session for one call and refuse a frozen campaign.

    Sessions 3 and 5 are reference data; a writer that skipped this check mutated them.

    @param session_id - caller's session; `None` resolves through `core.session.require_session`.
    @returns the resolved session id.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    from core.ooc import _refuse_frozen

    sid = require_session(session_id)
    _refuse_frozen(sid)
    return sid

async def generate(session_id: int | None = None) -> dict:
    """Roll one encounter. Read-only, so a frozen campaign may call it.

    @param session_id - campaign; `None` resolves through `require_session`.
    """
    session_id = require_session(session_id)
    etype = random.choice(ENCOUNTER_TYPES)
    system = await Database.fetchval("SELECT system_name FROM maya_rp.territory WHERE session_id=$1 ORDER BY RANDOM() LIMIT 1", session_id) or "Unknown"
    gold = random.randint(100, 2000) if etype in ("merchant","trade_fleet") else 0
    combat = etype in ("pirate","ambush")
    return {"type": etype, "system": system, "gold_reward": gold, "combat": combat, "description": f"A {etype} encounter at {system}"}

async def resolve(adventure_type: str, outcome: str, session_id: int | None = None) -> dict:
    """Pay out one encounter. The reward does NOT vary by encounter type.

    @param adventure_type - the type `generate` rolled. It is echoed back so the
        caller can narrate it; it does not price the reward, and the docstring
        says so rather than leaving a caller to assume it does.
    @param outcome - "success" or "failure"; anything else is refused, because a
        misspelling used to read as a resolved encounter that paid nothing.
    @raises ValueError - the outcome is not one this module knows.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of {OUTCOMES}, got {outcome!r}")
    if outcome == "success":
        reward = random.randint(500, 5000)
        tag = await Database.execute(
            "UPDATE maya_rp.resources SET credits=credits+$1 WHERE session_id=$2",
            reward, session_id)
        if isinstance(tag, str) and tag.split()[-1:] == ["0"]:
            info("adventures", f"session {session_id} has no resources row — "
                               f"{reward}C reward NOT paid")
            return {"reward": 0, "outcome": "success", "adventure_type": adventure_type,
                    "error": f"No treasury row for session {session_id}"}
        return {"reward": reward, "outcome": "success", "adventure_type": adventure_type}
    return {"reward": 0, "outcome": outcome, "adventure_type": adventure_type}

async def run_tick(session_id: int | None = None) -> dict:
    """No-op tick. @raises core.ooc.FrozenSession - the campaign is frozen."""
    _writable_session(session_id)
    return {"status": "adventures_ready"}
