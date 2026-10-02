"""Infrastructure — mining, refineries, stations, factories, farms, defense, logistics, arcane."""
import random, json
from datetime import datetime, timezone
from core.db import Database
from core.events import EventBus
from core.log import error

async def get_types_by_category(category: str) -> list:
    """Get infrastructure types filtered by category."""
    return [dict(r) for r in await Database.fetch(
        "SELECT * FROM maya_rp.infrastructure_types WHERE category = $1 ORDER BY fantasy_tier, name",
        category
    )]

async def build_infrastructure(session_id: int, type_id: int,
                               territory_id: int = None, sector_id: int = None,
                               name: str = None) -> dict:
    """Construct an infrastructure facility."""
    it = await Database.fetchrow(
        "SELECT * FROM maya_rp.infrastructure_types WHERE id = $1", type_id
    )
    if not it:
        return {"error": "Infrastructure type not found."}

    # Check research gate
    if it.get("required_tech"):
        researched = await Database.fetchrow(
            "SELECT unlocked FROM maya_rp.research_projects WHERE name = $1",
            it["required_tech"]
        )
        if not researched or not researched["unlocked"]:
            return {"error": f'Research "{it["required_tech"]}" required.'}

    # Check cost
    cost = {"credits": it["build_cost_credits"]}
    res_costs = _j(it.get("build_cost_resources"))
    for k, v in res_costs.items():
        cost[k] = v
    ok, msg = await _check_afford(session_id, cost)
    if not ok:
        return {"error": f"Insufficient resources: {msg}"}
    await _deduct_resources(session_id, cost)

    if not name:
        name = f"{it['name']} {random.randint(100, 999)}"

    iid = await Database.fetchrow("""
        INSERT INTO maya_rp.infrastructure_instances
            (session_id, infrastructure_type_id, territory_id, sector_id,
             name, level, status, built_at)
        VALUES ($1, $2, $3, $4, $5, 1, 'active', NOW())
        RETURNING id
    """, session_id, type_id, territory_id, sector_id, name)

    await _log(session_id, "infrastructure",
               f"🏗️ {it['category'].title()} Built: {name}",
               f"Constructed {it['name']} ({it['category']}).", 2)

    return {"infrastructure_id": iid["id"], "name": name,
            "type": it["name"], "category": it["category"]}

async def get_infrastructure(inst_id: int) -> dict:
    """Get infrastructure instance details."""
    row = await Database.fetchrow(
        "SELECT * FROM maya_rp.infrastructure_overview WHERE id = $1", inst_id
    )
    return dict(row) if row else {}

async def list_infrastructure() -> list:
    """List all infrastructure instances."""
    return [dict(r) for r in await Database.fetch(
        "SELECT * FROM maya_rp.infrastructure_overview ORDER BY territory_name, type_name"
    )]

async def upgrade_infrastructure(session_id: int, inst_id: int) -> dict:
    """Upgrade infrastructure to next level."""
    inst = await Database.fetchrow(
        "SELECT * FROM maya_rp.infrastructure_instances WHERE id = $1", inst_id
    )
    if not inst:
        return {"error": "Infrastructure not found."}

    level = inst["level"]
    upgrade_cost = {"credits": 50000 * level}

    # Additional costs by category
    it = await Database.fetchrow(
        "SELECT category FROM maya_rp.infrastructure_types WHERE id = $1",
        inst["infrastructure_type_id"]
    )
    if it:
        cat = it["category"]
        if cat in ("mining", "refinery"):
            upgrade_cost["alloys"] = 200 * level
        elif cat == "station":
            upgrade_cost["rare_earth"] = 5 * level
        elif cat == "arcane":
            upgrade_cost["dream_essence"] = 2 * level

    ok, _ = await _check_afford(session_id, upgrade_cost)
    if not ok:
        return {"error": "Insufficient resources for upgrade."}
    await _deduct_resources(session_id, upgrade_cost)

    new_level = level + 1
    bonus = 1.0 + (new_level - 1) * 0.1
    await Database.execute("""
        UPDATE maya_rp.infrastructure_instances
        SET level = $1, last_upgrade = NOW(), production_bonus = $2
        WHERE id = $3
    """, new_level, bonus, inst_id)

    await _log(session_id, "infrastructure",
               f"⬆️ Upgraded: {inst['name']}",
               f"Level {new_level} (×{bonus:.1f} production bonus).", 2)

    return {"infrastructure_id": inst_id, "new_level": new_level, "bonus": bonus}

# effect keys → `resources` column. The catalogue spells it "alloy_production"
# while the ledger column is `alloys` (the mismatch silently dropped every alloy
# payout). Only white-listed columns are ever interpolated into the UPDATE.
RESOURCE_COLUMNS = ("credits", "alloys", "fuel", "dream_essence", "rare_earth",
                    "starsteel", "void_crystal", "aetherium")
RESOURCE_ALIAS = {"alloy": "alloys"}


def _resource_column(effect_key: str) -> str | None:
    res = effect_key.replace("_production", "")
    res = RESOURCE_ALIAS.get(res, res)
    return res if res in RESOURCE_COLUMNS else None


async def run_production_tick(session_id: int, game_days: float = 0.5) -> dict:
    """Tick — produce resources from active infrastructure.

    Scoped to the session that owns the instance: the query used to select every
    session's active infrastructure and credit the totals to the session_id
    argument, so a second session's facilities paid into this one's treasury.
    """
    produced = {}
    for inst in await Database.fetch("""
        SELECT ii.*, it.effects, it.category
        FROM maya_rp.infrastructure_instances ii
        JOIN maya_rp.infrastructure_types it ON it.id = ii.infrastructure_type_id
        WHERE ii.status = 'active' AND ii.session_id = $1
    """, session_id):
        effects = _j(inst.get("effects"))
        # numeric columns and jsonb numerics arrive as Decimal → float() before
        # multiplying (Decimal * float raised TypeError, so the tick never
        # produced anything: infrastructure_production was empty).
        bonus = float(inst.get("production_bonus") or 1.0)
        production = {}

        for key, val in effects.items():
            if key.endswith("_production"):
                col = _resource_column(key)
                if not col:
                    continue
                amount = int(float(val) * bonus * game_days)
                if amount > 0:
                    production[col] = production.get(col, 0) + amount

        for res, amount in production.items():
            await Database.execute(
                f"UPDATE maya_rp.resources SET {res} = {res} + $1 WHERE session_id = $2",
                amount, session_id
            )
            await Database.execute("""
                INSERT INTO maya_rp.infrastructure_production
                    (infrastructure_id, resource_type, amount_produced, produced_at)
                VALUES ($1, $2, $3, NOW())
            """, inst["id"], res, amount)
            produced[res] = produced.get(res, 0) + amount
    return {"produced": produced}

async def run_tick(session_id: int = 3):
    """Infrastructure tick — run production."""
    from core.log import info, error
    try:
        out = await run_production_tick(session_id)
        info("infrastructure", f"Tick: produced {out['produced'] or 'nothing'}")
        return out
    except Exception as e:
        error("infrastructure", f"Tick error: {e}")
        return {"error": str(e)}

# ============================================================
# Helpers
# ============================================================

def _j(v):
    """Parse JSONB values that asyncpg may return as strings."""
    if isinstance(v, str):
        return json.loads(v)
    return v if v else {}

async def _check_afford(session_id: int, costs: dict) -> tuple:
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
    for res, qty in costs.items():
        if res in ("credits", "alloys", "fuel", "dream_essence",
                   "rare_earth", "starsteel", "void_crystal", "aetherium"):
            await Database.execute(
                f"UPDATE maya_rp.resources SET {res} = GREATEST(0, {res} - $1) WHERE session_id = $2",
                qty, session_id
            )

async def _log(sid, category, title, content, importance=2):
    try:
        await Database.execute(
            "INSERT INTO maya_rp.story_log (session_id, category, title, content, importance, happened_at) "
            "VALUES ($1, $2, $3, $4, $5, NOW())",
            sid, category, title, content, importance
        )
    except Exception as e:  # noqa: BLE001 - reported below
        error("infrastructure", f"_log: {e}")
