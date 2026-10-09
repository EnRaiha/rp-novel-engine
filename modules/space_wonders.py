"""Space Wonders — planet types, space animals, anomalies, discoveries."""
import random, json
from datetime import datetime, timezone
from core.db import Database
from core.config import Config
from core.events import EventBus
from core.log import error, info

# Loot key → maya_rp.resources column. Keys outside this map are not resources
# and are reported back to the caller instead of being dropped in silence.
_LOOT_COLUMNS = {
    "credits": "credits",
    "alloys": "alloys",
    "fuel": "fuel",
    "rare_earth": "rare_earth",
    "starsteel": "starsteel",
    "void_crystal": "void_crystal",
    "aetherium": "aetherium",
    "population": "population",
    "research": "research_points",
}

# Loot keys that are signals rather than treasury columns. `food` is a reward in
# space_anomalies.reward_pool and no maya_rp table has a food column, so it is
# reported back to the caller instead of being dropped in silence.
_NON_RESOURCE_KEYS = {
    "artifact", "artifact_chance", "exploration", "new_system_discovered", "food",
}

# ============================================================
# Planet Operations
# ============================================================


def _as_dict(value) -> dict:
    """Decode a jsonb column.

    asyncpg hands jsonb back as text in this engine, so `reward_pool.items()`
    raised AttributeError on every successful hunt and exploration, and the
    planet modifiers never applied. Non-dict payloads become an empty dict.
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _as_list(value) -> list:
    """Decode a jsonb array column into a new list.

    The driver returns jsonb as text, and the text `'[]'` is truthy, so
    `not features` never held and no feature rolled. Anything that is not a
    list, or does not parse to one, becomes an empty list.
    """
    if isinstance(value, list):
        return list(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return []
        return parsed if isinstance(parsed, list) else []
    return []


async def survey_planet(planet_id: int, session_id: int | None = None) -> dict:
    """Survey a planet to discover its type, features, and resource potential.

    The planet is read and written inside one session, so a survey cannot reach
    another campaign's planet.
    """
    if session_id is None:
        session_id = Config.SESSION_ID
    p = await Database.fetchrow("""
        SELECT p.*, pt.description AS type_desc, pt.special_events
        FROM maya_rp.planets p
        LEFT JOIN maya_rp.planet_types_catalog pt ON pt.name = p.planet_type
        WHERE p.id = $1 AND p.session_id = $2
    """, planet_id, session_id)
    if not p:
        return {"error": f"Planet {planet_id} not found in session {session_id}."}

    # Generate resource yield based on type modifiers + random
    mods = _as_dict(p.get("resource_modifiers"))
    base = {
        "alloys": random.randint(100, 1000),
        "fuel": random.randint(50, 500),
        "food": random.randint(50, 500),
        "research": random.randint(10, 100),
        "rare_earth": random.randint(1, 20)
    }
    final = {}
    for res, amt in base.items():
        mult = mods.get(res, 1.0) if isinstance(mods, dict) else 1.0
        final[res] = int(amt * mult)

    # Check for special features
    features = _as_list(p.get("features"))
    if not features and p.get("planet_type"):
        # Roll for a random feature
        feat = await _roll_feature(p["planet_type"])
        if feat:
            features.append(feat["name"])
            await Database.execute(
                "UPDATE maya_rp.planets SET features = $1 WHERE id = $2 AND session_id = $3",
                json.dumps(features), planet_id, session_id
            )

    await Database.execute(
        "UPDATE maya_rp.planets SET surveyed = TRUE WHERE id = $1 AND session_id = $2",
        planet_id, session_id
    )

    info = {
        "planet": p.get("name", f"Planet #{planet_id}"),
        "type": p.get("planet_type", "Unknown"),
        "habitability": p.get("habitability", 0),
        "yield": final,
        "features": features,
        "type_description": p.get("type_desc", "")
    }

    await _log(session_id, "exploration", f"Survey: {info['planet']}",
               f"Surveyed {info['planet']} — {info['type']}. Yield: {final}", 2)
    return info


async def _roll_feature(planet_type: str) -> dict | None:
    """Roll for a random special feature matching the planet type.

    Returns None when the roll misses, so the annotation says so.
    """
    feat = await Database.fetchrow("""
        SELECT name, description, effect, rarity
        FROM maya_rp.planet_features
        WHERE planet_type = $1
        ORDER BY random() LIMIT 1
    """, planet_type)
    if feat and random.random() < 0.4:  # 40% chance
        return dict(feat)
    return None


# ============================================================
# Space Animal Operations
# ============================================================

async def encounter_animal(system_id: int, animal_id: int = None,
                           session_id: int | None = None) -> dict:
    """Generate a random animal encounter in a system.

    The encounter belongs to the system's campaign unless the caller names one.
    """
    if session_id is None:
        session_id = await Database.fetchval(
            "SELECT session_id FROM maya_rp.sectors WHERE id = $1", system_id
        )
    if session_id is None:
        session_id = Config.SESSION_ID
    if not animal_id:
        animal = await Database.fetchrow(
            "SELECT * FROM maya_rp.space_animals ORDER BY random() LIMIT 1"
        )
        if not animal:
            return {"error": "No animals in the void."}
        animal_id = animal["id"]
    else:
        animal = await Database.fetchrow(
            "SELECT * FROM maya_rp.space_animals WHERE id = $1", animal_id
        )
        if not animal:
            return {"error": "Animal not found."}

    eid = await Database.fetchrow("""
        INSERT INTO maya_rp.animal_encounters
            (session_id, animal_id, system_id, status, encountered_at)
        VALUES ($1, $2, $3, 'active', NOW())
        RETURNING id
    """, session_id, animal_id, system_id)

    await _log(session_id, "exploration", f"Encounter: {animal['name']}",
               f"A {animal['species']} spotted in the system! "
               f"Aggression: {animal['aggression']}/10", 3)

    return {
        "encounter_id": eid["id"] if eid else None,
        "animal": {
            "id": animal["id"],
            "name": animal["name"],
            "species": animal["species"],
            "aggression": animal["aggression"],
            "taming_difficulty": animal["taming_difficulty"],
            "rarity": animal["rarity"],
            "special_ability": animal.get("special_ability", "")
        },
        "options": ["hunt", "tame", "flee"]
    }


async def hunt_animal(encounter_id: int, fleet_power: int = 100,
                      session_id: int | None = None) -> dict:
    """Hunt a space animal for resources."""
    if session_id is None:
        session_id = Config.SESSION_ID
    if int(fleet_power) <= 0:
        return {"error": f"fleet_power must be positive, got {fleet_power}."}
    enc = await Database.fetchrow(
        "SELECT * FROM maya_rp.animal_encounters WHERE id = $1 AND status = 'active'"
        " AND session_id = $2",
        encounter_id, session_id
    )
    if not enc:
        return {"error": f"Encounter {encounter_id} not found in session {session_id},"
                         f" or already resolved."}

    animal = await Database.fetchrow(
        "SELECT * FROM maya_rp.space_animals WHERE id = $1", enc["animal_id"]
    )
    if not animal:
        return {"error": "Animal not found."}

    difficulty = animal["aggression"] + animal["taming_difficulty"] / 2
    success_chance = fleet_power / max(1, fleet_power + difficulty * 10)
    roll = random.random()
    success = roll < success_chance

    if success:
        rv = _as_dict(animal["resource_value"]) or {"credits": 100}
        loot = {}
        for res, amt in rv.items():
            if res == "credits":
                loot["credits"] = int(amt * random.uniform(0.8, 1.2))
            elif res == "artifact_chance":
                if random.random() < amt:
                    loot["artifact"] = True
            else:
                loot[res] = int(amt * random.uniform(0.8, 1.2))

        # Claim first: a second hunt read the same active row and loses here.
        claimed = await Database.fetchval(
            "UPDATE maya_rp.animal_encounters SET status = 'hunted', resolved_at = NOW(), outcome = 'success'"
            " WHERE id = $1 AND status = 'active' RETURNING id", encounter_id)
        if claimed is None:
            return {"error": f"Encounter {encounter_id} not found in session {session_id},"
                             f" or already resolved."}

        # The bus carries the audit event; no listener is registered for
        # `resources:add`, so `_credit_resources` below is what moves the number.
        await EventBus.emit("resources:add", dict(loot, session_id=session_id))
        credited = await _credit_resources(session_id, loot)

        await _log(session_id, "exploration", f"Hunted {animal['name']}",
                   f"Successfully hunted a {animal['species']}! Gained: {loot}", 2)
        return {"success": True, "loot": loot, "target": animal["name"],
                "resources": credited}
    else:
        damage = int(fleet_power * random.uniform(0.05, 0.15))
        claimed = await Database.fetchval(
            "UPDATE maya_rp.animal_encounters SET status = 'fled', resolved_at = NOW(), outcome = 'failure'"
            " WHERE id = $1 AND status = 'active' RETURNING id", encounter_id)
        if claimed is None:
            return {"error": f"Encounter {encounter_id} not found in session {session_id},"
                             f" or already resolved."}

        await _log(session_id, "exploration", f"Hunt Failed: {animal['name']}",
                   f"Attempt to hunt {animal['species']} failed. Lost {damage} fleet power.", 2)
        return {"success": False, "damage": damage, "target": animal["name"]}


async def tame_animal(encounter_id: int, trainer_skill: int = 5,
                      session_id: int | None = None) -> dict:
    """Attempt to tame a space animal as a companion/asset."""
    if session_id is None:
        session_id = Config.SESSION_ID
    enc = await Database.fetchrow(
        "SELECT * FROM maya_rp.animal_encounters WHERE id = $1 AND status = 'active'"
        " AND session_id = $2",
        encounter_id, session_id
    )
    if not enc:
        return {"error": f"Encounter {encounter_id} not found in session {session_id},"
                         f" or already resolved."}

    animal = await Database.fetchrow(
        "SELECT * FROM maya_rp.space_animals WHERE id = $1", enc["animal_id"]
    )
    if not animal:
        return {"error": "Animal not found."}

    diff = animal["taming_difficulty"]
    success_chance = max(0.05, min(0.95, trainer_skill / max(1, diff)))
    roll = random.random()
    success = roll < success_chance

    if success:
        claimed = await Database.fetchval(
            "UPDATE maya_rp.animal_encounters SET status = 'tamed', resolved_at = NOW(), outcome = 'success'"
            " WHERE id = $1 AND status = 'active' RETURNING id", encounter_id)
        if claimed is None:
            return {"error": f"Encounter {encounter_id} not found in session {session_id},"
                             f" or already resolved."}

        # Add tamed animal bonus — store as empire modifier
        ability = animal.get("special_ability", "")
        await _log(session_id, "exploration", f"Tamed {animal['name']}",
                   f"You tamed a {animal['species']}! {ability}", 3)

        return {
            "success": True,
            "target": animal["name"],
            "species": animal["species"],
            "special_ability": ability,
            "rarity": animal["rarity"]
        }
    else:
        claimed = await Database.fetchval(
            "UPDATE maya_rp.animal_encounters SET status = 'fled', resolved_at = NOW(), outcome = 'failure'"
            " WHERE id = $1 AND status = 'active' RETURNING id", encounter_id)
        if claimed is None:
            return {"error": f"Encounter {encounter_id} not found in session {session_id},"
                             f" or already resolved."}

        await _log(session_id, "exploration", f"Taming Failed: {animal['name']}",
                   f"Attempt to tame {animal['species']} failed. It fled.", 1)
        return {"success": False, "target": animal["name"]}


# ============================================================
# Anomaly Operations
# ============================================================

async def discover_anomaly(system_id: int, trigger: str = "scan_low",
                           session_id: int | None = None) -> dict:
    """Discover a space anomaly in a system.

    The discovery belongs to the system's campaign unless the caller names one.
    """
    if session_id is None:
        session_id = await Database.fetchval(
            "SELECT session_id FROM maya_rp.sectors WHERE id = $1", system_id
        )
    if session_id is None:
        session_id = Config.SESSION_ID
    anomaly = await Database.fetchrow("""
        SELECT * FROM maya_rp.space_anomalies
        WHERE active = TRUE AND discovery_trigger = $1
        ORDER BY random() LIMIT 1
    """, trigger)
    if not anomaly:
        # Fallback: any anomaly
        info("space_wonders", f"No '{trigger}' anomaly active, falling back to any anomaly")
        anomaly = await Database.fetchrow("""
            SELECT * FROM maya_rp.space_anomalies WHERE active = TRUE
            ORDER BY random() LIMIT 1
        """)
    if not anomaly:
        return {"error": "No anomalies to discover."}

    did = await Database.fetchrow("""
        INSERT INTO maya_rp.discoveries (session_id, type, target_id, discovered_at, explored)
        VALUES ($1, 'anomaly', $2, NOW(), FALSE)
        RETURNING id
    """, session_id, anomaly["id"])

    await _log(session_id, "exploration", f"Anomaly: {anomaly['name']}",
               f"A {anomaly['type']} detected! Danger: {anomaly['danger_level']}/10", 3)

    return {
        "discovery_id": did["id"] if did else None,
        "anomaly": {
            "id": anomaly["id"],
            "name": anomaly["name"],
            "type": anomaly["type"],
            "description": anomaly["description"],
            "danger_level": anomaly["danger_level"],
            "rarity": anomaly["rarity"]
        }
    }


async def explore_anomaly(discovery_id: int, fleet_power: int = 100,
                          session_id: int | None = None) -> dict:
    """Explore a discovered anomaly for rewards or danger."""
    if session_id is None:
        session_id = Config.SESSION_ID
    if int(fleet_power) <= 0:
        return {"error": f"fleet_power must be positive, got {fleet_power}."}
    disc = await Database.fetchrow(
        "SELECT * FROM maya_rp.discoveries WHERE id = $1 AND explored = FALSE AND session_id = $2",
        discovery_id, session_id
    )
    if not disc:
        return {"error": f"Discovery {discovery_id} not found in session {session_id},"
                         f" or already explored."}

    anomaly = await Database.fetchrow(
        "SELECT * FROM maya_rp.space_anomalies WHERE id = $1", disc["target_id"]
    )
    if not anomaly:
        return {"error": "Anomaly not found."}

    danger = anomaly["danger_level"]
    risk = danger / max(1, fleet_power / 100)
    outcome = "success"
    loot = {}
    damage = 0
    roll = random.random()

    if roll < (1 - min(0.95, risk)):
        # Success
        rp = _as_dict(anomaly["reward_pool"]) or {"credits": 500}
        for res, amt in rp.items():
            if res == "credits":
                loot["credits"] = int(amt * random.uniform(0.8, 1.2))
            elif res == "artifact_chance":
                if random.random() < amt:
                    loot["artifact"] = True
            elif res == "exploration" and amt == "new_system":
                loot["new_system_discovered"] = True
            else:
                loot[res] = int(amt * random.uniform(0.8, 1.2))

        outcome = "success"
    else:
        damage = int(fleet_power * random.uniform(0.1, 0.4))
        outcome = "failure"

    # Claim first: a second exploration read the same unexplored row and loses here.
    claimed = await Database.fetchval(
        "UPDATE maya_rp.discoveries SET explored = TRUE, explored_at = NOW(), results = $1"
        " WHERE id = $2 AND explored = FALSE RETURNING id",
        json.dumps({"outcome": outcome, "loot": loot, "damage": damage}), discovery_id)
    if claimed is None:
        return {"error": f"Discovery {discovery_id} not found in session {session_id},"
                         f" or already explored."}

    if outcome == "success":
        await EventBus.emit("resources:add", dict(loot, session_id=session_id))
        credited = await _credit_resources(session_id, loot)
    else:
        credit_report = {"applied": {}, "skipped": {}, "credited": False}

    await _log(session_id, "exploration", f"Anomaly Explored: {anomaly['name']}",
               f"Outcome: {outcome}. {'Gained resources' if outcome == 'success' else f'Took {damage} damage.'}",
               3 if outcome == "success" else 2)

    return {"outcome": outcome, "loot": loot, "damage": damage,
            "anomaly_name": anomaly["name"],
            "resources": credited if outcome == "success" else credit_report}


# ============================================================
# Wonders Overview
# ============================================================

async def get_wonders_overview(session_id: int | None = None) -> dict:
    """An overview of the wonders in this session's galaxy.

    The planets are session-scoped; the animal and anomaly catalogues are not, because they describe
    the galaxy rather than one campaign in it.
    """
    if session_id is None:
        session_id = Config.SESSION_ID
    planets = await Database.fetch("""
        SELECT id, name, planet_type, habitability, surveyed
        FROM maya_rp.planets WHERE session_id = $1 ORDER BY name
    """, session_id)
    animals = await Database.fetch("""
        SELECT id, name, species, aggression, rarity
        FROM maya_rp.space_animals ORDER BY rarity, name
    """)
    anomalies = await Database.fetch("""
        SELECT id, name, type, danger_level, rarity
        FROM maya_rp.space_anomalies WHERE active = TRUE ORDER BY rarity, name
    """)
    return {
        "planets": [dict(p) for p in planets],
        "animals": [dict(a) for a in animals],
        "anomalies": [dict(a) for a in anomalies]
    }


# ============================================================
# Tick
# ============================================================

async def run_tick(session_id: int = None):
    """Space wonders tick — spawn animals, trigger discoveries.

    Every candidate row is read inside the tick's own session, and the three
    actions are told which session to write to. The default used to be the
    frozen reference campaign.
    """
    from core.log import error
    if session_id is None:
        session_id = Config.SESSION_ID
    spawned = discovered = surveyed = 0
    try:
        gd = 0.5  # simplified game days

        # 1. Random animal spawns in unoccupied systems
        if random.random() < 0.05 * gd:
            # sectors records its owner in `controlled_by`; there is no
            # occupied_by column (the old name aborted the tick 5% of the time).
            systems = await Database.fetch(
                "SELECT id FROM maya_rp.sectors WHERE session_id = $1 AND controlled_by IS NULL "
                "ORDER BY random() LIMIT 1",
                session_id,
            )
            if systems:
                await encounter_animal(systems[0]["id"], session_id=session_id)
                spawned += 1

        # 2. Random anomaly discoveries
        if random.random() < 0.03 * gd:
            systems = await Database.fetch(
                "SELECT id FROM maya_rp.sectors WHERE session_id = $1 ORDER BY random() LIMIT 1",
                session_id,
            )
            if systems:
                await discover_anomaly(systems[0]["id"],
                                       random.choice(["scan_low", "scan_high", "explore"]),
                                       session_id=session_id)
                discovered += 1

        # 3. Auto-survey un-surveyed planets (AI assist)
        if random.random() < 0.1 * gd:
            un = await Database.fetchrow(
                "SELECT id FROM maya_rp.planets WHERE session_id = $1 AND surveyed = FALSE "
                "ORDER BY random() LIMIT 1",
                session_id,
            )
            if un:
                await survey_planet(un["id"], session_id=session_id)
                surveyed += 1

    except Exception as e:
        # A bare print() left the orchestrator scoring a crash as success.
        error("space_wonders", f"Tick error: {e}")
        return {"error": str(e)}
    return {"spawned": spawned, "anomalies": discovered, "surveyed": surveyed}


# ============================================================
# Internal Helpers
# ============================================================

async def _log(sid, category, title, content, importance=2):
    """Write to story log, in the caller's session.

    The old COALESCE($1, 3) fell back to the frozen reference campaign, so a
    session 5 hunt wrote its story into session 3.
    """
    if sid is None:
        sid = Config.SESSION_ID
    try:
        await Database.execute("""
            INSERT INTO maya_rp.story_log (session_id, category, title, content, importance, happened_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
        """, sid, category, title, content, importance)
    except Exception as e:  # noqa: BLE001 - reported below
        error("space-wonders", f"_log: {e}")


async def _credit_resources(session_id: int, loot: dict) -> dict:
    """Pay hunt and exploration loot into the session treasury.

    `EventBus.emit("resources:add", ...)` has no listener, and the bus insert
    fails without a maya_rp schema prefix, so the loot a hunt reported was never
    paid. This writes the columns that exist, and returns the keys it could not
    pay instead of dropping them.
    """
    applied: dict = {}
    skipped: dict = {}
    sets = []
    params = [session_id]
    for key, value in (loot or {}).items():
        if key == "session_id":
            continue
        col = _LOOT_COLUMNS.get(key)
        if col is None or not isinstance(value, (int, float)) or isinstance(value, bool):
            skipped[key] = value
            continue
        params.append(int(value))
        sets.append(f"{col} = COALESCE({col}, 0) + ${len(params)}")
        applied[col] = int(value)
    credited = False
    if sets:
        row = await Database.fetchrow(
            f"UPDATE maya_rp.resources SET {', '.join(sets)} "
            "WHERE session_id = $1 RETURNING credits",
            *params,
        )
        credited = row is not None
        if not credited:
            info("space_wonders",
                 f"No resources row for session {session_id}; {applied} paid nothing")
    if skipped:
        info("space_wonders", f"Loot keys with no resources column: {skipped}")
    return {"applied": applied, "skipped": skipped, "credited": credited}
