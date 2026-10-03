#!/usr/bin/env python3
"""Character Memory System — persistent memories across sessions."""
from __future__ import annotations
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info, error


def _like_escape(word: str) -> str:
    """Escape LIKE metacharacters in a context word.

    Unescaped, a word containing `%` or `_` becomes a wildcard pattern: a
    context with "50%" matched far more than it should, and a lone "%" matched
    every memory the character owns.
    """
    return word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


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

    words = [f"%{_like_escape(w)}%" for w in (context_text or "").lower().split()[:20]]
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
            "last_recalled_at_game_day=$1 WHERE id=$2 AND session_id=$3",
            game_day, m["id"], session_id)
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
        tag = await Database.execute(
            "UPDATE maya_rp.character_memories SET expires_at_game_day=0 "
            "WHERE session_id=$1 AND expires_at_game_day IS NOT NULL AND expires_at_game_day < $2",
            session_id, game_day)
        # `Database.execute` returns the status tag, so this key used to hold the
        # string "UPDATE 3" where a count belongs.
        expired = int(tag.split()[-1]) if isinstance(tag, str) and tag.startswith("UPDATE") else 0
        return {"memories_expired": expired}
    except Exception as e:
        error("memories", f"tick error: {e}")
        return {"error": str(e)}


# ─── Memory Consolidation ("Sleep Cycle") — 2026-08-03 ─────────

def _extractive_gist(contents: list[str]) -> str:
    """Fallback summarizer: first sentence of each old memory, joined."""
    gist = []
    for c in contents:
        first = c.split(".")[0].strip()
        if first:
            gist.append(first)
    return ". ".join(gist[:6]) + "."


async def _summarize(contents: list[str]) -> str:
    """Summarize via local Ollama (qwen3.5:4b); extractive fallback."""
    text = "\n".join(f"- {c}" for c in contents)
    try:
        import httpx
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post("http://localhost:11434/api/chat", json={
                "model": "qwen3.5:4b",
                "messages": [{"role": "user", "content":
                    "Summarize these minor events into ONE concise high-level memory "
                    "paragraph (3-4 sentences, narrative voice, no bullet points):\n\n" + text}],
                "stream": False,
            })
            data = resp.json()
            summary = data.get("message", {}).get("content", "").strip()
            if summary:
                return summary
    except Exception as e:
        info("memories", f"Summarizer unavailable ({e}) — extractive fallback")
    return _extractive_gist(contents)


async def consolidate_memories(session_id: int = None, character_id: int | None = None,
                               age_days: int = 14, min_count: int = 10) -> dict:
    """
    Sleep-cycle consolidation: roll up old low-recall memories (>= age_days old,
    recalled < 3 times) into one 'consolidated' memory per character; archive the
    originals. Mimics human memory — the gist survives, the granular detail fades.
    """
    if session_id is None:
        session_id = Config.SESSION_ID
    # This path DELETES the originals, so a nonsense window would take the whole
    # history: a negative age_days moved the cutoff into the future and matched
    # every memory the character owned.
    if age_days < 0:
        raise ValueError(f"age_days cannot be negative, got {age_days}")
    if min_count < 1:
        raise ValueError(f"min_count must be at least 1, got {min_count}")
    try:
        game_day = await Database.fetchval(
            "SELECT COALESCE(game_day, 1) FROM maya_rp.sessions WHERE id=$1", session_id) or 1

        old = await Database.fetch(
            "SELECT id, character_id, content FROM maya_rp.character_memories "
            "WHERE session_id=$1 AND memory_type != 'consolidated' "
            "AND created_at_game_day IS NOT NULL AND created_at_game_day < $2::int - $3::int "
            "AND COALESCE(recalled_count, 0) < 3 "
            "ORDER BY character_id, created_at_game_day",
            session_id, game_day, age_days)

        # Group by character
        by_char: dict[int, list[dict]] = {}
        for m in old:
            by_char.setdefault(m["character_id"], []).append(m)

        consolidated = 0
        archived = 0
        for cid, mems in by_char.items():
            if len(mems) < min_count:
                continue
            summary = await _summarize([m["content"] for m in mems])
            # The gist REPLACES the originals (the old docstring said "archive",
            # the code deleted). Wrap insert+delete in one transaction so a
            # crash can't leave a duplicated summary or orphaned originals.
            async with Database.transaction() as conn:
                await conn.execute(
                    "INSERT INTO maya_rp.character_memories "
                    "(session_id, character_id, memory_type, content, created_at_game_day, emotional_weight) "
                    "VALUES ($1, $2, 'consolidated', $3, $4, 8)",
                    session_id, cid, summary, game_day)
                await conn.execute(
                    "DELETE FROM maya_rp.character_memories WHERE id = ANY($1::int[])",
                    [m["id"] for m in mems])
            consolidated += 1
            archived += len(mems)
            info("memories", f"Consolidated {len(mems)} memories -> char {cid} (day {game_day})")

        return {"characters": len(by_char), "consolidated": consolidated, "archived": archived,
                "game_day": game_day, "age_days": age_days, "min_count": min_count}
    except Exception as e:
        info("memories", f"Error: {e}")
        return {"error": str(e)}
