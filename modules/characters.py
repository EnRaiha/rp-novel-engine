"""Character module — tick + action-intent parser.

QA cleanup 2026-08-14: removed the CharacterManager class (dead API with
zero call sites; kilo_bridge queries characters directly). Presence/control
changes go through the database directly.
"""
from core.db import Database
from core.config import Config

async def run_tick(session_id: int = None):
    """Character arc aging (added 2026-08-14): arcs inactive for 20+ days
    are marked stale and surfaced as events so the GM can retire or resume."""
    from core.log import info
    import json
    if session_id is None: session_id = Config.SESSION_ID
    try:
        stale = await Database.fetch(
            "SELECT id, character_table, character_id, arc_name FROM maya_rp.character_arcs "
            "WHERE status='active' AND started_at < NOW() - INTERVAL '20 days'")
        if stale:
            for a in stale:
                await Database.execute(
                    "UPDATE maya_rp.character_arcs SET status='stale' WHERE id=$1", a["id"])
            await Database.execute(
                "INSERT INTO maya_rp.events (session_id, happened_at, event_type, title, description, tags, importance) "
                "VALUES ($1, NOW(), 'character_arc', $2, $3, $4, 2)",
                session_id, "Character arcs went stale",
                f"{len(stale)} character arcs untouched for 20+ days — resume or retire",
                json.dumps(["character", "arcs"]))
        info("characters", f"Tick: arcs={len(stale)} stale")
        return {"character_arcs": 0, "stale_arcs": len(stale)}
    except Exception as e:
        info("characters", f"Error: {e}")
        return {"error": str(e)}


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
