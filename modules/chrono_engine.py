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
import math, random
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info


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

    Args:
        days: Number of game days to skip (1-365)
        focus: 'balanced', 'economy', 'military', 'research'
        session_id: Game session (default from Config)

    Returns:
        dict with days_skipped, economy delta, events, montage_prompt
    """
    if session_id is None:
        session_id = Config.SESSION_ID

    if days < 1:
        return {"days_skipped": 0, "error": "Days must be >= 1", "montage_prompt": ""}
    if days > 365:
        # Hard cap per single skip. Use narration_sync / chunked rolls for long skips,
        # OR set ALLOW_LONG_SKIP = 1080+ for structural corrections (children comp).
        raise ValueError(f"Max 365 days per skip (got {days}) — split into chunks")

    results = {
        "days_skipped": days,
        "focus": focus,
        "events": [],
        "world_events": [],
    }

    months = days / 30.0

    # ═══════════════════════════════════════════════════════════════
    # 1. Snapshot before
    # ═══════════════════════════════════════════════════════════════
    before = await Database.fetchrow(
        "SELECT credits, alloys, fuel, aggregate_morale FROM maya_rp.resources WHERE session_id=$1",
        session_id,
    )
    credits_before = before["credits"] if before else 0

    # ═══════════════════════════════════════════════════════════════
    # 2. Compound Economy
    # ═══════════════════════════════════════════════════════════════
    daily_income = BASE_DAILY_INCOME
    daily_burn = BASE_DAILY_BURN

    if focus == "economy":
        daily_income = int(BASE_DAILY_INCOME * 1.5)
    elif focus == "military":
        daily_burn = int(BASE_DAILY_BURN * 1.5)

    net_daily = daily_income - daily_burn

    # Base accumulation
    base_credits = net_daily * days

    # Compound effect (diminishes for shorter skips, maxes at 8% for yearly)
    compound_rate = min(0.08, days / 365.0 * 0.08)
    compound_bonus = int(abs(base_credits) * compound_rate)

    final_credits = before["credits"] + base_credits + compound_bonus
    if final_credits < 0:
        final_credits = 0  # Floor at zero — triggers collapse later

    fuel_add = days * BASE_FUEL_PROD
    alloy_add = days * BASE_ALLOY_PROD

    await Database.execute(
        """UPDATE maya_rp.resources
           SET credits = GREATEST(0::bigint, $1),
               fuel = LEAST(5000000::bigint, fuel + $2),
               alloys = LEAST(3000000::bigint, alloys + $3)
           WHERE session_id = $4""",
        final_credits, fuel_add, alloy_add, session_id,
    )

    economy_line = f"Daily net: {net_daily:+,}C × {days}d = {base_credits:+,}C base + {compound_bonus:+,}C compound"
    results["economy"] = economy_line
    results["credits_before"] = credits_before
    results["credits_after"] = final_credits

    # ═══════════════════════════════════════════════════════════════
    # 3. Fast-Forward Research
    # ═══════════════════════════════════════════════════════════════
    research_rate = 5 if focus == "research" else 2
    await Database.execute(
        """UPDATE maya_rp.technologies
           SET research_progress = LEAST(100, research_progress + ($1::int * $2::int))
           WHERE session_id = $3 AND researched = false""",
        days, research_rate, session_id,
    )
    completed = await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.technologies WHERE research_progress >= 100 AND session_id=$1 AND researched=false",
        session_id,
    )
    if completed and completed > 0:
        # Mark them as researched
        await Database.execute(
            "UPDATE maya_rp.technologies SET researched=true WHERE research_progress >= 100 AND session_id=$1 AND researched=false",
            session_id,
        )
        results["events"].append(f"{completed} research projects completed.")

    # ═══════════════════════════════════════════════════════════════
    # 4. NPC Mood Decay/Shift
    # ═══════════════════════════════════════════════════════════════
    # Over time, stagnation drops morale; productivity raises it
    await Database.execute(
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

    # ═══════════════════════════════════════════════════════════════
    # 5. Advance Geopolitics (world moves while you wait)
    # ═══════════════════════════════════════════════════════════════
    faction_turns = max(1, days // 30)  # ~1 faction turn per month
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

    # ═══════════════════════════════════════════════════════════════
    # 6. Aggregate morale refresh
    # ═══════════════════════════════════════════════════════════════
    avg_morale = await Database.fetchval(
        "SELECT AVG(personal_morale) FROM maya_rp.npc_internal_state WHERE session_id=$1",
        session_id,
    ) or 50
    await Database.execute(
        "UPDATE maya_rp.resources SET aggregate_morale=$1 WHERE session_id=$2",
        int(avg_morale), session_id,
    )

    # ═══════════════════════════════════════════════════════════════
    # 7. Advance game day
    # ═══════════════════════════════════════════════════════════════
    await Database.execute(
        "UPDATE maya_rp.sessions SET game_day = game_day + $1 WHERE id=$2",
        days, session_id,
    )
    new_day = await Database.fetchval(
        "SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id,
    )
    results["new_game_day"] = new_day

    # ═══════════════════════════════════════════════════════════════
    # 8. Log the time skip
    # ═══════════════════════════════════════════════════════════════
    await Database.execute(
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
    months = results["days_skipped"] // 30
    days_remainder = results["days_skipped"] % 30
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
