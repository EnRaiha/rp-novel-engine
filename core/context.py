#!/usr/bin/env python3
"""Memory context — the blocks injected just before the player's turn (fasa 6, M1-M3).

The engine already knows what the scene needs; the model does not. This module
assembles the compact blocks a turn should see:

    [RECENT EVENTS]    the campaign chronicle, noise filtered out
    [RELATIONSHIPS]    companions of note with bond, stage and suspicion band
    [CURRENT GOAL]     active objectives, highest priority first
    [SCENE]            game day and the current location

`story_brief()` reads the campaign's structural brief (premise, narration rules,
overseer mechanics) from `adventures/tkg/story.md`; the harness injects it as a
prompt section, while the blocks above ride the per-turn context.

@module core.context
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Sequence

from core.config import Config
from core.db import Database
from core.ooc import suspicion_band

STORY_PATH = Path(
    os.environ.get("TKG_STORY_PATH", str(Path.home() / "Bumi-Hijau" / "adventures" / "tkg" / "story.md"))
)
# Event types that are engine chatter, not story beats.
NOISE_EVENT_TYPES = ("policy",)
MIN_EVENT_IMPORTANCE = 3


def story_brief() -> str:
    """The campaign's structural brief, or an empty string when absent."""
    if not STORY_PATH.is_file():
        return ""
    return STORY_PATH.read_text(encoding="utf-8", errors="replace").strip()


async def recent_events(session_id: int, limit: int = 6) -> list[dict[str, Any]]:
    """The chronicle's meaningful recent entries, newest first."""
    rows = await Database.fetch(
        "SELECT event_type, COALESCE(narrative_title, title) AS title,"
        " COALESCE(narrative_content, description) AS detail, importance,"
        " happened_at FROM maya_rp.events"
        " WHERE session_id=$1 AND importance >= $2 AND NOT (event_type = ANY($3::text[]))"
        " ORDER BY happened_at DESC NULLS LAST, id DESC LIMIT $4",
        int(session_id),
        MIN_EVENT_IMPORTANCE,
        list(NOISE_EVENT_TYPES),
        int(limit),
    )
    return [dict(row) for row in rows]


async def companions_of_note(session_id: int, limit: int = 5) -> list[dict[str, Any]]:
    """The companions the scene is most likely about, by bond then id."""
    rows = await Database.fetch(
        "SELECT c.id, c.name, c.bond, c.romance_stage, c.is_spouse, c.role,"
        " (SELECT s.suspicion FROM maya_rp.ooc_suspicion s"
        "  WHERE s.session_id = c.session_id AND s.observer_id = c.id) AS suspicion"
        " FROM maya_rp.characters c"
        " WHERE c.session_id=$1 AND c.status IS DISTINCT FROM 'dead'"
        "   AND (c.romance_flag IS TRUE OR c.is_spouse IS TRUE OR COALESCE(c.bond, 0) > 0)"
        " ORDER BY COALESCE(c.bond, 0) DESC, c.id LIMIT $2",
        int(session_id),
        int(limit),
    )
    return [dict(row) for row in rows]


async def current_goals(session_id: int, limit: int = 3) -> list[dict[str, Any]]:
    """Active objectives, highest priority first."""
    rows = await Database.fetch(
        "SELECT title, objective_type, priority, progress_pct FROM maya_rp.objectives"
        " WHERE session_id=$1 AND status='active'"
        " ORDER BY priority NULLS LAST, id LIMIT $2",
        int(session_id),
        int(limit),
    )
    return [dict(row) for row in rows]


async def ooc_status_lines(session_id: int, traits: Sequence[str] = ("general",)) -> list[str]:
    """The System's actionable lines: due beats, the loudest observer, exemptions.

    The model-facing `[SYSTEM STATE]` carries the score; these lines carry what
    the turn can *do* about it.
    """
    from core import ooc

    lines: list[str] = []
    beats = await ooc.milestones(session_id, traits=traits, due_only=True)
    if beats:
        lines.append("- due beats: " + ", ".join(beat["name"] for beat in beats[:4]))
    reading = await ooc.suspicion_reading(session_id)
    if reading["band"] != "unaware":
        lines.append(f"- observer: {reading['name']} — suspicion {reading['band']} ({reading['suspicion']})")
    live = await ooc.live_exemptions(session_id)
    if live:
        lines.append("- exemptions live: " + ", ".join(f"{rule} ({key})" for rule, key in list(live.items())[:3]))
    return lines


async def scene_state(session_id: int) -> dict[str, Any]:
    """Game day, campaign summary, and the location when one is recorded."""
    session = await Database.fetchrow(
        "SELECT name, game_day, summary, status FROM maya_rp.sessions WHERE id=$1", int(session_id)
    )
    location = await Database.fetchval(
        "SELECT mode() WITHIN GROUP (ORDER BY scene_location) FROM maya_rp.characters"
        " WHERE session_id=$1 AND presence='present' AND scene_location IS NOT NULL",
        int(session_id),
    )
    return {
        "name": session["name"] if session else None,
        "game_day": session["game_day"] if session else None,
        "summary": (session["summary"] or "")[:280] if session else "",
        "location": location,
    }


def render_blocks(blocks: dict[str, Any]) -> str:
    """The per-turn context text; empty sections drop out entirely."""
    lines: list[str] = []

    events = blocks.get("recent_events") or []
    if events:
        lines.append("[RECENT EVENTS]")
        for event in events:
            stamp = event.get("happened_at")
            day = stamp.date().isoformat() if hasattr(stamp, "date") else "—"
            title = (event.get("title") or "?").strip()
            if len(title) > 120:
                title = title[:117].rstrip() + "…"
            lines.append(f"- {day} · {event['event_type']} · {title}")

    companions = blocks.get("companions") or []
    if companions:
        lines.append("[RELATIONSHIPS]")
        for companion in companions:
            band = suspicion_band(companion.get("suspicion"))
            stage = companion.get("romance_stage") or ("spouse" if companion.get("is_spouse") else "—")
            lines.append(
                f"- {companion['name']} — bond {companion.get('bond') or 0} · {stage} · suspicion {band}"
            )

    goals = blocks.get("goals") or []
    if goals:
        lines.append("[CURRENT GOAL]")
        for goal in goals:
            progress = goal.get("progress_pct")
            progress_text = f", {progress}%" if progress is not None else ""
            lines.append(f"- {goal['title']} (priority {goal.get('priority') or '-'}{progress_text})")

    system = blocks.get("system") or []
    if system:
        lines.append("[SYSTEM]")
        lines.extend(system)

    scene = blocks.get("scene") or {}
    if scene.get("game_day") is not None or scene.get("location"):
        lines.append("[SCENE]")
        bits = [f"day {scene.get('game_day')}"]
        if scene.get("location"):
            bits.append(f"location: {scene['location']}")
        if scene.get("name"):
            bits.append(scene["name"])
        lines.append("- " + " · ".join(bits))

    return "\n".join(lines).strip()


async def build_context(
    session_id: int | None = None,
    *,
    events: int = 6,
    traits: Sequence[str] = ("general",),
) -> dict[str, Any]:
    """Everything the turn's context needs, in one call.

    @param session_id - session key.
    @param events - how many chronicle entries to include.
    @param traits - persona traits used for the due-beat list.
    @returns the story brief, the blocks, and the rendered text.
    """
    sid = int(session_id if session_id is not None else Config.SESSION_ID)
    blocks = {
        "recent_events": await recent_events(sid, events),
        "companions": await companions_of_note(sid),
        "goals": await current_goals(sid),
        "system": await ooc_status_lines(sid, traits),
        "scene": await scene_state(sid),
    }
    return {"session_id": sid, "story": story_brief(), "blocks": blocks, "text": render_blocks(blocks)}
