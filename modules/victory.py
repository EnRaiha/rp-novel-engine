"""Async victory module — progress tracking and victory checks."""
import json
from datetime import datetime, timezone
from core.db import Database
from core.config import Config
from core.log import info

async def run_tick(session_id: int = None):
    """Score the six victory axes for one campaign.

    Every read that can be session-scoped is: territory, factions and resources
    carry session_id, and research_projects is a galaxy-wide catalogue. The old
    queries had no filter at all, so the score counted every campaign's territory
    and every campaign's allies.
    """
    if session_id is None:
        session_id = Config.SESSION_ID
    factions = await Database.fetch(
        "SELECT COUNT(*) AS c FROM factions WHERE session_id=$1 AND name NOT IN ('Setia Empire')",
        session_id)
    total_f = max(1, factions[0]["c"]) if factions else 1
    terr = await Database.fetchrow(
        "SELECT COUNT(*) AS t FROM territory WHERE session_id=$1 AND controlling_faction='Setia Empire'",
        session_id)
    mil = min(100, (terr["t"] if terr else 0) / total_f * 20)
    res = await Database.fetchrow("SELECT credits FROM resources WHERE session_id=$1", session_id)
    eco = min(100, (res["credits"] if res else 0) / 100_000_000 * 100)
    allied = await Database.fetch(
        "SELECT COUNT(*) AS a FROM factions WHERE session_id=$1 AND standing='allied'", session_id)
    dip = min(100, (allied[0]["a"] if allied else 0) / total_f * 100)
    tech = await Database.fetchrow("SELECT COUNT(*) AS t, COUNT(*) FILTER (WHERE unlocked=true) AS u FROM research_projects")
    tec = min(100, (tech["u"] / max(1, tech["t"]) * 100 if tech else 0))
    rep = await Database.fetchrow(
        "SELECT reputation FROM factions WHERE session_id=$1 AND name='Setia Empire'", session_id)
    cul = min(100, ((rep["reputation"] if rep else 0) + 100) / 200 * 100)
    score = (mil + eco + dip + tec + cul) / 5

    track = {}
    for vt, p in [("military", mil), ("economic", eco), ("diplomatic", dip), ("technological", tec), ("cultural", cul), ("score", score)]:
        await Database.execute(
            "UPDATE victory_tracking SET progress=$1 WHERE faction_id="
            "(SELECT id FROM factions WHERE session_id=$3 AND name='Setia Empire') AND victory_type=$2",
            p, vt, session_id)
        if p >= 100:
            await Database.execute(
                "UPDATE victory_tracking SET completed=true, completed_at=$1 WHERE faction_id="
                "(SELECT id FROM factions WHERE session_id=$3 AND name='Setia Empire') "
                "AND victory_type=$2 AND completed=false",
                datetime.now(timezone.utc).replace(tzinfo=None), vt, session_id)
        track[vt] = round(p, 1)

    # A bare print() left the caller with nothing; the tick returns the axes now.
    info("victory", "Victory: " + " ".join(f"{k}:{v:.0f}%" for k, v in track.items()))
    return {"session_id": session_id, "victory": track, "score": round(score, 1)}
