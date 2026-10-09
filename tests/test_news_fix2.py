"""news fix 2: the sentiment hook upserts on the faction index and shifts only for a minted article.

Real database. Every write lands in a scratch session (900-999). `Config.SESSION_ID` points at the
scratch id too, so no default can reach session 3 or 5.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest_asyncio  # noqa: E402

import core.config  # noqa: E402
from core.db import Database  # noqa: E402
from modules import news  # noqa: E402

#: Children of `sessions` this file writes, removed before the session row (territory has a foreign key to it).
_TABLES = ("population_sentiment", "news_articles", "territory")

_ECONOMY = {"economy": ["Trade volumes up {pct}% this quarter.",
                        "Market index hits {pct}% of quarterly target."]}


async def _wipe(session_id):
    for table in _TABLES:
        await Database.execute(f"DELETE FROM maya_rp.{table} WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", session_id)


@pytest_asyncio.fixture
async def sid(scratch_session, monkeypatch):
    """A scratch session with one Setia-controlled territory."""
    await Database.init()
    await _wipe(scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status, game_day) "
        "VALUES ($1, 'news fix2 scratch', 'active', 10)", scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.territory (session_id, system_name, controlling_faction) "
        "VALUES ($1, 'Kappa', 'Setia Empire')", scratch_session)
    monkeypatch.setattr(core.config.Config, "SESSION_ID", scratch_session)
    try:
        yield scratch_session
    finally:
        await _wipe(scratch_session)
        await Database.close()


def _patch(monkeypatch, templates):
    """Make `generate` deterministic: the hook fires, one article per call, the first template wins."""
    monkeypatch.setattr(news.random, "random", lambda: 0.0)
    monkeypatch.setattr(news.random, "randint", lambda a, b: 1)
    monkeypatch.setattr(news.random, "choice", lambda seq: seq[0])
    monkeypatch.setattr(news, "NEWS_TEMPLATES", templates)


async def _sentiment(session_id):
    rows = await Database.fetch(
        "SELECT sentiment, approval, faction_name FROM maya_rp.population_sentiment WHERE session_id=$1",
        session_id)
    return [(r["sentiment"], r["approval"], r["faction_name"]) for r in rows]


async def test_generate_writes_a_sentiment_row_for_the_setia_territory(sid, monkeypatch):
    _patch(monkeypatch, _ECONOMY)
    articles = await news.generate(sid)
    assert len(articles) == 1, articles
    assert await _sentiment(sid) == [(2, 2, "Setia Empire")]


async def test_a_second_article_updates_the_same_row(sid, monkeypatch):
    _patch(monkeypatch, _ECONOMY)
    assert len(await news.generate(sid)) == 1
    assert len(await news.generate(sid)) == 1
    assert await _sentiment(sid) == [(4, 4, "Setia Empire")]


async def test_no_article_means_no_sentiment_shift(sid, monkeypatch):
    _patch(monkeypatch, _ECONOMY)
    await news.generate(sid)
    await news.generate(sid)
    assert await news.generate(sid) == []
    assert await _sentiment(sid) == [(4, 4, "Setia Empire")]


async def test_the_shift_uses_the_minted_articles_category(sid, monkeypatch):
    _patch(monkeypatch, {"military": ["Military alert: {faction} movements detected."]})
    articles = await news.generate(sid)
    assert [a["category"] for a in articles] == ["military"]
    assert await _sentiment(sid) == [(-1, -1, "Setia Empire")]
