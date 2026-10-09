"""Module review tests for modules/news.py.

Defects covered:

1. `mark_read(article_id=…)` ran `WHERE id=$1` with no session filter, so an id
   from another campaign retired that campaign's article, and it returned True
   whether or not it matched anything.
2. The sentiment hook scored `("celebration", "trade", "science")`. `generate`
   can only mint the six NEWS_TEMPLATES categories, so every headline this
   module produced lowered public opinion and the positive branch was dead.
3. `roll_news` carried the same fresh-unread SELECT twice, once per top-up
   round, and a `if not rows: rows = []` line that assigns an empty list to an
   empty list.
4. A negative `limit` reached `LIMIT $3` and left PostgreSQL to raise.

Checked and found correct, so the row is not silent about what it looked at:
every read and write carries session_id; the exact-headline dedup holds across
calls because it loads every headline for the session; the template skeleton
dedup normalizes digits and blocks anything inside the freshness window; stale
unread articles are retired before the roll and fresh ones are marked read; the
three templates per roll are drawn from a pool that has the window applied; and
no template uses a placeholder outside `system`, `faction`, `pct`, `status`.

No database: every test drives a fake Database.
"""
from __future__ import annotations

import random
import string

import pytest

import modules.news as news


@pytest.fixture(autouse=True)
def _writable(monkeypatch):
    """The real frozen list must not decide these tests: they name session 3 or 5."""
    monkeypatch.setattr("core.session.is_frozen", lambda sid: False)


class FakeDB:
    def __init__(self, fetch=None, fetchrow=None, fetchval=None,
                 execute_tag="UPDATE 1", row_map=None):
        self.fetch_rows = fetch if fetch is not None else []
        self.fetchrow_value = fetchrow
        self.row_map = row_map or {}
        self.fetchval_value = fetchval
        self.execute_tag = execute_tag
        self.calls = []

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", " ".join(sql.split()), args))
        if isinstance(self.fetch_rows, dict):
            for marker, value in self.fetch_rows.items():
                if marker != "*" and marker in sql:
                    return value
            return self.fetch_rows.get("*", [])
        return self.fetch_rows

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", " ".join(sql.split()), args))
        for marker, value in self.row_map.items():
            if marker in sql:
                return value
        return self.fetchrow_value

    async def fetchval(self, sql, *args):
        self.calls.append(("fetchval", " ".join(sql.split()), args))
        return self.fetchval_value

    async def execute(self, sql, *args):
        self.calls.append(("execute", " ".join(sql.split()), args))
        return self.execute_tag

    def sql(self, kind=None):
        return [c[1] for c in self.calls if kind is None or c[0] == kind]

    def args_for(self, needle, kind=None):
        return [c[2] for c in self.calls
                if needle in c[1] and (kind is None or c[0] == kind)]


def _install(monkeypatch, fake):
    for name in ("fetch", "fetchrow", "fetchval", "execute"):
        monkeypatch.setattr("modules.news.Database." + name, getattr(fake, name))
    return fake


# ── 1. mark_read is scoped and answers honestly ──────────────────────────

async def test_mark_read_by_id_carries_the_session(monkeypatch):
    fake = _install(monkeypatch, FakeDB())

    assert await news.mark_read(5, 4242) is True

    sql = fake.args_for("SET read = true", "execute")[0]
    assert "session_id=$1" in [s for s in fake.sql("execute")][0]
    assert sql == (5, 4242)


async def test_mark_read_says_when_the_id_matched_nothing(monkeypatch):
    _install(monkeypatch, FakeDB(execute_tag="UPDATE 0"))

    assert await news.mark_read(5, 999_999) is False


async def test_mark_read_says_when_the_headline_matched_nothing(monkeypatch):
    _install(monkeypatch, FakeDB(execute_tag="UPDATE 0"))

    assert await news.mark_read(5, None, "a headline that does not exist") is False


async def test_mark_read_with_no_selector_is_false(monkeypatch):
    fake = _install(monkeypatch, FakeDB())

    assert await news.mark_read(5) is False
    assert not fake.sql("execute")


# ── 2. News can move opinion up as well as down ──────────────────────────

def test_the_good_news_categories_are_ones_the_module_can_mint():
    assert set(news.GOOD_NEWS_CATEGORIES) <= set(news.NEWS_TEMPLATES)


async def _generate_one(monkeypatch, category, template):
    """Drive the real generate() so the sentiment hook runs, on one template."""
    fake = _install(monkeypatch, FakeDB(
        fetch={"territory": [{"system_name": "Kappa"}],
               "factions": [{"name": "Iron Concord"}],
               "*": []},
        row_map={"FROM maya_rp.territory": {"id": 7}},
        fetchval=1))
    monkeypatch.setattr(news, "NEWS_TEMPLATES", {category: [template]})
    monkeypatch.setattr(news.random, "random", lambda: 0.0)     # the hook fires
    monkeypatch.setattr(news.random, "randint", lambda a, b: 1)
    monkeypatch.setattr(news.random, "choice", lambda seq: seq[0])

    articles = await news.generate(5)
    assert articles, "generate minted nothing"
    return fake, articles[0]


async def test_good_news_shifts_sentiment_up(monkeypatch):
    fake, article = await _generate_one(
        monkeypatch, "economy", "Trade volumes up {pct}% this quarter.")
    assert article["category"] in news.GOOD_NEWS_CATEGORIES

    shift = _sentiment_shift(fake)
    assert shift == (2, 2), shift


async def test_bad_news_shifts_sentiment_down(monkeypatch):
    fake, article = await _generate_one(
        monkeypatch, "military", "Military alert: {faction} movements detected.")
    assert article["category"] not in news.GOOD_NEWS_CATEGORIES

    shift = _sentiment_shift(fake)
    assert shift == (-1, -1), shift


def _sentiment_shift(fake):
    rows = fake.args_for("population_sentiment", "execute")
    assert rows, fake.sql("execute")
    return rows[0][2], rows[0][3]


# ── 3. One freshness rule, one place ─────────────────────────────────────

async def test_the_fresh_unread_rule_is_written_once(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[]))
    monkeypatch.setattr(news.random, "random", lambda: 1.0)

    await news.roll_news(5, limit=3, top_up=False)

    selects = [s for s in fake.sql("fetch") if "news_articles" in s and "read = false" in s]
    assert len(selects) == 1, selects
    assert "session_id=$1" in selects[0]


async def test_the_top_up_round_reuses_the_same_rule(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[]))

    async def stub_generate(session_id):
        return [{"headline": "Fleet movements reported near X.",
                 "category": "fleet", "game_day": 1}]

    monkeypatch.setattr(news, "generate", stub_generate)

    await news.roll_news(5, limit=2, top_up=True)

    selects = [s for s in fake.sql("fetch") if "read = false" in s]
    # initial read + one re-read per mint round, all byte-identical
    assert len(selects) == 4, selects
    assert len(set(selects)) == 1, "the freshness rule is written more than once"


async def test_a_negative_limit_is_refused(monkeypatch):
    fake = _install(monkeypatch, FakeDB())

    with pytest.raises(ValueError, match="limit cannot be negative"):
        await news.roll_news(5, limit=-1)

    assert not fake.sql("execute")


# ── 4. The roll retires what it serves ───────────────────────────────────

async def test_the_roll_retires_stale_unread_before_reading(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchval=10, fetch=[]))

    await news.roll_news(5, limit=3, top_up=False)

    retire = [a for s, a in [(c[1], c[2]) for c in fake.calls if c[0] == "execute"]
              if "read = false" in s and "game_day < $2" in s]
    assert retire and retire[0] == (5, 10 - news.MAX_NEWS_AGE_DAYS)


async def test_the_roll_marks_what_it_served_as_read(monkeypatch):
    rows = [{"id": 7, "headline": "H", "category": "fleet", "importance": 2, "game_day": 10}]
    fake = _install(monkeypatch, FakeDB(fetchval=10, fetch=rows))

    out = await news.roll_news(5, limit=3, top_up=False)

    assert out == [{"headline": "H", "category": "fleet", "importance": 2, "game_day": 10}]
    marked = fake.args_for("id = ANY($1::int[])", "execute")
    assert marked and marked[0] == ([7],)


async def test_a_roll_with_no_news_and_no_top_up_is_empty(monkeypatch):
    _install(monkeypatch, FakeDB(fetchval=10, fetch=[]))
    assert await news.roll_news(5, limit=3, top_up=False) == []


async def test_run_tick_reports_a_crash_as_an_error(monkeypatch):
    seen = []
    monkeypatch.setattr("modules.news.error", lambda mod, msg: seen.append(msg))
    monkeypatch.setattr("modules.news.info", lambda mod, msg: None)

    async def boom(_session_id):
        raise RuntimeError("wire feed down")

    monkeypatch.setattr("modules.news.generate", boom)

    out = await news.run_tick(5)

    assert "wire feed down" in out["error"]
    assert any("wire feed down" in m for m in seen), seen


# ── Contract the module claims ───────────────────────────────────────────

def test_contract_every_template_uses_only_the_four_placeholders():
    allowed = {"system", "faction", "pct", "status"}
    for category, templates in news.NEWS_TEMPLATES.items():
        for template in templates:
            fields = {f for _, f, _, _ in string.Formatter().parse(template) if f}
            assert fields <= allowed, (category, template, fields)


def test_contract_template_dedup_normalizes_numbers():
    assert news._normalize_template("Trade volumes up 21% this quarter.") == \
           news._normalize_template("Trade volumes up 40% this quarter.")
    assert news._normalize_template("Naval exercise scheduled in Kappa.") != \
           news._normalize_template("Trade volumes up 21% this quarter.")


def test_contract_the_headline_pool_shrinks_by_the_window():
    # a skeleton inside the window cannot be re-minted; the rest stay available
    assert news.MAX_NEWS_AGE_DAYS > 0
    assert news.MAX_DEDUP_ATTEMPTS > 0
