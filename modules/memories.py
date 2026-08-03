#!/usr/bin/env python3
"""Character Memory System — persistent memories across sessions."""
from __future__ import annotations
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info


async def store(character_id: int, memory_type: str, content: str,
                keywords: list = None, weight: int = 5, expires_day: int = None,
                source_event_id: int = None, session_id: int = None):
    """Store a character memory."""
    if session_id is None:
        session_id = Config.SESSION_ID
    game_day = await Database.fetchval(
        "SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id) or 1

    await Database.execute(
        "INSERT INTO maya_rp.character_memories (session_id, character_id, memory_type, "
        "content, source_event_id, created_at_game_day, recall_trigger_keywords, "
        "emotional_weight, expires_at_game_day) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)",
        session_id, character_id, memory_type, content, source_event_id, game_day,
        keywords or [], weight, expires_day)
    info("memories", f"Stored: [{memory_type}] {content[:60]}...")


async def recall(character_id: int, context_text: str,
                 session_id: int = None) -> list[dict]:
    """Find memories relevant to current context."""
    if session_id is None:
        session_id = Config.SESSION_ID
    game_day = await Database.fetchval(
        "SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id) or 1

    words = [f"%{w}%" for w in context_text.lower().split()[:20]]
    if not words:
        words = ["%"]

    rows = await Database.fetch(
        "SELECT id, memory_type, content, emotional_weight, recalled_count, "
        "created_at_game_day FROM maya_rp.character_memories "
        "WHERE character_id=$1 AND session_id=$2 "
        "AND (expires_at_game_day IS NULL OR expires_at_game_day > $3) "
        "AND (recall_trigger_keywords = '{}' OR EXISTS ("
        "  SELECT 1 FROM unnest(recall_trigger_keywords) kw WHERE kw ILIKE ANY($4))) "
        "ORDER BY emotional_weight DESC, recalled_count ASC LIMIT 5",
        character_id, session_id, game_day, words)

    for m in rows:
        await Database.execute(
            "UPDATE maya_rp.character_memories SET recalled_count=recalled_count+1, "
            "last_recalled_at_game_day=$1 WHERE id=$2",
            game_day, m["id"])
    return [dict(r) for r in rows]


async def get_inner_world(character_id: int, session_id: int = None) -> dict:
    """Full emotional state packet for narration."""
    if session_id is None:
        session_id = Config.SESSION_ID
    rows = await Database.fetch(
        "SELECT memory_type, content, emotional_weight FROM maya_rp.character_memories "
        "WHERE character_id=$1 AND session_id=$2 "
        "AND (expires_at_game_day IS NULL OR expires_at_game_day > "
        "  (SELECT game_day FROM maya_rp.sessions WHERE id=$2)) "
        "ORDER BY emotional_weight DESC", character_id, session_id)

    grouped = {}
    for r in rows:
        grouped.setdefault(r["memory_type"], []).append({"content": r["content"], "weight": r["emotional_weight"]})

    return {
        "character_id": character_id,
        "total_memories": len(rows),
        "memories_by_type": {k: len(v) for k, v in grouped.items()},
        "promises": len(grouped.get("promise", [])),
        "traumas": len(grouped.get("trauma", [])),
        "secrets": len(grouped.get("secret", [])),
        "grudges": len(grouped.get("grudge", [])),
        "high_impact": [{"type": r["memory_type"], "content": r["content"]}
                        for r in rows if r["emotional_weight"] >= 8][:5],
    }


async def cmd_memory_surface(character_name: str, context: str, session_id: int = None):
    """CLI: surface relevant memories for a character."""
    if session_id is None:
        session_id = Config.SESSION_ID
    char = await Database.fetchrow(
        "SELECT id, name FROM maya_rp.characters WHERE session_id=$1 AND LOWER(name) LIKE LOWER($2) LIMIT 1",
        session_id, f"%{character_name}%")
    if not char:
        print(f"Character '{character_name}' not found.")
        return
    memories = await recall(char["id"], context, session_id)
    print(f"\nMemories for {char['name']} (context: {context[:50]}...):")
    for m in memories:
        print(f"  [{m['memory_type']}] {m['content'][:80]}")
    if not memories:
        print("  (no relevant memories)")


async def run_tick(session_id: int = None) -> dict:
    """Memory tick: expire old memories."""
    if session_id is None:
        session_id = Config.SESSION_ID
    try:
        game_day = await Database.fetchval(
            "SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id) or 1
        expired = await Database.execute(
            "UPDATE maya_rp.character_memories SET expires_at_game_day=0 "
            "WHERE session_id=$1 AND expires_at_game_day IS NOT NULL AND expires_at_game_day < $2",
            session_id, game_day)
        return {"memories_expired": expired}
    except Exception as e:
        info("memories", f"Error: {e}")
        return {"error": str(e)}
