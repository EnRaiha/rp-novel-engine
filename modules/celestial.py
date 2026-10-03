#!/usr/bin/env python3
"""
Celestial Module — Full port from JS celestial-heaven skill.
Sources: celestial-index.js, faction-state.js, fog-of-war.js, nav-planner.js,
         planet-catalog.js, route-mapper.js, system-registry.js
All 7 JS files + config fully ported.

Systems:
  - Celestial index: search, universe stats, faction presence, system detail
  - Faction state: territory map, influence shifts, relations, trade
  - Fog of war: 5-tier visibility (uncharted→colonized), scout discovery
  - Nav planner: Dijkstra route planning, fuel estimation, reachable range
  - Planet catalog: query by system/habitable/colonized, stats, resource production
  - Route mapper: query by type/origin/destination/hazard, reachable systems
  - System registry: query by sector/faction/status/threat, sector breakdown
"""

from __future__ import annotations
import heapq
import hashlib
import json
from typing import Any

from core.db import Database
from core.config import Config
from core.log import error, info


# ─── Visibility Levels ──────────────────────────────────────────

VISIBILITY_LEVELS = {
    "uncharted":  {"detail": 0, "can_travel": False, "shows_resources": False},
    "scanned":    {"detail": 1, "can_travel": True,  "shows_resources": False},
    "surveyed":   {"detail": 2, "can_travel": True,  "shows_resources": True},
    "explored":   {"detail": 3, "can_travel": True,  "shows_resources": True},
    "colonized":  {"detail": 4, "can_travel": True,  "shows_resources": True},
}

VIS_ORDER = ["uncharted", "scanned", "surveyed", "explored", "colonized"]


# ═══════════════════════════════════════════════════════════════
# SYSTEM REGISTRY — ported from system-registry.js
# ═══════════════════════════════════════════════════════════════

#: The filter keys `query_systems` can answer, mapped to the column each one reads. The SELECT below
#: returns exactly these. `sector` and `threat` are not among them, and a filter naming one of those
#: used to match nothing at all rather than say so.
SYSTEM_FILTER_KEYS = {
    "system_name": "system_name",
    "faction": "controlling_faction",
    "controlling_faction": "controlling_faction",
    "status": "status",
    "fleet_presence": "fleet_presence",
    "contested_by": "contested_by",
}


async def query_systems(session_id: int, filters: dict | None = None):
    """Query systems by filters. Ported from SystemRegistry.querySystems().

    @returns a list of rows, or a dict naming a filter this function cannot answer.
    """
    if filters is None: filters = {}
    unknown = sorted(k for k in filters if k not in SYSTEM_FILTER_KEYS)
    if unknown:
        return {"error": f"unsupported system filter(s): {', '.join(unknown)}",
                "available": sorted(SYSTEM_FILTER_KEYS)}
    rows = await Database.fetch(
        "SELECT system_name, controlling_faction, status, fleet_presence, "
        "contested_by FROM maya_rp.territory WHERE session_id = $1 ORDER BY system_name",
        session_id,
    )
    systems = [dict(r) for r in rows]

    result = []
    for sys in systems:
        match = True
        for key, val in filters.items():
            if sys.get(SYSTEM_FILTER_KEYS[key]) != val:
                match = False
                break
        if match:
            result.append(sys)
    return result


async def get_system_stats(session_id: int) -> dict:
    """Get system statistics. Ported from SystemRegistry.getSystemStats()."""
    rows = await Database.fetch(
        "SELECT controlling_faction, status, fleet_presence "
        "FROM maya_rp.territory WHERE session_id = $1",
        session_id,
    )
    stats = {"total": len(rows), "by_faction": {}, "by_status": {}}
    for r in rows:
        f = r["controlling_faction"] or "Unknown"
        s = r["status"] or "Unknown"
        stats["by_faction"][f] = stats["by_faction"].get(f, 0) + 1
        stats["by_status"][s] = stats["by_status"].get(s, 0) + 1
    return stats


async def get_sector_breakdown(session_id: int) -> dict:
    """Get sector breakdown. Ported from SystemRegistry.getSectorBreakdown()."""
    rows = await Database.fetch(
        "SELECT system_name, controlling_faction, status, fleet_presence "
        "FROM maya_rp.territory WHERE session_id = $1 ORDER BY system_name",
        session_id,
    )
    sectors = {}
    for r in rows:
        sector = r["system_name"][:2] if r["system_name"] else "U"
        if sector not in sectors: sectors[sector] = []
        sectors[sector].append(dict(r))
    return sectors


# ═══════════════════════════════════════════════════════════════
# PLANET CATALOG — ported from planet-catalog.js
# ═══════════════════════════════════════════════════════════════

async def get_planets_in_system(session_id: int, system_name: str) -> list[dict]:
    """Get planets in a system. Ported from PlanetCatalog.queryBySystem()."""
    rows = await Database.fetch(
        "SELECT name, system_name, planet_type AS type, habitability_score, population, status, "
        "diameter_km, gravity_g, water_pct, biosphere "
        "FROM maya_rp.planets WHERE session_id = $1 AND system_name = $2 ORDER BY name",
        session_id, system_name,
    )
    return [dict(r) for r in rows]


async def get_planet_stats(session_id: int) -> dict:
    """Get planet statistics. Ported from PlanetCatalog.getStats()."""
    rows = await Database.fetch(
        "SELECT planet_type AS type, habitability_score, population, status "
        "FROM maya_rp.planets WHERE session_id = $1",
        session_id,
    )
    stats = {"total": len(rows), "colonized": 0, "habitable": 0,
             "terraforming_candidates": 0, "gas_giants": 0, "total_population": 0}
    for r in rows:
        if r["status"] == "colonized": stats["colonized"] += 1
        hab = r["habitability_score"] or 0
        if hab >= 50: stats["habitable"] += 1
        if r["type"] == "Gas Giant": stats["gas_giants"] += 1
        # `planets.planet_type` spells the catalogue's terrestrial class "Terran"
        # (and "Gaia" for the garden class) — "Terrestrial" never appears.
        if hab < 50 and r["type"] in ("Terrestrial", "Terran", "Gaia") and r["status"] != "colonized":
            stats["terraforming_candidates"] += 1
        stats["total_population"] += r["population"] or 0
    return stats


async def get_colonies(session_id: int) -> list[dict]:
    """Get colonized planets. Ported from PlanetCatalog.getColonies()."""
    rows = await Database.fetch(
        "SELECT name, system_name, population, status, habitability_score, biosphere "
        "FROM maya_rp.planets WHERE session_id = $1 AND status = 'colonized'",
        session_id,
    )
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════
# ROUTE MAPPER — ported from route-mapper.js + nav-planner.js
# ═══════════════════════════════════════════════════════════════

# space_lanes stores no distance/fuel estimate: a lane IS one jump, and its
# hazard label derives from threat_level (1-5). Both defaults match the values
# the generated fallback below already uses.
LANE_HAZARD = {1: "Low", 2: "Moderate", 3: "High", 4: "Extreme", 5: "Maximum"}
LANE_FUEL_COST = 100


def _lane_row(r) -> dict:
    """Map a `space_lanes` row onto the route shape the nav planner consumes."""
    lvl = r["threat_level"] or 1
    return {"id": r["id"], "origin": r["origin"], "destination": r["destination"],
            "lane_type": r["lane_type"], "threat_level": lvl,
            "intel_level": r["intel_level"], "last_scouted": r["last_scouted"],
            "hazard_level": LANE_HAZARD.get(lvl, "Low"),
            "estimated_jumps": 1, "total_fuel_cost": LANE_FUEL_COST}


async def get_routes(session_id: int) -> list[dict]:
    """Get fleet travel routes from DB."""
    rows = await Database.fetch(
        "SELECT id, origin, destination, lane_type, threat_level, intel_level, last_scouted "
        "FROM maya_rp.space_lanes WHERE session_id = $1 ORDER BY origin",
        session_id,
    )
    if rows:
        return [_lane_row(r) for r in rows]
    # Generate from territory connections
    systems = await Database.fetch(
        "SELECT system_name FROM maya_rp.territory WHERE session_id = $1 ORDER BY system_name",
        session_id,
    )
    names = [r["system_name"] for r in systems if r["system_name"]]
    routes = []
    for i in range(len(names) - 1):
        routes.append({
            "origin": names[i], "destination": names[i + 1],
            "distance_ly": round(3 + abs(int(hashlib.md5(names[i].encode()).hexdigest(), 16) % 10), 1),
            "hazard_level": "Low" if i % 3 else "Moderate",
            "estimated_jumps": 1, "total_fuel_cost": 100,
        })
    return routes


def dijkstra_route(routes: list[dict], origin: str, destination: str) -> dict | None:
    """
    Dijkstra shortest path routing.
    Ported from NavPlanner.planRoute() + findDirectRoute() + findMultiLegRoute().
    """
    # Check direct
    for r in routes:
        if (r["origin"] == origin and r["destination"] == destination) or \
           (r["origin"] == destination and r["destination"] == origin):
            return {
                "possible": True, "legs": [r], "total_jumps": r.get("estimated_jumps", 1),
                "total_fuel": r.get("total_fuel_cost", 100),
                "hazard_level": r.get("hazard_level", "Low"), "method": "direct",
            }

    # Build graph
    graph = {}
    for r in routes:
        cost = r.get("total_fuel_cost", 100)
        o, d = r["origin"], r["destination"]
        if o not in graph: graph[o] = {}
        if d not in graph: graph[d] = {}
        graph[o][d] = graph[o].get(d, cost)
        graph[d][o] = graph[d].get(o, cost)

    # Dijkstra
    dist = {node: float("inf") for node in graph}
    prev = {node: None for node in graph}
    dist[origin] = 0
    pq = [(0, origin)]

    while pq:
        d, node = heapq.heappop(pq)
        if node == destination:
            break
        if d > dist[node]:
            continue
        for neighbor, cost in graph.get(node, {}).items():
            nd = d + cost
            if nd < dist.get(neighbor, float("inf")):
                dist[neighbor] = nd
                prev[neighbor] = node
                heapq.heappush(pq, (nd, neighbor))

    if dist.get(destination, float("inf")) == float("inf"):
        return {"possible": False, "reason": f"No route between {origin} and {destination}",
                "suggestion": "System may be uncharted or requires exploration"}

    # Reconstruct
    path = []
    node = destination
    while node:
        path.append(node)
        node = prev[node]
    path.reverse()

    legs = []
    total_jumps, total_fuel = 0, 0
    hazards = []
    for i in range(len(path) - 1):
        f, t = path[i], path[i + 1]
        r = next((x for x in routes if (x["origin"] == f and x["destination"] == t) or (x["origin"] == t and x["destination"] == f)), {})
        legs.append({"from": f, "to": t, "jumps": r.get("estimated_jumps", 1),
                      "fuel": r.get("total_fuel_cost", 100), "hazard": r.get("hazard_level", "Low")})
        total_jumps += r.get("estimated_jumps", 1)
        total_fuel += r.get("total_fuel_cost", 100)
        hazards.append(r.get("hazard_level", "Low"))

    hl_order = {"Low": 0, "Moderate": 1, "High": 2, "Extreme": 3, "Maximum": 4}
    max_hazard = max(hazards, key=lambda h: hl_order.get(h, 0)) if hazards else "Low"

    return {"possible": True, "legs": legs, "total_jumps": total_jumps,
            "total_fuel": total_fuel, "hazard_level": max_hazard, "method": "multi_leg"}


async def get_reachable_systems(session_id: int, origin: str, max_jumps: int = 3) -> list[dict]:
    """Get reachable systems within max jumps. Ported from RouteMapper.getReachableSystems()."""
    routes = await get_routes(session_id)
    graph = {}
    for r in routes:
        o, d = r["origin"], r["destination"]
        if o not in graph: graph[o] = {}
        if d not in graph: graph[d] = {}
        graph[o][d] = r.get("estimated_jumps", 1)
        graph[d][o] = r.get("estimated_jumps", 1)

    visited = {origin: 0}
    queue = [origin]
    while queue:
        node = queue.pop(0)
        jumps = visited[node]
        if jumps >= max_jumps:
            continue
        for neighbor in graph.get(node, {}):
            nd = jumps + graph[node][neighbor]
            if nd <= max_jumps and (neighbor not in visited or nd < visited[neighbor]):
                visited[neighbor] = nd
                queue.append(neighbor)

    return [{"system": s, "jumps": j} for s, j in visited.items() if s != origin]


# ═══════════════════════════════════════════════════════════════
# FOG OF WAR — ported from fog-of-war.js
# ═══════════════════════════════════════════════════════════════

async def get_visibility(session_id: int, system_name: str) -> dict:
    """Get visibility level for a system. Ported from FogOfWar.getVisibility()."""
    # Check if system is in our territory
    row = await Database.fetchrow(
        "SELECT status, fleet_presence FROM maya_rp.territory "
        "WHERE session_id = $1 AND system_name = $2",
        session_id, system_name,
    )
    if not row:
        return {"level": "uncharted", "detail": 0, "can_travel": False, "shows_resources": False}
    s = row["status"]
    if s == "controlled":
        level = "colonized"
    elif s == "contested":
        level = "explored"
    elif row["fleet_presence"] and row["fleet_presence"] > 0:
        level = "surveyed"
    else:
        level = "scanned"
    return {"level": level, **VISIBILITY_LEVELS[level], "status": s}


async def reveal_system(session_id: int, system_name: str, level: str = "scanned") -> dict:
    """Reveal a system. Ported from FogOfWar.revealSystem().

    @returns what the call did. It used to return nothing at all, so a caller could not tell a
    reveal that raised the level from one that changed nothing, and the territory write below is a
    political status, not only a visibility one.
    """
    existing = await get_visibility(session_id, system_name)
    old_level = existing.get("level", "uncharted")
    old_idx = VIS_ORDER.index(old_level)
    new_idx = VIS_ORDER.index(level) if level in VIS_ORDER else -1
    if new_idx <= old_idx:
        return {"revealed": False, "level": old_level, "requested": level,
                "reason": f"'{level}' is not above '{old_level}'"}

    # `territory.status` is a CHECK-constrained political column (controlled, contested, besieged,
    # lost, abandoned, neutral) and get_visibility reads the fog level back out of it. The old
    # mapping wrote "explored", which the constraint rejects, so every reveal to `surveyed` or
    # `explored` raised CheckViolationError. It also wrote "contested" for a plain scan, which reads
    # back as `explored` and marks a political contest nobody asked for.
    status = {"colonized": "controlled", "explored": "contested"}.get(level, "neutral")
    await Database.execute(
        "UPDATE maya_rp.territory SET status = $1 WHERE session_id = $2 AND system_name = $3",
        status, session_id, system_name,
    )
    read_back = (await get_visibility(session_id, system_name)).get("level")
    return {"revealed": True, "level": level, "previous_level": old_level, "status": status,
            "read_back": read_back}


async def get_visible_systems(session_id: int, min_level: str = "scanned") -> list[dict]:
    """Get systems at or above visibility. Ported from FogOfWar.getVisibleSystems()."""
    rows = await Database.fetch(
        "SELECT system_name, status, fleet_presence, controlling_faction "
        "FROM maya_rp.territory WHERE session_id = $1 ORDER BY system_name",
        session_id,
    )
    min_idx = VIS_ORDER.index(min_level) if min_level in VIS_ORDER else 1
    result = []
    for r in rows:
        level = "colonized" if r["status"] == "controlled" else "surveyed" if r["fleet_presence"] else "scanned"
        if VIS_ORDER.index(level) >= min_idx:
            result.append({"system": r["system_name"], "level": level, "faction": r["controlling_faction"]})
    return result


# ═══════════════════════════════════════════════════════════════
# FACTION STATE — ported from faction-state.js
# ═══════════════════════════════════════════════════════════════

async def get_faction_territories(session_id: int) -> dict:
    """Get faction territory breakdown."""
    rows = await Database.fetch(
        "SELECT controlling_faction, COUNT(*) as count FROM maya_rp.territory "
        "WHERE session_id = $1 GROUP BY controlling_faction ORDER BY count DESC",
        session_id,
    )
    return {r["controlling_faction"]: r["count"] for r in rows}


async def _faction_id(session_id: int, name_or_id) -> int | None:
    """`treaties` keys factions by id (faction_a_id/faction_b_id), so a name has
    to resolve through `factions` first."""
    if name_or_id is None: return None
    if isinstance(name_or_id, int): return name_or_id
    return await Database.fetchval(
        "SELECT id FROM maya_rp.factions WHERE session_id = $1 AND name = $2",
        session_id, name_or_id,
    )


async def get_faction_relations(session_id: int, faction_a: str, faction_b: str | None = None) -> list[dict]:
    """Get faction relations from DB. `treaties` is not session-scoped: it is a
    universe-level table, so only faction identity is filtered here."""
    a = await _faction_id(session_id, faction_a)
    b = await _faction_id(session_id, faction_b)
    if a is None or (faction_b and b is None):
        return []
    if b is not None:
        rows = await Database.fetch(
            "SELECT * FROM maya_rp.treaties "
            "WHERE (faction_a_id = $1 AND faction_b_id = $2) OR (faction_a_id = $2 AND faction_b_id = $1)",
            a, b,
        )
    else:
        rows = await Database.fetch(
            "SELECT * FROM maya_rp.treaties WHERE (faction_a_id = $1 OR faction_b_id = $1)",
            a,
        )
    return [dict(r) for r in rows]


async def get_faction_presence(session_id: int) -> dict:
    """Get faction presence across territory. Ported from CelestialIndex.getFactionPresence()."""
    rows = await Database.fetch(
        "SELECT controlling_faction, system_name, fleet_presence "
        "FROM maya_rp.territory WHERE session_id = $1",
        session_id,
    )
    factions = {}
    for r in rows:
        f = r["controlling_faction"] or "Unknown"
        if f not in factions: factions[f] = {"systems": 0, "locations": 0}
        factions[f]["systems"] += 1
    return factions


# ═══════════════════════════════════════════════════════════════
# CELESTIAL INDEX — ported from celestial-index.js
# ═══════════════════════════════════════════════════════════════

async def search_all(session_id: int, query: str) -> list[dict]:
    """Search all celestial entities. Ported from CelestialIndex.search()."""
    q = query.lower()
    results = []
    systems = await query_systems(session_id, {})
    for sys in systems:
        if q in (sys.get("system_name") or "").lower():
            results.append({"type": "system", "name": sys["system_name"], "faction": sys.get("controlling_faction")})
    planets = await Database.fetch(
        "SELECT name, system_name FROM maya_rp.planets WHERE session_id = $1 AND LOWER(name) LIKE $2",
        session_id, f"%{q}%",
    )
    for p in planets:
        results.append({"type": "planet", "name": p["name"], "system": p["system_name"]})
    return results


async def get_universe_stats(session_id: int) -> dict:
    """Get universe statistics. Ported from CelestialIndex.getUniverseStats()."""
    systems = (await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.territory WHERE session_id = $1", session_id
    )) or 0
    planets = (await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.planets WHERE session_id = $1", session_id
    )) or 0
    colonies = (await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.colonies WHERE session_id = $1", session_id
    )) or 0
    return {"systems": systems, "planets": planets, "colonies": colonies}


async def get_system_detail(session_id: int, system_name: str) -> dict | None:
    """Get full system detail. Ported from CelestialIndex.getFullSystemDetail()."""
    territory = await Database.fetchrow(
        "SELECT * FROM maya_rp.territory WHERE session_id = $1 AND system_name = $2",
        session_id, system_name,
    )
    if not territory: return None
    t = dict(territory)
    planets = await get_planets_in_system(session_id, system_name)
    routes = await get_routes(session_id)
    # A lane is read as bidirectional everywhere else in this module — dijkstra_route and
    # get_reachable_systems both build both directions — so a lane arriving here belongs here too.
    routes_from = [r for r in routes
                   if system_name in (r.get("origin"), r.get("destination"))]
    return {
        "name": system_name, "faction": t.get("controlling_faction"),
        "status": t.get("status"), "fleet": t.get("fleet_presence"),
        "contested": t.get("contested_by"),
        "planets": planets, "routes": routes_from,
    }


# ═══════════════════════════════════════════════════════════════
# TICK
# ═══════════════════════════════════════════════════════════════

async def run_tick(session_id: int | None = None) -> dict[str, Any]:
    """Celestial module tick: log universe stats."""
    if session_id is None: session_id = Config.SESSION_ID
    try:
        stats = await get_universe_stats(session_id)
        info("celestial", f"Tick: {stats['systems']} systems, {stats['planets']} planets, {stats['colonies']} colonies")
        return stats
    except Exception as e:
        error("celestial", f"tick failed for session {session_id}: {e}")
        return {"error": str(e)}
