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
from core.db import Database
from core.session import require_session


def _sid(session_id: int | None) -> int:
    """The session for this call, resolved at call time.

    An explicit id wins. Otherwise RP_SESSION, then the active arc file. Raises RuntimeError when
    nothing resolves. Never reads `Config.SESSION_ID`, which is fixed at import.
    """
    return require_session(session_id)

ADJUTANTS = ["Maya", "Hanum Voss", "Sara Valdez", "Maria"]


async def king_status(session_id: int | None = None) -> bool:
    session_id = _sid(session_id)
    return bool(await Database.fetchval(
        "SELECT king_present FROM maya_rp.sessions WHERE id=$1", session_id))


async def dark_status(session_id: int | None = None) -> bool:
    """DARK MODE: King unreachable (stealth/away). Ministries run via their
    co-ministers (deputies). Prompts only for critical items + Mastika capital."""
    session_id = _sid(session_id)
    return bool(await Database.fetchval(
        "SELECT dark_mode FROM maya_rp.sessions WHERE id=$1", session_id))


async def set_king(session_id: int | None, present: bool) -> None:
    session_id = _sid(session_id)
    await Database.execute(
        "UPDATE maya_rp.sessions SET king_present=$2, dark_mode=NOT $2 WHERE id=$1",
        session_id, present)


async def set_dark(session_id: int | None, dark: bool) -> None:
    """DARK MODE toggle: dark=TRUE → king_present=FALSE; dark=FALSE → king_present=TRUE."""
    session_id = _sid(session_id)
    await Database.execute(
        "UPDATE maya_rp.sessions SET dark_mode=$2, king_present=NOT $2 WHERE id=$1",
        session_id, dark)


async def _prompt(session_id: int, ministry: str, holder: str, action: str,
                  target: str, impact: str, urgency: str = "normal",
                  adj: str | None = None) -> bool:
    """Queue one prompt unless the same (session, ministry, action) is already pending.

    The table has no unique key for this, so the check and the insert run under one per-session
    advisory lock: a concurrent tick waits, then sees the committed row.

    @returns True when a row was inserted, False when a pending duplicate exists.
    """
    async with Database.transaction() as conn:
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtext('ministry_ai_prompt'), $1)", session_id)
        if adj is None:
            n = await conn.fetchval(
                "SELECT COUNT(*) FROM maya_rp.adjutant_prompts WHERE session_id=$1", session_id)
            adj = ADJUTANTS[n % len(ADJUTANTS)]
        tag = await conn.execute(
            """INSERT INTO maya_rp.adjutant_prompts
               (session_id, ministry, holder, action, target, impact, urgency, status, routed_via)
               SELECT $1::int, $2::text, $3::text, $4::text, $5::text, $6::text, $7::text,
                      'pending', $8::text
               WHERE NOT EXISTS (
                   SELECT 1 FROM maya_rp.adjutant_prompts
                   WHERE session_id=$1::int AND ministry=$2::text AND action=$4::text
                     AND status='pending')""",
            session_id, ministry, holder, action, target, impact, urgency, adj)
    return tag == "INSERT 0 1"


async def run_tick(session_id: int | None = None) -> dict:
    session_id = _sid(session_id)
    present = await king_status(session_id)
    dark = await dark_status(session_id)
    taken = 0      # actions ministries executed autonomously (King away / dark mode)
    prompted = 0   # new prompts queued; a pending duplicate is not counted

    async def raise_prompt(*args, **kwargs) -> None:
        nonlocal prompted
        if await _prompt(session_id, *args, **kwargs):
            prompted += 1

    # Dark mode: deputies (co-ministers) run their portfolios — prompt only critical.
    def holder_for(ministry: str) -> str:
        return f"{ministry} — Deputy (co-minister acting)" if dark else ministry

    # ── Lord of War ──
    probes = await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.factions WHERE session_id=$1 AND name='Iron Concord' AND status='active'",
        session_id) or 0
    if present:
        await raise_prompt("Lord of War", "Kapten Rizwan Aziz",
                           "Respond to Iron Concord activity", "frontier staging",
                           f"Iron Concord active ({probes} faction) — recommend response posture.",
                           "high")
    else:
        # Away/dark: autonomous defense posture (within charter: patrol/escort only)
        # Dark mode: deputies also quietly reposition fleets, no prompt.
        taken += 1

    # ── Mastika capital: ALWAYS prompts, King present or away ──
    # The capital was read as the literal territory id 170, which is session 3's row: in any other
    # campaign the query matched nothing, `crisis` stayed 0, and the one prompt the rule says is
    # unconditional never fired. `requires_king_prompt` is the column that marks the capital.
    crisis = await Database.fetchval(
        "SELECT crisis_level FROM maya_rp.territory "
        "WHERE session_id=$1 AND requires_king_prompt ORDER BY id LIMIT 1", session_id) or 0
    if crisis and crisis >= 3:
        await raise_prompt("Cabinet", "Aina Merpati & Azlan Perak",
                           "Mastika crisis response", "TKG Mastika",
                           f"Crisis level {crisis} at capital — requires King's direction.",
                           "critical")

    # ── Lord of Industry ──
    queued = await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.build_queue WHERE session_id=$1 AND status='queued'", session_id) or 0
    if present:
        if queued > 15:
            await raise_prompt("Lord of Industry", "Maya Khatri",
                               "Production backlog review", "Heaven Yard",
                               f"{queued} builds queued — prioritization needs royal direction.",
                               "normal")
        else:
            taken += 1
    else:
        # Away/dark: autonomous — queue within budget; dark mode deputies fast-track essentials
        taken += 1

    # ── Lord Diplomat ──
    if present:
        await raise_prompt("Lord Diplomat", "Lady Serena Ashford",
                           "Diplomatic overture available", "rim factions",
                           "Trade/treaty window with neutral factions; requires royal sign-off.",
                           "normal")
    else:
        # Away: low-stakes trade autonomous, no treaties. Dark: also freeze high-value talks.
        taken += 1

    # ── Lord of the Deep ──
    if present:
        await raise_prompt("Lord of the Deep", "Nadia Voss",
                           "Deep recon proposal", "uncharted rim",
                           "Propose extended survey of uncharted lanes.",
                           "normal")
    else:
        taken += 1

    # ── Lord Governor (colonial/trade) ──
    if present:
        await raise_prompt("Lord Governor", "Council-appointed",
                           "Governor portfolio review", "crown systems",
                           "Colonial/trade actions awaiting royal direction.",
                           "normal")
    else:
        taken += 1

    # ── Governor pipeline (added 2026-08-14) ──
    # Conquered/acquired territories without a governor get one: highest-score
    # vetted applicant first, else a Crown caretaker. Applicant status flow:
    # applied -> vetted | skipped_loyalty -> appointed. Only `vetted` is appointable.
    assigned = 0
    ungov = await Database.fetch(
        "SELECT id, system_name FROM maya_rp.territory WHERE session_id=$1 AND "
        "controlling_faction='Setia Empire' AND (governor_name IS NULL OR governor_name='')",
        session_id)
    for t in ungov:
        # One transaction: the territory lock, the applicant claim, the name and the event commit
        # together. A concurrent tick skips the locked territory and cannot take the same applicant.
        async with Database.transaction() as conn:
            open_row = await conn.fetchrow(
                "SELECT id FROM maya_rp.territory WHERE id=$1 AND session_id=$2 AND "
                "(governor_name IS NULL OR governor_name='') FOR UPDATE SKIP LOCKED",
                t["id"], session_id)
            if not open_row:
                continue
            applicant = await conn.fetchrow(
                "UPDATE maya_rp.governor_applicants SET status='appointed' WHERE id=("
                "SELECT id FROM maya_rp.governor_applicants WHERE session_id=$1 AND status='vetted' "
                "ORDER BY total_score DESC NULLS LAST, id LIMIT 1 FOR UPDATE SKIP LOCKED) "
                "RETURNING id, name", session_id)
            gov = applicant["name"] if applicant else "Acting Governor (Crown caretaker)"
            await conn.execute(
                "UPDATE maya_rp.territory SET governor_name=$1 WHERE id=$2", gov, t["id"])
            await conn.execute(
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
    session_id = _sid(session_id)
    return await Database.fetch(
        """SELECT id, ministry, holder, action, target, impact, urgency, routed_via, created_at
           FROM maya_rp.adjutant_prompts
           WHERE session_id=$1 AND status='pending'
           ORDER BY CASE urgency WHEN 'critical' THEN 0 WHEN 'high' THEN 1 ELSE 2 END, id""",
        session_id)


async def resolve(session_id: int, prompt_id: int, decision: str) -> dict:
    if decision not in ("accepted", "rejected"):
        return {"error": "decision must be accepted/rejected"}
    # The update targeted a prompt by id and session and answered with the decision either way, so a
    # prompt id from another campaign read as a resolved prompt.
    exists = await Database.fetchval(
        "SELECT id FROM maya_rp.adjutant_prompts WHERE id=$1 AND session_id=$2",
        prompt_id, session_id)
    if not exists:
        return {"error": f"prompt {prompt_id} not found in session {session_id}"}
    await Database.execute(
        """UPDATE maya_rp.adjutant_prompts
           SET status=$3, resolved_at=NOW() WHERE id=$1 AND session_id=$2""",
        prompt_id, session_id, decision)
    return {"prompt_id": prompt_id, "decision": decision}