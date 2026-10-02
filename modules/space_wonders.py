"""Space Wonders — planet types, space animals, anomalies, discoveries."""
import random, json
from datetime import datetime, timezone
from core.db import Database
from core.events import EventBus
from core.log import error

# ============================================================
# Planet Operations
# ============================================================

async def survey_planet(planet_id: int) -> dict:
    """Survey a planet to discover its type, features, and resource potential."""
    p = await Database.fetchrow("""
        SELECT p.*, pt.description AS type_desc, pt.special_events
        FROM maya_rp.planets p
        LEFT JOIN maya_rp.planet_types_catalog pt ON pt.name = p.planet_type
        WHERE p.id = $1
    """, planet_id)
    if not p:
        return {"error": "Planet not found."}

    # Generate resource yield based on type modifiers + random
    mods = p.get("resource_modifiers") or {}
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
    features = p.get("features") or []
    if not features and p.get("planet_type"):
        # Roll for a random feature
        feat = await _roll_feature(p["planet_type"])
        if feat:
            features.append(feat["name"])
            await Database.execute(
                "UPDATE maya_rp.planets SET features = $1 WHERE id = $2",
                json.dumps(features), planet_id
            )

    await Database.execute(
        "UPDATE maya_rp.planets SET surveyed = TRUE WHERE id = $1", planet_id
    )

    info = {
        "planet": p.get("name", f"Planet #{planet_id}"),
        "type": p.get("planet_type", "Unknown"),
        "habitability": p.get("habitability", 0),
        "yield": final,
        "features": features,
        "type_description": p.get("type_desc", "")
    }

    await _log(None, "exploration", f"Survey: {info['planet']}",
               f"Surveyed {info['planet']} — {info['type']}. Yield: {final}", 2)
    return info


async def _roll_feature(planet_type: str) -> dict:
    """Roll for a random special feature matching the planet type."""
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

async def encounter_animal(system_id: int, animal_id: int = None) -> dict:
    """Generate a random animal encounter in a system."""
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
        VALUES (COALESCE((SELECT session_id FROM maya_rp.sectors WHERE id = $1), 3),
                $2, $3, 'active', NOW())
        RETURNING id
    """, system_id, animal_id, system_id)

    await _log(None, "exploration", f"Encounter: {animal['name']}",
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
        rv = animal["resource_value"] or {"credits": 100}
        loot = {}
        for res, amt in rv.items():
            if res == "credits":
                loot["credits"] = int(amt * random.uniform(0.8, 1.2))
            elif res == "artifact_chance":
                if random.random() < amt:
                    loot["artifact"] = True
            else:
                loot[res] = int(amt * random.uniform(0.8, 1.2))

        # Apply loot via event
        await EventBus.emit("resources:add", loot)

        await Database.execute("""
            UPDATE maya_rp.animal_encounters
            SET status = 'hunted', resolved_at = NOW(), outcome = 'success'
            WHERE id = $1
        """, encounter_id)

        await _log(None, "exploration", f"Hunted {animal['name']}",
                   f"Successfully hunted a {animal['species']}! Gained: {loot}", 2)
        return {"success": True, "loot": loot, "target": animal["name"]}
    else:
        damage = int(fleet_power * random.uniform(0.05, 0.15))
        await Database.execute("""
            UPDATE maya_rp.animal_encounters
            SET status = 'fled', resolved_at = NOW(), outcome = 'failure'
            WHERE id = $1
        """, encounter_id)

        await _log(None, "exploration", f"Hunt Failed: {animal['name']}",
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
        await Database.execute("""
            UPDATE maya_rp.animal_encounters
            SET status = 'tamed', resolved_at = NOW(), outcome = 'success'
            WHERE id = $1
        """, encounter_id)

        # Add tamed animal bonus — store as empire modifier
        ability = animal.get("special_ability", "")
        await _log(None, "exploration", f"Tamed {animal['name']}",
                   f"You tamed a {animal['species']}! {ability}", 3)

        return {
            "success": True,
            "target": animal["name"],
            "species": animal["species"],
            "special_ability": ability,
            "rarity": animal["rarity"]
        }
    else:
        await Database.execute("""
            UPDATE maya_rp.animal_encounters
            SET status = 'fled', resolved_at = NOW(), outcome = 'failure'
            WHERE id = $1
        """, encounter_id)

        await _log(None, "exploration", f"Taming Failed: {animal['name']}",
                   f"Attempt to tame {animal['species']} failed. It fled.", 1)
        return {"success": False, "target": animal["name"]}


# ============================================================
# Anomaly Operations
# ============================================================

async def discover_anomaly(system_id: int, trigger: str = "scan_low") -> dict:
    """Discover a space anomaly in a system."""
    anomaly = await Database.fetchrow("""
        SELECT * FROM maya_rp.space_anomalies
        WHERE active = TRUE AND discovery_trigger = $1
        ORDER BY random() LIMIT 1
    """, trigger)
    if not anomaly:
        # Fallback: any anomaly
        anomaly = await Database.fetchrow("""
            SELECT * FROM maya_rp.space_anomalies WHERE active = TRUE
            ORDER BY random() LIMIT 1
        """)
    if not anomaly:
        return {"error": "No anomalies to discover."}

    did = await Database.fetchrow("""
        INSERT INTO maya_rp.discoveries (session_id, type, target_id, discovered_at, explored)
        VALUES (COALESCE((SELECT session_id FROM maya_rp.sectors WHERE id = $1), 3),
                'anomaly', $2, NOW(), FALSE)
        RETURNING id
    """, system_id, anomaly["id"])

    await _log(None, "exploration", f"Anomaly: {anomaly['name']}",
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
        rp = anomaly["reward_pool"] or {"credits": 500}
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

        await EventBus.emit("resources:add", loot)
        outcome = "success"
    else:
        damage = int(fleet_power * random.uniform(0.1, 0.4))
        outcome = "failure"

    await Database.execute("""
        UPDATE maya_rp.discoveries
        SET explored = TRUE, explored_at = NOW(), results = $1
        WHERE id = $2
    """, json.dumps({"outcome": outcome, "loot": loot, "damage": damage}), discovery_id)

    await _log(None, "exploration", f"Anomaly Explored: {anomaly['name']}",
               f"Outcome: {outcome}. {'Gained resources' if outcome == 'success' else f'Took {damage} damage.'}",
               3 if outcome == "success" else 2)

    return {"outcome": outcome, "loot": loot, "damage": damage,
            "anomaly_name": anomaly["name"]}


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

async def run_tick(session_id: int = 3):
    """Space wonders tick — spawn animals, trigger discoveries."""
    from core.log import error
    spawned = discovered = surveyed = 0
    try:
        gd = 0.5  # simplified game days

        # 1. Random animal spawns in unoccupied systems
        if random.random() < 0.05 * gd:
            # sectors records its owner in `controlled_by`; there is no
            # occupied_by column (the old name aborted the tick 5% of the time).
            systems = await Database.fetch(
                "SELECT id FROM maya_rp.sectors WHERE controlled_by IS NULL ORDER BY random() LIMIT 1"
            )
            if systems:
                await encounter_animal(systems[0]["id"])
                spawned += 1

        # 2. Random anomaly discoveries
        if random.random() < 0.03 * gd:
            systems = await Database.fetch(
                "SELECT id FROM maya_rp.sectors ORDER BY random() LIMIT 1"
            )
            if systems:
                await discover_anomaly(systems[0]["id"],
                                       random.choice(["scan_low", "scan_high", "explore"]))
                discovered += 1

        # 3. Auto-survey un-surveyed planets (AI assist)
        if random.random() < 0.1 * gd:
            un = await Database.fetchrow(
                "SELECT id FROM maya_rp.planets WHERE surveyed = FALSE ORDER BY random() LIMIT 1"
            )
            if un:
                await survey_planet(un["id"])
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
    """Write to story log."""
    try:
        await Database.execute("""
            INSERT INTO maya_rp.story_log (session_id, category, title, content, importance, happened_at)
            VALUES (COALESCE($1, 3), $2, $3, $4, $5, NOW())
        """, sid, category, title, content, importance)
    except Exception as e:  # noqa: BLE001 - reported below
        error("space-wonders", f"_log: {e}")
