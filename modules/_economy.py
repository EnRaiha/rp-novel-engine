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
#:
#: `maya_rp.resources` has NO `food` column, and the live catalogues charge `food`:
#: infrastructure_types id 21 (Bio-dome, `{"food": 100, "alloys": 600}`),
#: megastructure_types and port_types. Every build those costs belong to is refused
#: today, so the Bio-dome cannot be constructed at all. Reported to the lead: the
#: fix is a migration that adds the column or a catalogue edit that drops it, and
#: neither belongs to the ledger.
RESOURCE_COLUMNS = ("credits", "alloys", "fuel", "dream_essence", "rare_earth",
                    "starsteel", "void_crystal", "aetherium")

#: One source for the SELECT list and the whitelist. They were two copies of the
#: same eight names, so a column added to one and not the other read as missing.
_RESOURCE_SELECT = ", ".join(RESOURCE_COLUMNS)


async def _check_afford(session_id: int, costs: dict) -> tuple:
    """Can this session pay? @returns (ok, reason when it cannot).

    A resource the ledger has no column for is refused with THAT reason, so a
    caller can tell a catalogue naming a missing column from a treasury that is
    short. Both used to read as "unknown resource".
    """
    r = await Database.fetchrow(
        f"SELECT {_RESOURCE_SELECT} FROM maya_rp.resources WHERE session_id = $1", session_id
    )
    if not r:
        return False, "no resources"
    for res, qty in costs.items():
        if res not in r:
            return False, (f"'{res}' is not a ledger resource column "
                           f"(maya_rp.resources has no such column)")
        if (r[res] or 0) < qty:
            return False, f"need {qty} {res}, have {r[res] or 0}"
    return True, ""


async def _deduct_resources(session_id: int, costs: dict) -> dict:
    """Take the cost.

    @returns what was actually charged, per resource: NUMBERS only, so a caller
    can iterate `.items()` without meeting a bookkeeping entry.

    A cost naming anything outside the whitelist is REFUSED before a single
    charge, and named. It used to be skipped and reported under a "#skipped"
    string key, which is both a mixed-type dict and a building paid for with
    nothing at all. Refusing up front also means a rejected cost cannot leave a
    half-charged treasury behind.
    """
    unknown = [res for res in costs if res not in RESOURCE_COLUMNS]
    if unknown:
        raise ValueError(
            f"cost names resources the ledger cannot charge: {unknown}. "
            f"Known columns: {list(RESOURCE_COLUMNS)}")
    charged: dict[str, float] = {}
    for res, qty in costs.items():
        await Database.execute(
            f"UPDATE maya_rp.resources SET {res} = GREATEST(0, {res} - $1) WHERE session_id = $2",
            qty, session_id,
        )
        charged[res] = qty
    return charged
