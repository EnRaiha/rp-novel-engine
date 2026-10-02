#!/usr/bin/env python3
"""Magic accounting — what an act of magic costs the audit.

Canon: wiki/rp-dev/POWERS-WELL-AEGIS-SYSTEM-2026-10-02.md and the third mixing law in
wiki/rp-dev/WORLD-THREE-BLOCS-2026-10-02.md. Magic leaves data: every act prices into
the deviation the OOC engine already tracks, and into observer suspicion.

Two properties this module holds, both deliberate:

1. **The declaration is the Host's assertion.** The engine cannot read a turn and decide
   that magic happened; nothing in the prose proves it. The caller declares act keys, and
   the engine prices what it is told. A Host that never declares leaves the ledger silent,
   and that silence is a fact about the Host, not about the world.
2. **Arithmetic only.** No dice, no randomness, no LLM. Same keys in, same cost out.

Deliberate limits, so a single act can never end a campaign:

- One act is capped at `MAX_ACT_DEVIATION`. System Reclamation sits at the execution
  threshold (75 by default), so pricing can approach it but never jump it in one turn.
- Healing that the Well performs for free, such as the first skin layer turning aside
  heat, is priced at zero. `well_aegis.py` already refuses to spend reserve for it.
- An unknown act key is refused, not guessed. A guessed price would enter the ledger as
  if it were canon.

The reserve itself has no engine home yet. This module prices acts; it cannot refuse a
day whose reserve is already spent. That needs a power ledger, which is deferred.
"""
from __future__ import annotations

from typing import Iterable, Sequence

# Deviation charged per act, and the suspicion it raises in an observer.
# Keys are the acts canon names, not prose fragments.
ACT_TABLE: dict[str, tuple[int, int]] = {
    # the Well, by size. Restorative only: a body returns to its own baseline.
    "well:touch": (2, 1),
    "well:close_wound": (6, 2),
    "well:immersion": (10, 3),
    "well:field_lock": (12, 4),
    "well:heat": (0, 0),          # the vessel turns aside; the body's own toughness stops it
    # the Sight. Reading is the cheapest magic a person can do with an audience.
    "sight:read": (1, 1),
    "sight:mark": (3, 2),
    "sight:deep_read": (5, 2),
    # anything a later arc adds must be priced here, deliberately
    "casting:minor": (8, 3),
    "casting:major": (18, 5),
}

MAX_ACT_DEVIATION = 25
"""No single act bills more than this. The execution threshold is 75."""

WITNESS_SUSPICION_MULTIPLIER = 2
"""A witness holding an instrument doubles the suspicion, not the deviation.

Deviation is a fact about the act. Suspicion is a fact about being seen, so only the
second one scales with an audience.
"""

INSTRUMENT_RECORD_DEVIATION = 4
"""A witnessed act that an instrument can read raises a record, and the Panel files it.

The record is what a court accepts (LAW-COURTS-2026-10-02.md). It is not a second
penalty on the actor; it is the reason the case exists.
"""


class UnknownAct(ValueError):
    """Raised when an act key is not in ACT_TABLE. Guessing a price is not allowed."""


def price_act(act: str) -> tuple[int, int]:
    """Price one declared act.

    @param act - an act key from ACT_TABLE.
    @returns (deviation, suspicion), deviation capped at MAX_ACT_DEVIATION.
    @raises UnknownAct - the key is not canon-priced.
    """
    if act not in ACT_TABLE:
        raise UnknownAct(
            f"unknown magic act {act!r}; add it to ACT_TABLE in modules/magic_cost.py "
            f"or declare one of: {', '.join(sorted(ACT_TABLE))}"
        )
    deviation, suspicion = ACT_TABLE[act]
    return min(deviation, MAX_ACT_DEVIATION), suspicion


def price_acts(acts: Iterable[str], *, witnessed: bool = False,
               instrument: bool = False) -> dict[str, object]:
    """Price a turn's declared acts.

    @param acts - the act keys the Host declares for this turn.
    @param witnessed - true when a present character could see the act.
    @param instrument - true when a witness holds an instrument that can measure magic.
    @returns a dict: deviation, suspicion, record, priced (act -> (deviation, suspicion)),
        and unknown (keys refused, priced at zero). Nothing is written by this call.
    """
    priced: dict[str, tuple[int, int]] = {}
    unknown: list[str] = []
    deviation = 0
    suspicion = 0
    acts = list(acts)
    for act in acts:
        try:
            act_deviation, act_suspicion = price_act(act)
        except UnknownAct:
            unknown.append(act)
            continue
        priced[act] = (act_deviation, act_suspicion)
        deviation += act_deviation
        suspicion += act_suspicion
    if acts and witnessed and not unknown:
        suspicion *= WITNESS_SUSPICION_MULTIPLIER
    record = instrument and witnessed and deviation > 0
    return {
        "deviation": min(deviation, MAX_ACT_DEVIATION * len(acts)) if acts else 0,
        "suspicion": suspicion,
        "record": record,
        "record_deviation": INSTRUMENT_RECORD_DEVIATION if record else 0,
        "priced": priced,
        "unknown": unknown,
        "acts": acts,
    }


def declared_acts(value: Sequence[str] | str | None) -> list[str]:
    """Normalise a declared act input into a list of keys.

    @param value - None, one key, or a sequence of keys.
    @returns a list. Blank and whitespace-only entries are dropped.
    """
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    return [str(item).strip() for item in value if str(item).strip()]
