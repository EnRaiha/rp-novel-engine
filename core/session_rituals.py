#!/usr/bin/env python3
"""Session Bookends — open/close rituals. 'Previously on' and 'Next time on'."""
from __future__ import annotations
from datetime import datetime, timezone
from core.db import Database
from core.config import Config
from core.log import error
from core.utils import comma

async def generate_open(session_id: int = None) -> str:
    if session_id is None: session_id = Config.SESSION_ID
    parts = ["## SESSION OPEN\n"]
    le = await Database.fetchrow("SELECT title, happened_at FROM maya_rp.events WHERE session_id=$1 ORDER BY id DESC LIMIT 1", session_id)
    if le:
        ago = _ago(le["happened_at"])
        parts.append(f"**Last session ended:** {ago}")
        parts.append(f"> {le['title']}\n")

    from core.scene_stack import get_stack_summary
    st = await get_stack_summary(session_id)
    if st:
        lat = st[-1]
        ctx = lat["context"]
        parts.append(f"**Unfinished scene:** {ctx.get('what_was_happening','?')}")
        parts.append(f"Location: {ctx.get('location','?')} with {', '.join(ctx.get('characters_present',[]))}\n")

    from core.pacing import PacingDirector
    pm = await PacingDirector.get_mode(session_id)
    parts.append(f"**Atmosphere:** {pm['mode'].upper()}\n")

    from modules.locations import get_player_location
    loc = await get_player_location(session_id)
    try:
        from modules.environment import generate_details
        env = await generate_details(loc.get("location","bridge"), session_id)
        if env:
            parts.append("**The world around you:**")
            for d in env: parts.append(f"- {d}")
            parts.append("")
    except Exception as e:  # noqa: BLE001 - reported below
        error("session-rituals", f"generate_open: {e}")

    from modules.objectives import objectives_to_prompt
    obj = await objectives_to_prompt(session_id)
    critical_lines = [l for l in obj.split("\n") if "CRITICAL" in l or l.startswith("- ") and any(ll in l for ll in ["🔴","🟡"])]
    if critical_lines:
        parts.extend(critical_lines[:6])
        parts.append("")

    ob = {"combat":"The alarms haven't stopped.","crisis":"Something is wrong.","social":"The room settles as you enter.","intimate":"The door closes behind you.","exploration":"The viewscreen fills with something new.","political":"The council chamber waits.","downtime":"The ship hums its quiet song.","horror":"Something changed while you were sleeping."}
    parts.append(ob.get(pm["mode"], ob["downtime"]))
    return "\n".join(parts)

async def generate_close(session_id: int = None) -> str:
    if session_id is None: session_id = Config.SESSION_ID
    parts = ["---\n## Session Summary\n"]
    evs = await Database.fetch("SELECT title, importance FROM maya_rp.events WHERE session_id=$1 ORDER BY id DESC LIMIT 5", session_id)
    if evs:
        parts.append("**What happened:**")
        for e in evs:
            icon = "!" if (e["importance"] or 0) >= 4 else "\u2022"
            parts.append(f"  {icon} {e['title']}")
        parts.append("")
    r = await Database.fetchrow("SELECT credits, alloys, fuel FROM maya_rp.resources WHERE session_id=$1", session_id)
    if r: parts.append(f"**State:** {comma(r['credits'])}C | {comma(r['alloys'])}A | {comma(r['fuel'])}F\n")
    bs = await Database.fetch("SELECT c.name, c.bond FROM maya_rp.romance_arcs ra JOIN maya_rp.characters c ON c.id=ra.character_id WHERE ra.session_id=$1 AND c.session_id=$1 AND c.bond>=5 ORDER BY c.bond DESC LIMIT 5", session_id)
    if bs:
        parts.append("**Bonds:**")
        for b in bs: parts.append(f"  {b['name']}: {'\u2665'*min(10,b['bond'])+'\u2661'*max(0,10-b['bond'])}")
        parts.append("")
    from core.pacing import PacingDirector
    pm = await PacingDirector.get_mode(session_id)
    parts.append(pm["mode"] in ("combat","crisis","horror") and "*The session ends, but the danger doesn't.*" or "*The session pauses. The story continues.*")
    return "\n".join(parts)

def _ago(dt) -> str:
    if not dt: return "unknown"
    if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)
    h = int((datetime.now(timezone.utc)-dt).total_seconds()/3600)
    if h < 1: return "just now"
    if h < 24: return f"{h}h ago"
    return f"{h//24}d ago"
