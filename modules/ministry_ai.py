#!/usr/bin/env python3
"""Ministry AI — Setia ministries (Day 1384, Izzat rule).

RULE: ministries decide THEMSELVES only when the KING IS AWAY.
      When the King is PRESENT, every proposal is a PROMPT delivered
      via Maya or any adjutant (Hanum Voss, Sara Valdez, Maria).

  king_present = sessions.king_present
    TRUE  → all ministry actions become adjutant_prompts (King decides)
    FALSE → ministries act autonomously within charter; only
            Mastika (capital) + critical items still prompt.

CLI:
  cli.py king present | away          → set the flag
  cli.py adjutant pending             → list prompts
  cli.py adjutant resolve <id> accept|reject
"""
from __future__ import annotations
import json
import asyncio, sys
sys.path.insert(0, str(__file__ + "/../../"))
from core.config import Config
from core.db import Database

SID = Config.SESSION_ID

ADJUTANTS = ["Maya", "Hanum Voss", "Sara Valdez", "Maria"]


async def king_status(session_id: int | None = None) -> bool:
    if session_id is None:
        session_id = SID
    return bool(await Database.fetchval(
        "SELECT king_present FROM maya_rp.sessions WHERE id=$1", session_id))


async def dark_status(session_id: int | None = None) -> bool:
    """DARK MODE: King unreachable (stealth/away). Ministries run via their
    co-ministers (deputies). Prompts only for critical items + Mastika capital."""
    if session_id is None:
        session_id = SID
    return bool(await Database.fetchval(
        "SELECT dark_mode FROM maya_rp.sessions WHERE id=$1", session_id))


async def set_king(session_id: int | None, present: bool) -> None:
    if session_id is None:
        session_id = SID
    await Database.execute(
        "UPDATE maya_rp.sessions SET king_present=$2, dark_mode=NOT $2 WHERE id=$1",
        session_id, present)


async def set_dark(session_id: int | None, dark: bool) -> None:
    """DARK MODE toggle: dark=TRUE → king_present=FALSE; dark=FALSE → king_present=TRUE."""
    if session_id is None:
        session_id = SID
    await Database.execute(
        "UPDATE maya_rp.sessions SET dark_mode=$2, king_present=NOT $2 WHERE id=$1",
        session_id, dark)


async def _prompt(session_id: int, ministry: str, holder: str, action: str,
                  target: str, impact: str, urgency: str = "normal",
                  adj: str | None = None) -> None:
    if adj is None:
        n = await Database.fetchval(
            "SELECT COUNT(*) FROM maya_rp.adjutant_prompts WHERE session_id=$1", session_id)
        adj = ADJUTANTS[n % len(ADJUTANTS)]
    await Database.execute(
        """INSERT INTO maya_rp.adjutant_prompts
           (session_id, ministry, holder, action, target, impact, urgency, status, routed_via)
           VALUES ($1,$2,$3,$4,$5,$6,$7,'pending',$8)""",
        session_id, ministry, holder, action, target, impact, urgency, adj)


async def run_tick(session_id: int | None = None) -> dict:
    if session_id is None:
        session_id = SID
    present = await king_status(session_id)
    dark = await dark_status(session_id)
    taken = 0      # actions ministries executed autonomously (King away / dark mode)
    prompted = 0   # prompts raised (King present, or Mastika/critical always)

    # Dark mode: deputies (co-ministers) run their portfolios — prompt only critical.
    def holder_for(ministry: str) -> str:
        return f"{ministry} — Deputy (co-minister acting)" if dark else ministry

    # ── Lord of War ──
    probes = await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.factions WHERE session_id=$1 AND name='Iron Concord' AND status='active'",
        session_id) or 0
    if present:
        await _prompt(session_id, "Lord of War", "Kapten Rizwan Aziz",
                      "Respond to Iron Concord activity", "frontier staging",
                      f"Iron Concord active ({probes} faction) — recommend response posture.",
                      "high")
        prompted += 1
    else:
        # Away/dark: autonomous defense posture (within charter: patrol/escort only)
        # Dark mode: deputies also quietly reposition fleets, no prompt.
        taken += 1

    # ── Mastika capital: ALWAYS prompts, King present or away ──
    crisis = await Database.fetchval(
        "SELECT crisis_level FROM maya_rp.territory WHERE session_id=$1 AND id=170", session_id) or 0
    if crisis and crisis >= 3:
        await _prompt(session_id, "Cabinet", "Aina Merpati & Azlan Perak",
                      "Mastika crisis response", "TKG Mastika",
                      f"Crisis level {crisis} at capital — requires King's direction.",
                      "critical")
        prompted += 1

    # ── Lord of Industry ──
    queued = await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.build_queue WHERE session_id=$1 AND status='queued'", session_id) or 0
    if present:
        if queued > 15:
            await _prompt(session_id, "Lord of Industry", "Maya Khatri",
                          "Production backlog review", "Heaven Yard",
                          f"{queued} builds queued — prioritization needs royal direction.",
                          "normal")
            prompted += 1
        else:
            taken += 1
    else:
        # Away/dark: autonomous — queue within budget; dark mode deputies fast-track essentials
        taken += 1

    # ── Lord Diplomat ──
    if present:
        await _prompt(session_id, "Lord Diplomat", "Lady Serena Ashford",
                      "Diplomatic overture available", "rim factions",
                      "Trade/treaty window with neutral factions; requires royal sign-off.",
                      "normal")
        prompted += 1
    else:
        # Away: low-stakes trade autonomous, no treaties. Dark: also freeze high-value talks.
        taken += 1

    # ── Lord of the Deep ──
    if present:
        await _prompt(session_id, "Lord of the Deep", "Nadia Voss",
                      "Deep recon proposal", "uncharted rim",
                      "Propose extended survey of uncharted lanes.",
                      "normal")
        prompted += 1
    else:
        taken += 1

    # ── Lord Governor (colonial/trade) ──
    if present:
        await _prompt(session_id, "Lord Governor", "Council-appointed",
                      "Governor portfolio review", "crown systems",
                      "Colonial/trade actions awaiting royal direction.",
                      "normal")
        prompted += 1
    else:
        taken += 1

    # ── Governor pipeline (added 2026-08-14) ──
    # Conquered/acquired territories without a governor get one: highest-score
    # pending applicant first, else a Crown caretaker.
    assigned = 0
    ungov = await Database.fetch(
        "SELECT id, system_name FROM maya_rp.territory WHERE session_id=$1 AND "
        "controlling_faction='Setia Empire' AND (governor_name IS NULL OR governor_name='')",
        session_id)
    for t in ungov:
        applicant = await Database.fetchrow(
            "SELECT id, name FROM maya_rp.governor_applicants "
            "WHERE session_id=$1 AND status='pending' ORDER BY total_score DESC LIMIT 1",
            session_id)
        gov = applicant["name"] if applicant else "Acting Governor (Crown caretaker)"
        await Database.execute(
            "UPDATE maya_rp.territory SET governor_name=$1 WHERE id=$2", gov, t["id"])
        if applicant:
            await Database.execute(
                "UPDATE maya_rp.governor_applicants SET status='appointed' WHERE id=$1",
                applicant["id"])
        await Database.execute(
            "INSERT INTO maya_rp.events (session_id, happened_at, event_type, title, description, tags, importance) "
            "VALUES ($1, NOW(), 'appointment', $2, $3, $4, 3)",
            session_id, f"Governor: {gov}",
            f"{gov} appointed governor of {t['system_name']}",
            json.dumps(["governor", t["system_name"]]))
        assigned += 1
    if assigned:
        taken += assigned

    return {"king_present": present, "dark_mode": dark, "taken_autonomous": taken,
            "prompted": prompted, "governors_assigned": assigned}


async def pending(session_id: int | None = None) -> list[dict]:
    if session_id is None:
        session_id = SID
    return await Database.fetch(
        """SELECT id, ministry, holder, action, target, impact, urgency, routed_via, created_at
           FROM maya_rp.adjutant_prompts
           WHERE session_id=$1 AND status='pending'
           ORDER BY CASE urgency WHEN 'critical' THEN 0 WHEN 'high' THEN 1 ELSE 2 END, id""",
        session_id)


async def resolve(session_id: int, prompt_id: int, decision: str) -> dict:
    if decision not in ("accepted", "rejected"):
        return {"error": "decision must be accepted/rejected"}
    await Database.execute(
        """UPDATE maya_rp.adjutant_prompts
           SET status=$3, resolved_at=NOW() WHERE id=$1 AND session_id=$2""",
        prompt_id, session_id, decision)
    return {"prompt_id": prompt_id, "decision": decision}