"""Infrastructure — mining, refineries, stations, factories, farms, defense, logistics, arcane."""
import random, json
from datetime import datetime, timezone
from core.config import Config
from core.db import Database
from modules._economy import RESOURCE_COLUMNS, _check_afford, _deduct_resources
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

    # Placement is checked before anything is charged: the foreign keys reach
    # `territory` and `sectors`, which both carry a session, so a build in this
    # campaign could hang off the frozen campaign's world or sector.
    if territory_id is not None:
        owned = await Database.fetchval(
            "SELECT 1 FROM maya_rp.territory WHERE id = $1 AND session_id = $2",
            territory_id, session_id)
        if not owned:
            return {"error": f"Territory {territory_id} is not in session {session_id}."}
    if sector_id is not None:
        owned = await Database.fetchval(
            "SELECT 1 FROM maya_rp.sectors WHERE id = $1 AND session_id = $2",
            sector_id, session_id)
        if not owned:
            return {"error": f"Sector {sector_id} is not in session {session_id}."}

    # Check research gate. `research_projects` carries no session of its own — it
    # is the global tech catalogue, so an unfiltered name lookup is correct here.
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
    charged = await _deduct_resources(session_id, cost)

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
            "type": it["name"], "category": it["category"], "charged": charged}

async def get_infrastructure(inst_id: int, session_id: int | None = None) -> dict:
    """Get infrastructure instance details, from this session only.

    Reviewed 2026-10-03 before wiring: neither this nor `list_infrastructure` filtered by session, so
    playing session 5 listed and opened session 3's facilities. The same leak was fixed in battle and
    pirate aggregates; this is the same class.
    """
    if session_id is None:
        session_id = Config.SESSION_ID
    row = await Database.fetchrow(
        "SELECT * FROM maya_rp.infrastructure_overview WHERE id = $1 AND session_id = $2",
        inst_id, session_id
    )
    return dict(row) if row else {}

async def list_infrastructure(session_id: int | None = None) -> list:
    """List this session's infrastructure instances."""
    if session_id is None:
        session_id = Config.SESSION_ID
    return [dict(r) for r in await Database.fetch(
        "SELECT * FROM maya_rp.infrastructure_overview WHERE session_id = $1"
        " ORDER BY territory_name, type_name", session_id
    )]

async def upgrade_infrastructure(session_id: int, inst_id: int) -> dict:
    """Upgrade infrastructure to next level."""
    inst = await Database.fetchrow(
        "SELECT * FROM maya_rp.infrastructure_instances WHERE id = $1 AND session_id = $2",
        inst_id, session_id
    )
    if not inst:
        return {"error": f"Infrastructure {inst_id} not found in session {session_id}."}

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

    ok, why = await _check_afford(session_id, upgrade_cost)
    if not ok:
        return {"error": f"Insufficient resources for upgrade: {why}"}
    charged = await _deduct_resources(session_id, upgrade_cost)

    new_level = level + 1
    bonus = 1.0 + (new_level - 1) * 0.1
    await Database.execute("""
        UPDATE maya_rp.infrastructure_instances
        SET level = $1, last_upgrade = NOW(), production_bonus = $2
        WHERE id = $3 AND session_id = $4
    """, new_level, bonus, inst_id, session_id)

    await _log(session_id, "infrastructure",
               f"⬆️ Upgraded: {inst['name']}",
               f"Level {new_level} (×{bonus:.1f} production bonus).", 2)

    return {"infrastructure_id": inst_id, "new_level": new_level, "bonus": bonus, "charged": charged}

# effect keys → `resources` column. The catalogue spells it "alloy_production"
# while the ledger column is `alloys` (the mismatch silently dropped every alloy
# payout). Only white-listed columns are ever interpolated into the UPDATE.
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

    A payout is counted only when it landed: a session with no `resources` row
    (session 5 has none) used to log production into `infrastructure_production`
    that never reached a treasury. One malformed `effects` row is skipped and
    named rather than aborting the whole tick.
    """
    produced = {}
    unlanded = {}
    skipped = []
    for inst in await Database.fetch("""
        SELECT ii.*, it.effects, it.category
        FROM maya_rp.infrastructure_instances ii
        JOIN maya_rp.infrastructure_types it ON it.id = ii.infrastructure_type_id
        WHERE ii.status = 'active' AND ii.session_id = $1
    """, session_id):
        try:
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
                tag = await Database.execute(
                    f"UPDATE maya_rp.resources SET {res} = {res} + $1 WHERE session_id = $2",
                    amount, session_id
                )
                if isinstance(tag, str) and tag.split()[-1:] == ["0"]:
                    unlanded[res] = unlanded.get(res, 0) + amount
                    continue          # no production row for a payout nobody received
                await Database.execute("""
                    INSERT INTO maya_rp.infrastructure_production
                        (infrastructure_id, resource_type, amount_produced, produced_at)
                    VALUES ($1, $2, $3, NOW())
                """, inst["id"], res, amount)
                produced[res] = produced.get(res, 0) + amount
        except Exception as e:  # noqa: BLE001 - one bad row must not stop the fleet
            skipped.append(inst.get("id"))
            error("infrastructure", f"instance {inst.get('id')} skipped: {e}")
    if unlanded:
        error("infrastructure", f"session {session_id} has no resources row — "
                                f"{unlanded} produced but NOT credited")
    return {"produced": produced, "unlanded": unlanded, "skipped": skipped}

async def run_tick(session_id: int = None):
    """Infrastructure tick — run production.

    Defaults to the engine's session (Config.SESSION_ID), not the literal 3: that
    id is the frozen reference campaign, so a bare tick produced there.
    """
    from core.log import info, error
    if session_id is None:
        session_id = Config.SESSION_ID
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

async def _log(sid, category, title, content, importance=2):
    try:
        await Database.execute(
            "INSERT INTO maya_rp.story_log (session_id, category, title, content, importance, happened_at) "
            "VALUES ($1, $2, $3, $4, $5, NOW())",
            sid, category, title, content, importance
        )
    except Exception as e:  # noqa: BLE001 - reported below
        error("infrastructure", f"_log: {e}")
