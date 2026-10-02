"""Communications latency, the unity ceiling, and stance drift by distance.

Unit U9, Fasa 5.1, 5.2 and 5.3. Pure arithmetic only: no database, no files,
no randomness, no seed, no clock. Every function returns an exact value a test
can assert. The caller supplies every row.

Columns this reads against (the caller supplies the values, never the module):

    maya_rp.sector_connections  lane_type, distance, travel_time_hours
    maya_rp.factions            systems_held, origin, doctrine, stance_score
    maya_rp.ships               faction_id (counted by the caller)

The lane law is **reused, not restated**. `lane_hours` and `HOURS_PER_DAY` are
imported from `modules.economy_physics`, so this module holds no second copy of
24.0, 0.45 or 0.40. `voyage.py` already carries two unreconciled rates (24.0
hours per unit grid and 710 ly per day); a third would be a defect.

Formulas, written out so a test can check them:

    lane_latency_days(lane_type, delta, sigma)
        = lane_hours(lane_type, delta) / (HOURS_PER_DAY * sigma)
    path_latency_days(lanes, sigma)
        = sum of lane_latency_days over the lanes of one simple path
    mean_latency_days(days)      = arithmetic mean
    latency_days_ceil(days)      = ceil(days)
    arrival_game_day(d, days)    = d + latency_days_ceil(days)
    lag_fraction(days)           = min(1, days / LATENCY_REFERENCE_DAYS)

    pressure_default(s)          = clamp_0^1((1 - s) / 2)
    grip(N, H)                   = 0 if H < 1 else min(1, (N / (1 + H)) / 500)
    reach(H)                     = log10(1 + H) / 2
    span(H, lag)                 = 0.60 reach(H) + 0.40 min(1, lag)

    unity(N, H, s, origin, doctrine, pressure, lag)
        = clamp_0^1( base(origin) + gain(origin) * P
                     + doc(doctrine) + 0.10 |s| + 0.15 grip(N, H) - span(H, lag) )

    drift(score, lag)            = sgn(score) * max(0, |score| - 0.35 min(1, lag))

    bands, on unity: 0.75 unanimous, 0.55 united, 0.40 strained,
                     0.25 divided, else fractured.

Measured 2026-10-02, read-only SQL through `scripts/cli.py query`:

    76 faction rows, 75 live (`Setia Empire (Kingdom)` id 1 carries
    `status = 'not_yet_established'`). 44,277 hulls across 75 owners. Origins
    natural 3, imposed 66, sponsored 7. Holdings 0 -> 40 rows, 1..3 -> 16,
    4..9 -> 0, 10..30 -> 13, 31+ -> 7. Unity over all 76 rows, pressure at
    its stance-derived default and lag 0: fractured 25, divided 4, strained 8,
    united 38, unanimous 1. Mean 0.4023, min 0.0221, max 0.8412.

    4,711 lanes on session 3, 0 on session 5. The ordinary lane law holds on
    4,704 rows.

Nothing here reads the world. The caller supplies every number.
"""

from __future__ import annotations

import math
from typing import Iterable, Mapping, Sequence

from modules.economy_physics import HOURS_PER_DAY, lane_hours

# ─── 5.1 The signal multiplier ──────────────────────────────────────
SIGNAL_COURIER = 1.0
# A message crosses a lane at the pace of a hull. This introduces zero new
# physics: the lane law is already exact on 4,704 of 4,711 rows, and the setting
# has no FTL comm, only courier boats. Every other value would be a second rate
# beside the first.

SIGNAL_ANSIBLE = 10.0
# Declared design constant, signed by the orchestrator on 2026-10-02. It turns
# the worst crossing on the session-3 map from 33.185 days into 3.318 days. It is
# unsigned by data: no faction flag, no relay row, no bandwidth column exists.
# It is therefore unreachable without an explicit `sigma` argument, and no
# default path in this module or in `faction_stance.py` uses it.

LATENCY_REFERENCE_DAYS = 30.0
# One month on the 365-day calendar. An order that takes a month is an order the
# holding can ignore, so a full lag is one month of travel.

LANE_TYPES: tuple[str, ...] = ("standard", "hazardous", "unstable", "gate", "hidden_thread")
# The five lane types `economy_physics.LANE_HOURS_PER_UNIT` carries. Named here so
# a caller can validate a row without importing that table, and so a test can
# assert the two lists are the same list.

# ─── 5.2 The unity ceiling ──────────────────────────────────────────
ORIGIN_BASE: dict[str, float] = {
    "natural": 0.20,
    "imposed": 0.50,
    "sponsored": 0.45,
}
# A natural faction has no founder and no flag, so it starts loose. An imposed
# one has a decree holding it, so it starts tight, but only at 0.50: at the
# earlier draft value 0.62 the mean unity over the 76 rows read 0.505 and 42 of
# 75 factions read united, almost all of them imposed pirate bands with no
# ground. At 0.50 the mean is 0.4023 and the band the row earns is closer to the
# row. A sponsored faction sits between: it has a patron, not a decree.

ORIGIN_PRESSURE_GAIN: dict[str, float] = {
    "natural": 0.55,
    "imposed": 0.05,
    "sponsored": -0.10,
}
# The design rule as a number. A natural faction gains 0.55 of unity by being
# pressed. An imposed one barely moves, because a decree does not need an enemy.
# A sponsored one loses, because its patron is the first thing to leave.

DOCTRINE_UNITY: dict[str, float] = {
    "science_tech": 0.05,
    "magic": -0.05,
    "balance": 0.02,
    "unaligned": -0.10,
}
# Records and chains of command survive distance. Magic does not scale: one
# blessing goes to one person, not to one fleet, so a magic faction holds its
# holdings least well. Unaligned holds nothing together on purpose.

STANCE_UNITY_WEIGHT = 0.10
# A faction with a declared bearing has a reason to close ranks. The magnitude
# is used, so a declared enemy is as coherent as a declared friend and neutral
# reads as undecided.

GRIP_WEIGHT = 0.15
GRIP_HULLS_REF = 500.0
# Hulls hold ground, but they are capped low so holdings dominate. The reference
# is hulls per (holding + 1), measured: TKG 1,040, The Limbah Compact 1,445,
# Iron Concord 34.3. The gate below is what makes the Compact quarrel unpressed.

REACH_DIVISOR = 2.0
# log10(1 + H) / 2 normalises 100 holdings to 1.0, so each extra voice costs
# less than the first.

SPAN_REACH_WEIGHT = 0.60
SPAN_LAG_WEIGHT = 0.40
# Holdings enter logarithmically and distance enters linearly, in one span. The
# lag half is inert at lag 0: the term is present, and it contributes nothing.

DEFAULT_ORIGIN = "imposed"
DEFAULT_DOCTRINE = "unaligned"
# The model's existing fallback style, matching `faction_stance.py`, which reads
# a null `doctrine` as unaligned and a null `origin` as imposed.

UNITY_EDGES: tuple[tuple[float, str], ...] = (
    (0.75, "unanimous"),
    (0.55, "united"),
    (0.40, "strained"),
    (0.25, "divided"),
)
UNITY_FLOOR_BAND = "fractured"
# Five declared edges. A row on an edge is reproducible because `unity` rounds
# to 4 decimals before the band lookup, the same discipline as `faction_stance`.

# ─── 5.3 Stance drift by distance ───────────────────────────────────
DRIFT_PER_FULL_LAG = 0.35
# Score points subtracted from |score| at a full lag. The widest central band in
# `faction_stance.BANDS` is 0.30 wide, so a full-lag holding must move at least
# one band. 0.35 clears it with margin without turning a maximally distant enemy
# neutral, which is what 0.60 would do (The Den -1.0000 -> -0.4000 wary).
# `faction_stance.WEIGHTS` publishes it as `drift:lag`, marked as a second
# normalisation stage rather than a raw-sum term.

SCORE_FLOOR = -1.0
SCORE_CEILING = 1.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _clamp01(value: float) -> float:
    return _clamp(value, 0.0, 1.0)


def _number(value, default: float = 0.0) -> float:
    """A column value as a float. A missing or unparseable value reads default."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ─── 5.1 Latency ────────────────────────────────────────────────────
def lane_latency_days(lane_type: str, distance: float, sigma: float = SIGNAL_COURIER) -> float:
    """Days for a signal to cross one lane.

    @param lane_type - one of LANE_TYPES, checked by `economy_physics`.
    @param distance - the lane's stored distance in units.
    @param sigma - the signal multiplier. Courier 1.0 is the default; 10.0 is
                   the declared ansible and must be passed explicitly.
    """
    if sigma <= 0:
        raise ValueError("sigma must be greater than zero: a signal that cannot move cannot be timed")
    return lane_hours(lane_type, distance) / (HOURS_PER_DAY * sigma)


def latency_from_hours(hours: float, sigma: float = SIGNAL_COURIER) -> float:
    """Days for a stored `travel_time_hours`, divided by the signal multiplier."""
    if hours < 0:
        raise ValueError("hours cannot be negative")
    if sigma <= 0:
        raise ValueError("sigma must be greater than zero: a signal that cannot move cannot be timed")
    return hours / (HOURS_PER_DAY * sigma)


def path_latency_days(lanes: Iterable[Mapping[str, object]], sigma: float = SIGNAL_COURIER) -> float:
    """Days for a signal to cross one simple path.

    Each lane is a mapping with `lane_type` and `distance`, which is the shape
    `maya_rp.sector_connections` returns. The sum is over the path the caller
    chose; this module does not route. The existing router
    `celestial.dijkstra_route` weights every lane at 100 fuel, so it minimises
    hops and not hours, and it is not used here.
    """
    total = 0.0
    for lane in lanes:
        total += lane_latency_days(str(lane["lane_type"]), _number(lane["distance"]), sigma)
    return total


def mean_latency_days(latencies: Sequence[float]) -> float:
    """Arithmetic mean of one faction's holding-to-capital latencies."""
    if not latencies:
        raise ValueError("a mean needs at least one latency")
    return sum(latencies) / len(latencies)


def latency_days_ceil(days: float) -> int:
    """Whole days, rounded up. Prose needs a whole day; a mean needs a fraction."""
    if days < 0:
        raise ValueError("days cannot be negative")
    return math.ceil(days)


def arrival_game_day(send_day: int, days: float) -> int:
    """The game day a message sent on `send_day` arrives."""
    return send_day + latency_days_ceil(days)


def lag_fraction(days: float) -> float:
    """A latency as a fraction of one reference month, capped at 1.0.

    The one lag function 5.2 and 5.3 share. `faction_stance` imports this, so a
    full lag means the same thing in both models.
    """
    if days < 0:
        raise ValueError("days cannot be negative")
    return min(1.0, days / LATENCY_REFERENCE_DAYS)


# ─── 5.2 Unity ──────────────────────────────────────────────────────
def pressure_default(stance_score: float) -> float:
    """External pressure derived from the row's stance.

    A faction that faces a hostile power has a reason to hold together. The row
    carries no pressure column and cannot: pressure is situational. `stance_score`
    is the nearest thing on the row, and a caller with a scene value overrides it.
    """
    return _clamp01((1.0 - _clamp(_number(stance_score), SCORE_FLOOR, SCORE_CEILING)) / 2.0)


def grip(hull_count: int, systems_held: int) -> float:
    """How hard the hulls hold the holdings, 0..1.

    A faction with no holdings gets zero: hulls garrison ground, and the engine
    records no ground for that faction to garrison. Without the gate a faction
    with 1,445 hulls and no system would read a full grip and would never quarrel
    with itself.
    """
    if systems_held < 1:
        return 0.0
    return _clamp01((_number(hull_count) / (1.0 + systems_held)) / GRIP_HULLS_REF)


def reach(systems_held: int) -> float:
    """log10(1 + H) / 2, the logarithmic cost of an extra holding."""
    if systems_held < 0:
        raise ValueError("systems_held cannot be negative")
    return math.log10(1.0 + systems_held) / REACH_DIVISOR


def span(systems_held: int, lag: float = 0.0) -> float:
    """Unity lost to span of command: holdings plus distance.

    Inert at lag 0. The distance half enters only through `lag_fraction`.
    """
    return SPAN_REACH_WEIGHT * reach(systems_held) + SPAN_LAG_WEIGHT * _clamp01(lag)


def unity(
    hull_count: int,
    systems_held: int,
    stance_score: float,
    origin: str = DEFAULT_ORIGIN,
    doctrine: str = DEFAULT_DOCTRINE,
    pressure: float | None = None,
    lag: float = 0.0,
) -> float:
    """The unity ceiling of one faction row, 0..1, rounded to 4 decimals.

    @param hull_count - hulls owned, from `maya_rp.ships.faction_id`.
    @param systems_held - `maya_rp.factions.systems_held`.
    @param stance_score - `maya_rp.factions.stance_score`, -1..1.
    @param origin - natural, imposed or sponsored.
    @param doctrine - science_tech, magic, balance or unaligned.
    @param pressure - 0..1, or None to derive it from the stance.
    @param lag - fraction from `lag_fraction`, 0..1. Inert at 0.0.
    """
    if origin not in ORIGIN_BASE:
        origin = DEFAULT_ORIGIN
    if doctrine not in DOCTRINE_UNITY:
        doctrine = DEFAULT_DOCTRINE
    p = pressure_default(stance_score) if pressure is None else _clamp01(_number(pressure))
    value = (
        ORIGIN_BASE[origin]
        + ORIGIN_PRESSURE_GAIN[origin] * p
        + DOCTRINE_UNITY[doctrine]
        + STANCE_UNITY_WEIGHT * abs(_clamp(_number(stance_score), SCORE_FLOOR, SCORE_CEILING))
        + GRIP_WEIGHT * grip(hull_count, systems_held)
        - span(systems_held, lag)
    )
    return round(_clamp01(value), 4)


def unity_band(value: float) -> str:
    """The band a rounded unity value falls in."""
    for edge, name in UNITY_EDGES:
        if value >= edge:
            return name
    return UNITY_FLOOR_BAND


# ─── 5.3 Drift ──────────────────────────────────────────────────────
def drift(score: float, lag: float = 0.0) -> float:
    """Shrink a stance score toward zero at distance.

    The capital declares a line. A holding a month away cannot be held to it, so
    what the model reads is the holding's own position, which is the one nobody
    declared: zero. The shrink is deterministic and sign-safe, so a faction the
    capital calls friendly never becomes hostile just by being far away.

    @param score - the clamped score from `faction_stance`.
    @param lag - fraction from `lag_fraction`. At 0.0 the score is returned
                 unchanged, which is what makes the install inert.
    """
    score = _number(score)
    if score == 0.0 or lag <= 0.0:
        return score
    magnitude = max(0.0, abs(score) - DRIFT_PER_FULL_LAG * _clamp01(lag))
    if magnitude == 0.0:
        return 0.0
    return magnitude if score > 0 else -magnitude
