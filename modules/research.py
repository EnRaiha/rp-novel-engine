"""Async research module — queue, progress, unlocks."""
import json
from datetime import datetime, timezone
from core.db import Database
from core.utils import calc_game_days

async def run_tick(session_id: int = 3):
    row = await Database.fetchrow("SELECT last_tick_at FROM resources WHERE session_id=$1", session_id)
    if not row or not row.get("last_tick_at"): return
    gd = calc_game_days(row["last_tick_at"])
    if gd < 0.01: return

    # Find active project
    active = await Database.fetchrow(
        "SELECT rq.id AS qid, rp.* FROM research_queue rq "
        "JOIN research_projects rp ON rp.id=rq.project_id "
        "WHERE rq.status='active' AND rq.session_id=$1 ORDER BY rq.queue_position LIMIT 1", session_id)

    if not active:
        # Start next pending
        pending = await Database.fetchrow(
            "SELECT rq.id AS qid, rp.* FROM research_queue rq "
            "JOIN research_projects rp ON rp.id=rq.project_id "
            "WHERE rq.status='pending' AND rq.session_id=$1 ORDER BY rq.queue_position LIMIT 1", session_id)
        if pending:
            # Check resource costs
            costs = pending.get("resource_costs")
            can_start = True
            if costs and isinstance(costs, dict):
                for res_name, qty in costs.items():
                    inv = await Database.fetchrow(
                        "SELECT COALESCE(quantity,0) AS avail FROM resource_inventory ri "
                        "JOIN strategic_resources sr ON sr.id=ri.resource_id WHERE sr.name=$1", res_name)
                    if not inv or inv["avail"] < qty:
                        can_start = False
                        break
            if can_start:
                if costs:
                    for res_name, qty in costs.items():
                        await Database.execute(
                            "UPDATE resource_inventory ri SET quantity=ri.quantity-$1 "
                            "FROM strategic_resources sr WHERE sr.name=$2 AND ri.resource_id=sr.id", qty, res_name)
                await Database.execute("UPDATE research_queue SET status='active' WHERE id=$1", pending["qid"])
                await Database.execute("UPDATE research_projects SET started_at=$1 WHERE id=$2",
                                       datetime.now(timezone.utc), pending["id"])
                active = await Database.fetchrow(
                    "SELECT rq.id AS qid, rp.* FROM research_queue rq "
                    "JOIN research_projects rp ON rp.id=rq.project_id WHERE rq.id=$1", pending["qid"])

    if not active:
        return

    # Advance
    inc = (gd / active["duration_days"]) * 100
    new_progress = min(100, float(active["progress_pct"]) + inc)
    await Database.execute("UPDATE research_projects SET progress_pct=$1 WHERE id=$2", round(new_progress, 1), active["id"])

    if new_progress >= 100:
        await Database.execute("UPDATE research_projects SET completed_at=$1, unlocked=true WHERE id=$2",
                               datetime.now(timezone.utc), active["id"])
        await Database.execute("UPDATE research_queue SET status='complete' WHERE id=$1", active["qid"])
        et = active.get("bonus_type")
        ev = float(active.get("bonus_value") or 0) if active.get("bonus_value") else None
        if et and ev:
            if et == "tax_bonus":
                await Database.execute("UPDATE territory SET tax_rate=tax_rate+$1 WHERE session_id=$2", ev, session_id)
            elif et == "growth_bonus":
                await Database.execute("UPDATE territory SET birth_rate=birth_rate+$1 WHERE session_id=$2", ev, session_id)
            elif et in ("hull_mult", "shield_mult", "ship_damage_mult"):
                types = await Database.fetch("SELECT DISTINCT ship_type FROM ships WHERE session_id=$1", session_id)
                for st in types:
                    await Database.execute("INSERT INTO ship_tech_bonuses (ship_type, bonus_type, value) VALUES ($1,$2,$3) ON CONFLICT DO NOTHING",
                                           st["ship_type"], et, ev)
            else:
                await Database.execute("INSERT INTO global_modifiers (modifier_type, value) VALUES ($1,$2)", et, ev)

        # Queue next
        nxt = await Database.fetchrow(
            "SELECT id FROM research_queue WHERE status='pending' AND session_id=$1 ORDER BY queue_position LIMIT 1", session_id)
        if nxt:
            await Database.execute("UPDATE research_queue SET status='active' WHERE id=$1", nxt["id"])

        print(f"  Research complete: {active['name']}")
    else:
        print(f"  Research: {active['name']} {new_progress:.0f}%")
