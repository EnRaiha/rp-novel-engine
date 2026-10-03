#!/usr/bin/env python3
"""Voyage transit — real travel-time accounting between systems.

Narration says "we sail" — the ENGINE books the days.
Two canonical rates, both evidence-anchored:

  GRID_HOURS_PER_UNIT = 24.0   (the lane law, owned by modules.economy_physics)
  LY_PER_DAY          = 710.0  (canon: Serein->Mastika 28,400 ly in 40 days)

register(): create a voyage, automagically compute travel time + arrival day from
            coordinates/distance/ly. Game clock advances by exactly that many days.
advance() : tick hook — mark voyages arrived when game_day >= arrive_day.
"""
from __future__ import annotations
import math
import random
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info
from modules.economy_physics import HOURS_PER_DAY, HOURS_PER_UNIT

# One owner for the lane law: `economy_physics` derives it from all 4,704
# ordinary session-3 lanes and `unity.py` imports the same constant. This module
# restated 24.0 under its own name, which is the drift `unity.py` calls a defect.
GRID_HOURS_PER_UNIT = HOURS_PER_UNIT
LY_PER_DAY = 710.0                # canon anchor: 28,400 ly / 40 days

# ── Gate tolls (2026-08-15 Izzat canon) ──
# Public price is standardized at 25,000C per crossing (economy.GATE_TOLL_RATE,
# paid by third parties → treasury income). Setia's own fleet pays only the
# INTERNAL cost — a smaller share (20%) that covers gate maintenance/garrison.
# Gates need NO exotic matter (wormholes only).
GATE_INTERNAL_COST_SHARE = 0.20

# ── Wormhole / black hole / white hole (2026-08-15, Izzat's theory build) ──
# Wormholes (Einstein-Rosen / Morris-Thorne): A↔B pairs, ~90% travel cut, need
#   exotic matter to stay open — without upkeep they decay and can collapse
#   mid-transit. Black holes: slingshot (Oberth) ×0.6 travel but roll vs
#   hazard (fail → event horizon), plus time dilation (1 ship-day = N game
#   days). White holes: exit-only — swallowed ships can emerge here.
WORMHOLE_COLLAPSE_PCT = 30        # decaying wormhole: d100 <= 30 → collapse
BLACK_HOLE_SLINGSHOT_DC = 0.75    # d100 roll vs hazard*100: >= pass → clean


def _num(value, default: float) -> float:
    """Read a numeric column, falling back only when the column is NULL.

    `value or default` treats a real 0 as missing: a wormhole at stability 0,
    a slingshot multiplier of 0, a hazard of 0. Tests assert the difference.
    """
    return default if value is None else float(value)


async def wormhole_status(session_id: int | None = None) -> list[dict]:
    """List all wormholes with their pair endpoints and health."""
    if session_id is None:
        session_id = Config.SESSION_ID
    return await Database.fetch(
        """SELECT w.id, w.name, w.stability, w.travel_multiplier, w.status, w.discovered,
                  e.name AS entry_name, x.name AS exit_name,
                  e.x_coord AS ex, e.y_coord AS ey, x.x_coord AS xx, x.y_coord AS xy
           FROM maya_rp.wormholes w
           JOIN maya_rp.sectors e ON e.id = w.entry_sector_id
           JOIN maya_rp.sectors x ON x.id = w.exit_sector_id
           WHERE w.session_id=$1 ORDER BY w.id""",
        session_id)


async def wormhole_jump(name: str, session_id: int | None = None) -> dict:
    """Book a wormhole transit between an A↔B pair.

    Returns the jump plan (entry/exit sectors, travel_days = euclidean ×
    travel_multiplier) or raises ValueError for unknown/collapsed holes.
    """
    if session_id is None:
        session_id = Config.SESSION_ID
    row = await Database.fetchrow(
        """SELECT w.id, w.name, w.stability, w.travel_multiplier, w.status,
                  e.name AS entry_name, e.x_coord AS ex, e.y_coord AS ey, e.z_coord AS ez,
                  x.name AS exit_name, x.x_coord AS xx, x.y_coord AS xy, x.z_coord AS xz
           FROM maya_rp.wormholes w
           JOIN maya_rp.sectors e ON e.id = w.entry_sector_id
           JOIN maya_rp.sectors x ON x.id = w.exit_sector_id
           WHERE w.session_id=$1 AND w.name ILIKE $2
           ORDER BY w.id LIMIT 1""",
        session_id, f"%{name}%")
    if not row:
        raise ValueError(f"No wormhole named {name!r}")
    if row["status"] == "collapsed":
        raise ValueError(f"Wormhole {row['name']} has COLLAPSED — no passage.")
    dist = euclidean((row["ex"] or 0, row["ey"] or 0), (row["xx"] or 0, row["xy"] or 0))
    travel_days = dist * _num(row["travel_multiplier"], 0.1) * GRID_HOURS_PER_UNIT / HOURS_PER_DAY
    return {"id": row["id"], "name": row["name"], "status": row["status"],
            "stability": _num(row["stability"], 1.0), "entry": row["entry_name"],
            "exit": row["exit_name"], "travel_days": travel_days,
            "entry_z": row["ez"], "exit_z": row["xz"],
            "collapsed": row["status"] == "collapsed"}


async def wormhole_decay(session_id: int | None = None) -> dict:
    """Tick hook: decaying wormholes lose stability; at 0 they collapse.

    Stable holes stay open (Aether Nexus hub keeps its pair fed). Returns
    changes so the orchestrator can narrate collapses.
    """
    if session_id is None:
        session_id = Config.SESSION_ID
    rows = await Database.fetch(
        """SELECT id, name, stability, decay_per_tick, status
           FROM maya_rp.wormholes WHERE session_id=$1 AND status IN ('stable','decaying')""",
        session_id)
    collapsed, decayed = [], []
    for r in rows:
        if r["status"] == "stable":
            continue  # hub-fed: no decay
        new_stab = float(r["stability"] or 0.5) - float(r["decay_per_tick"] or 0.01)
        new_stab = max(0.0, new_stab)
        if new_stab <= 0:
            await Database.execute(
                "UPDATE maya_rp.wormholes SET stability=0, status='collapsed' WHERE id=$1",
                r["id"])
            collapsed.append(r["name"])
            await Database.execute(
                """INSERT INTO maya_rp.events (session_id, event_type, title, description, importance)
                   VALUES ($1, 'wormhole_collapse', $2, $3, 5)""",
                session_id,
                f"Wormhole collapse — {r['name']}",
                f"The wormhole {r['name']} ran out of exotic matter and collapsed. "
                f"Ships inside would be lost — check transits.",
            )
        else:
            await Database.execute(
                "UPDATE maya_rp.wormholes SET stability=$1 WHERE id=$2", new_stab, r["id"])
            decayed.append((r["name"], new_stab))
    if collapsed or decayed:
        info("voyage", f"Wormhole decay: {len(decayed)} decaying, {len(collapsed)} collapsed")
    return {"collapsed": collapsed, "decayed": decayed}


async def black_hole_slingshot(bh_name: str, session_id: int | None = None,
                               rng: random.Random | None = None) -> dict:
    """Slingshot past a black hole (Oberth effect): travel ×multiplier,
    but roll d100 vs hazard*100 — fail pulls toward the event horizon.

    Returns the plan; a fail result must be resolved by the caller
    (ships lost / voyage destroyed).
    """
    if session_id is None:
        session_id = Config.SESSION_ID
    r = rng or random
    row = await Database.fetchrow(
        """SELECT b.id, b.name, b.hazard_level, b.slingshot_multiplier,
                  b.time_dilation_ratio, s.name AS sector, s.x_coord, s.y_coord, s.z_coord
           FROM maya_rp.black_holes b
           JOIN maya_rp.sectors s ON s.id = b.sector_id
           WHERE b.session_id=$1 AND b.name ILIKE $2
           ORDER BY b.id LIMIT 1""",
        session_id, f"%{bh_name}%")
    if not row:
        raise ValueError(f"No black hole named {bh_name!r}")
    hazard = _num(row["hazard_level"], BLACK_HOLE_SLINGSHOT_DC)
    roll = r.randint(1, 100)
    pass_dc = int(hazard * 100)
    ok = roll >= pass_dc
    return {"id": row["id"], "name": row["name"], "sector": row["sector"],
            "hazard_level": hazard,
            "slingshot_multiplier": _num(row["slingshot_multiplier"], 0.6),
            "time_dilation_ratio": _num(row["time_dilation_ratio"], 4.0),
            "roll": roll, "pass_dc": pass_dc, "ok": ok}


async def white_hole_events(session_id: int | None = None) -> list[dict]:
    """White holes are exit-only: list what has emerged (mystery feed)."""
    if session_id is None:
        session_id = Config.SESSION_ID
    return await Database.fetch(
        """SELECT w.name, w.status, w.mystery_pct, s.name AS sector,
                  COALESCE(b.name,'—') AS linked_bh
           FROM maya_rp.white_holes w
           JOIN maya_rp.sectors s ON s.id = w.sector_id
           LEFT JOIN maya_rp.black_holes b ON b.id = w.linked_black_hole_id
           WHERE w.session_id=$1 ORDER BY w.id""",
        session_id)

# Hidden-thread (smuggler) risk model v2 (2026-08-15, Izzat's design):
#   base danger 10-20% → detection roll on arrival → the ACT determines outcome.
#   act='run'  : +30-50% danger (running is reckless, burns the surprise)
#   no guide   : +20% danger
#   prep/equip/knowledge each -5% (persediaan, peralatan, pengetahuan)
#   cargo_heat each +5% (berharga/ilegal = sasaran menarik)
#   Danger clamps 5..95. On detection: sneak with gear ≥6 slips away; run gets
#   chased (30-50% loss); guard fights (10-30% + counter); bribe buys out (0-5%).
HIDDEN_THREAD_BASE_MIN = 10
HIDDEN_THREAD_BASE_MAX = 20
HIDDEN_THREAD_RUN_DANGER_MIN = 30
HIDDEN_THREAD_RUN_DANGER_MAX = 50
HIDDEN_THREAD_NO_GUIDE_PCT = 20
HIDDEN_THREAD_PREP_BONUS = 5      # per level, for prep + equip + knowledge
HIDDEN_THREAD_HEAT_PENALTY = 5    # per level of cargo_heat
HIDDEN_THREAD_DANGER_MIN = 5
HIDDEN_THREAD_DANGER_MAX = 95
HIDDEN_THREAD_SNEAK_GEAR = 6      # prep+equip+knowledge+guide >= 6 → slip away
HIDDEN_THREAD_LOSS_MIN = 0.10
HIDDEN_THREAD_LOSS_MAX = 0.30
HIDDEN_THREAD_RUN_LOSS_MIN = 0.30
HIDDEN_THREAD_RUN_LOSS_MAX = 0.50
HIDDEN_THREAD_ESCAPE_LOSS_MAX = 0.05

# ── POSITIVE SIDE — profit margin on clean arrival (2026-08-15) ──
# Hidden thread = smuggling = high risk, HIGH reward. cargo_value is sold at a
# premium margin when the run lands clean; treasury is credited the profit.
HIDDEN_THREAD_MARGIN_MIN = 0.25    # base margin band 25-40%
HIDDEN_THREAD_MARGIN_MAX = 0.40
HIDDEN_THREAD_MARGIN_ACT = {"sneak": 0.10, "guard": 0.05, "run": -0.10, "bribe": -0.05}
HIDDEN_THREAD_MARGIN_GUIDE = 0.05  # guide finds better buyers
HIDDEN_THREAD_MARGIN_PREP = 0.02   # per level: prep + equip + knowledge
HIDDEN_THREAD_MARGIN_HEAT = 0.08   # per heat level: hotter cargo = bigger premium
HIDDEN_THREAD_MARGIN_MIN_CLAMP = 0.05
HIDDEN_THREAD_MARGIN_MAX_CLAMP = 0.95
HIDDEN_THREAD_SLIPPED_PROFIT = 0.50  # slipped away → half profit (cargo dumped)

ACTS = ("sneak", "run", "guard", "bribe")


def _require_act(act: str) -> str:
    """The act decides the stakes; an unknown name is a caller error, not a default.

    Every hidden-thread model branches on act. A typo used to fall through to
    the catch-all branch and read as a minor loss — the run looked resolved.
    """
    if act not in ACTS:
        raise ValueError(f"act must be one of {ACTS}, got {act!r}")
    return act


def hidden_thread_margin(
    act: str = "sneak",
    has_guide: bool = True,
    prep_level: int = 0,
    equip_level: int = 0,
    knowledge_level: int = 0,
    cargo_heat: int = 0,
    rng: random.Random | None = None,
) -> float:
    """Profit margin (fraction of cargo_value) on a clean hidden-thread run.

    The act cuts both ways: sneak commands a premium, run sells cheap and
    rushed, guard costs escort overhead, bribe loses a cut to the buyer-side.
    Preparation/equipment/knowledge reduce cargo damage (+2% each); a guide
    negotiates better (+5%); hot cargo is worth more on the black market
    (+8% per level) — which is exactly why it attracts attention.
    """
    _require_act(act)
    r = rng or random
    margin = r.uniform(HIDDEN_THREAD_MARGIN_MIN, HIDDEN_THREAD_MARGIN_MAX)
    margin += HIDDEN_THREAD_MARGIN_ACT.get(act, 0.0)
    if has_guide:
        margin += HIDDEN_THREAD_MARGIN_GUIDE
    margin += (prep_level + equip_level + knowledge_level) * HIDDEN_THREAD_MARGIN_PREP
    margin += cargo_heat * HIDDEN_THREAD_MARGIN_HEAT
    return max(HIDDEN_THREAD_MARGIN_MIN_CLAMP, min(HIDDEN_THREAD_MARGIN_MAX_CLAMP, margin))


def hidden_thread_danger(
    act: str = "sneak",
    has_guide: bool = True,
    prep_level: int = 0,
    equip_level: int = 0,
    knowledge_level: int = 0,
    cargo_heat: int = 0,
    rng: random.Random | None = None,
) -> int:
    """Detection chance % for a hidden-thread voyage (Izzat model v2).

    Base 10-20%, plus act/guide/heat modifiers, minus prep/equip/knowledge.
    """
    _require_act(act)
    r = rng or random
    danger = r.uniform(HIDDEN_THREAD_BASE_MIN, HIDDEN_THREAD_BASE_MAX)
    if act == "run":
        danger += r.uniform(HIDDEN_THREAD_RUN_DANGER_MIN, HIDDEN_THREAD_RUN_DANGER_MAX)
    if not has_guide:
        danger += HIDDEN_THREAD_NO_GUIDE_PCT
    danger -= (prep_level + equip_level + knowledge_level) * HIDDEN_THREAD_PREP_BONUS
    danger += cargo_heat * HIDDEN_THREAD_HEAT_PENALTY
    return int(max(HIDDEN_THREAD_DANGER_MIN, min(HIDDEN_THREAD_DANGER_MAX, danger)))


def hidden_thread_outcome(
    act: str,
    has_guide: bool,
    prep_level: int,
    equip_level: int,
    knowledge_level: int,
    ship_count: int,
    rng: random.Random | None = None,
) -> dict:
    """Resolve what happens when a hidden-thread voyage IS detected.

    The act determines the stakes (Izzat: "if detected nothing happen but the
    act will determine"):
      sneak → gear >= 6 slips away (0-5% loss); else caught (10-30%)
      run   → chased down: 30-50% loss (reckless = expensive)
      guard → engaged: 10-30% loss, pursuers driven off
      bribe → bought out: 0-5% loss, credits spent
    Returns {loss, outcome, chased} where chased=True means "caught/interdicted".
    """
    _require_act(act)
    r = rng or random
    gear = prep_level + equip_level + knowledge_level + (1 if has_guide else 0)
    escape = (0.0, HIDDEN_THREAD_ESCAPE_LOSS_MAX)
    if act == "sneak":
        if gear >= HIDDEN_THREAD_SNEAK_GEAR:
            return {"loss": hidden_thread_loss(ship_count, r, band=escape, minimum=0),
                    "outcome": "slipped_away", "chased": False}
        return {"loss": hidden_thread_loss(ship_count, r),
                "outcome": "caught", "chased": True}
    if act == "run":
        return {"loss": hidden_thread_loss(
                    ship_count, r, band=(HIDDEN_THREAD_RUN_LOSS_MIN, HIDDEN_THREAD_RUN_LOSS_MAX)),
                "outcome": "chased_down", "chased": True}
    if act == "guard":
        return {"loss": hidden_thread_loss(ship_count, r),
                "outcome": "engaged", "chased": True}
    if act == "bribe":
        return {"loss": hidden_thread_loss(ship_count, r, band=escape, minimum=0),
                "outcome": "bought_out", "chased": False}
    # An act added to ACTS without a branch here lands in the catch-all; a
    # misspelt act never reaches it (see _require_act).
    return {"loss": hidden_thread_loss(ship_count, r),
            "outcome": "caught", "chased": True}

_GRID_RE = r'^\s*(-?\d+(?:\.\d+)?)\s*[,\-x]\s*(-?\d+(?:\.\d+)?)\s*$'


def parse_coord(coord: str | None) -> tuple | None:
    """Parse 'X,Y', 'X-Y', 'X x Y' → (x, y); 'X,Y,Z' → (x, y, z).
    z: 2 = current map, 1 = bottom veil, 3 = top veil (2026-08-14)."""
    if not coord:
        return None
    import re
    s = coord.strip()
    m3 = re.match(r'^\s*(-?\d+(?:\.\d+)?)\s*[,\-x]\s*(-?\d+(?:\.\d+)?)\s*[,\-x]\s*(-?\d+(?:\.\d+)?)\s*$', s)
    if m3:
        return (float(m3.group(1)), float(m3.group(2)), float(m3.group(3)))
    m = re.match(_GRID_RE, s)
    if not m:
        return None
    return (float(m.group(1)), float(m.group(2)))


def euclidean(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


async def compute_travel(
    origin: str | None = None,
    destination: str | None = None,
    distance_ly: float | None = None,
    distance_units: float | None = None,
    session_id: int | None = None,
) -> dict:
    """Compute travel_hours + travel_days from whatever is known.
    Priority: explicit ly > explicit units > coordinate euclidean > sector_connections lookup.

    An explicit distance of 0 is a distance, not a missing argument: `if distance_ly:`
    let 0 fall through to the coordinate branch and raised when no coords were given.
    """
    if session_id is None:
        session_id = Config.SESSION_ID

    if distance_ly is not None:
        if distance_ly < 0:
            raise ValueError(f"distance_ly cannot be negative, got {distance_ly}")
        travel_hours = distance_ly / LY_PER_DAY * HOURS_PER_DAY
        return {"travel_hours": travel_hours, "travel_days": distance_ly / LY_PER_DAY,
                "distance_ly": distance_ly, "distance_units": None, "mode": "ly"}

    if distance_units is not None:
        if distance_units < 0:
            raise ValueError(f"distance_units cannot be negative, got {distance_units}")
        travel_hours = distance_units * GRID_HOURS_PER_UNIT
        return {"travel_hours": travel_hours, "travel_days": travel_hours / HOURS_PER_DAY,
                "distance_ly": None, "distance_units": distance_units, "mode": "units"}

    # Coordinate-based euclidean (grid space) — z-aware (2026-08-14)
    a, b = parse_coord(origin), parse_coord(destination)
    if a and b:
        dist = euclidean(a[:2], b[:2])
        travel_hours = dist * GRID_HOURS_PER_UNIT
        za, zb = (a[2] if len(a) > 2 else None), (b[2] if len(b) > 2 else None)
        if za is not None and zb is not None and za != zb:
            gate = await gate_crossing(za, zb, session_id)
            travel_hours += gate["travel_time_hours"]
            return {"travel_hours": travel_hours, "travel_days": travel_hours / HOURS_PER_DAY,
                    "distance_ly": None, "distance_units": dist + gate["distance"],
                    "mode": "gate", "via_gate": gate["name"],
                    "hidden": gate.get("hidden", False),
                    "lane_type": gate["lane_type"],
                    "toll_credits": gate["toll_credits"],
                    "pirate_density": gate["pirate_density"]}
        return {"travel_hours": travel_hours, "travel_days": travel_hours / HOURS_PER_DAY,
                "distance_ly": None, "distance_units": dist, "mode": "coord"}

    # Fallback: try sector_connections for a direct link.
    # from_sector_id/to_sector_id are INTEGER sector ids — the old code bound
    # '%Name%' against their ::text form, which could never match (dead path).
    if origin and destination:
        async def _sector_id(name: str):
            return await Database.fetchval(
                "SELECT id FROM maya_rp.sectors WHERE session_id=$1 AND name ILIKE $2 "
                "ORDER BY id LIMIT 1",
                session_id, f"%{str(name).split('-')[0]}%")

        o_id, d_id = await _sector_id(origin), await _sector_id(destination)
        row = None
        if o_id and d_id:
            row = await Database.fetchrow(
                """SELECT distance, travel_time_hours FROM maya_rp.sector_connections
                   WHERE session_id=$1
                     AND ((from_sector_id=$2 AND to_sector_id=$3)
                       OR (from_sector_id=$3 AND to_sector_id=$2))
                   ORDER BY id LIMIT 1""",
                session_id, o_id, d_id)
        if row is None and (o_id or d_id):
            row = await Database.fetchrow(
                """SELECT distance, travel_time_hours FROM maya_rp.sector_connections
                   WHERE session_id=$1 AND (from_sector_id=$2 OR to_sector_id=$2)
                   ORDER BY id LIMIT 1""",
                session_id, o_id or d_id)
        if row and row["travel_time_hours"]:
            return {"travel_hours": row["travel_time_hours"],
                    "travel_days": row["travel_time_hours"] / HOURS_PER_DAY,
                    "distance_ly": None, "distance_units": row["distance"], "mode": "link"}

    raise ValueError(f"Cannot compute travel between {origin!r} and {destination!r} — "
                     "give ly, units, or grid coordinates.")


async def gate_crossing(z1, z2, session_id: int | None = None) -> dict:
    """Find the gate/hidden-thread connection between two z-planes.

    Gates are the only legal crossings; hidden threads are smugglers'
    routes (flagged hidden). Raises ValueError when no passage exists —
    'the map has few connections' is enforced here.
    """
    if session_id is None:
        session_id = Config.SESSION_ID
    rows = await Database.fetch(
        """SELECT sc.id, fs.name AS from_name, fs.z_coord AS fz,
                  ts.name AS to_name, ts.z_coord AS tz,
                  sc.distance, sc.travel_time_hours, sc.lane_type,
                  sc.toll_credits, sc.pirate_density
           FROM maya_rp.sector_connections sc
           JOIN maya_rp.sectors fs ON fs.id = sc.from_sector_id
           JOIN maya_rp.sectors ts ON ts.id = sc.to_sector_id
           WHERE sc.session_id=$1
             AND ((fs.z_coord=$2 AND ts.z_coord=$3) OR (fs.z_coord=$3 AND ts.z_coord=$2))
             AND sc.lane_type IN ('gate','hidden_thread')
           ORDER BY (sc.lane_type='gate') DESC, sc.travel_time_hours ASC""",
        session_id, z1, z2)
    if not rows:
        raise ValueError(f"No passage between z={z1} and z={z2} — "
                         "crossing requires a gate (or a hidden thread).")
    r = rows[0]
    return {"name": f"{r['from_name']} ↔ {r['to_name']}",
            "distance": r["distance"], "travel_time_hours": r["travel_time_hours"],
            "hidden": r["lane_type"] == "hidden_thread",
            "lane_type": r["lane_type"],
            "toll_credits": int(r.get("toll_credits") or 0),
            "pirate_density": float(r.get("pirate_density") or 0.0)}


async def _charge_treasury(sql: str, *args) -> bool:
    """Run a treasury UPDATE and report whether it touched a row.

    asyncpg returns the status tag ('UPDATE 1', 'UPDATE 0'). A session with no
    resources row would otherwise book a toll or a profit that never moved.
    """
    tag = await Database.execute(sql, *args)
    return not (isinstance(tag, str) and tag.split()[-1:] == ["0"])


async def register(
    voyage_name: str,
    origin: str | None = None,
    destination: str | None = None,
    distance_ly: float | None = None,
    distance_units: float | None = None,
    fleet_tag: str | None = None,
    ship_count: int = 0,
    notes: str = "",
    session_id: int | None = None,
    depart_day: int | None = None,
    act: str = "sneak",
    guide: str | None = None,
    prep_level: int = 0,
    equip_level: int = 0,
    knowledge_level: int = 0,
    cargo_heat: int = 0,
    cargo_value: int = 0,
    wormhole: str | None = None,
    slingshot: str | None = None,
    fleet: str | None = None,
    void: bool = False,
) -> dict:
    """Register a voyage. Books travel days into the clock via game_day + travel_days.

    Transit kinds (2026-08-15 theory build):
      wormhole=<name>  → A↔B pair, ~90% travel cut; decaying holes roll
                         collapse on arrival (ships lost if it pops).
      slingshot=<name> → black-hole Oberth boost: travel ×multiplier plus
                         TIME DILATION (1 ship-day = N game-days, extra
                         dilation_days booked). Slingshot roll happens on
                         arrival (event-horizon risk).
      hidden-thread    → Izzat risk model v2 (act/guide/prep/equip/knowledge).
    """
    if session_id is None:
        session_id = Config.SESSION_ID

    # ── Input validation (checklist: quantities checked before they are used) ──
    # A negative prep level RAISED the danger instead of lowering it, and a
    # negative cargo_value silently booked a loss-making run.
    if not voyage_name or not str(voyage_name).strip():
        raise ValueError("voyage_name is required — it titles every arrival event")
    if ship_count < 0:
        raise ValueError(f"ship_count cannot be negative, got {ship_count}")
    if cargo_value < 0:
        raise ValueError(f"cargo_value cannot be negative, got {cargo_value}")
    for _label, _level in (("prep_level", prep_level), ("equip_level", equip_level),
                           ("knowledge_level", knowledge_level), ("cargo_heat", cargo_heat)):
        if _level < 0:
            raise ValueError(f"{_label} cannot be negative, got {_level}")

    gd = depart_day if depart_day is not None else await Database.fetchval(
        "SELECT COALESCE(game_day,1) FROM maya_rp.sessions WHERE id=$1", session_id) or 1

    t = await compute_travel(origin, destination, distance_ly, distance_units, session_id)
    travel_days = t["travel_days"]
    arrive_day = gd + int(math.ceil(travel_days))
    via_hidden = bool(t.get("hidden", False))
    danger_pct = None
    transit_kind = "regular"
    transit_name = None
    dilation_days = 0
    if via_hidden:
        _require_act(act)
        danger_pct = hidden_thread_danger(
            act=act, has_guide=bool(guide), prep_level=prep_level,
            equip_level=equip_level, knowledge_level=knowledge_level,
            cargo_heat=cargo_heat)
        transit_kind = "hidden"
    if wormhole:
        j = await wormhole_jump(wormhole, session_id)
        if j["collapsed"]:
            raise ValueError(f"Wormhole {j['name']} has collapsed — no passage.")
        travel_days = j["travel_days"]
        arrive_day = gd + int(math.ceil(travel_days))
        transit_kind = "wormhole"
        transit_name = j["name"]
    if slingshot:
        b = await black_hole_slingshot(slingshot, session_id)
        travel_days = travel_days * b["slingshot_multiplier"]
        dilation_days = int(math.ceil(travel_days * (b["time_dilation_ratio"] - 1.0)))
        arrive_day = gd + int(math.ceil(travel_days)) + dilation_days
        transit_kind = "slingshot"
        transit_name = b["name"]
    if void:
        # ── VOID CROSSING (2026-08-15): inter-nebular travel without a gate ──
        # Requires a Void Drive in the fleet; fast (12h/u) but risky (base 20%,
        # cut by Nebular Ward). Only valid when the voyage crosses z-planes.
        from modules.ship_modules import void_crossing_cost
        a_c, b_c = parse_coord(origin), parse_coord(destination)
        za = a_c[2] if a_c and len(a_c) > 2 else 2
        zb = b_c[2] if b_c and len(b_c) > 2 else 2
        if za == zb:
            raise ValueError("void crossing requires z-planes to differ "
                             "(e.g. 10,480,3 → 450,450,1) — use normal travel within a plane")
        vc = await void_crossing_cost(za, zb, fleet, session_id)
        dist_void = euclidean((a_c[0], a_c[1]), (b_c[0], b_c[1])) if a_c and b_c else (t.get("distance_units") or 0)
        travel_days = dist_void * vc["hours_per_unit"] / HOURS_PER_DAY
        arrive_day = gd + int(math.ceil(travel_days))
        transit_kind = "void"
        transit_name = f"void z{za}→z{zb}"
        danger_pct = vc["risk_pct"]   # persist crossing risk for advance()

    # lane type + toll (2026-08-15 Izzat canon): Setia gates are the fair highway.
    #   · Setia's OWN fleet: free to use, AT INTERNAL COST — the toll is an
    #     operating expense (maintenance + garrison). Internal cost is SMALLER
    #     than the public price; the public price is standardized at 25,000C
    #     (see modules/economy.py GATE_TOLL_RATE).
    #   · Common people / anyone else: pay the standardized public price —
    #     that income arrives via the economy tick (gate_toll_income).
    #   · Gates need NO exotic matter — that's wormholes only.
    lane_type = t.get("lane_type") or (transit_kind if transit_kind != "regular" else "standard")
    # exotic transits own their lane label (void/wormhole/slingshot) even if
    # compute_travel found a hidden-thread crossing underneath (z-planes differ)
    if transit_kind in ("void", "wormhole", "slingshot"):
        lane_type = transit_kind
    elif t.get("lane_type") == "hidden_thread":
        lane_type = "hidden_thread"
    # internal fleet cost = smaller share of the public price (20%)
    # only GATE lanes carry the toll — exotic transits (void/wormhole/slingshot)
    # and hidden threads are toll-free
    internal_gate_cost = 0
    if lane_type == "gate":
        internal_gate_cost = int((t.get("toll_credits") or 0) * GATE_INTERNAL_COST_SHARE)
    toll_paid = internal_gate_cost
    toll_charged = False
    if lane_type == "gate" and toll_paid > 0:
        # treasury absorbs the internal cost (Setia fleet free, treasury pays).
        # No resources row = no money moved: report the toll as uncharged
        # rather than booking a cost the treasury never paid.
        toll_charged = await _charge_treasury(
            "UPDATE maya_rp.resources SET credits=credits-$1 WHERE session_id=$2",
            toll_paid, session_id)
        if not toll_charged:
            info("voyage", f"{voyage_name}: session {session_id} has no resources row — "
                           f"{toll_paid:,}C internal gate toll NOT charged")
            toll_paid = 0

    vid = await Database.fetchval(
        """INSERT INTO maya_rp.voyages
           (session_id, voyage_name, origin, destination, distance_units, distance_ly,
            travel_hours, travel_days, depart_day, arrive_day, status, fleet_tag, ship_count, notes,
            via_hidden, act, guide, prep_level, equip_level, knowledge_level,
            cargo_heat, cargo_value, danger_pct,
            transit_kind, transit_name, dilation_days,
            lane_type, toll_paid)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'in_transit',$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27)
           RETURNING id""",
        session_id, voyage_name, origin, destination, t.get("distance_units"), t.get("distance_ly"),
        t["travel_hours"], travel_days, gd, arrive_day, fleet_tag, ship_count, notes,
        via_hidden, act, guide, prep_level, equip_level, knowledge_level,
        cargo_heat, cargo_value, danger_pct,
        transit_kind, transit_name, dilation_days,
        lane_type, toll_paid,
    )

    info("voyage", f"{voyage_name}: {origin or '?'} → {destination or '?'} "
                   f"({t.get('distance_units')}u / {t.get('distance_ly')}ly) = "
                   f"{travel_days:.2f}d → arrives day {arrive_day}"
                   + (f" · {lane_type} lane" if lane_type != "standard" else "")
                   + (f" · toll {toll_paid:,}C" if toll_paid else "")
                   + (f" · hidden thread {act} danger {danger_pct}%" if via_hidden else "")
                   + (f" · wormhole {transit_name}" if transit_kind == "wormhole" else "")
                   + (f" · slingshot {transit_name} +{dilation_days}d dilation"
                      if transit_kind == "slingshot" else ""))
    return {"id": vid, "voyage_name": voyage_name, "origin": origin, "destination": destination,
            "travel_hours": t["travel_hours"], "travel_days": travel_days,
            "depart_day": gd, "arrive_day": arrive_day, "status": "in_transit",
            "via_hidden": via_hidden, "act": act, "danger_pct": danger_pct,
            "transit_kind": transit_kind, "transit_name": transit_name,
            "dilation_days": dilation_days, "lane_type": lane_type, "toll_paid": toll_paid,
            "toll_charged": toll_charged}


def hidden_thread_loss(
    ship_count: int,
    rng: random.Random | None = None,
    band: tuple[float, float] = (HIDDEN_THREAD_LOSS_MIN, HIDDEN_THREAD_LOSS_MAX),
    minimum: int = 1,
) -> int:
    """Ships lost when a hidden-thread run is interdicted.

    `band` is the loss fraction range: interdiction 10-30%, a reckless run
    30-50%, an escape 0-5%. `minimum=1` books a hull for a caught run; an
    escape passes 0 because a graze can cost nothing.
    """
    r = rng or random
    lo, hi = band
    return max(minimum, int((ship_count or 0) * r.uniform(lo, hi)))


async def advance(session_id: int | None = None) -> dict:
    """Tick hook: mark voyages arrived when arrive_day <= game_day. Log each arrival.

    Hidden-thread voyages (smugglers' routes) resolve on arrival with the Izzat
    risk model v2 (2026-08-15):
      1. roll d100 vs danger_pct (base 10-20% + act/guide/heat − prep/equip/knowledge)
      2. roll > danger → CLEAN: cargo sold at margin, profit → treasury
      3. roll <= danger → DETECTED → the act determines: sneak may slip away;
         run gets chased (30-50% loss); guard fights; bribe buys out.
    """
    if session_id is None:
        session_id = Config.SESSION_ID
    gd = await Database.fetchval("SELECT COALESCE(game_day,1) FROM maya_rp.sessions WHERE id=$1", session_id) or 1
    arrived = await Database.fetch(
        """UPDATE maya_rp.voyages
           SET status='arrived', arrived_at=NOW()
           WHERE session_id=$1 AND status='in_transit' AND arrive_day <= $2
           RETURNING id, voyage_name, origin, destination, arrive_day, fleet_tag, ship_count,
                     via_hidden, act, guide, prep_level, equip_level, knowledge_level,
                     cargo_heat, cargo_value, danger_pct,
                     transit_kind, transit_name, dilation_days, collapse_roll,
                     lane_type""",
        session_id, gd,
    )
    arrivals = 0
    interdictions = 0
    clean_runs = 0
    profit_total = 0
    collapses = 0
    slingshot_fails = 0
    lost_voyages: list[str] = []
    unbooked_credits = 0
    for a in arrived:
        arrivals += 1
        # ── PIRATE ENCOUNTER on standard lanes (2026-08-15 Izzat canon) ──
        # Gates are garrisoned (5% — the fair toll buys safety); open lanes
        # are riskier: standard 15%, hazardous 30%, unstable 45%. Hidden
        # threads, void, wormhole and slingshot have their own models below.
        lane = (a["lane_type"] or "standard")
        if lane in ("standard", "hazardous", "unstable"):
            density = {"standard": 0.15, "hazardous": 0.30, "unstable": 0.45}.get(lane, 0.15)
            prowl = random.randint(1, 100)
            await Database.execute(
                "UPDATE maya_rp.voyages SET risk_roll=$1 WHERE id=$2", prowl, a["id"])
            if prowl <= int(density * 100):
                lost = hidden_thread_loss(a["ship_count"] or 0)
                await Database.execute(
                    """UPDATE maya_rp.voyages SET interdicted=TRUE, loss_ships=$1 WHERE id=$2""",
                    lost, a["id"])
                await Database.execute(
                    """INSERT INTO maya_rp.events (session_id, event_type, title, description, importance)
                       VALUES ($1, 'pirate_encounter', $2, $3, 3)""",
                    session_id,
                    f"Pirate encounter — {a['voyage_name']}",
                    f"{a['voyage_name']} was hit by pirates on a {lane} lane on day "
                    f"{a['arrive_day']}: {lost} ship(s) lost near {a['destination']} "
                    f"(roll {prowl} ≤ {int(density*100)}% — the {lane} lane is open ground, "
                    f"tag {a['fleet_tag'] or '—'}).",
                )
                info("voyage", f"PIRATES: {a['voyage_name']} lost {lost} "
                               f"on {lane} lane (roll {prowl})")
                continue
        # ── WORMHOLE transit: collapse risk on arrival ──
        if a["transit_kind"] == "wormhole":
            collapse_roll = random.randint(1, 100)
            await Database.execute(
                "UPDATE maya_rp.voyages SET collapse_roll=$1 WHERE id=$2",
                collapse_roll, a["id"])
            # decaying holes pop; stable hub-fed ones don't. The name search is
            # session-scoped: a same-named hole in another campaign must not
            # decide whether THIS session's ships survive the crossing.
            stab = await Database.fetchval(
                "SELECT stability FROM maya_rp.wormholes "
                "WHERE session_id=$1 AND name ILIKE $2 ORDER BY id LIMIT 1",
                session_id, f"%{a['transit_name'] or ''}%")
            if stab is None:
                stab = 1.0
            if float(stab) < 0.99 and collapse_roll <= WORMHOLE_COLLAPSE_PCT:
                collapses += 1
                lost = a["ship_count"] or 0
                lost_voyages.append(a["voyage_name"])
                # The event text claims the ships are gone. Book it: the voyage
                # ends 'lost' with the hulls counted, not 'arrived' at full
                # strength with the loss living only in prose.
                await Database.execute(
                    """UPDATE maya_rp.voyages
                       SET status='lost', loss_ships=$1 WHERE id=$2""",
                    lost, a["id"])
                await Database.execute(
                    """INSERT INTO maya_rp.events (session_id, event_type, title, description, importance)
                       VALUES ($1, 'wormhole_collapse', $2, $3, 5)""",
                    session_id,
                    f"WORMHOLE COLLAPSED — {a['voyage_name']}",
                    f"{a['voyage_name']} was inside {a['transit_name']} when it popped "
                    f"on day {a['arrive_day']}: {lost or '?'} ship(s) lost to "
                    f"the exotic-matter cascade near {a['destination']} "
                    f"(collapse roll {collapse_roll} ≤ {WORMHOLE_COLLAPSE_PCT}).",
                )
                info("voyage", f"WORMHOLE COLLAPSE: {a['voyage_name']} "
                               f"({a['transit_name']}, roll {collapse_roll}, "
                               f"{lost} ship(s) lost)")
                continue
            await Database.execute(
                """INSERT INTO maya_rp.events (session_id, event_type, title, description)
                   VALUES ($1, 'wormhole_arrival', $2, $3)""",
                session_id,
                f"Wormhole arrival — {a['voyage_name']}",
                f"{a['voyage_name']} emerged from {a['transit_name']} on day "
                f"{a['arrive_day']} at {a['destination']} — the A↔B pair held. "
                f"(collapse roll {collapse_roll}, tag {a['fleet_tag'] or '—'}).",
            )
            continue
        # ── SLINGSHOT transit: event-horizon risk resolved on arrival ──
        if a["transit_kind"] == "slingshot":
            b = await black_hole_slingshot(a["transit_name"] or "", session_id)
            if not b["ok"]:
                slingshot_fails += 1
                lost = hidden_thread_loss(a["ship_count"] or 0, rng=random.Random(b["roll"]))
                await Database.execute(
                    """UPDATE maya_rp.voyages SET interdicted=TRUE, loss_ships=$1 WHERE id=$2""",
                    lost, a["id"])
                await Database.execute(
                    """INSERT INTO maya_rp.events (session_id, event_type, title, description, importance)
                       VALUES ($1, 'event_horizon', $2, $3, 5)""",
                    session_id,
                    f"EVENT HORIZON — {a['voyage_name']}",
                    f"{a['voyage_name']} slingshot {a['transit_name']} went wrong: the "
                    f"gravity gradient bit — {lost} ship(s) pulled past the event "
                    f"horizon on day {a['arrive_day']} (roll {b['roll']} < "
                    f"{b['pass_dc']} hazard). They may yet emerge from a white hole...",
                )
                info("voyage", f"EVENT HORIZON: {a['voyage_name']} lost {lost} "
                               f"(roll {b['roll']} < {b['pass_dc']})")
                continue
            await Database.execute(
                """INSERT INTO maya_rp.events (session_id, event_type, title, description)
                   VALUES ($1, 'slingshot_arrival', $2, $3)""",
                session_id,
                f"Slingshot arrival — {a['voyage_name']}",
                f"{a['voyage_name']} rode the Oberth boost past {a['transit_name']} and "
                f"arrived on day {a['arrive_day']} at {a['destination']} "
                f"(+{a['dilation_days']}d time dilation, roll {b['roll']} ≥ {b['pass_dc']}).",
            )
            continue
        # ── VOID CROSSING: hazard roll on arrival (2026-08-15) ──
        if a["transit_kind"] == "void":
            # risk was persisted at register (danger_pct = void risk, cut by ward)
            risk = a["danger_pct"] if a["danger_pct"] is not None else 20
            roll = random.randint(1, 100)
            await Database.execute(
                "UPDATE maya_rp.voyages SET risk_roll=$1 WHERE id=$2", roll, a["id"])
            if roll <= risk:
                lost = hidden_thread_loss(a["ship_count"] or 0)
                await Database.execute(
                    """UPDATE maya_rp.voyages SET interdicted=TRUE, loss_ships=$1 WHERE id=$2""",
                    lost, a["id"])
                await Database.execute(
                    """INSERT INTO maya_rp.events (session_id, event_type, title, description, importance)
                       VALUES ($1, 'void_hazard', $2, $3, 4)""",
                    session_id,
                    f"VOID HAZARD — {a['voyage_name']}",
                    f"{a['voyage_name']} crossed the void but the dark between the "
                    f"nebulas bit on day {a['arrive_day']}: {lost} ship(s) lost to "
                    f"void radiation / turbulence near {a['destination']} "
                    f"(roll {roll} ≤ {risk}% void risk).",
                )
                info("voyage", f"VOID HAZARD: {a['voyage_name']} lost {lost} "
                               f"(roll {roll} ≤ {risk}%)")
                continue
            await Database.execute(
                """INSERT INTO maya_rp.events (session_id, event_type, title, description)
                   VALUES ($1, 'void_arrival', $2, $3)""",
                session_id,
                f"Void crossing — {a['voyage_name']}",
                f"{a['voyage_name']} crossed the void between the nebulas and "
                f"emerged on day {a['arrive_day']} at {a['destination']} — "
                f"Void Drive held, no ships lost (roll {roll} > {risk}%).",
            )
            continue
        if a["via_hidden"]:
            roll = random.randint(1, 100)
            await Database.execute(
                "UPDATE maya_rp.voyages SET risk_roll=$1 WHERE id=$2", roll, a["id"])
            danger = a["danger_pct"] if a["danger_pct"] is not None else hidden_thread_danger(
                act=a["act"] or "sneak", has_guide=bool(a["guide"]),
                prep_level=a["prep_level"] or 0, equip_level=a["equip_level"] or 0,
                knowledge_level=a["knowledge_level"] or 0, cargo_heat=a["cargo_heat"] or 0)
            act = a["act"] or "sneak"
            if roll > danger:
                # ── CLEAN RUN — the positive side pays out ──
                clean_runs += 1
                margin = hidden_thread_margin(
                    act=act, has_guide=bool(a["guide"]),
                    prep_level=a["prep_level"] or 0, equip_level=a["equip_level"] or 0,
                    knowledge_level=a["knowledge_level"] or 0, cargo_heat=a["cargo_heat"] or 0)
                profit = int((a["cargo_value"] or 0) * margin)
                credited = False
                if profit > 0:
                    credited = await _charge_treasury(
                        "UPDATE maya_rp.resources SET credits=credits+$1 WHERE session_id=$2",
                        profit, session_id)
                    if not credited:
                        unbooked_credits += profit
                        info("voyage", f"{a['voyage_name']}: +{profit:,}C earned but "
                                       f"session {session_id} has no resources row — "
                                       f"NOT credited")
                await Database.execute(
                    """UPDATE maya_rp.voyages SET reward_credits=$1 WHERE id=$2""",
                    profit, a["id"])
                await Database.execute(
                    """INSERT INTO maya_rp.events (session_id, event_type, title, description, importance)
                       VALUES ($1, 'smuggle_profit', $2, $3, 2)""",
                    session_id,
                    f"Clean run — {a['voyage_name']}",
                    f"{a['voyage_name']} slipped through a hidden thread and landed on day "
                    f"{a['arrive_day']}: cargo sold at {margin*100:.0f}% margin, "
                    + (f"{profit:,}C credited." if credited else
                       f"{profit:,}C NOT credited — no treasury row for this session.")
                    + f" (roll {roll} > danger {danger}%, {act} run, "
                      f"tag {a['fleet_tag'] or '—'}).",
                )
                if credited:
                    profit_total += profit
                info("voyage", f"CLEAN: {a['voyage_name']} +{profit:,}C "
                               f"{'booked' if credited else 'UNBOOKED'} (roll {roll} > {danger}%)")
                continue
            # ── DETECTED — the act determines the outcome ──
            interdictions += 1
            res = hidden_thread_outcome(
                act=act, has_guide=bool(a["guide"]),
                prep_level=a["prep_level"] or 0, equip_level=a["equip_level"] or 0,
                knowledge_level=a["knowledge_level"] or 0,
                ship_count=a["ship_count"] or 0)
            lost = res["loss"]
            if res["chased"]:
                await Database.execute(
                    """UPDATE maya_rp.voyages SET interdicted=TRUE, loss_ships=$1 WHERE id=$2""",
                    lost, a["id"])
            title = f"INTERDICTED — {a['voyage_name']}"
            desc = (
                f"{a['voyage_name']} ran a hidden thread but was caught on day "
                f"{a['arrive_day']}: {lost} ship(s) lost near {a['destination']} "
                f"(roll {roll} ≤ {danger}%, {act} run, tag {a['fleet_tag'] or '—'})."
            )
            if res["outcome"] == "slipped_away":
                title = f"Slipped away — {a['voyage_name']}"
                desc = (
                    f"{a['voyage_name']} was spotted on the hidden thread but slipped "
                    f"away on day {a['arrive_day']}: {lost} ship(s) grazed, cargo "
                    f"{HIDDEN_THREAD_SLIPPED_PROFIT*100:.0f}% intact "
                    f"(roll {roll} ≤ {danger}%, {act} run, gear won the day)."
                )
            elif res["outcome"] == "chased_down":
                desc = (
                    f"{a['voyage_name']} ran — and ran straight into a chase on day "
                    f"{a['arrive_day']}: {lost} ship(s) lost near {a['destination']} "
                    f"(roll {roll} ≤ {danger}%, run act is reckless — tag {a['fleet_tag'] or '—'})."
                )
            elif res["outcome"] == "engaged":
                desc = (
                    f"{a['voyage_name']} fought through a hidden-thread ambush on day "
                    f"{a['arrive_day']}: {lost} ship(s) lost, pursuers driven off "
                    f"(roll {roll} ≤ {danger}%, guard act, tag {a['fleet_tag'] or '—'})."
                )
            elif res["outcome"] == "bought_out":
                title = f"Bought out — {a['voyage_name']}"
                desc = (
                    f"{a['voyage_name']} bought its way through a hidden-thread "
                    f"roadblock on day {a['arrive_day']}: {lost} ship(s) lost to the "
                    f"payoff, cargo intact (roll {roll} ≤ {danger}%, bribe act, "
                    f"tag {a['fleet_tag'] or '—'})."
                )
            await Database.execute(
                """INSERT INTO maya_rp.events (session_id, event_type, title, description, importance)
                   VALUES ($1, 'interdiction', $2, $3, 4)""",
                session_id, title, desc)
            info("voyage", f"{res['outcome'].upper()}: {a['voyage_name']} "
                           f"lost {lost} ships (roll {roll} ≤ {danger}%)")
            continue
        await Database.execute(
            """INSERT INTO maya_rp.events (session_id, event_type, title, description)
               VALUES ($1, 'arrival', $2, $3)""",
            session_id,
            f"Arrival — {a['voyage_name']}",
            f"{a['voyage_name']} arrived at {a['destination']} on day {a['arrive_day']} "
            f"({a['ship_count']} ships, {a['lane_type'] or 'standard'} lane, "
            f"tag {a['fleet_tag'] or '—'}).",
        )
    if arrived:
        info("voyage", f"{len(arrived)} voyage(s) arrived at day {gd} "
                       f"({interdictions} interdicted, {clean_runs} clean, "
                       f"{collapses} wormhole collapses, {slingshot_fails} slingshot fails, "
                       f"+{profit_total:,}C profit)")
    return {"arrivals": arrivals, "interdictions": interdictions, "clean_runs": clean_runs,
            "profit_credits": profit_total, "collapses": collapses,
            "slingshot_fails": slingshot_fails,
            "lost": lost_voyages, "unbooked_credits": unbooked_credits,
            "arrived": [a["voyage_name"] for a in arrived]}


async def status(session_id: int | None = None) -> list[dict]:
    if session_id is None:
        session_id = Config.SESSION_ID
    return await Database.fetch(
        """SELECT id, voyage_name, origin, destination, travel_days, depart_day,
                  arrive_day, status, fleet_tag, ship_count, via_hidden, act,
                  danger_pct, loss_ships, reward_credits,
                  transit_kind, transit_name, dilation_days, collapse_roll,
                  lane_type, toll_paid
           FROM maya_rp.voyages WHERE session_id=$1
           ORDER BY status='in_transit' DESC, arrive_day ASC""",
        session_id,
    )


async def run_tick(session_id: int | None = None) -> dict:
    if session_id is None:
        session_id = Config.SESSION_ID
    try:
        return await advance(session_id)
    except Exception as e:
        info("voyage", f"Error: {e}")
        return {"error": str(e)}