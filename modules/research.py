"""Async research module — queue, progress, unlocks."""
import json
from datetime import datetime, timezone
from core.db import Database
from core.log import error, warn
from core.utils import calc_game_days


def _writable_session(session_id):
    """Resolve the session for one call and refuse a frozen campaign.

    Sessions 3 and 5 are reference data. The fallback was `Config.SESSION_ID`, fixed at import.

    @param session_id - caller's session; `None` resolves through `core.session.require_session`.
    @returns the resolved session id.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    from core.ooc import _refuse_frozen
    from core.session import require_session

    sid = require_session(session_id)
    _refuse_frozen(sid)
    return sid


def parse_costs(raw, project: str = "?") -> dict[str, int] | None:
    """Read `research_projects.resource_costs` into `{resource name: whole quantity}`.

    The column is jsonb and the pool registers no jsonb codec, so it arrives as TEXT. The old
    check `isinstance(costs, dict)` was False for that string, so every costed project started
    for free, and a stray `.items()` on a string would have raised.

    @param raw - the column value: `None`, a JSON string, or an already-decoded dict.
    @param project - project name for the error log.
    @returns the costs; `{}` when the project has none; `None` when the value is unreadable, which
        the caller treats as "cannot start" rather than "free".
    """
    if raw is None or raw == "":
        return {}
    if isinstance(raw, (str, bytes, bytearray)):
        try:
            raw = json.loads(raw)
        except ValueError as e:
            error("research", f"{project}: resource_costs is not JSON ({e}); project not started")
            return None
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        error("research", f"{project}: resource_costs is {type(raw).__name__}, expected an object; "
                          f"project not started")
        return None
    out = {}
    for res_name, qty in raw.items():
        try:
            whole = int(qty)
        except (TypeError, ValueError):
            whole = None
        if whole is None or whole != qty or whole < 0:
            error("research", f"{project}: cost of {res_name!r} is {qty!r}, expected a whole "
                              f"number of at least 0; project not started")
            return None
        out[res_name] = whole
    return out


class _CannotStart(Exception):
    """Raised inside the start transaction to roll it back."""


async def run_tick(session_id: int = None):
    """Advance the research queue for one campaign.

    `resource_inventory` and `research_projects` carry no session_id: the strategic-resource
    pool and a project's progress are shared by every campaign. Only `research_queue` is scoped.

    @param session_id - campaign; `None` resolves through `require_session`.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
    row = await Database.fetchrow("SELECT last_tick_at FROM resources WHERE session_id=$1", session_id)
    if not row:
        return
    if not row.get("last_tick_at"):
        # A NULL stamp has no elapsed time to convert; the tick returned here in silence.
        warn("research", f"session {session_id}: resources.last_tick_at is NULL, "
                         f"elapsed days unknown, research not advanced")
        return
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
            costs = parse_costs(pending.get("resource_costs"), pending.get("name", "?"))
            if costs is not None:
                try:
                    # Check, debit, activate and stamp in one transaction: a debit that landed
                    # before a failing activation was never refunded.
                    async with Database.transaction() as conn:
                        for res_name, qty in costs.items():
                            inv = await conn.fetchrow(
                                "SELECT COALESCE(quantity,0) AS avail FROM resource_inventory ri "
                                "JOIN strategic_resources sr ON sr.id=ri.resource_id WHERE sr.name=$1 "
                                "FOR UPDATE OF ri", res_name)
                            if not inv or inv["avail"] < qty:
                                raise _CannotStart(res_name)
                        for res_name, qty in costs.items():
                            paid = await conn.fetchrow(
                                "UPDATE resource_inventory ri SET quantity=ri.quantity-$1 "
                                "FROM strategic_resources sr WHERE sr.name=$2 AND ri.resource_id=sr.id "
                                "AND ri.quantity>=$1 RETURNING ri.resource_id", qty, res_name)
                            if paid is None:
                                raise _CannotStart(res_name)
                        await conn.execute(
                            "UPDATE research_queue SET status='active' WHERE id=$1 AND session_id=$2",
                            pending["qid"], session_id)
                        await conn.execute("UPDATE research_projects SET started_at=$1 WHERE id=$2",
                                           datetime.now(timezone.utc).replace(tzinfo=None), pending["id"])
                        active = await conn.fetchrow(
                            "SELECT rq.id AS qid, rp.* FROM research_queue rq "
                            "JOIN research_projects rp ON rp.id=rq.project_id WHERE rq.id=$1", pending["qid"])
                except _CannotStart:
                    active = None

    if not active:
        return

    # Advance. `progress_pct` is nullable and `duration_days` can be zero in
    # principle: float(None) and a division by zero both killed the tick.
    duration = active["duration_days"] or 0
    if duration <= 0:
        print(f"  Research: {active['name']} has no duration — cannot advance")
        return
    started = active["progress_pct"] if active["progress_pct"] is not None else 0
    inc = (gd / duration) * 100
    new_progress = min(100, float(started) + inc)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    # The progress write, the completion stamp, the bonus and the queue advance commit together:
    # a bonus insert that raised left the project "complete" with no bonus and no way to re-run it.
    async with Database.transaction() as conn:
        await conn.execute("UPDATE research_projects SET progress_pct=$1 WHERE id=$2",
                           round(new_progress, 1), active["id"])

        if new_progress >= 100:
            await conn.execute("UPDATE research_projects SET completed_at=$1, unlocked=true WHERE id=$2",
                               now, active["id"])
            await conn.execute("UPDATE research_queue SET status='complete' WHERE id=$1 AND session_id=$2",
                               active["qid"], session_id)
            et = active.get("bonus_type")
            ev = float(active.get("bonus_value") or 0) if active.get("bonus_value") else None
            if et and ev:
                if et == "tax_bonus":
                    await conn.execute("UPDATE territory SET tax_rate=tax_rate+$1 WHERE session_id=$2", ev, session_id)
                elif et == "growth_bonus":
                    await conn.execute("UPDATE territory SET birth_rate=birth_rate+$1 WHERE session_id=$2", ev, session_id)
                elif et in ("hull_mult", "shield_mult", "ship_damage_mult"):
                    types = await conn.fetch("SELECT DISTINCT ship_type FROM ships WHERE session_id=$1", session_id)
                    for st in types:
                        await conn.execute("INSERT INTO ship_tech_bonuses (ship_type, bonus_type, value) VALUES ($1,$2,$3) ON CONFLICT DO NOTHING",
                                           st["ship_type"], et, ev)
                else:
                    await conn.execute("INSERT INTO global_modifiers (modifier_type, value) VALUES ($1,$2)", et, ev)

            # Queue next
            nxt = await conn.fetchrow(
                "SELECT id FROM research_queue WHERE status='pending' AND session_id=$1 ORDER BY queue_position LIMIT 1", session_id)
            if nxt:
                await conn.execute("UPDATE research_queue SET status='active' WHERE id=$1 AND session_id=$2",
                                   nxt["id"], session_id)

    if new_progress >= 100:
        print(f"  Research complete: {active['name']}")
    else:
        print(f"  Research: {active['name']} {new_progress:.0f}%")
