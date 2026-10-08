"""Character module — tick + action-intent parser.

QA cleanup 2026-08-14: removed the CharacterManager class (dead API with
zero call sites; kilo_bridge queries characters directly). Presence/control
changes go through the database directly.
"""
from core.db import Database
from core.session import require_session

def _contains(text: str) -> str:
    """LIKE pattern matching `text` as a literal substring (pair with `ESCAPE '\\'`).

    @param text - user text.
    @returns the escaped `%text%` pattern.
    """
    return "%" + str(text).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _writable_session(session_id: int | None) -> int:
    """Resolve the session for one call and refuse a frozen campaign.

    @param session_id - caller's session; `None` resolves through `core.session.require_session`.
    @returns the resolved session id.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    from core.ooc import _refuse_frozen

    sid = session_id if session_id is not None else require_session(None)
    _refuse_frozen(sid)
    return sid


async def run_tick(session_id: int = None):
    """Character arc aging (added 2026-08-14): arcs inactive for 20+ days
    are marked stale and surfaced as events so the GM can retire or resume.

    `character_arcs` has no `session_id`: it reaches a session through `characters`. The old
    query and `UPDATE ... WHERE id=$1` ran on every campaign's arcs, so a tick for a live session
    staled the frozen sessions' arcs. One scoped statement now selects and updates, and the event
    row commits with it.

    @param session_id - session to tick; `None` resolves through `require_session`.
    @returns `{"character_arcs": 0, "stale_arcs": n}`, or `{"error": ...}` on a database error.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    from core.log import info
    import json
    session_id = _writable_session(session_id)
    try:
        async with Database.transaction() as conn:
            stale = await conn.fetch(
                "UPDATE maya_rp.character_arcs a SET status='stale' "
                "FROM maya_rp.characters c "
                "WHERE a.character_table='characters' AND c.id=a.character_id AND c.session_id=$1 "
                "AND a.status='active' AND a.started_at < NOW() - INTERVAL '20 days' "
                "RETURNING a.id",
                session_id)
            if stale:
                await conn.execute(
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

    @param session_id - session of the character; a frozen campaign is refused.
    @param target - name fragment, matched literally (`%` and `_` are not wildcards).
    @returns the result dict for narration.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
    if character_id:
        char = await Database.fetchrow(
            "SELECT id, name, bond, role FROM maya_rp.characters WHERE id=$1 AND session_id=$2",
            character_id, session_id)
    elif target:
        char = await Database.fetchrow(
            "SELECT id, name, bond, role FROM maya_rp.characters "
            "WHERE session_id=$1 AND LOWER(name) LIKE LOWER($2) ESCAPE '\\' LIMIT 1",
            session_id, _contains(target))
    else:
        return {"domain": "character", "success": False, "narrative_hook": "No character specified."}

    if not char:
        return {"domain": "character", "success": False, "narrative_hook": f"Character not found: {target}"}

    # `char["bond"] or 50` read a stored 0 as a missing value: 696 of the 715 live
    # characters sit at bond 0, so every interaction reported bond_before 50 and
    # wrote 50 + shift, raising a character nobody had spoken to.
    bond_before = char["bond"] if char["bond"] is not None else 50

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

    bond_after = max(0, min(100, bond_before + bond_shift))
    if bond_shift != 0:
        await Database.execute(
            "UPDATE maya_rp.characters SET bond=$1 WHERE id=$2 AND session_id=$3",
            bond_after, char["id"], session_id)

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
        "bond_before": bond_before,
        "bond_after": bond_after,
        "bond_shift": bond_shift,
        "reaction": reaction,
        "narrative_hook": f"Interaction with {char['name']}: bond shifted by {bond_shift:+d}.",
    }
