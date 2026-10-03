#!/usr/bin/env python3
"""Objective Tracker — aggregates all active goals into one view. Critical → Urgent → Active → Background."""
from __future__ import annotations
import json
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info, error

async def get_active(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    obj = {"critical":[],"urgent":[],"active":[],"background":[]}
    for r in await Database.fetch("SELECT hook_type,description,status FROM maya_rp.narrative_hooks WHERE session_id=$1 AND status='active'", session_id):
        obj["active"].append({"source":"hook","title":r["hook_type"],"detail":(r.get("description")or"")[:80],"icon":"\U0001f4cc"})

    for r in await Database.fetch("SELECT opponent_faction,phase,war_goal FROM maya_rp.wars WHERE session_id=$1 AND status='active'", session_id):
        obj["urgent"].append({"source":"war","title":f"War vs {r['opponent_faction']}","detail":f"Phase: {r['phase']}","icon":"\u2694\ufe0f"})

    for r in await Database.fetch("SELECT title,description FROM maya_rp.quests WHERE session_id=$1 AND status='active' LIMIT 5", session_id):
        obj["active"].append({"source":"quest","title":r["title"],"detail":(r["description"]or"")[:80],"icon":"\U0001f4dc"})

    for r in await Database.fetch("SELECT trigger_type,cause_description FROM maya_rp.consequence_seeds WHERE session_id=$1 AND status='planted' AND can_be_prevented=true ORDER BY id LIMIT 3", session_id):
        obj["urgent"].append({"source":"consequence","title":f"Prevent: {r['trigger_type']}","detail":(r.get("cause_description")or"")[:80],"icon":"\u23f3"})

    return obj

async def objectives_to_prompt(session_id: int = None) -> str:
    obj = await get_active(session_id)
    lines = ["## ACTIVE OBJECTIVES",""]
    for label,key in [("\U0001f534 CRITICAL","critical"),("\U0001f7e1 URGENT","urgent"),("\U0001f7e2 IN PROGRESS","active"),("\u26aa BACKGROUND","background")]:
        items = obj[key]
        if items:
            lines.append(f"### {label}")
            for o in items: lines.append(f"- {o['icon']} {o['detail']}")
            lines.append("")
    if not any(obj.values()): lines.append("_No active objectives. The galaxy is quiet..._")
    return "\n".join(lines)

async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    try:
        # The EventBus auto-tracking existed and was never registered, so a
        # quarterly task could only advance when a caller pushed it by hand.
        await _register_event_listeners()
        expired = await Database.fetch("SELECT id,hook_type FROM maya_rp.narrative_hooks WHERE session_id=$1 AND status='active' AND created_at IS NOT NULL AND created_at < NOW() - INTERVAL '30 days'", session_id)
        for e in expired:
            await Database.execute("UPDATE maya_rp.narrative_hooks SET status='expired' WHERE id=$1 AND session_id=$2", e["id"], session_id)
        return {"expired":len(expired)}
    except Exception as e:
        error("objectives", f"tick error: {e}")
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════
# NOVEL ADAPTATION — QUARTERLY TASK SYSTEM (novel bab 499)
# Setiap 90 hari: 4 misi berjadual → reward Tier Blueprint (gacha draw)
# ═══════════════════════════════════════════════════════════════

QUARTERLY_TASK_POOL = [
    {"title": "Fleet Exercise", "objective": "Sweep X hostiles di sempadan", "target": 10, "kind": "kills"},
    {"title": "Survey Push", "objective": "Survey X planets baru", "target": 4, "kind": "survey"},
    {"title": "Trade Dominance", "objective": "Raise trade income ke X", "target": 15000000, "kind": "trade"},
    {"title": "Treasury Growth", "objective": "Treasury melebihi X credits", "target": 950000000, "kind": "credits"},
    {"title": "Duel Champion", "objective": "Menang X formal duels", "target": 3, "kind": "duels"},
    {"title": "Wreck Recovery", "objective": "Kumpul X wrecks", "target": 5, "kind": "wrecks"},
    {"title": "Territory Dev", "objective": "Development X sistem ke tier 3", "target": 2, "kind": "dev"},
    {"title": "Crew Pipeline", "objective": "Recruit X crew baru", "target": 10, "kind": "crew"},
]

BLUEPRINT_TIERS = [1, 2, 3, 4]  # gacha draw weights: rare = high tier

#: The listener kinds that are not pool kinds. A built ship advances the closest
#: thing the pool has to a construction objective, which is Development.
KIND_ALIASES = {"build": "dev"}

#: `EventBus.on` APPENDS, so registering per tick would stack a duplicate
#: listener every tick and multiply every bump. One flag, one registration.
_LISTENERS_REGISTERED = False


def task_titles_for(kind: str) -> list[str]:
    """The pool titles a progress kind belongs to.

    The objective text is localised BM, so a text probe for the English kind
    missed: "kills" matched nothing ("Sweep X hostiles di sempadan") and
    "build" matched nothing ("Development X sistem ke tier 3"). The pool's own
    `kind` field is the mapping, and the title carries it into the query.
    """
    wanted = KIND_ALIASES.get(kind, kind)
    return [t["title"] for t in QUARTERLY_TASK_POOL if t["kind"] == wanted]


async def generate_quarterly_tasks(session_id: int = None) -> dict:
    """Generate 4 quarterly tasks untuk quarter semasa (game_day // 90)."""
    if session_id is None: session_id = Config.SESSION_ID
    gd = await Database.fetchval("SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id)
    quarter = (gd or 1) // 90
    existing = await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.quarterly_tasks WHERE session_id=$1 AND quarter=$2 AND status='active'",
        session_id, quarter)
    if existing:
        return {"quarter": quarter, "already_active": existing}

    import random
    tasks = random.sample(QUARTERLY_TASK_POOL, 4)
    for i, t in enumerate(tasks, start=1):
        # Gacha blueprint reward: tier weight (rare = high tier)
        tier = random.choices(BLUEPRINT_TIERS, weights=[50, 30, 15, 5])[0]
        reward_val = {1: 250000, 2: 750000, 3: 2000000, 4: 6000000}[tier]
        await Database.execute(
            """INSERT INTO maya_rp.quarterly_tasks
               (session_id, quarter, task_index, title, objective, target_value, reward_type, reward_value)
               VALUES ($1, $2, $3, $4, $5, $6, 'blueprint', $7)""",
            session_id, quarter, i, t["title"], t["objective"], t["target"], reward_val)
    return {"quarter": quarter, "generated": len(tasks)}


async def update_quarterly_progress(session_id: int = None, kind: str = None, amount: int = 1) -> dict:
    """Kemaskini progress tasks ikut kind (kills/survey/trade/credits/duels/wrecks/dev/crew)."""
    if session_id is None: session_id = Config.SESSION_ID
    if not kind:
        return {"error": "kind required (kills/survey/trade/credits/duels/wrecks/dev/crew)"}
    if amount < 1:
        raise ValueError(f"amount must be at least 1, got {amount}")
    titles = task_titles_for(kind)
    tasks = await Database.fetch(
        "SELECT id, title, target_value, progress, reward_value FROM maya_rp.quarterly_tasks "
        "WHERE session_id=$1 AND status='active' "
        "AND (title = ANY($3::text[]) OR objective ILIKE '%'||$2||'%')",
        session_id, kind, titles)
    completed = []
    for t in tasks:
        np_ = (t["progress"] or 0) + amount
        done = np_ >= t["target_value"]
        await Database.execute(
            "UPDATE maya_rp.quarterly_tasks SET progress=$1, status=$2, completed_at=CASE WHEN $2='completed' THEN NOW() ELSE completed_at END WHERE id=$3",
            np_, "completed" if done else "active", t["id"])
        if done:
            # Gacha blueprint reward → research project unlocked (simulated)
            await Database.execute(
                "UPDATE maya_rp.resources SET research_points=research_points+$1 WHERE session_id=$2",
                t["reward_value"] // 1000, session_id)
            completed.append({"title": t["title"], "reward": t["reward_value"]})
    return {"updated": len(tasks), "completed": completed}


async def quarterly_tasks_view(session_id: int = None) -> dict:
    """View aktif quarterly tasks (format novel 【Quarterly Tasks】)."""
    if session_id is None: session_id = Config.SESSION_ID
    gd = await Database.fetchval("SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id)
    quarter = (gd or 1) // 90
    tasks = await Database.fetch(
        "SELECT task_index, title, objective, target_value, progress, status, reward_value "
        "FROM maya_rp.quarterly_tasks WHERE session_id=$1 AND quarter=$2 ORDER BY task_index", session_id, quarter)
    return {"quarter": quarter, "tasks": [dict(t) for t in tasks]}


# ═══════════════════════════════════════════════════════════════
# NOVEL ULTIMATE #2b — EVENTBUS AUTO-TRACKING
# Quarterly tasks update progress secara automatik via events.
# ═══════════════════════════════════════════════════════════════

async def _register_event_listeners() -> None:
    """Daftar listeners untuk auto-update quarterly progress. Registers ONCE."""
    from core.events import EventBus

    global _LISTENERS_REGISTERED
    if _LISTENERS_REGISTERED:
        return

    async def _on_ship_built(data):
        ship = data.get("ship") or {}
        sid = data.get("session_id") or ship.get("session_id")
        if sid:
            await _bump_kind(sid, "build", 1)

    async def _on_duel(data):
        sid = data.get("session_id")
        if sid:
            await _bump_kind(sid, "duels", 1)

    async def _on_battle(data):
        sid = data.get("session_id")
        if sid:
            await _bump_kind(sid, "kills", 1)

    for evt, cb in [("ship_built", _on_ship_built), ("duel_resolved", _on_duel),
                    ("battle_completed", _on_battle)]:
        try:
            EventBus.on(evt, cb)
        except Exception as e:  # noqa: BLE001 - reported below
            error("objectives", f"_register_event_listeners: {e}")
    _LISTENERS_REGISTERED = True


async def _bump_kind(session_id: int, kind: str, amount: int = 1) -> dict:
    """Kemaskini progress tasks ikut kind (kills/survey/trade/credits/duels/wrecks/dev/crew/build).

    One matcher, shared with `update_quarterly_progress`: the pool's own kind
    mapping. The three text probes this replaced could not match a localised
    objective, and every live task carries `task_type = 'generic'`, so the probe
    was the only path that could ever have worked.
    """
    titles = task_titles_for(kind)
    tasks = await Database.fetch(
        "SELECT id, task_type, objective, title, target_value, current_progress, required_amount, reward_blueprint, progress "
        "FROM maya_rp.quarterly_tasks WHERE session_id=$1 AND status='active' "
        "AND (title = ANY($3::text[]) OR objective ILIKE '%'||$2||'%')",
        session_id, kind, titles)
    completed = []
    for t in tasks:
        cur = (t.get("current_progress") or t.get("progress") or 0) + amount
        req = t.get("required_amount") or t.get("target_value") or 0
        done = req > 0 and cur >= req
        await Database.execute(
            "UPDATE maya_rp.quarterly_tasks SET current_progress=$1, progress=$1, "
            "status=$2, completed_at=CASE WHEN $2='completed' THEN NOW() ELSE completed_at END WHERE id=$3",
            cur, "completed" if done else "active", t["id"])
        if done:
            rw = t.get("reward_blueprint") or t.get("reward_value") or 0
            completed.append({"title": t.get("title") or t.get("objective"), "reward": rw})
    return {"updated": len(tasks), "completed": completed}
