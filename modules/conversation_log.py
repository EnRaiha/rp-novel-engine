#!/usr/bin/env python3
"""Conversation Dedup — track topics discussed. Prevent repeating the same conversation."""
from __future__ import annotations
from typing import Any
from core.db import Database
from core.config import Config

STOP = {"the","a","an","about","with","to","for","of","and","is","are","was","were","have","has","had","that","this","it","you","i","we","they","she","he","her","his","my","our","their","what","how","why","when","where","who","which","would","could","should","will","can","do","does","did","not","no","but","or","if","then","than","so","very","just","also","too","more","most","some","any","all","each","every","both","few","other","such","only","own","same","been","being","have","having","doing","going","thing","things"}

def _kw(txt: str) -> list[str]:
    """Keywords of a topic. A missing or blank topic has none, not a crash.

    `keywords` is a text[] column, so asyncpg hands it back as a list and the
    overlap comparison works as written.
    """
    return [w for w in str(txt if txt is not None else "").lower().split()
            if len(w) > 3 and w not in STOP]

async def log(character_id: int, topic: str, outcome: str = "neutral", beat: str = "neutral", session_id: int = None):
    """Record one discussed topic for the duplicate check.

    Nothing in the repo calls this yet, so `check` reads an empty table and can
    never report a duplicate: the writer needs a caller at the turn boundary.
    """
    if session_id is None: session_id = Config.SESSION_ID
    if not str(topic if topic is not None else "").strip():
        raise ValueError(f"topic must be a non-empty string, got {topic!r}")
    kws = _kw(topic)
    gd = await Database.fetchval("SELECT COALESCE(game_day,1) FROM maya_rp.sessions WHERE id=$1", session_id)
    await Database.execute("INSERT INTO maya_rp.conversation_log(session_id,character_id,topic,keywords,outcome,emotional_beat,game_day) VALUES($1,$2,$3,$4,$5,$6,$7)", session_id,character_id,topic,kws,outcome,beat,gd)

async def check(character_id: int, proposed: str, session_id: int = None) -> dict | None:
    """The most recent too-similar topic for this character, or None.

    None covers two cases on purpose: nothing to compare (no keywords), and no
    duplicate found. The bridge reports null as "no duplicate".
    """
    if session_id is None: session_id = Config.SESSION_ID
    kws = _kw(proposed)
    if not kws: return None
    gd = await Database.fetchval("SELECT COALESCE(game_day,1) FROM maya_rp.sessions WHERE id=$1", session_id)
    recent = await Database.fetch("SELECT topic,outcome,emotional_beat,game_day,keywords FROM maya_rp.conversation_log WHERE session_id=$1 AND character_id=$2 AND game_day>$3", session_id,character_id,(gd or 0)-20)
    for c in recent:
        ck = c["keywords"] if isinstance(c["keywords"],list) else []
        overlap = len(set(kws)&set(ck))
        if overlap >= max(2,len(kws)*0.5):
            return {"duplicate":True,"previous":c["topic"],"previous_outcome":c["outcome"],"games_ago":(gd or 0)-c["game_day"],"suggestion":f"Already discussed '{c['topic']}' {c['game_day']} games ago. Reference it directly or take a NEW direction."}
    return None
