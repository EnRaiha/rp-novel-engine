"""Character Manager — presence, control, relationships, arcs, unified view."""
from typing import Dict, List, Optional
from core.db import Database
from core.events import EventBus
from core.config import Config

class CharacterManager:
    @classmethod
    async def get(cls, table: str, cid: int) -> Optional[Dict]:
        return await Database.fetchrow(f"SELECT * FROM {table} WHERE id=$1", cid)

    @classmethod
    async def all_present(cls, scene: str = None) -> List[Dict]:
        q = "SELECT * FROM characters_unified WHERE presence='available'"
        p = []
        if scene: q += " AND scene_location=$1"; p.append(scene)
        return await Database.fetch(q, *p)

    @classmethod
    async def set_presence(cls, table: str, cid: int, presence: str, reason: str = "system"):
        old = await cls.get(table, cid)
        if not old or old.get("presence") == presence: return
        await Database.execute(f"UPDATE {table} SET presence=$1 WHERE id=$2", presence, cid)
        await Database.execute(
            "INSERT INTO character_presence_log (character_table,character_id,previous_presence,new_presence,changed_by,reason) VALUES ($1,$2,$3,$4,$5,$6)",
            table, cid, old.get("presence","?"), presence, "system", reason)
        await EventBus.emit("presence_changed", {"table": table, "id": cid, "to": presence})

    @classmethod
    async def set_control(cls, table: str, cid: int, control: str):
        await Database.execute(f"UPDATE {table} SET controlled_by=$1 WHERE id=$2", control, cid)
        await EventBus.emit("control_changed", {"table": table, "id": cid, "to": control})

    @classmethod
    async def set_relationship(cls, ta: str, ia: int, tb: str, ib: int, rtype: str, strength: int):
        await Database.execute(
            "INSERT INTO character_relationships (character_a_table,character_a_id,character_b_table,character_b_id,relationship_type,strength) "
            "VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT DO UPDATE SET relationship_type=$5,strength=$6,updated_at=NOW()",
            ta, ia, tb, ib, rtype, strength)
        await EventBus.emit("relationship_set", {"a": f"{ta}/{ia}", "b": f"{tb}/{ib}", "type": rtype})

    @classmethod
    async def move_to_scene(cls, table: str, cid: int, scene: str):
        await Database.execute(f"UPDATE {table} SET scene_location=$1, presence='available' WHERE id=$2", scene, cid)
        await EventBus.emit("character_moved", {"table": table, "id": cid, "scene": scene})

    @classmethod
    async def start_arc(cls, table: str, cid: int, name: str, desc: str):
        await Database.execute(
            "INSERT INTO character_arcs (character_table,character_id,arc_name,arc_description,status,started_at) VALUES ($1,$2,$3,$4,'active',NOW())",
            table, cid, name, desc)

async def run_tick(session_id: int = None):
    from core.log import info
    if session_id is None: session_id = Config.SESSION_ID
    info("characters", "Tick: no active arcs")
    return {"character_arcs": 0}


# ─── Action Parser: resolve_intent ───────────────────────────────────────

async def resolve_intent(session_id: int, action: str, target: str, character_id: int = 0) -> dict:
    """
    Resolve a character interaction intent — talk/gift/arrest/promote.
    Returns {success, bond_change, reaction} for Deepseek narration.
    """
    if character_id:
        char = await Database.fetchrow(
            "SELECT id, name, bond, role FROM maya_rp.characters WHERE id=$1 AND session_id=$2",
            character_id, session_id)
    elif target:
        char = await Database.fetchrow(
            "SELECT id, name, bond, role FROM maya_rp.characters "
            "WHERE session_id=$1 AND LOWER(name) LIKE LOWER($2) LIMIT 1",
            session_id, f"%{target}%")
    else:
        return {"domain": "character", "success": False, "narrative_hook": "No character specified."}

    if not char:
        return {"domain": "character", "success": False, "narrative_hook": f"Character not found: {target}"}

    bond_shift = 0
    if action in ("talk", "converse", "chat"):
        bond_shift = 1
    elif action in ("gift", "compliment", "praise"):
        bond_shift = 2
    elif action in ("arrest", "confine", "detain"):
        bond_shift = -5
    elif action in ("promote", "reward"):
        bond_shift = 3
    elif action in ("reprimand", "punish"):
        bond_shift = -3

    if bond_shift != 0:
        new_bond = max(0, min(100, (char["bond"] or 50) + bond_shift))
        await Database.execute(
            "UPDATE maya_rp.characters SET bond=$1 WHERE id=$2",
            new_bond, char["id"])

    reactions = {
        1: f"{char['name']} acknowledges you with a nod.",
        2: f"{char['name']} smiles warmly. The gesture is appreciated.",
        -3: f"{char['name']} stiffens. The air grows cold.",
        -5: f"{char['name']} is led away without a word. Their eyes burn with betrayal.",
        3: f"{char['name']} stands taller. The recognition means more than they let on.",
    }
    reaction = reactions.get(bond_shift, f"{char['name']} regards you silently.")

    return {
        "domain": "character",
        "success": True,
        "character": char["name"],
        "bond_before": char["bond"] or 50,
        "bond_after": max(0, min(100, (char["bond"] or 50) + bond_shift)),
        "bond_shift": bond_shift,
        "reaction": reaction,
        "narrative_hook": f"Interaction with {char['name']}: bond shifted by {bond_shift:+d}.",
    }
