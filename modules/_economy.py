#!/usr/bin/env python3
"""Resource accounting, in one place.

`_check_afford` and `_deduct_resources` existed as byte-identical copies in `infrastructure.py`,
`space_horror.py` and `megastructures_ports.py`. Three copies of a ledger rule is three places for
the rule to drift, and the column whitelist is the part that must not drift: an unlisted resource is
silently skipped by the deduction, so a building could be paid for with nothing at all.

Extracted 2026-10-03 during the caller-less review, when `infrastructure.py` came up for wiring.
"""
from __future__ import annotations

from core.db import Database

#: Every column a cost may name. Interpolated into SQL, so it is a whitelist and not a suggestion.
RESOURCE_COLUMNS = ("credits", "alloys", "fuel", "dream_essence", "rare_earth",
                    "starsteel", "void_crystal", "aetherium")


async def _check_afford(session_id: int, costs: dict) -> tuple:
    """Can this session pay? @returns (ok, reason when it cannot)."""
    r = await Database.fetchrow(
        "SELECT credits, alloys, fuel, dream_essence, rare_earth, starsteel, void_crystal, aetherium "
        "FROM maya_rp.resources WHERE session_id = $1", session_id
    )
    if not r:
        return False, "no resources"
    for res, qty in costs.items():
        if res not in r:
            return False, f"unknown resource '{res}'"
        if (r[res] or 0) < qty:
            return False, f"need {qty} {res}, have {r[res] or 0}"
    return True, ""


async def _deduct_resources(session_id: int, costs: dict) -> dict:
    """Take the cost.

    @returns what was actually charged, per resource. The old body returned nothing, so a session with
    no `resources` row paid nothing and was charged nothing, with no error and no trace — session 5 was
    in exactly that state. A caller can now see which resources were charged and which were skipped.
    """
    charged: dict[str, float] = {}
    skipped: list[str] = []
    for res, qty in costs.items():
        if res not in RESOURCE_COLUMNS:
            skipped.append(res)
            continue
        await Database.execute(
            f"UPDATE maya_rp.resources SET {res} = GREATEST(0, {res} - $1) WHERE session_id = $2",
            qty, session_id,
        )
        charged[res] = qty
    if skipped:
        charged["#skipped"] = skipped  # type: ignore[assignment]
    return charged
