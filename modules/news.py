#!/usr/bin/env python3
"""News — Ported from Rust news.rs. News articles, public opinion, propaganda.

Guardrails:
  - Exact dedup: a headline never appears twice.
  - Template dedup: the same story skeleton (numbers normalized) never
    re-rolls within the freshness window — "Trade volumes up 21%" cannot
    be followed by "Trade volumes up 40%" days later.
  - Freshness: roll_news() only serves articles younger than
    MAX_NEWS_AGE_DAYS; stale unread articles are retired automatically.
"""
from __future__ import annotations
import random
import re
from core.db import Database
from core.config import Config
from core.log import info, error

NEWS_TEMPLATES = {
    "fleet": [
        "Fleet movements reported near {system}.",
        "Naval exercise scheduled in {system}.",
        "Supply convoy arrives at {system}.",
        "Dockyard expansion announced for {system}.",
        "Patrol wing returns from {system} with full holds.",
        "Escort carrier assigned permanent station at {system}.",
    ],
    "diplomacy": [
        "Relations with {faction} shift.",
        "Ambassador meets with {faction} delegation.",
        "Trade pact signed with {faction}.",
        "{faction} envoy requests audience with the Crown.",
        "Border talks with {faction} conclude peacefully.",
        "{faction} opens new embassy in the capital.",
    ],
    "economy": [
        "Trade volumes up {pct}% this quarter.",
        "Resource shortage looms as production lags.",
        "New mining claim staked in {system}.",
        "Market index hits {pct}% of quarterly target.",
        "Reconstruction bond oversubscribed in hours.",
        "Civilian ship registry grows {pct}% year over year.",
        "Guild fair draws record crowds in {system}.",
        "Export tariffs adjusted — analysts see {pct}% impact.",
    ],
    "military": [
        "{faction} fleet spotted near border.",
        "Military alert: {faction} movements detected.",
        "{faction} warships observed in convoy formation.",
        "Defense drills concluded in {system}.",
        "{faction} scout vessel intercepted near {system}.",
        "Border patrols doubled after {faction} activity.",
    ],
    "discovery": [
        "New anomaly discovered in {system}.",
        "Expedition reports findings from {system}.",
        "Precursor signal traced to {system}.",
        "Derelict vessel recovered near {system}.",
        "Survey team maps uncharted region of {system}.",
        "Research outpost established in {system}.",
    ],
    "social": [
        "Crew morale reported {status}.",
        "Festival celebrated across the fleet.",
        "New academy cohort begins training in {system}.",
        "Long-service medals awarded to {pct}% of veteran crews.",
        "Veterans' hall opens its doors in {system}.",
        "Courier service expands to {system}.",
    ],
}

MAX_DEDUP_ATTEMPTS = 8
MAX_NEWS_AGE_DAYS = 5   # articles older than this many game days are stale — retired on roll

# Categories `generate` can mint, since they are NEWS_TEMPLATES' keys. The
# sentiment hook scored ("celebration", "trade", "science"), none of which this
# module can produce, so every headline it minted lowered public opinion. These
# are the real ones: good news is the economy, the fleet families and discovery.
GOOD_NEWS_CATEGORIES = ("economy", "social", "discovery")

# Normalizes "Trade volumes up 21%" -> "Trade volumes up N%"
_NUM_RE = re.compile(r"\d+")


def _normalize_template(headline: str) -> str:
    """Reduce a headline to its story skeleton for template-level dedup."""
    return _NUM_RE.sub("N", headline)


async def _game_day(session_id: int) -> int:
    return await Database.fetchval(
        "SELECT COALESCE(game_day, 1) FROM maya_rp.sessions WHERE id=$1", session_id
    ) or 1


async def _existing_headlines(session_id: int) -> set[str]:
    """All headlines ever generated for this session — used to avoid re-rolling old news."""
    rows = await Database.fetch(
        "SELECT headline FROM maya_rp.news_articles WHERE session_id=$1", session_id
    )
    return {r["headline"] for r in rows}


async def _recent_templates(session_id: int, gd: int, window: int) -> set[str]:
    """Story skeletons used within the last `window` game days.
    Blocks same-template repeats like 'Trade volumes up N%' re-rolling.

    An article with a NULL game_day counts as inside the window: an undated row
    cannot prove it is stale, and this guard errs toward not repeating a
    skeleton. Every generator writes game_day, so the branch is defensive.
    """
    cutoff = gd - window
    rows = await Database.fetch(
        """SELECT headline FROM maya_rp.news_articles
           WHERE session_id=$1 AND (game_day IS NULL OR game_day >= $2)""",
        session_id, cutoff,
    )
    return {_normalize_template(r["headline"]) for r in rows}


async def generate(session_id: int | None = None) -> list[dict]:
    if session_id is None: session_id = Config.SESSION_ID
    gd = await _game_day(session_id)
    systems = await Database.fetch("SELECT system_name FROM maya_rp.territory WHERE session_id=$1 ORDER BY RANDOM() LIMIT 3", session_id)
    factions = await Database.fetch("SELECT name FROM maya_rp.factions WHERE session_id=$1 ORDER BY RANDOM() LIMIT 3", session_id)
    existing = await _existing_headlines(session_id)
    recent_templates = await _recent_templates(session_id, gd, MAX_NEWS_AGE_DAYS)

    # Build a pool of templates whose skeleton has NOT been used recently.
    fresh_pool = []
    for category, templates in NEWS_TEMPLATES.items():
        for template in templates:
            sample = _normalize_template(template.format(
                system="SYS", faction="FAC", pct="N", status="stable"))
            if sample not in recent_templates:
                fresh_pool.append((category, template))

    articles = []
    for _ in range(random.randint(1, 3)):
        if not fresh_pool:
            break  # every template used within window — nothing new to mint
        for _attempt in range(MAX_DEDUP_ATTEMPTS):
            category, template = random.choice(fresh_pool)
            system = random.choice(systems)["system_name"] if systems else "Unknown"
            faction = random.choice(factions)["name"] if factions else "Unknown"
            headline = template.format(system=system, faction=faction, pct=str(random.randint(5, 50)), status=random.choice(["stable","improving","declining"]))
            if headline not in existing:
                break
            headline = None
        if headline is None:
            continue  # all candidates exhausted — skip, don't duplicate
        existing.add(headline)
        recent_templates.add(_normalize_template(headline))
        # drop the used template from the fresh pool so next round picks something new
        fresh_pool = [(c, t) for (c, t) in fresh_pool if t != template]
        tick = await Database.fetchval("SELECT COALESCE(MAX(tick_number),0)+1 FROM maya_rp.news_articles WHERE session_id=$1", session_id) or 1
        await Database.execute("INSERT INTO maya_rp.news_articles (session_id, tick_number, headline, category, read, game_day) VALUES ($1,$2,$3,$4,false,$5)", session_id, tick, headline, category, gd)
        articles.append({"headline": headline, "category": category, "game_day": gd})
    # sentiment hook (2026-08-14): each headline shifts a random system's
    # sentiment/approval a notch — the news actually moves public opinion.
    try:
        if random.random() < 0.5:
            terr = await Database.fetchrow(
                "SELECT id FROM maya_rp.territory WHERE session_id=$1 AND "
                "controlling_faction='Setia Empire' ORDER BY RANDOM() LIMIT 1", session_id)
            if terr:
                delta = 2 if category in GOOD_NEWS_CATEGORIES else -1
                await Database.execute(
                    "INSERT INTO maya_rp.population_sentiment "
                    "(session_id, territory_id, faction_name, sentiment, approval, fear, trust, "
                    "bias, last_shift, last_shift_reason) "
                    "VALUES ($1,$2,'Setia Empire',$3,$4,0,0,0,0,$5) "
                    "ON CONFLICT (session_id, territory_id) DO UPDATE SET "
                    "sentiment=GREATEST(-100,LEAST(100,population_sentiment.sentiment+$3)), "
                    "approval=GREATEST(-100,LEAST(100,population_sentiment.approval+$4)), "
                    "last_shift=0, last_shift_reason=$5, updated_at=NOW()",
                    session_id, terr["id"], delta, delta, f"news: {category}")
    except Exception as e:  # noqa: BLE001 - reported below
        error("news", f"generate: {e}")
    return articles


async def _fresh_unread(session_id: int, cutoff: int, limit: int) -> list:
    """The fresh, unread articles for one campaign, newest first.

    One definition: `roll_news` re-ran this identical SELECT after each top-up
    round, so a change to the freshness rule had two places to land.
    """
    return await Database.fetch(
        "SELECT id, headline, category, importance, game_day FROM maya_rp.news_articles "
        "WHERE session_id=$1 AND read = false AND (game_day IS NULL OR game_day >= $2) "
        "ORDER BY game_day DESC NULLS LAST, id DESC LIMIT $3",
        session_id, cutoff, limit,
    )


async def roll_news(session_id: int | None = None, limit: int = 5, top_up: bool = True) -> list[dict]:
    """Fetch fresh unread news (a 'news roll'). Stale articles (older than
    MAX_NEWS_AGE_DAYS) are retired as read — they never return. Fresh ones
    are marked read so they won't reappear on a later roll either.

    top_up=True: if the pool of fresh unread news is thinner than `limit`,
    generate new articles on the spot so there is always news to serve.
    """
    if session_id is None: session_id = Config.SESSION_ID
    if limit < 0:
        raise ValueError(f"limit cannot be negative, got {limit}")
    gd = await _game_day(session_id)
    cutoff = gd - MAX_NEWS_AGE_DAYS
    # Retire anything unread that is older than the freshness window.
    await Database.execute(
        "UPDATE maya_rp.news_articles SET read = true "
        "WHERE session_id=$1 AND read = false AND game_day IS NOT NULL AND game_day < $2",
        session_id, cutoff,
    )
    rows = await _fresh_unread(session_id, cutoff, limit)
    if top_up and len(rows) < limit:
        # Pool is running dry — mint fresh articles so news is always available.
        for _ in range(3):  # up to 3 mint rounds per roll
            if len(rows) >= limit:
                break
            await generate(session_id)
            rows = await _fresh_unread(session_id, cutoff, limit)
    if rows:
        ids = [r["id"] for r in rows]
        await Database.execute(
            "UPDATE maya_rp.news_articles SET read = true WHERE id = ANY($1::int[])", ids
        )
    return [{"headline": r["headline"], "category": r["category"], "importance": r["importance"], "game_day": r["game_day"]} for r in rows]


async def _retire(sql: str, *args) -> bool:
    """Run a retire UPDATE and report whether it matched a row.

    asyncpg returns the status tag ('UPDATE 1', 'UPDATE 0'), which is how a
    mark-read for an id that does not exist stops being a silent True.
    """
    tag = await Database.execute(sql, *args)
    return not (isinstance(tag, str) and tag.split()[-1:] == ["0"])


async def mark_read(session_id: int | None = None, article_id: int | None = None, headline: str | None = None) -> bool:
    """Mark one article as read — by id, or by headline match. Already-checked news stays retired.

    Scoped by session in both branches: `WHERE id=$1` alone retired another
    campaign's article. Returns whether it retired anything.
    """
    if session_id is None: session_id = Config.SESSION_ID
    if article_id is not None:
        return await _retire(
            "UPDATE maya_rp.news_articles SET read = true WHERE session_id=$1 AND id=$2",
            session_id, article_id)
    if headline is not None:
        return await _retire(
            "UPDATE maya_rp.news_articles SET read = true WHERE session_id=$1 AND headline=$2",
            session_id, headline)
    return False


async def run_tick(session_id: int = None) -> dict:
    if session_id is None: session_id = Config.SESSION_ID
    try:
        articles = await generate(session_id)
        info("news", f"Generated {len(articles)} articles")
        return {"articles": len(articles)}
    except Exception as e:
        error("news", f"tick error: {e}")
        return {"error": str(e)}
