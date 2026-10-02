"""Megastructures & Ports — endgame mythical constructions and strategic port infrastructure."""
import random, json
from datetime import datetime, timezone, timedelta
from core.db import Database
from core.events import EventBus
from core.log import error

# ============================================================
# Megastructure Operations
# ============================================================

async def get_megastructure_types():
    """List all available megastructure blueprints."""
    return [dict(r) for r in await Database.fetch(
        "SELECT * FROM maya_rp.megastructure_types ORDER BY fantasy_tier, name"
    )]

async def start_construction(session_id: int, megastructure_type_id: int,
                             sector_id: int = None, territory_id: int = None) -> dict:
    """Begin building a megastructure."""
    mt = await Database.fetchrow(
        "SELECT * FROM maya_rp.megastructure_types WHERE id = $1", megastructure_type_id
    )
    if not mt:
        return {"error": "Megastructure type not found."}

    # Check research requirement
    if mt.get("research_required"):
        researched = await Database.fetchrow(
            "SELECT unlocked FROM maya_rp.research_projects WHERE name = $1",
            mt["research_required"]
        )
        if not researched or not researched["unlocked"]:
            return {"error": f'Research "{mt["research_required"]}" required.'}

    # Check phase 1 cost affordability
    phases = _j(mt.get("construction_phases"))
    if not phases:
        return {"error": "No construction phases defined."}
    phase1_cost = phases[0].get("cost", {})
    ok, msg = await _check_afford(session_id, phase1_cost)
    if not ok:
        return {"error": f"Insufficient resources: {msg}"}

    # Deduct phase 1 cost
    await _deduct_resources(session_id, phase1_cost)

    # Schedule completion
    total_days = sum(p.get("time_days", 0) for p in phases)
    estimated = datetime.now(timezone.utc) + timedelta(days=total_days)

    cid = await Database.fetchrow("""
        INSERT INTO maya_rp.megastructure_construction
            (session_id, megastructure_type_id, sector_id, territory_id,
             current_phase, progress_pct, started_at, estimated_completion,
             status, resources_allocated)
        VALUES ($1, $2, $3, $4, 1, 0, NOW(), $5, 'construction', $6)
        RETURNING id
    """, session_id, megastructure_type_id, sector_id, territory_id,
        estimated, json.dumps({"phase1": phase1_cost}))

    await _log(session_id, "megastructure",
               f"🏗️ Megastructure Started: {mt['name']}",
               f"Construction of {mt['name']} begun. Estimated: {estimated.strftime('%Y-%m-%d')}", 4)

    return {"construction_id": cid["id"], "name": mt["name"],
            "estimated_completion": estimated.isoformat()}

async def advance_megastructure(session_id: int, game_days: float = 0.5):
    """Tick — advance all active megastructure construction."""
    for const in await Database.fetch("""
        SELECT mc.*, mt.construction_phases, mt.name
        FROM maya_rp.megastructure_construction mc
        JOIN maya_rp.megastructure_types mt ON mt.id = mc.megastructure_type_id
        WHERE mc.status = 'construction'
    """):
        phases = _j(const.get("construction_phases"))
        if not phases or const["current_phase"] > len(phases):
            continue

        phase = phases[const["current_phase"] - 1]
        total_days = phase.get("time_days", 30)
        advance = (game_days / total_days) * 100
        new_progress = min(100, (const["progress_pct"] or 0) + advance)

        await Database.execute(
            "UPDATE maya_rp.megastructure_construction SET progress_pct = $1 WHERE id = $2",
            new_progress, const["id"]
        )

        if new_progress >= 100:
            if const["current_phase"] < len(phases):
                # Advance to next phase
                next_phase = phases[const["current_phase"]]
                next_cost = next_phase.get("cost", {})
                ok, _ = await _check_afford(session_id, next_cost)
                if ok:
                    await _deduct_resources(session_id, next_cost)
                    await Database.execute("""
                        UPDATE maya_rp.megastructure_construction
                        SET current_phase = $1, progress_pct = 0 WHERE id = $2
                    """, const["current_phase"] + 1, const["id"])
                    await _log(session_id, "megastructure",
                               f"Phase {const['current_phase']+1} Started: {const['name']}",
                               f"Phase {const['current_phase']+1} of {const['name']} begun.", 3)
                else:
                    await Database.execute(
                        "UPDATE maya_rp.megastructure_construction SET status = 'paused' WHERE id = $1",
                        const["id"]
                    )
                    await _log(session_id, "megastructure",
                               f"⏸️ Paused: {const['name']}",
                               "Insufficient resources for next phase. Paused.", 2)
            else:
                # COMPLETE!
                await Database.execute(
                    "UPDATE maya_rp.megastructure_construction SET status = 'completed' WHERE id = $1",
                    const["id"]
                )
                await _apply_benefits(session_id, const)
                await _log(session_id, "megastructure",
                           f"🎉 Megastructure Complete: {const['name']}",
                           f"The {const['name']} is fully operational!", 5)

async def get_megastructure_status():
    """View all megastructures in construction/completed."""
    return [dict(r) for r in await Database.fetch(
        "SELECT * FROM maya_rp.megastructure_status ORDER BY status, estimated_completion"
    )]

async def _apply_benefits(session_id: int, const: dict):
    """Apply completion benefits to the session."""
    mt = await Database.fetchrow(
        "SELECT benefits FROM maya_rp.megastructure_types WHERE id = $1",
        const["megastructure_type_id"]
    )
    if not mt:
        return
    benefits = _j(mt.get("benefits"))
    for key, val in benefits.items():
        if key == "production_mult":
            # Apply multiplier to resource production
            resources = await Database.fetchrow(
                "SELECT alloys FROM maya_rp.resources WHERE session_id = $1", session_id
            )
            if resources:
                await Database.execute(
                    "UPDATE maya_rp.resources SET alloys = GREATEST(alloys, alloys * $1) WHERE session_id = $2",
                    val, session_id
                )
        elif key == "morale_bonus":
            await Database.execute(
                "UPDATE maya_rp.territory SET morale = LEAST(100, morale + $1) WHERE session_id = $2",
                val, session_id
            )
        elif key.endswith("_production"):
            res = key.replace("_production", "")
            col = res if res in ("credits", "alloys", "fuel", "dream_essence",
                                  "rare_earth", "starsteel", "void_crystal") else None
            if col:
                await Database.execute(
                    f"UPDATE maya_rp.resources SET {col} = {col} + $1 WHERE session_id = $2",
                    int(val), session_id
                )

# ============================================================
# Port Operations
# ============================================================

async def get_port_types():
    """List all available port types."""
    return [dict(r) for r in await Database.fetch(
        "SELECT * FROM maya_rp.port_types ORDER BY category, name"
    )]

async def build_port(session_id: int, territory_id: int, port_type_id: int, name: str = None) -> dict:
    """Construct a port in a territory."""
    pt = await Database.fetchrow(
        "SELECT * FROM maya_rp.port_types WHERE id = $1", port_type_id
    )
    if not pt:
        return {"error": "Port type not found."}

    # Check and deduct cost
    cost = pt["build_cost_credits"]
    res_costs = _j(pt.get("build_cost_resources"))
    total_cost = {"credits": cost}
    for k, v in res_costs.items():
        total_cost[k] = v
    ok, msg = await _check_afford(session_id, total_cost)
    if not ok:
        return {"error": f"Insufficient resources: {msg}"}
    await _deduct_resources(session_id, total_cost)

    if not name:
        name = f"{pt['name']} {random.randint(100, 999)}"

    pid = await Database.fetchrow("""
        INSERT INTO maya_rp.ports (session_id, territory_id, port_type_id, name, level, built_at, status)
        VALUES ($1, $2, $3, $4, 1, NOW(), 'active') RETURNING id
    """, session_id, territory_id, port_type_id, name)

    await _log(session_id, "infrastructure",
               f"🏗️ Port Built: {name}",
               f"Constructed {pt['name']} in territory #{territory_id}.", 3)

    return {"port_id": pid["id"], "name": name, "type": pt["name"]}

async def upgrade_port(session_id: int, port_id: int, upgrade_name: str) -> dict:
    """Upgrade a port with a named upgrade."""
    port = await Database.fetchrow("SELECT * FROM maya_rp.ports WHERE id = $1", port_id)
    if not port:
        return {"error": "Port not found."}

    pt = await Database.fetchrow(
        "SELECT upgrades FROM maya_rp.port_types WHERE id = $1", port["port_type_id"]
    )
    if not pt or upgrade_name not in (_j(pt.get("upgrades")) or []):
        return {"error": f"Upgrade '{upgrade_name}' not available for this port type."}

    cost = 100000 * port["level"]
    ok, _ = await _check_afford(session_id, {"credits": cost})
    if not ok:
        return {"error": "Insufficient credits."}
    await _deduct_resources(session_id, {"credits": cost})

    new_level = port["level"] + 1
    upgrades = list(_j(port.get("upgrades_applied")) or [])
    upgrades.append(upgrade_name)

    await Database.execute(
        "UPDATE maya_rp.ports SET level = $1, upgrades_applied = $2 WHERE id = $3",
        new_level, json.dumps(upgrades), port_id
    )
    await Database.execute(
        "INSERT INTO maya_rp.port_upgrades (port_id, upgrade_name, cost_credits) VALUES ($1, $2, $3)",
        port_id, upgrade_name, cost
    )

    await _log(session_id, "infrastructure",
               f"⬆️ Port Upgraded: {port['name']}",
               f"Level {new_level} with {upgrade_name}.", 2)

    return {"port_id": port_id, "new_level": new_level, "upgrade": upgrade_name}

async def get_port_overview():
    """View all ports."""
    return [dict(r) for r in await Database.fetch(
        "SELECT * FROM maya_rp.port_overview ORDER BY territory_name, name"
    )]

# ============================================================
# Tick
# ============================================================

async def run_tick(session_id: int = 3):
    """Megastructure + Port tick — advance construction."""
    try:
        await advance_megastructure(session_id)
    except Exception as e:
        print(f"  Megastructures: {e}")

# ============================================================
# Helpers
# ============================================================

def _j(v):
    """Parse JSONB values that asyncpg may return as strings."""
    if isinstance(v, str):
        return json.loads(v)
    return v if v else {}

async def _check_afford(session_id: int, costs: dict) -> tuple:
    """Check if session can afford costs. Returns (ok, missing_resource)."""
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

async def _deduct_resources(session_id: int, costs: dict):
    """Deduct costs from session resources."""
    for res, qty in costs.items():
        if res in ("credits", "alloys", "fuel", "dream_essence",
                   "rare_earth", "starsteel", "void_crystal", "aetherium"):
            await Database.execute(
                f"UPDATE maya_rp.resources SET {res} = GREATEST(0, {res} - $1) WHERE session_id = $2",
                qty, session_id
            )

async def _log(sid, category, title, content, importance=2):
    """Write narrative entry."""
    try:
        await Database.execute(
            "INSERT INTO maya_rp.story_log (session_id, category, title, content, importance, happened_at) "
            "VALUES ($1, $2, $3, $4, $5, NOW())",
            sid, category, title, content, importance
        )
    except Exception as e:  # noqa: BLE001 - reported below
        error("megastructures-ports", f"_log: {e}")
