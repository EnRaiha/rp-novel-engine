#!/usr/bin/env python3
"""News — Ported from Rust news.rs. News articles, public opinion, propaganda."""
from __future__ import annotations
import random
from core.db import Database
from core.config import Config
from core.log import info

NEWS_TEMPLATES = {
    "fleet": ["Fleet movements reported near {system}.", "Naval exercise scheduled in {system}."],
    "diplomacy": ["Relations with {faction} shift.", "Ambassador meets with {faction} delegation."],
    "economy": ["Trade volumes up {pct}% this quarter.", "Resource shortage looms as production lags."],
    "military": ["{faction} fleet spotted near border.", "Military alert: {faction} movements detected."],
    "discovery": ["New anomaly discovered in {system}.", "Expedition reports findings from {system}."],
    "social": ["Crew morale reported {status}.", "Festival celebrated across the fleet."],
}

MAX_DEDUP_ATTEMPTS = 8


async def _existing_headlines(session_id: int) -> set[str]:
    """All headlines ever generated for this session — used to avoid re-rolling old news."""
    rows = await Database.fetch(
        "SELECT headline FROM maya_rp.news_articles WHERE session_id=$1", session_id
    )
    return {r["headline"] for r in rows}


async def generate(session_id: int | None = None) -> list[dict]:
    if session_id is None: session_id = Config.SESSION_ID
    systems = await Database.fetch("SELECT system_name FROM maya_rp.territory WHERE session_id=$1 ORDER BY RANDOM() LIMIT 3", session_id)
    factions = await Database.fetch("SELECT name FROM maya_rp.factions WHERE session_id=$1 ORDER BY RANDOM() LIMIT 3", session_id)
    existing = await _existing_headlines(session_id)
    articles = []
    for _ in range(random.randint(1, 3)):
        for _attempt in range(MAX_DEDUP_ATTEMPTS):
            category = random.choice(list(NEWS_TEMPLATES.keys()))
            system = random.choice(systems)["system_name"] if systems else "Unknown"
            faction = random.choice(factions)["name"] if factions else "Unknown"
            template = random.choice(NEWS_TEMPLATES[category])
            headline = template.format(system=system, faction=faction, pct=str(random.randint(5, 50)), status=random.choice(["stable","improving","declining"]))
            if headline not in existing:
                break
            headline = None
        if headline is None:
            continue  # all candidates exhausted — skip, don't duplicate
        existing.add(headline)
        tick = await Database.fetchval("SELECT COALESCE(MAX(tick_number),0)+1 FROM maya_rp.news_articles WHERE session_id=$1", session_id) or 1
        await Database.execute("INSERT INTO maya_rp.news_articles (session_id, tick_number, headline, category, read) VALUES ($1,$2,$3,$4,false)", session_id, tick, headline, category)
        articles.append({"headline": headline, "category": category})
    return articles


async def roll_news(session_id: int | None = None, limit: int = 5) -> list[dict]:
    """Fetch unread news (a 'news roll'). Marks them read so they never return on a later roll."""
    if session_id is None: session_id = Config.SESSION_ID
    rows = await Database.fetch(
        "SELECT id, headline, category, importance FROM maya_rp.news_articles "
        "WHERE session_id=$1 AND read = false ORDER BY tick_number DESC, id DESC LIMIT $2",
        session_id, limit,
    )
    if rows:
        ids = [r["id"] for r in rows]
        await Database.execute(
            "UPDATE maya_rp.news_articles SET read = true WHERE id = ANY($1::int[])", ids
        )
    return [{"headline": r["headline"], "category": r["category"], "importance": r["importance"]} for r in rows]


async def mark_read(session_id: int | None = None, article_id: int | None = None, headline: str | None = None) -> bool:
    """Mark one article as read — by id, or by headline match. Already-checked news stays retired."""
    if session_id is None: session_id = Config.SESSION_ID
    if article_id is not None:
        await Database.execute("UPDATE maya_rp.news_articles SET read = true WHERE id=$1", article_id)
        return True
    if headline is not None:
        await Database.execute(
            "UPDATE maya_rp.news_articles SET read = true WHERE session_id=$1 AND headline=$2",
            session_id, headline,
        )
        return True
    return False


async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    try:
        articles = await generate(session_id)
        info("news", f"Generated {len(articles)} articles")
        return {"articles": len(articles)}
    except Exception as e:
        info("news", f"Error: {e}")
        return {"error": str(e)}
