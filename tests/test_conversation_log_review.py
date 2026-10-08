"""Module review tests for modules/conversation_log.py.

Findings:

1. `_kw(None)` raised AttributeError on `.lower()`, and `log(None)` would store a
   null topic. Both are refused or emptied by name now.
2. `log` has no caller anywhere in the repo, so the table stays empty and
   `check` can never report a duplicate. That is reported, not wired: the writer
   needs a turn-boundary caller outside this module. The live door is
   `kilo_bridge.py check_duplicate`, which only ever reaches `check`.

Checked and found correct: `keywords` is a text[] column, so asyncpg hands it
back as a list and the overlap comparison is not comparing a JSON string against
a set (that would have made the dedup dead, and the column type cleared it);
`check` filters by session and character; an unknown game day falls back to
`(gd or 0)` so the window arithmetic cannot crash.

No database: every test drives a fake Database.
"""
from __future__ import annotations

import os

import pytest

import modules.conversation_log as conv

#: Scratch session: `log` writes, and the frozen guard refuses sessions 3 and 5.
SID = 900 + os.getpid() % 100


class FakeDB:
    def __init__(self, fetch=None, fetchval=100):
        self.fetch_rows = fetch if fetch is not None else []
        self.fetchval_value = fetchval
        self.calls = []

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", " ".join(sql.split()), args))
        return self.fetch_rows

    async def fetchval(self, sql, *args):
        self.calls.append(("fetchval", " ".join(sql.split()), args))
        return self.fetchval_value

    async def execute(self, sql, *args):
        self.calls.append(("execute", " ".join(sql.split()), args))
        return "INSERT 0 1"

    def sql(self, kind=None):
        return [c[1] for c in self.calls if kind is None or c[0] == kind]

    def args_for(self, needle, kind=None):
        return [c[2] for c in self.calls
                if needle in c[1] and (kind is None or c[0] == kind)]


def _install(monkeypatch, fake):
    for name in ("fetch", "fetchval", "execute"):
        monkeypatch.setattr("modules.conversation_log.Database." + name, getattr(fake, name))
    return fake


# ── 1. Keywords and topics ───────────────────────────────────────────────

def test_keywords_drop_stopwords_and_short_words():
    assert conv._kw("The captain spoke about the wreck") == ["captain", "spoke", "wreck"]


@pytest.mark.parametrize("topic", [None, "", "   ", 42])
def test_keywords_of_a_missing_topic_are_empty_not_a_crash(topic):
    assert conv._kw(topic) == []


async def test_log_stores_the_keywords_for_the_session(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchval=2244))

    await conv.log(11, "the brass key and the vault", "tense", "guarded", SID)

    insert = fake.args_for("INSERT INTO maya_rp.conversation_log", "execute")[0]
    assert insert[0] == SID and insert[1] == 11
    assert insert[3] == ["brass", "vault"]
    assert insert[6] == 2244


@pytest.mark.parametrize("topic", [None, "", "   "])
async def test_log_refuses_a_missing_topic(monkeypatch, topic):
    fake = _install(monkeypatch, FakeDB())

    with pytest.raises(ValueError, match="topic must be a non-empty string"):
        await conv.log(11, topic, session_id=SID)

    assert not fake.sql("execute")


# ── 2. The duplicate check ───────────────────────────────────────────────

def _row(topic, keywords, day=100, outcome="tense", beat="guarded"):
    return {"topic": topic, "keywords": keywords, "game_day": day,
            "outcome": outcome, "emotional_beat": beat}


async def test_a_repeated_topic_is_reported_with_its_previous_outcome(monkeypatch):
    rows = [_row("the brass key and the vault", ["brass", "vault", "key"])]
    fake = _install(monkeypatch, FakeDB(fetch=rows, fetchval=120))

    # "key" is three characters and dropped by the tokenizer, so this proposal
    # shares exactly two keywords with the row: brass and vault.
    out = await conv.check(11, "ask about the brass vault key", 5)

    assert out["duplicate"] is True
    assert out["previous"] == "the brass key and the vault"
    assert out["previous_outcome"] == "tense"
    assert out["games_ago"] == 20
    assert "brass key" in out["suggestion"]
    assert fake.args_for("conversation_log", "fetch")[0] == (5, 11, 100)


async def test_a_new_direction_is_not_reported(monkeypatch):
    rows = [_row("the brass key and the vault", ["brass", "vault", "key"])]
    _install(monkeypatch, FakeDB(fetch=rows, fetchval=120))

    assert await conv.check(11, "inspect the engine room", 5) is None


async def test_a_topic_with_no_keywords_is_not_a_duplicate(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[_row("x", ["brass"])]))

    assert await conv.check(11, None, 5) is None
    assert not fake.sql("fetch"), "no query needed when there is nothing to compare"


async def test_one_shared_keyword_out_of_four_is_not_enough(monkeypatch):
    rows = [_row("the brass key and the vault", ["brass", "vault", "key", "iron"])]
    _install(monkeypatch, FakeDB(fetch=rows, fetchval=120))

    # one overlap against a four-keyword proposal: below max(2, 4*0.5)
    assert await conv.check(11, "the brass engine room", 5) is None


# ── Contract the module claims ───────────────────────────────────────────

async def test_contract_the_window_cannot_crash_on_an_unknown_game_day(monkeypatch):
    _install(monkeypatch, FakeDB(fetch=[], fetchval=None))

    assert await conv.check(11, "ask about the brass key", 5) is None


async def test_contract_the_log_is_read_back_through_a_session_filter(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[], fetchval=100))

    await conv.check(11, "ask about the brass key", 5)

    sql = fake.sql("fetch")[0]
    assert "session_id=$1" in sql and "character_id=$2" in sql
