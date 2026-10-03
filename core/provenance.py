#!/usr/bin/env python3
"""Provenance — the ONLY entry point that answers 'why is X = Y' for engine facts.

Semantica-inspired (plan 2026-08-18). Zero LLM in this path. The LLM may
narrate a chain; it can never produce one.

Sources the fact path reads:

  1. the fact's current-state table, resolved through FACT_REGISTRY
  2. maya_rp.cabinet_decrees — the decisions and the chains that touch the fact,
     read through `core.decision.by_fact` and `core.decision.chain`

The unified maya_rp.decision_stream view is read by `core.decision.decisions`,
not on this path. maya_rp.events is not read here either: each decision arrives
with its `event_ids` and nothing resolves them, so a chain cites evidence the
answer does not show.
"""
from __future__ import annotations
from typing import Any, Optional
from core.db import Database
from core.config import Config

# fact key -> (table, column or expression, current-value query)
FACT_REGISTRY: dict[str, dict] = {
    "treasury": {
        "table": "resources", "column": "credits",
        "sql": "SELECT credits AS value FROM maya_rp.resources WHERE session_id=$1",
    },
    "credits": {"alias": "treasury"},
    "alloys": {
        "table": "resources", "column": "alloys",
        "sql": "SELECT alloys AS value FROM maya_rp.resources WHERE session_id=$1",
    },
    "fuel": {
        "table": "resources", "column": "fuel",
        "sql": "SELECT fuel AS value FROM maya_rp.resources WHERE session_id=$1",
    },
    "ships": {
        "table": "ships", "column": "status='active'",
        "sql": "SELECT COUNT(*) AS value FROM maya_rp.ships WHERE session_id=$1 AND status='active'",
    },
    "queens": {
        "table": "characters", "column": "is_spouse=true",
        "sql": "SELECT COUNT(*) AS value FROM maya_rp.characters WHERE session_id=$1 AND is_spouse=true",
    },
    "bonds": {
        "table": "bank_bonds", "column": "amount",
        "sql": "SELECT COUNT(*) AS value FROM maya_rp.bank_bonds WHERE session_id=$1 AND status='issued'",
    },
    "game_day": {
        "table": "sessions", "column": "game_day",
        "sql": "SELECT game_day AS value FROM maya_rp.sessions WHERE id=$1",
    },
    "mode": {
        "table": "narrative_pacing", "column": "mode",
        "sql": "SELECT mode AS value FROM maya_rp.narrative_pacing WHERE session_id=$1",
    },
}


async def resolve(fact: str) -> Optional[dict]:
    """Resolve fact key -> registry entry (follows aliases)."""
    key = fact.strip().lower()
    seen = set()
    while key in FACT_REGISTRY:
        if key in seen:
            break
        seen.add(key)
        entry = FACT_REGISTRY[key]
        if "alias" in entry:
            key = entry["alias"]
            continue
        return {**entry, "fact": key}
    return None


async def current_value(fact: str, session_id: Optional[int] = None) -> Any:
    """Current value of a fact, from its source table.

    An unknown fact is refused by name. `None` is the answer for a fact whose
    session has no row, and a key the registry does not hold must not read the
    same as a value that is empty.
    """
    sid = session_id or Config.SESSION_ID
    entry = await resolve(fact)
    if not entry:
        raise ValueError(f"unknown fact {fact!r}: not in FACT_REGISTRY")
    if "sql" not in entry:
        raise ValueError(f"fact {fact!r} has no source SQL in FACT_REGISTRY")
    row = await Database.fetchrow(entry["sql"], sid)
    return row["value"] if row else None


async def why(fact: str, session_id: Optional[int] = None,
              limit: int = 25) -> dict:
    """Answer 'why is X = Y': current value + touching decisions + chains.

    Returns:
      {fact, current_value, decision_count, decisions: [...], chains: [[...], ...]},
      or the same keys with an `error` for a fact key the registry does not hold.
    """
    sid = session_id or Config.SESSION_ID
    entry = await resolve(fact)
    if not entry:
        return {"fact": fact, "current_value": None, "decisions": [],
                "chains": [], "error": f"unknown fact '{fact}'"}
    value = await current_value(fact, sid)

    # decisions touching this fact (state_after / impact_deltas key match)
    from core.decision import by_fact, chain
    key = entry["fact"]
    decisions = await by_fact(sid, key, limit=limit)

    chains: list[list[dict]] = []
    for d in decisions[:5]:
        hops = await chain(sid, d["id"])
        if hops:
            chains.append(hops)

    return {
        "fact": key,
        "current_value": value,
        "decision_count": len(decisions),
        "decisions": decisions,
        "chains": chains,
    }


async def why_cli(fact: str, session_id: Optional[int] = None) -> str:
    """Human-readable rendering for the CLI/bridge."""
    r = await why(fact, session_id)
    lines = [f"PROVENANCE: {r['fact']} = {r['current_value']}",
             f"touching decisions: {r.get('decision_count', 0)}"]
    for d in r["decisions"]:
        lines.append(
            f"  [D{d['game_day'] or '?'}] #{d['id']} {d['actor']} · "
            f"{d['decision_type']} · {d['title'][:70]}"
        )
    for c in r["chains"]:
        lines.append("  chain:")
        for h in reversed(c):
            lines.append(
                f"    [D{h['game_day'] or '?'}] {h['actor']} · {h['decision_type']} · "
                f"{h['title'][:60]}"
            )
    return "\n".join(lines)
