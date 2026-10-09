"""Space Horror — bug infestation containment, war, and eradication."""
import random, json
from datetime import datetime, timezone
from core.db import Database
from core.config import Config
from core.session import require_session
from modules._economy import InsufficientResources, _deduct_resources, stochastic_round
from core.events import EventBus
from core.log import error

# ============================================================
# Infestation Management
# ============================================================

async def seed_infestation(session_id: int, sector_id: int, territory_id: int = None) -> dict:
    """Seed a new space bug infestation. The horror begins."""
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    existing = await Database.fetchrow(
        "SELECT id FROM maya_rp.infestation_instances WHERE session_id = $1 AND sector_id = $2 "
        "AND status NOT IN ('destroyed','eradicated')",
        session_id, sector_id
    )
    if existing:
        return {"error": "Sector already infested."}

    stage = await Database.fetchrow(
        "SELECT id FROM maya_rp.infestation_stages WHERE name = 'Spore Drift'"
    )
    if not stage:
        return {"error": "Infestation stage not found."}

    iid = await Database.fetchrow("""
        INSERT INTO maya_rp.infestation_instances
            (session_id, sector_id, territory_id, stage_id, biomass, spread_progress,
             discovered, contained, created_at, status)
        VALUES ($1, $2, $3, $4, $5, 0, FALSE, FALSE, NOW(), 'active')
        RETURNING id
    """, session_id, sector_id, territory_id, stage["id"], random.randint(10, 50))

    sector = await Database.fetchrow("SELECT name FROM maya_rp.sectors WHERE id = $1", sector_id)
    sname = sector["name"] if sector else f"Sector #{sector_id}"
    await _log(session_id, "horror",
               "🚨 SOMETHING IS WRONG",
               f"Strange readings from {sname}. Spores detected. Infestation begun.", 5)

    await EventBus.emit("infestation_seeded", {"infestation_id": iid["id"], "sector_id": sector_id,
                                               "session_id": session_id})
    return {"infestation_id": iid["id"], "sector": sname, "stage": "Spore Drift"}

async def spread_infestation(session_id: int, game_days: float = 0.5):
    """Tick — spread infestation across sectors and escalate stages.

    The read took no session, so every campaign's infestations spread on every campaign's tick and
    the writes below landed on rows belonging to the other one. A campaign is its own horror.
    """
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    for inst in await Database.fetch("""
        SELECT ii.*, st.spread_rate, st.threat_level, st.name AS stage_name
        FROM maya_rp.infestation_instances ii
        JOIN maya_rp.infestation_stages st ON st.id = ii.stage_id
        WHERE ii.status = 'active' AND ii.session_id = $1
    """, session_id):
        # `spread_rate` is NUMERIC and arrives as Decimal, which a float multiply refuses.
        rate = float(inst["spread_rate"])
        base_spread = rate * game_days
        if inst.get("contained"):
            base_spread *= max(0, 1 - (inst["containment_level"] or 0) / 100)

        # `spread_progress` and `biomass` are INTEGER and a tick adds under 1 at slow rates
        # (Spore Drift: 0.25), so a plain int() would store 0 on every tick.
        new_progress = min(100, stochastic_round((inst["spread_progress"] or 0) + base_spread * 5))

        if new_progress >= 100:
            next_s = await Database.fetchrow(
                "SELECT id, name, threat_level FROM maya_rp.infestation_stages "
                "WHERE threat_level > $1 ORDER BY threat_level LIMIT 1",
                inst["threat_level"]
            )
            if next_s:
                await Database.execute(
                    "UPDATE maya_rp.infestation_instances SET stage_id = $1, spread_progress = 0 WHERE id = $2",
                    next_s["id"], inst["id"]
                )
                sector = await Database.fetchrow(
                    "SELECT name FROM maya_rp.sectors WHERE id = $1", inst["sector_id"]
                )
                await _log(session_id, "horror",
                           f"⚠️ INFESTATION ESCALATES: {next_s['name']}",
                           f"{sector['name'] if sector else ''} stage: {next_s['name']} (threat {next_s['threat_level']}).", 4)

                if next_s["threat_level"] >= 8:
                    await _trigger_crisis(session_id, inst)
            else:
                await Database.execute("""
                    UPDATE maya_rp.infestation_instances
                    SET spread_progress = $1, biomass = biomass + $2
                    WHERE id = $3
                """, new_progress, stochastic_round(rate * game_days * 10), inst["id"])
        else:
            await Database.execute("""
                UPDATE maya_rp.infestation_instances
                SET spread_progress = $1, biomass = biomass + $2
                WHERE id = $3
            """, new_progress, stochastic_round(rate * game_days * 5), inst["id"])

        # Spread to neighbor sectors. `space_lanes.origin` and `.destination` are sector NAMES (TEXT),
        # and `sectors` is UNIQUE (session_id, name), so the join inside the lane's session maps the
        # infested sector id to its neighbours' ids. A name with no sector in this session resolves to nothing.
        if random.random() < (0.01 * inst["threat_level"] * game_days):
            neighbors = await Database.fetch("""
                SELECT d.id FROM maya_rp.space_lanes sl
                JOIN maya_rp.sectors o ON o.name = sl.origin AND o.session_id = sl.session_id
                JOIN maya_rp.sectors d ON d.name = sl.destination AND d.session_id = sl.session_id
                WHERE sl.session_id = $1 AND o.id = $2
            """, session_id, inst["sector_id"])
            if neighbors:
                target = random.choice(neighbors)["id"]
                existing = await Database.fetchrow(
                    "SELECT id FROM maya_rp.infestation_instances "
                    "WHERE session_id = $1 AND sector_id = $2 AND status = 'active'",
                    session_id, target
                )
                if not existing:
                    await seed_infestation(session_id, target)

async def _trigger_crisis(session_id: int, inst: dict):
    """Trigger a crisis event for high-threat infestations."""
    sector = await Database.fetchrow("SELECT name FROM maya_rp.sectors WHERE id = $1", inst["sector_id"])
    await Database.execute("""
        INSERT INTO maya_rp.crisis_events (session_id, crisis_type, severity, started_at, description)
        VALUES ($1, 'infestation', $2, NOW(), $3)
    """, session_id, inst["threat_level"],
        f"Space bug infestation in {sector['name'] if sector else ''} at crisis level {inst['threat_level']}!")

# ============================================================
# Containment
# ============================================================

async def get_containment_measures() -> list:
    return [dict(r) for r in await Database.fetch(
        "SELECT * FROM maya_rp.containment_measures ORDER BY name"
    )]

async def apply_containment(session_id: int, infestation_id: int, measure_name: str) -> dict:
    """Apply a containment measure to slow the infestation."""
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    inf = await Database.fetchrow(
        "SELECT * FROM maya_rp.infestation_instances WHERE id = $1 AND session_id = $2",
        infestation_id, session_id
    )
    if not inf:
        return {"error": f"Infestation {infestation_id} not found in session {session_id}."}

    measure = await Database.fetchrow(
        "SELECT * FROM maya_rp.containment_measures WHERE name = $1", measure_name
    )
    if not measure:
        return {"error": "Containment measure not found."}

    # Check research
    if measure.get("research_required"):
        researched = await Database.fetchrow(
            "SELECT unlocked FROM maya_rp.research_projects WHERE name = $1",
            measure["research_required"]
        )
        if not researched or not researched["unlocked"]:
            return {"error": f'Research "{measure["research_required"]}" required.'}

    cost = {"credits": measure["cost_credits"]}
    res_costs = _j(measure.get("cost_resources"))
    for k, v in res_costs.items():
        cost[k] = v

    # The guarded debit decides affordability, so no read-then-debit window exists. The charge and
    # the containment commit together: a fault in the effect refunds the cost.
    new_level = min(100, (inf["containment_level"] or 0) + int(measure["effectiveness"] * 30))
    try:
        async with Database.transaction() as conn:
            await _deduct_resources(session_id, cost, conn=conn)
            await conn.execute("""
                UPDATE maya_rp.infestation_instances SET contained = TRUE, containment_level = $1 WHERE id = $2
            """, new_level, infestation_id)
    except InsufficientResources as e:
        return {"error": f"Insufficient: {e}"}

    await _log(session_id, "horror",
               f"🛡️ CONTAINMENT: {measure_name}",
               f"Containment level: {new_level}%.", 3)
    return {"success": True, "measure": measure_name, "containment_level": new_level}

# ============================================================
# Bug War — Eradication Campaigns
# ============================================================

async def get_bug_war_assets() -> list:
    return [dict(r) for r in await Database.fetch(
        "SELECT * FROM maya_rp.bug_war_assets ORDER BY type, name"
    )]

async def launch_eradication(session_id: int, infestation_id: int,
                              strategy: str = "systematic", assets: list = None) -> dict:
    """Launch a military campaign to eradicate an infestation."""
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    inf = await Database.fetchrow(
        "SELECT * FROM maya_rp.infestation_instances WHERE id = $1 AND session_id = $2",
        infestation_id, session_id
    )
    if not inf or inf["status"] in ("destroyed", "eradicated"):
        return {"error": f"Infestation {infestation_id} not found in session {session_id},"
                         f" or already gone."}

    cid = await Database.fetchrow("""
        INSERT INTO maya_rp.eradication_campaigns
            (session_id, target_infestation_id, campaign_name, strategy,
             assets_assigned, status)
        VALUES ($1, $2, $3, $4, $5, 'active')
        RETURNING id
    """, session_id, infestation_id,
        f"Campaign #{random.randint(100, 999)}",
        strategy, json.dumps(assets or []))

    sector = await Database.fetchrow("SELECT name FROM maya_rp.sectors WHERE id = $1", inf["sector_id"])
    await _log(session_id, "war",
               "⚔️ ERADICATION LAUNCHED",
               f"Campaign against infestation in {sector['name'] if sector else ''}. Strategy: {strategy}.", 5)

    return {"campaign_id": cid["id"], "strategy": strategy}

async def advance_eradication(session_id: int, game_days: float = 0.5):
    """Tick — advance all active eradication campaigns."""
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    for camp in await Database.fetch(
        "SELECT * FROM maya_rp.eradication_campaigns WHERE status = 'active' AND session_id = $1",
        session_id
    ):
        inf = await Database.fetchrow(
            "SELECT * FROM maya_rp.infestation_instances WHERE id = $1",
            camp["target_infestation_id"]
        )
        if not inf or inf["status"] in ("destroyed", "eradicated"):
            await Database.execute(
                "UPDATE maya_rp.eradication_campaigns SET status = 'successful', completed_at = NOW() WHERE id = $1",
                camp["id"]
            )
            continue

        strat_mod = {"systematic": 1.0, "bombardment": 1.3,
                      "biological": 0.8, "psychic": 0.9}.get(camp["strategy"], 1.0)
        assets = _j(camp.get("assets_assigned")) or []
        asset_bonus = 1 + len(assets) * 0.1

        gain = 5 * strat_mod * asset_bonus * game_days
        # `progress` is INTEGER and a tick adds under 1 at low game_days; int() would stall the campaign.
        new_progress = min(100, stochastic_round((camp["progress"] or 0) + gain))
        biomass_removed = int((inf["biomass"] or 0) * (gain / 100))

        await Database.execute(
            "UPDATE maya_rp.eradication_campaigns SET progress = $1 WHERE id = $2",
            new_progress, camp["id"]
        )
        await Database.execute(
            "UPDATE maya_rp.infestation_instances SET biomass = GREATEST(0, biomass - $1) WHERE id = $2",
            biomass_removed, inf["id"]
        )

        if new_progress >= 100 or (inf["biomass"] or 0) <= 0:
            await Database.execute("""
                UPDATE maya_rp.infestation_instances SET status = 'eradicated', destroyed_at = NOW() WHERE id = $1
            """, inf["id"])
            await Database.execute("""
                UPDATE maya_rp.eradication_campaigns SET status = 'successful', completed_at = NOW() WHERE id = $1
            """, camp["id"])

            sector = await Database.fetchrow("SELECT name FROM maya_rp.sectors WHERE id = $1", inf["sector_id"])
            await _log(session_id, "war",
                       "🎉 INFESTATION ERADICATED",
                       f"The infestation in {sector['name'] if sector else ''} is no more!", 6)
        elif random.random() < 0.05 * game_days:
            await _generate_campaign_event(session_id, camp, inf)

async def _generate_campaign_event(session_id: int, camp: dict, inf: dict):
    """Random event during eradication."""
    events = [
        ("mutant_attack", "Mutant bugs attacked the fleet!", {"damage": 20}),
        ("supply_issue", "Supply lines disrupted. Progress slowed.", {"penalty": 0.5}),
        ("breakthrough", "New weakness discovered! Progress boosted.", {"bonus": 1.5}),
        ("casualties", "Squadron lost in combat.", {"casualties": 10})
    ]
    etype, desc, effects = random.choice(events)

    # `assets_assigned` is jsonb with no codec, so it arrives as a str; `_j` decodes it. list() on
    # the str would split it into characters. NULL and an empty list both mean no assets.
    decoded = _j(camp.get("assets_assigned"))
    assets = list(decoded) if isinstance(decoded, list) else []
    if "damage" in effects and assets:
        assets.pop(random.randrange(len(assets)))
        await Database.execute(
            "UPDATE maya_rp.eradication_campaigns SET assets_assigned = $1 WHERE id = $2",
            json.dumps(assets), camp["id"]
        )
    if "bonus" in effects:
        await Database.execute(
            "UPDATE maya_rp.eradication_campaigns SET progress = progress + 5 WHERE id = $1",
            camp["id"]
        )

    await _log(session_id, "war",
               f"⚡ CAMPAIGN: {etype.replace('_',' ').upper()}", desc, 3)

async def get_active_threats(session_id: int) -> list:
    """This session's active infestation threats.

    The signature took a session and the query ignored it: `SELECT * FROM infestation_threats` with no
    WHERE at all, so Arc I listed the frozen campaign's infestations. A parameter that does nothing is
    worse than a missing one, because it reads as scoping at every call site.
    """
    return [dict(r) for r in await Database.fetch(
        "SELECT * FROM maya_rp.infestation_threats WHERE session_id = $1", session_id
    )]

async def get_infestation_detail(infestation_id: int, session_id: int | None = None) -> dict:
    """Detailed view of one infestation, from this session."""
    session_id = require_session(session_id)
    row = await Database.fetchrow("""
        SELECT ii.*, st.name AS stage, st.threat_level, st.description AS stage_description,
               s.name AS sector_name, t.system_name AS territory_name
        FROM maya_rp.infestation_instances ii
        JOIN maya_rp.infestation_stages st ON st.id = ii.stage_id
        LEFT JOIN maya_rp.sectors s ON s.id = ii.sector_id
        LEFT JOIN maya_rp.territory t ON t.id = ii.territory_id
        WHERE ii.id = $1 AND ii.session_id = $2
    """, infestation_id, session_id)
    return dict(row) if row else {}

# ============================================================
# Tick
# ============================================================

async def run_tick(session_id: int | None = None):
    """Full space horror tick — spread, eradicate, seed new."""
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    try:
        gd = 0.5
        await spread_infestation(session_id, gd)
        await advance_eradication(session_id, gd)

        # Random new infestation in clean sectors
        if random.random() < 0.01 * gd:
            sectors = await Database.fetch("""
                SELECT id FROM maya_rp.sectors
                WHERE session_id = $1 AND id NOT IN (
                    SELECT sector_id FROM maya_rp.infestation_instances
                    WHERE session_id = $1 AND status NOT IN ('destroyed','eradicated')
                )
                ORDER BY random() LIMIT 1
            """, session_id)
            if sectors:
                await seed_infestation(session_id, sectors[0]["id"])
    except Exception as e:
        # A `print` into the tick's stdout is not a log: nothing durable recorded the fault.
        error("space-horror", f"tick failed for session {session_id}: {e}")
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
    try:
        await Database.execute(
            "INSERT INTO maya_rp.story_log (session_id, category, title, content, importance, happened_at) "
            "VALUES ($1, $2, $3, $4, $5, NOW())",
            sid, category, title, content, importance
        )
    except Exception as e:  # noqa: BLE001 - reported below
        error("space-horror", f"_log: {e}")
