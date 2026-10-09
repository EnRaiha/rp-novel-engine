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
from core.session import require_session

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


class InsufficientResources(ValueError):
    """The ledger cannot pay a cost. Subclasses `ValueError`, the type callers already catch for a
    cost the ledger cannot charge, so an uncaught shortage reads as a refused cost and not a crash."""


def stochastic_round(value: float) -> int:
    """Round to an integer with an expected value equal to `value`.

    `progress_pct`, `spread_progress` and `eradication_campaigns.progress` are INTEGER columns and a
    tick adds well under 1 (Spore Drift: 0.25 per tick). `int()` truncated every such step to 0, so a
    site or infestation at that rate never moved. Rounding up with probability equal to the fraction
    keeps the long-run rate exact without a column change.

    @param value - a non-negative float.
    @returns floor(value), plus 1 with probability equal to the fractional part.
    """
    import random

    whole = int(value)
    return whole + (1 if random.random() < (value - whole) else 0)


def _cost_qty(res: str, qty) -> int:
    """A cost as the integer the ledger columns take.

    asyncpg rejects a float for an INTEGER or BIGINT parameter, and catalogue costs come out of jsonb,
    where `50000.0` is legal. A negative cost would credit the treasury, so it is refused.
    """
    if isinstance(qty, bool) or qty is None or qty != int(qty) or qty < 0:
        raise ValueError(f"cost for {res!r} must be a non-negative whole number, got {qty!r}")
    return int(qty)


async def _check_afford(session_id: int, costs: dict, conn=None) -> tuple:
    """Can this session pay? @returns (ok, reason when it cannot).

    A resource the ledger has no column for is refused with THAT reason, so a
    caller can tell a catalogue naming a missing column from a treasury that is
    short. Both used to read as "unknown resource".

    @param session_id - the campaign whose treasury is read.
    @param costs - resource column to quantity.
    @param conn - the caller's transaction connection. Omitted: the pool.
    """
    sql = f"SELECT {_RESOURCE_SELECT} FROM maya_rp.resources WHERE session_id = $1"
    r = await (conn or Database).fetchrow(sql, session_id)
    if not r:
        return False, "no resources"
    for res, qty in costs.items():
        if res not in r:
            return False, (f"'{res}' is not a ledger resource column "
                           f"(maya_rp.resources has no such column)")
        if (r[res] or 0) < qty:
            return False, f"need {qty} {res}, have {r[res] or 0}"
    return True, ""


async def _deduct_resources(session_id: int, costs: dict, conn=None) -> dict:
    """Take the cost, all of it or none of it.

    The debit is ONE `UPDATE ... WHERE session_id AND every column >= its cost RETURNING`. It used
    to run one `GREATEST(0, col - $n)` statement per resource after a separate check: two requests
    could both pass the check and spend the same credits, the clamp hid the shortfall, and a
    multi-resource cost could charge credits and then fail on alloys.

    @param session_id - the campaign whose treasury is charged.
    @param costs - resource column to quantity. Whole, non-negative numbers.
    @param conn - the caller's transaction connection, so the charge commits or rolls back with the
        effect it pays for. Omitted: the pool, one statement.
    @returns what was charged, per resource: NUMBERS only, so a caller can iterate `.items()`.
    @raises ValueError - a cost names a resource the ledger cannot charge, or a bad quantity.
        Refused before any charge.
    @raises InsufficientResources - the treasury is short, or the session has no resources row.
        Nothing is charged.
    @raises FrozenSession - the campaign is frozen reference data and maintenance is not armed.
    """
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    unknown = [res for res in costs if res not in RESOURCE_COLUMNS]
    if unknown:
        raise ValueError(
            f"cost names resources the ledger cannot charge: {unknown}. "
            f"Known columns: {list(RESOURCE_COLUMNS)}")
    charged = {res: _cost_qty(res, qty) for res, qty in costs.items()}
    due = {res: qty for res, qty in charged.items() if qty > 0}
    if not due:
        return charged
    sets, guards, args = [], [], [session_id]
    for res, qty in due.items():
        args.append(qty)
        sets.append(f"{res} = COALESCE({res}, 0) - ${len(args)}")
        guards.append(f"COALESCE({res}, 0) >= ${len(args)}")
    sql = (f"UPDATE maya_rp.resources SET {', '.join(sets)} "
           f"WHERE session_id = $1 AND {' AND '.join(guards)} "
           f"RETURNING {', '.join(due)}")
    runner = conn or Database
    row = await runner.fetchrow(sql, *args)
    if row is None:
        ok, why = await _check_afford(session_id, due, conn)
        raise InsufficientResources(why or f"the ledger changed under the charge for session {session_id}")
    from core.log import info as _log

    _log("economy", f"charged {due} from session {session_id}: balance now {dict(row)}")
    return charged
