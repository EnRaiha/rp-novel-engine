"""Deterministic economy physics for the TKG fleet: tiers, losses, transit.

Unit U8a, Fasa 4.1, 4.2 and 4.3. Pure functions only: no database, no files,
no randomness, no seed. Every function returns an exact value a test can assert.

Columns this reads against (the caller supplies the values, never the module):

    maya_rp.factions            systems_held, scale_class
    maya_rp.ships               tier, ship_type, crew, crew_current, class_id
    maya_rp.ship_classes        base_speed
    maya_rp.sector_connections  lane_type, distance, travel_time_hours

Measured 2026-10-02, session 3, read-only SQL through `scripts/cli.py query`:

    44,269 hulls, 75 owning factions, tiers t1 19,916 · t2 15,616 · t3 6,592
    · t4 2,139 · t5 6. `factions.scale_class = 'major'` holds 0 rows. 23 of the
    75 owners clear the major threshold in this file.

    437 hulls carry status destroyed (297) or lost (140), and every one of them
    has crew_current = 0. The complement is on ships.crew, 2 to 520.

    4,711 lanes. The three ordinary lane types satisfy
    `travel_time_hours = 24.0 * distance` on all 4,704 rows. Gate is 0.45 and
    hidden_thread is 0.40, on 7 rows.

    Median ship_classes.base_speed is 55.0 at tiers 1, 2, 3 and 4. Tier is not
    speed in this data: a Starforged worldship at base_speed 5 sits at tier 1.
    Travel time is therefore per class, with TIER_REF_SPEED as a declared
    reporting table only.

Formulas, written out so a test can check them:

    is_major(systems_held, hull_count)
        = systems_held >= 10 or hull_count >= 1000
        A threshold is auditable and does not rot. A name list does.

    tier_targets(N, major)             band sizes for N buildable hulls
        n4 = floor(0.02 N) if major else 0
        n3 = floor(0.17 N) - n4
        n2 = floor(0.67 N) - floor(0.17 N)
        n1 = N - floor(0.67 N)
        n1 + n2 + n3 + n4 = N exactly.

    tier_cap(major) = 4 if major else 3
        Tier 5 is frozen at its six existing prototypes and is never allocated.

    hull_loss_cost(hull_type)  = HULL_COST[hull_type]   (credit, alloy, days)
    crew_at_loss(crew, crew_current)
        = crew_current if crew_current > 0 else crew
        Measured: every destroyed or lost hull carries crew_current = 0.
    crew_recovered(c) = floor(0.7 c)        SURVIVABILITY, fleet_refill.py
    crew_replaced(c)  = c - crew_recovered(c)
        The 0.7 is shared with `scripts/fleet_refill.py`; the ROUNDING is not.
        That script writes `round(c * 0.7)`, which differs from this floor for
        26 crew sizes below 60 (5 aboard: 3 here, 4 there). The ledger floors.

    lane_hours(lane_type, delta)
        = 24.0 delta   standard, hazardous, unstable
        = 0.45 delta   gate
        = 0.40 delta   hidden_thread

    class_factor(v)   = 100 / v            100 is the corvette, the reference
    hull_transit(h, v)  = h * class_factor(v)
    fleet_transit(h, vs) = h * class_factor(min(vs))   a fleet moves at its slowest
    tier_transit(h, tier) = h * class_factor(TIER_REF_SPEED[tier])   reporting only

Nothing here reads the world. The caller supplies every number.
"""

from __future__ import annotations

from typing import Iterable, Sequence

# ─── 4.1 The buildable ladder ───────────────────────────────────────
MAJOR_SYSTEMS = 10
MAJOR_HULLS = 1000
# A faction is major at 10 systems or at 1000 hulls. The threshold is the rule:
# measured 2026-10-02, 23 of 75 session-3 owners clear it, and
# `factions.scale_class` holds zero 'major' rows. `ship_tiers.py` MAJOR_NAMES
# hardcodes six names and is the defect the threshold replaces.

MAJOR_TIER_CAP = 4
MINOR_TIER_CAP = 3
# The heaviest new tier a faction may hold. Tier 5 is not allocated to anyone.

FROZEN_TIER = 5
# Six hulls sit at tier 5 and stay there. New allocation tops out one below.

MYTHIC_FLOOR = 10
# Tier 10 and beyond are relics with no yard and no replacement. Nothing here
# allocates them, and nothing here flattens them either.

TIER4_DIVISOR = 50  # floor(N / 50) == floor(0.02 N), integer arithmetic
TIER3_PERCENT = 17
TIER2_PERCENT = 67
# Integer arithmetic, not float: floor(0.67 * N) drifts by one on large N.

BUILDABLE_TIERS = (1, 2, 3, 4)

# ─── 4.2 The loss ledger ────────────────────────────────────────────
HULL_COST: dict[str, tuple[int, int, int]] = {
    "battle_cruiser": (25_000_000, 12_000, 8),
    "medium_cruiser": (8_000_000, 4_000, 5),
    "frigate": (3_000_000, 1_500, 3),
    "interceptor": (1_500_000, 800, 2),
    "patrol_boat": (1_200_000, 600, 2),
    "spy_plane": (2_000_000, 900, 3),
    "bomber": (2_500_000, 1_200, 3),
    "science_small": (2_500_000, 1_000, 4),
    "science_large": (4_000_000, 2_000, 5),
    "supply_courier": (1_000_000, 500, 2),
    "fuel_tanker": (1_200_000, 600, 2),
    "repair_tender": (1_500_000, 700, 3),
    "ammo_ship": (1_200_000, 600, 3),
    "cargo_freighter": (1_500_000, 700, 3),
    "capital-ship": (40_000_000, 20_000, 12),
    "carrier": (30_000_000, 15_000, 10),
}
# type -> (credit, alloy, days). Mirrors `scripts/fleet_refill.py` COST, which is
# the live price list. The ledger reads it; the ledger does not own it.

DEFAULT_HULL_COST = (1_500_000, 800, 3)
# fleet_refill.py's own fallback for an unlisted hull type.

CREW_SURVIVABILITY_NUM = 7
CREW_SURVIVABILITY_DEN = 10
# 0.7. Battle of Gate 7 canon: 30% of the crew perish, the rest eject and return
# to the pool. `scripts/fleet_refill.py` SURVIVABILITY holds the same fraction.
# The two copies round it differently: that script uses round(), this module
# floors. On a 5-crew hull that is 4 survivors there and 3 here. The number is
# deliberately shared; the divergence is real and is reported, not hidden.

# ─── 4.3 Transit ────────────────────────────────────────────────────
HOURS_PER_UNIT = 24.0
GATE_HOURS_PER_UNIT = 0.45
HIDDEN_HOURS_PER_UNIT = 0.40

LANE_HOURS_PER_UNIT: dict[str, float] = {
    "standard": HOURS_PER_UNIT,
    "hazardous": HOURS_PER_UNIT,
    "unstable": HOURS_PER_UNIT,
    "gate": GATE_HOURS_PER_UNIT,
    "hidden_thread": HIDDEN_HOURS_PER_UNIT,
}
# Measured 2026-10-02 on all 4,711 session-3 lanes: ordinary lanes are exactly
# 24.0 hours per unit, gate is 18.0 hours at 40.0 units, hidden_thread is 96.0
# hours at 240.0 units.

HOURS_PER_DAY = 24.0

REFERENCE_SPEED = 100.0
# The corvette. `ship_classes.base_speed` 100 is the fastest common hull, so a
# corvette crosses a lane in the lane's own hours and everything else is slower.

TIER_REF_SPEED: dict[int, int] = {1: 100, 2: 100, 3: 90, 4: 80, 5: 70}
# Declared design constant, for reporting a tier figure only. It is NOT read
# from `ship_classes.base_speed`: the measured median is 55.0 at tiers 1, 2, 3
# and 4, so tier does not determine speed in this data. Replace with a real
# seed in a later unit, or report per class and drop the table.

ZERO_SPEED_MESSAGE = "base_speed must be greater than zero: a hull that cannot move cannot be timed"


# ─── 4.1 The buildable ladder ───────────────────────────────────────
def is_major(systems_held: int, hull_count: int) -> bool:
    """True when a faction holds 10 or more systems, or 1000 or more hulls."""
    if systems_held < 0:
        raise ValueError("systems_held cannot be negative")
    if hull_count < 0:
        raise ValueError("hull_count cannot be negative")
    return systems_held >= MAJOR_SYSTEMS or hull_count >= MAJOR_HULLS


def tier_cap(major: bool) -> int:
    """The heaviest new tier a faction may hold. Tier 5 is frozen, not given."""
    return MAJOR_TIER_CAP if major else MINOR_TIER_CAP


def tier_targets(hull_count: int, major: bool) -> dict[int, int]:
    """Band sizes for a faction's buildable hulls. The four sizes sum to N."""
    if hull_count < 0:
        raise ValueError("hull_count cannot be negative")
    over_two = hull_count // TIER4_DIVISOR
    over_three = (TIER3_PERCENT * hull_count) // 100
    over_two_band = (TIER2_PERCENT * hull_count) // 100
    four = over_two if major else 0
    three = over_three - four
    two = over_two_band - over_three
    one = hull_count - over_two_band
    return {1: one, 2: two, 3: three, 4: four}


def allocate_tiers(hull_count: int, major: bool) -> list[int]:
    """One tier per hull, best hull first. Rank 0 is the faction's best hull."""
    if hull_count < 0:
        raise ValueError("hull_count cannot be negative")
    targets = tier_targets(hull_count, major)
    plan: list[int] = []
    for tier in (4, 3, 2, 1):
        plan.extend([tier] * targets[tier])
    return plan


# ─── 4.2 The loss ledger ────────────────────────────────────────────
def hull_loss_cost(hull_type: str) -> tuple[int, int, int]:
    """Rebuild price of one hull: (credit, alloy, build days)."""
    return HULL_COST.get(hull_type, DEFAULT_HULL_COST)


def crew_at_loss(crew: int, crew_current: int) -> int:
    """Crew aboard a hull when it was lost.

    Measured 2026-10-02: all 437 destroyed and lost session-3 hulls carry
    crew_current = 0, so the complement on `ships.crew` is the only live number.
    crew_current is preferred when it is positive, because a damaged hull that
    really was short-handed should not be billed at full complement.
    """
    if crew < 0:
        raise ValueError("crew cannot be negative")
    if crew_current < 0:
        raise ValueError("crew_current cannot be negative")
    return crew_current if crew_current > 0 else crew


def crew_recovered(crew_lost: int) -> int:
    """Crew that eject and return to the pool. 0.7 of the complement, floored."""
    if crew_lost < 0:
        raise ValueError("crew_lost cannot be negative")
    return (CREW_SURVIVABILITY_NUM * crew_lost) // CREW_SURVIVABILITY_DEN


def crew_replaced(crew_lost: int) -> int:
    """Crew a refill must find. The survivors are not enough."""
    return crew_lost - crew_recovered(crew_lost)


def crew_split(crew_lost: int) -> dict[str, int]:
    """One loss, split into lost, recovered and replaced."""
    lost = crew_lost
    recovered = crew_recovered(lost)
    return {"lost": lost, "recovered": recovered, "replaced": lost - recovered}


def loss_cost(hull_type: str, crew: int, crew_current: int) -> dict[str, object]:
    """Every number one destroyed hull puts on the ledger.

    The ledger row a caller writes from this is one hull, not a fleet:
    `hulls` is 1 and the caller sums the rows.
    """
    credit, alloy, days = hull_loss_cost(hull_type)
    split = crew_split(crew_at_loss(crew, crew_current))
    return {
        "hull_type": hull_type,
        "credit_cost": credit,
        "alloy_cost": alloy,
        "build_days": days,
        "crew_lost": split["lost"],
        "crew_recovered": split["recovered"],
        "crew_replaced": split["replaced"],
    }


# ─── 4.3 Transit ────────────────────────────────────────────────────
def lane_hours(lane_type: str, distance: float) -> float:
    """Hours to cross one lane at the reference hull speed of 100."""
    if lane_type not in LANE_HOURS_PER_UNIT:
        raise ValueError(f"unknown lane_type {lane_type!r}")
    if distance < 0:
        raise ValueError("distance cannot be negative")
    return LANE_HOURS_PER_UNIT[lane_type] * distance


def class_factor(base_speed: float) -> float:
    """Slowdown against the corvette at 100. A zero-speed hull is refused."""
    if base_speed <= 0:
        raise ValueError(ZERO_SPEED_MESSAGE)
    return REFERENCE_SPEED / base_speed


def hull_transit_hours(hours: float, base_speed: float) -> float:
    """One hull crosses a lane that takes `hours` at the reference speed."""
    if hours < 0:
        raise ValueError("hours cannot be negative")
    return hours * class_factor(base_speed)


def fleet_transit_hours(hours: float, speeds: Sequence[float]) -> float:
    """A fleet crosses a lane at the pace of its slowest hull."""
    if not speeds:
        raise ValueError("a fleet needs at least one hull")
    return hull_transit_hours(hours, min(speeds))


def tier_transit_hours(hours: float, tier: int) -> float:
    """Reporting figure for a tier, from the declared TIER_REF_SPEED table."""
    if tier not in TIER_REF_SPEED:
        raise ValueError(f"tier {tier} is not in TIER_REF_SPEED")
    return hull_transit_hours(hours, TIER_REF_SPEED[tier])


def hours_to_days(hours: float) -> float:
    """Game days, on the 24-hour day both lane and travel columns use."""
    if hours < 0:
        raise ValueError("hours cannot be negative")
    return hours / HOURS_PER_DAY


def fitted_hours_per_unit(samples: Iterable[tuple[float, float]]) -> float:
    """Hours per unit fitted from (distance, hours) pairs.

    The second, independent derivation of the lane law: the declared constant is
    24.0, and this is what the rows themselves say. Sum of hours over sum of
    distance, so a mixed sample of ordinary lanes returns exactly 24.0.
    """
    total_distance = 0.0
    total_hours = 0.0
    seen = 0
    for distance, hours in samples:
        if distance < 0 or hours < 0:
            raise ValueError("distance and hours cannot be negative")
        total_distance += distance
        total_hours += hours
        seen += 1
    if seen == 0:
        raise ValueError("no samples")
    if total_distance <= 0:
        raise ValueError("total distance must be greater than zero")
    return total_hours / total_distance
