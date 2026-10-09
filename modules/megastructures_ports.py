"""Megastructures & Ports — endgame mythical constructions and strategic port infrastructure."""
import random, json
from datetime import datetime, timezone, timedelta
from core.db import Database
from core.config import Config
from modules._economy import _check_afford, _deduct_resources, stochastic_round
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

    # `estimated_completion` is TIMESTAMP WITHOUT TIME ZONE and asyncpg raises DataError on a tz-aware
    # value for it (measured on 0.31.0), so the timestamp is stripped before the insert. Charge and
    # insert share one transaction because a debit committed alone left the credits spent with no
    # construction row when the insert raised on that timestamp.
    total_days = sum(p.get("time_days", 0) for p in phases)
    estimated = (datetime.now(timezone.utc) + timedelta(days=total_days)).replace(tzinfo=None)

    async with Database.transaction() as conn:
        charged = await _deduct_resources(session_id, phase1_cost, conn)
        cid = await conn.fetchrow("""
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
            "estimated_completion": estimated.isoformat(), "charged": charged}

async def advance_megastructure(session_id: int, game_days: float = 0.5) -> dict:
    """Tick — advance all active megastructure construction.

    The read took no session, so one campaign's tick advanced every campaign's construction sites,
    and a phase that fell due elsewhere was charged to whichever session ran the tick.

    A `paused` site is read as well: no statement anywhere writes `construction` back after the
    pause, so a read filtered on that one status dropped a site for good the moment it could not
    afford its next phase, and it was never retried once the treasury recovered.
    """
    tally = {"advanced": 0, "paused": 0, "completed": 0}
    for const in await Database.fetch("""
        SELECT mc.*, mt.construction_phases, mt.name
        FROM maya_rp.megastructure_construction mc
        JOIN maya_rp.megastructure_types mt ON mt.id = mc.megastructure_type_id
        WHERE mc.status IN ('construction', 'paused') AND mc.session_id = $1
    """, session_id):
        phases = _j(const.get("construction_phases"))
        if not phases or const["current_phase"] > len(phases):
            continue

        phase = phases[const["current_phase"] - 1]
        total_days = phase.get("time_days", 30)
        advance = (game_days / total_days) * 100
        # `progress_pct` is INTEGER and asyncpg truncates a float into it without a word (measured on
        # 0.31.0: `SELECT $1::int4` with 0.25 gives 0). A tick adds well under one percent: 0.5 game
        # days against a 365-day phase is 0.137, so a truncated write stored 0 on every tick and the
        # site never moved. `int()` truncates the same way and would reproduce the defect in Python.
        new_progress = min(100, stochastic_round((const["progress_pct"] or 0) + advance))

        await Database.execute(
            "UPDATE maya_rp.megastructure_construction SET progress_pct = $1 WHERE id = $2",
            new_progress, const["id"]
        )
        tally["advanced"] += 1

        if new_progress >= 100:
            if const["current_phase"] < len(phases):
                # Advance to next phase
                next_phase = phases[const["current_phase"]]
                next_cost = next_phase.get("cost", {})
                ok, _ = await _check_afford(session_id, next_cost)
                if ok:
                    await _deduct_resources(session_id, next_cost)
                    # The resume rides on the phase this site can now pay for. Writing
                    # `construction` on the progress update instead flipped the site back a tick
                    # early, so the next tick paused it again: one stall, two log entries.
                    await Database.execute("""
                        UPDATE maya_rp.megastructure_construction
                        SET current_phase = $1, progress_pct = 0, status = 'construction' WHERE id = $2
                    """, const["current_phase"] + 1, const["id"])
                    if const["status"] == "paused":
                        await _log(session_id, "megastructure",
                                   f"▶️ Resumed: {const['name']}",
                                   "The next phase is affordable again; construction resumed.", 2)
                    await _log(session_id, "megastructure",
                               f"Phase {const['current_phase']+1} Started: {const['name']}",
                               f"Phase {const['current_phase']+1} of {const['name']} begun.", 3)
                else:
                    # One write and one entry per stall, not per tick: the paused site is in the
                    # read set now, so an unguarded branch logged the shortage on every tick.
                    if const["status"] != "paused":
                        await Database.execute(
                            "UPDATE maya_rp.megastructure_construction SET status = 'paused' WHERE id = $1",
                            const["id"]
                        )
                        await _log(session_id, "megastructure",
                                   f"⏸️ Paused: {const['name']}",
                                   "Insufficient resources for next phase. Paused.", 2)
                    tally["paused"] += 1
            else:
                # COMPLETE!
                await Database.execute(
                    "UPDATE maya_rp.megastructure_construction SET status = 'completed' WHERE id = $1",
                    const["id"]
                )
                tally["completed"] += 1
                await _apply_benefits(session_id, const)
                await _log(session_id, "megastructure",
                           f"🎉 Megastructure Complete: {const['name']}",
                           f"The {const['name']} is fully operational!", 5)
    return tally

async def get_megastructure_status(session_id: int | None = None):
    """This session's megastructures, in construction or completed.

    Reviewed 2026-10-03 before wiring. Neither this nor `get_port_overview` scoped by session: the
    view behind it exposed no `session_id` at all, so playing Arc I listed the frozen campaign's
    construction sites. Migration 129 adds the column; this asks for it.
    """
    if session_id is None:
        session_id = Config.SESSION_ID
    return [dict(r) for r in await Database.fetch(
        "SELECT * FROM maya_rp.megastructure_status WHERE session_id = $1"
        " ORDER BY status, estimated_completion", session_id
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
    charged = await _deduct_resources(session_id, total_cost)

    if not name:
        name = f"{pt['name']} {random.randint(100, 999)}"

    rid = await Database.fetchrow("""
        INSERT INTO maya_rp.ports (session_id, territory_id, port_type_id, name, level, built_at, status)
        VALUES ($1, $2, $3, $4, 1, NOW(), 'active') RETURNING id
    """, session_id, territory_id, port_type_id, name)

    await _log(session_id, "infrastructure",
               f"🏗️ Port Built: {name}",
               f"Constructed {pt['name']} in territory #{territory_id}.", 3)
    return {"port_id": rid["id"], "name": name, "type": pt["name"], "charged": charged}


async def upgrade_port(session_id: int, port_id: int, upgrade_name: str) -> dict:
    """Upgrade a port with a named upgrade.

    The port was resolved by id alone, so a campaign could spend its own credits raising another
    campaign's port.
    """
    port = await Database.fetchrow(
        "SELECT * FROM maya_rp.ports WHERE id = $1 AND session_id = $2", port_id, session_id)
    if not port:
        return {"error": f"Port {port_id} not found in session {session_id}."}

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

async def get_port_overview(session_id: int | None = None):
    """This session's ports."""
    if session_id is None:
        session_id = Config.SESSION_ID
    return [dict(r) for r in await Database.fetch(
        "SELECT * FROM maya_rp.port_overview WHERE session_id = $1 ORDER BY territory_name, name",
        session_id
    )]

# ============================================================
# Tick
# ============================================================

async def run_tick(session_id: int | None = None) -> dict:
    """Megastructure + Port tick — advance construction."""
    if session_id is None:
        # The default was the literal 3, the frozen reference campaign: a tick run without an
        # argument advanced that campaign's building sites.
        session_id = Config.SESSION_ID
    try:
        return await advance_megastructure(session_id)
    except Exception as e:
        # A `print` into the tick's stdout is not a log: nothing durable recorded the fault.
        error("megastructures-ports", f"tick failed for session {session_id}: {e}")
        return {"error": str(e)}

# ============================================================
# Helpers
# ============================================================

def _j(v):
    """Parse JSONB values that asyncpg may return as strings."""
    if isinstance(v, str):
        return json.loads(v)
    return v if v else {}

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
