"""Space Horror — bug infestation containment, war, and eradication."""
import random, json
from datetime import datetime, timezone
from core.db import Database
from modules._economy import _check_afford, _deduct_resources
from core.events import EventBus
from core.log import error

# ============================================================
# Infestation Management
# ============================================================

async def seed_infestation(session_id: int, sector_id: int, territory_id: int = None) -> dict:
    """Seed a new space bug infestation. The horror begins."""
    existing = await Database.fetchrow(
        "SELECT id FROM maya_rp.infestation_instances WHERE sector_id = $1 AND status NOT IN ('destroyed','eradicated')",
        sector_id
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

    await EventBus.emit("infestation_seeded", {"infestation_id": iid["id"], "sector_id": sector_id})
    return {"infestation_id": iid["id"], "sector": sname, "stage": "Spore Drift"}

async def spread_infestation(session_id: int, game_days: float = 0.5):
    """Tick — spread infestation across sectors and escalate stages."""
    for inst in await Database.fetch("""
        SELECT ii.*, st.spread_rate, st.threat_level, st.name AS stage_name
        FROM maya_rp.infestation_instances ii
        JOIN maya_rp.infestation_stages st ON st.id = ii.stage_id
        WHERE ii.status = 'active'
    """):
        base_spread = inst["spread_rate"] * game_days
        if inst.get("contained"):
            base_spread *= max(0, 1 - (inst["containment_level"] or 0) / 100)

        new_progress = (inst["spread_progress"] or 0) + base_spread * 5

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
                """, new_progress, int(inst["spread_rate"] * game_days * 10), inst["id"])
        else:
            await Database.execute("""
                UPDATE maya_rp.infestation_instances
                SET spread_progress = $1, biomass = biomass + $2
                WHERE id = $3
            """, new_progress, int(inst["spread_rate"] * game_days * 5), inst["id"])

        # Spread to neighbor sectors
        if random.random() < (0.01 * inst["threat_level"] * game_days):
            neighbors = await Database.fetch(
                "SELECT destination FROM maya_rp.space_lanes WHERE origin = $1",
                inst["sector_id"]
            )
            if neighbors:
                target = random.choice(neighbors)["destination"]
                existing = await Database.fetchrow(
                    "SELECT id FROM maya_rp.infestation_instances "
                    "WHERE sector_id = $1 AND status = 'active'", target
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
    inf = await Database.fetchrow(
        "SELECT * FROM maya_rp.infestation_instances WHERE id = $1", infestation_id
    )
    if not inf:
        return {"error": "Infestation not found."}

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

    # Check and deduct cost
    cost = {"credits": measure["cost_credits"]}
    res_costs = _j(measure.get("cost_resources"))
    for k, v in res_costs.items():
        cost[k] = v
    ok, msg = await _check_afford(session_id, cost)
    if not ok:
        return {"error": f"Insufficient: {msg}"}
    await _deduct_resources(session_id, cost)

    new_level = min(100, (inf["containment_level"] or 0) + int(measure["effectiveness"] * 30))
    await Database.execute("""
        UPDATE maya_rp.infestation_instances SET contained = TRUE, containment_level = $1 WHERE id = $2
    """, new_level, infestation_id)

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
    inf = await Database.fetchrow(
        "SELECT * FROM maya_rp.infestation_instances WHERE id = $1", infestation_id
    )
    if not inf or inf["status"] in ("destroyed", "eradicated"):
        return {"error": "Infestation not found or already gone."}

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
    for camp in await Database.fetch(
        "SELECT * FROM maya_rp.eradication_campaigns WHERE status = 'active'"
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
        new_progress = min(100, (camp["progress"] or 0) + gain)
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

    if "damage" in effects and _j(camp.get("assets_assigned")):
        assets = list(camp["assets_assigned"])
        if assets:
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
    """List all active infestation threats."""
    return [dict(r) for r in await Database.fetch(
        "SELECT * FROM maya_rp.infestation_threats"
    )]

async def get_infestation_detail(infestation_id: int) -> dict:
    """Detailed view of a specific infestation."""
    row = await Database.fetchrow("""
        SELECT ii.*, st.name AS stage, st.threat_level, st.description AS stage_description,
               s.name AS sector_name, t.system_name AS territory_name
        FROM maya_rp.infestation_instances ii
        JOIN maya_rp.infestation_stages st ON st.id = ii.stage_id
        LEFT JOIN maya_rp.sectors s ON s.id = ii.sector_id
        LEFT JOIN maya_rp.territory t ON t.id = ii.territory_id
        WHERE ii.id = $1
    """, infestation_id)
    return dict(row) if row else {}

# ============================================================
# Tick
# ============================================================

async def run_tick(session_id: int = 3):
    """Full space horror tick — spread, eradicate, seed new."""
    try:
        gd = 0.5
        await spread_infestation(session_id, gd)
        await advance_eradication(session_id, gd)

        # Random new infestation in clean sectors
        if random.random() < 0.01 * gd:
            sectors = await Database.fetch("""
                SELECT id FROM maya_rp.sectors
                WHERE id NOT IN (
                    SELECT sector_id FROM maya_rp.infestation_instances WHERE status NOT IN ('destroyed','eradicated')
                )
                ORDER BY random() LIMIT 1
            """)
            if sectors:
                await seed_infestation(session_id, sectors[0]["id"])
    except Exception as e:
        print(f"  Space Horror: {e}")

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
