#!/usr/bin/env python3
"""
Chrono-Engine — handles multi-month time skips gracefully.
Instead of running 180 individual ticks, it runs 1 scaled 'macro-tick'
that applies compound growth, resolves off-screen events, and generates
a narrative montage prompt for Deepseek.

Usage:
  from modules.chrono_engine import execute_time_skip
  result = await execute_time_skip(180, focus="economy", session_id=3)
"""
from __future__ import annotations
from typing import Any
from core.db import Database
from core.session import require_session
from core.log import info
from modules.calendar_tkg import DAYS_PER_MONTH

# The four focuses this engine knows. An unknown name used to fall through every
# branch and read exactly like "balanced", so a typo changed nothing and said nothing.
FOCUSES = ("balanced", "economy", "military", "research")


# ─── Base income/expense rates (per day) ────────────────────────────────
# These should eventually be derived from actual fleet size / territory count
BASE_DAILY_INCOME = 200_000    # Credits
BASE_DAILY_BURN = 50_000       # Credits
BASE_FUEL_PROD = 100_000       # Fuel units
BASE_ALLOY_PROD = 80_000       # Alloy units


async def execute_time_skip(
    days: int,
    focus: str = "balanced",
    session_id: int = None,
) -> dict:
    """
    Execute a macro-tick time skip. Returns a summary + montage prompt.

    Credits move by a relative delta (`credits + delta`, floored at zero) under a row lock. The old
    code wrote `before.credits + delta` from a snapshot, so any income or spend between the read and
    the write was lost. The resource, research, morale, day and log writes share one transaction: a
    failure at the log insert used to leave the economy and the day advanced with no record.
    Geopolitics ticks run first on their own connection, because that module owns its writes.

    Args:
        days: Number of game days to skip (1-365)
        focus: 'balanced', 'economy', 'military', 'research'
        session_id: Game session; None resolves through `require_session`

    Returns:
        dict with days_skipped, economy delta, events, montage_prompt

    Raises:
        core.ooc.FrozenSession: the campaign is frozen and maintenance is not armed.
    """
    from core.ooc import _refuse_frozen

    if session_id is None:
        session_id = require_session(None)
    _refuse_frozen(session_id)

    if days < 1:
        return {"days_skipped": 0, "error": "Days must be >= 1", "montage_prompt": ""}
    if days > 365:
        # Hard cap per single skip. Use narration_sync / chunked rolls for long skips,
        # OR set ALLOW_LONG_SKIP = 1080+ for structural corrections (children comp).
        raise ValueError(f"Max 365 days per skip (got {days}) — split into chunks")
    if focus not in FOCUSES:
        return {"days_skipped": 0, "error": f"Unknown focus {focus!r}: use one of {', '.join(FOCUSES)}",
                "montage_prompt": ""}

    results = {
        "days_skipped": days,
        "focus": focus,
        "events": [],
        "world_events": [],
    }

    if await Database.fetchval("SELECT 1 FROM maya_rp.resources WHERE session_id=$1", session_id) is None:
        # Checked again under the lock below. Here it keeps the world from moving on a refused skip.
        return {"days_skipped": 0, "focus": focus,
                "error": f"No resources row for session {session_id}: time skip refused",
                "montage_prompt": ""}

    # Geopolitics first: it owns its writes on its own connection, and the log row below needs the
    # world events it produced.
    faction_turns = max(1, days // DAYS_PER_MONTH)  # ~1 faction turn per month
    from modules.geopolitics import run_tick as geopolitics_tick

    world_events = []
    for _ in range(faction_turns):
        turn = await geopolitics_tick(session_id)
        if turn.get("events_generated", 0) > 0:
            world_events.append(f"Geopolitical shift: {turn['events_generated']} incidents.")

    if world_events:
        # Get the latest 2 political events for flavor
        latest = await Database.fetch(
            """SELECT description FROM maya_rp.events
               WHERE session_id=$1 AND event_type='geopolitics'
               ORDER BY happened_at DESC LIMIT 2""",
            session_id,
        )
        for ev in latest:
            results["world_events"].append(ev["description"][:120])

    daily_income = BASE_DAILY_INCOME
    daily_burn = BASE_DAILY_BURN

    if focus == "economy":
        daily_income = int(BASE_DAILY_INCOME * 1.5)
    elif focus == "military":
        daily_burn = int(BASE_DAILY_BURN * 1.5)

    net_daily = daily_income - daily_burn
    base_credits = net_daily * days
    # Compound effect (diminishes for shorter skips, maxes at 8% for yearly)
    compound_rate = min(0.08, days / 365.0 * 0.08)
    compound_bonus = int(abs(base_credits) * compound_rate)
    delta_credits = base_credits + compound_bonus
    fuel_add = days * BASE_FUEL_PROD
    alloy_add = days * BASE_ALLOY_PROD
    research_rate = 5 if focus == "research" else 2

    async with Database.transaction() as conn:
        # 1. Lock the resources row and snapshot it.
        before = await conn.fetchrow(
            "SELECT credits, alloys, fuel, aggregate_morale FROM maya_rp.resources "
            "WHERE session_id=$1 FOR UPDATE",
            session_id,
        )
        if not before:
            # No resources row, no skip: refuse before anything moves.
            return {"days_skipped": 0, "focus": focus,
                    "error": f"No resources row for session {session_id}: time skip refused",
                    "montage_prompt": ""}
        credits_before = before["credits"]

        # 2. Compound economy, as a relative update. Floor at zero triggers collapse later.
        final_credits = await conn.fetchval(
            """UPDATE maya_rp.resources
               SET credits = GREATEST(0::bigint, credits + $1),
                   fuel = LEAST(5000000::bigint, fuel + $2),
                   alloys = LEAST(3000000::bigint, alloys + $3)
               WHERE session_id = $4 RETURNING credits""",
            delta_credits, fuel_add, alloy_add, session_id,
        )
        results["economy"] = f"Daily net: {net_daily:+,}C × {days}d = {base_credits:+,}C base + {compound_bonus:+,}C compound"
        results["credits_before"] = credits_before
        results["credits_after"] = final_credits

        # 3. Fast-forward research.
        await conn.execute(
            """UPDATE maya_rp.technologies
               SET research_progress = LEAST(100, research_progress + ($1::int * $2::int))
               WHERE session_id = $3 AND researched = false""",
            days, research_rate, session_id,
        )
        completed = await conn.fetchval(
            "SELECT COUNT(*) FROM maya_rp.technologies WHERE research_progress >= 100 AND session_id=$1 AND researched=false",
            session_id,
        )
        if completed and completed > 0:
            await conn.execute(
                "UPDATE maya_rp.technologies SET researched=true WHERE research_progress >= 100 AND session_id=$1 AND researched=false",
                session_id,
            )
            results["events"].append(f"{completed} research projects completed.")

        # 4. NPC mood decay/shift: stagnation drops morale, productivity raises it.
        await conn.execute(
            """UPDATE maya_rp.npc_internal_state
               SET personal_morale = GREATEST(10, LEAST(100,
                       personal_morale + CASE
                           WHEN $1 <= 30 THEN 5     -- Short skip: slight boost from routine
                           WHEN $1 <= 90 THEN 0     -- Medium skip: neutral
                           ELSE -5                  -- Long skip: stagnation
                       END
                   )),
                   personal_fear = GREATEST(0, LEAST(100,
                       personal_fear + CASE
                           WHEN $2 = 'military' THEN 5   -- Military focus: tension rises
                           ELSE -3                        -- Peaceful focus: fear drops
                       END
                   ))
               WHERE session_id = $3""",
            days, focus, session_id,
        )
        results["events"].append("Crew morale adjusted for time elapsed.")

        # 5. Aggregate morale refresh.
        avg_morale = await conn.fetchval(
            "SELECT AVG(personal_morale) FROM maya_rp.npc_internal_state WHERE session_id=$1",
            session_id,
        ) or 50
        await conn.execute(
            "UPDATE maya_rp.resources SET aggregate_morale=$1 WHERE session_id=$2",
            int(avg_morale), session_id,
        )

        # 6. Advance the game day, relative.
        new_day = await conn.fetchval(
            "UPDATE maya_rp.sessions SET game_day = game_day + $1 WHERE id=$2 RETURNING game_day",
            days, session_id,
        )
        results["new_game_day"] = new_day

        # 7. Log the time skip.
        await conn.execute(
            """INSERT INTO maya_rp.time_skip_log
               (session_id, days_skipped, focus, credits_before, credits_after, events_summary)
               VALUES ($1, $2, $3, $4, $5, $6)""",
            session_id, days, focus, credits_before, final_credits,
            results["events"] + results["world_events"],
        )

    # ═══════════════════════════════════════════════════════════════
    # 9. Generate montage prompt for Deepseek
    # ═══════════════════════════════════════════════════════════════
    results["montage_prompt"] = _build_montage_prompt(results)

    info("chrono", f"Time skip: {days}d ({focus}) → day {new_day}, credits: {final_credits:,}")

    # ═══════════════════════════════════════════════════════════════
    # 10. Check for collapse conditions after time skip
    # ═══════════════════════════════════════════════════════════════
    from modules.collapse import check_for_collapse
    collapse = await check_for_collapse(session_id)
    if collapse:
        results["collapse"] = collapse
        results["events"].append(f"⚠️ COLLAPSE TRIGGERED: {collapse['new_arc']}")

    return results


def _build_montage_prompt(results: dict) -> str:
    """Generate a narrative instruction for Deepseek to write the time-skip montage."""
    months = results["days_skipped"] // DAYS_PER_MONTH
    days_remainder = results["days_skipped"] % DAYS_PER_MONTH
    time_str = f"{months} month{'s' if months != 1 else ''}"
    if days_remainder:
        time_str += f" and {days_remainder} day{'s' if days_remainder != 1 else ''}"

    world = "\n".join(f"- {e}" for e in results.get("world_events", ["Quiet on the galactic front."])[:3])
    economy = results.get("economy", "Routine operations.")

    collapse_section = ""
    if results.get("collapse"):
        c = results["collapse"]
        collapse_section = (
            f"\n⚠️ CRITICAL: {c.get('new_arc', 'A collapse has occurred')}!\n"
            f"GM Instruction: {c.get('gm_instruction', 'The situation is dire.')}\n"
            f"Recovery path: {c.get('recovery', 'Find a way back from the brink.')}"
        )

    return f"""
[TIME SKIP: {time_str} has passed. Focus: {results.get('focus', 'balanced')}.]
Write a short, evocative montage (3-4 paragraphs) summarizing this period.

Economy: {economy}
World events during this time:
{world}
{collapse_section}

End the montage by grounding the player back in the present moment — on the bridge,
in the war room, or wherever feels natural. Describe what has changed visibly.
"""
