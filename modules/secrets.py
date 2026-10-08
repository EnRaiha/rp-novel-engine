#!/usr/bin/env python3
"""Secrets System — secrets, lies & dramatic irony. What characters hide from each other."""
from __future__ import annotations
import math
import random
import re
from typing import Any
from core.db import Database
from core.log import info

PAST_ORGS = ("Den", "Vigil", "Federation")

# `{org}` is filled when a secret is drawn. The template list used to hold an f-string whose
# random.choice ran once at import, so every personal_past secret in a process named the same org.
SECRET_TEMPLATES = {
    "personal_past": ["was once part of {org}. Left under unclear circumstances.","has a family never mentioned.","was responsible for a crew death on a previous ship.","can't read. Hidden entire career.","changed name when joining."],
    "guilt": ["took something from cargo during supply crisis.","ignored a maintenance warning.","reported a crewmate for something minor — they were punished harshly."],
    "capability": ["has medical training never mentioned.","speaks Den trade language.","can pilot small craft — hid it to avoid dangerous missions."],
}

def _writable_session(session_id: int | None) -> int:
    """Resolve the session for one call and refuse a frozen campaign.

    @param session_id - caller's session; `None` resolves through `core.session.require_session`.
    @returns the resolved session id.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    from core.ooc import _refuse_frozen
    from core.session import require_session

    sid = require_session(session_id)
    _refuse_frozen(sid)
    return sid


def draw_template(kind: str) -> str:
    """Pick one secret text of `kind`, filling `{org}` with a fresh random org.

    @param kind - key of `SECRET_TEMPLATES`.
    @returns the text without the holder's name.
    """
    return random.choice(SECRET_TEMPLATES[kind]).replace("{org}", random.choice(PAST_ORGS))


async def plant(secret_type: str, holder_id: int, content: str, hidden_from: list = None, trigger: str = "deep_bond_conversation", consequence: str = "", auto_reveal_day: int = None, session_id: int = None) -> int:
    """Plant one active secret.

    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
    gd = await Database.fetchval("SELECT COALESCE(game_day,1) FROM maya_rp.sessions WHERE id=$1", session_id)
    sid = await Database.fetchval("INSERT INTO maya_rp.secrets(session_id,secret_type,holder_character_id,content,hidden_from_ids,discovery_trigger,consequence_description,planted_game_day,auto_reveal_game_day,status) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,'active') RETURNING id", session_id,secret_type,holder_id,content,(hidden_from or []),trigger,consequence,gd,auto_reveal_day)
    info("secrets", f"Planted: {secret_type} for holder {holder_id}")
    return sid

MIN_TOKEN_LEN = 3
_NON_WORD_RE = re.compile(r"[^a-z0-9]+")


def trigger_tokens(trigger: str | None) -> list[str]:
    """Split a `discovery_trigger` into the words that must appear in the context.

    @param trigger - snake_case phrase such as "deep_bond_conversation"; `None` yields no tokens.
    @returns lowercase tokens of at least `MIN_TOKEN_LEN` characters. A trigger like "a__b" or "" gave
        empty tokens, and `"" in text` is always true, so it counted as matched.
    """
    return [t for t in _NON_WORD_RE.split((trigger or "").lower()) if len(t) >= MIN_TOKEN_LEN]


async def check_discovery(context: str, session_id: int = None) -> list[dict]:
    """Reveal the active secrets whose trigger the context matches, or whose auto-reveal day passed.

    A trigger matches when at least half of its tokens (and at least one) appear in the context. A
    trigger with no usable token never matches by text: it reached the old test `0 >= 0` and
    revealed on any context. A NULL context reads as empty text.

    @param context - text to match against; `None` is treated as "".
    @param session_id - campaign; `None` resolves through `require_session`.
    @returns one dict per newly revealed secret.
    @raises core.ooc.FrozenSession - the campaign is frozen and maintenance is not armed.
    """
    session_id = _writable_session(session_id)
    context = context or ""
    lower = context.lower()
    active = await Database.fetch("SELECT id,secret_type,holder_character_id,content,discovery_trigger,consequence_description,auto_reveal_game_day FROM maya_rp.secrets WHERE session_id=$1 AND status='active'", session_id)
    gd = await Database.fetchval("SELECT COALESCE(game_day,1) FROM maya_rp.sessions WHERE id=$1", session_id) or 1
    discovered = []
    for s in active:
        tokens = trigger_tokens(s.get("discovery_trigger"))
        matches = sum(1 for w in tokens if w in lower)
        by_text = bool(tokens) and matches >= max(1, math.ceil(len(tokens) * 0.5))
        auto = s.get("auto_reveal_game_day") is not None and gd >= s["auto_reveal_game_day"]
        if by_text or auto:
            # status='active' in the WHERE makes a concurrent reveal win once, not twice.
            hit = await Database.fetchval("UPDATE maya_rp.secrets SET status='revealed',revealed_game_day=$1,revelation_context=$2 WHERE id=$3 AND session_id=$4 AND status='active' RETURNING id", gd, context[:200], s["id"], session_id)
            if hit is None:
                continue
            hn = await Database.fetchval(
                "SELECT name FROM maya_rp.characters WHERE id=$1 AND session_id=$2",
                s["holder_character_id"], session_id)
            discovered.append({"secret_id":s["id"],"type":s["secret_type"],"holder":hn,"content":s["content"],"consequence":s["consequence_description"]})
    return discovered

async def get_dramatic_irony(session_id: int = None) -> list[dict]:
    from core.session import require_session
    session_id = require_session(session_id)
    rows = await Database.fetch("SELECT s.id,s.secret_type,s.content,c.name as holder FROM maya_rp.secrets s JOIN maya_rp.characters c ON c.id=s.holder_character_id WHERE s.session_id=$1 AND s.status='active' AND s.secret_type='player_blind' ORDER BY s.planted_game_day DESC LIMIT 5", session_id)
    return [dict(r) for r in rows]

async def seed_initial(session_id: int = None):
    session_id = _writable_session(session_id)
    existing = await Database.fetchval("SELECT COUNT(*) FROM maya_rp.secrets WHERE session_id=$1", session_id)
    if existing and existing>0: return
    chars = await Database.fetch("SELECT id,name,role FROM maya_rp.characters WHERE session_id=$1 AND status='active' AND role NOT IN ('player') ORDER BY RANDOM() LIMIT 10", session_id)
    for c in chars:
        roll = random.random()
        if roll < 0.4:
            content = c['name'] + " " + draw_template("personal_past")
            await plant("personal_past",c["id"],content,trigger="deep_bond_conversation",consequence="Could strengthen or damage bond",session_id=session_id)
        elif roll < 0.55:
            content = c['name'] + " " + draw_template("guilt")
            await plant("guilt",c["id"],content,trigger="confession_under_stress",consequence="Trust could be damaged",session_id=session_id)
        elif roll < 0.65:
            content = c['name'] + " " + draw_template("capability")
            await plant("capability",c["id"],content,trigger="desperate_moment",consequence="Could change their role",session_id=session_id)
    player = await Database.fetchrow("SELECT id FROM maya_rp.characters WHERE session_id=$1 AND role='player'", session_id)
    if player:
        blinds = ["The Den armada has a spy among the crew.","The Vein Network artifact is still emitting a faint signal.","Three crew have been meeting in secret — it's a birthday planning committee but looks suspicious.","The water recycler has a micro-fracture. Critical in 20 days if unfound."]
        for b in blinds:
            await plant("player_blind",player["id"],b,trigger="investigation",auto_reveal_day=(await Database.fetchval("SELECT COALESCE(game_day,1) FROM maya_rp.sessions WHERE id=$1", session_id) or 0)+random.randint(15,40),session_id=session_id)

async def run_tick(session_id: int = None) -> dict:
    session_id = _writable_session(session_id)
    gd = await Database.fetchval("SELECT COALESCE(game_day,1) FROM maya_rp.sessions WHERE id=$1", session_id) or 1
    expired = await Database.fetch("SELECT id,content FROM maya_rp.secrets WHERE session_id=$1 AND status='active' AND auto_reveal_game_day IS NOT NULL AND auto_reveal_game_day<=$2", session_id,gd)
    for e in expired:
        await Database.execute("UPDATE maya_rp.secrets SET status='revealed',revealed_game_day=$1,revelation_context='Time revealed' WHERE id=$2", gd,e["id"])
    return {"auto_revealed":len(expired)}
