"""Module review tests for modules/memories.py.

Defects covered:

1. `recall` built its LIKE patterns straight from the context words, so `%` and
   `_` in a word became wildcards: a context containing "50%" matched far more
   than it should, and a lone "%" matched every memory the character owns.
2. `context_text=None` raised AttributeError on `.lower()`.
3. `run_tick` returned whatever `Database.execute` gave it, which is the status
   tag: the key `memories_expired` held the string "UPDATE 3" where a count
   belongs.
4. `consolidate_memories` DELETES the originals it rolls up, and a negative
   `age_days` moved the cutoff into the future, so the "older than N days"
   window matched every memory the character owned and consolidated the lot.
   `min_count` had no floor either.
5. The recall counter update matched on id alone, and the tick logged its crash
   at info level.

Checked and found correct: every read and write carries session_id; the expiry
window is compared against the session's own game day; the roll-up inserts the
summary and deletes the originals inside one transaction; and the summarizer
falls back to an extractive gist when the local model is unavailable.

No database: every test drives a fake Database.
"""
from __future__ import annotations

import pytest

import modules.memories as memories


@pytest.fixture(autouse=True)
def _writable(monkeypatch):
    """The real frozen list must not decide these tests: they name session 3 or 5."""
    monkeypatch.setattr("core.session.is_frozen", lambda sid: False)


class FakeDB:
    def __init__(self, fetch=None, fetchrow=None, fetchval=100, execute_tag="UPDATE 3"):
        self.fetch_rows = fetch if fetch is not None else []
        self.fetchrow_value = fetchrow
        self.fetchval_value = fetchval
        self.execute_tag = execute_tag
        self.calls = []

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", " ".join(sql.split()), args))
        return self.fetch_rows

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", " ".join(sql.split()), args))
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
        monkeypatch.setattr("modules.memories.Database." + name, getattr(fake, name))
    return fake


# ── 1. Context words are not wildcards ───────────────────────────────────

async def test_like_metacharacters_in_a_context_word_are_escaped(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[]))

    await memories.recall(7, "guard the 50% vault_door", 5)

    patterns = fake.args_for("character_memories", "fetch")[-1][3]
    assert "%50\\%%" in patterns, patterns
    assert "%vault\\_door%" in patterns, patterns


def test_a_lone_percent_is_a_literal_word():
    assert memories._like_escape("%") == "\\%"
    assert memories._like_escape("a_b") == "a\\_b"
    assert memories._like_escape("plain") == "plain"


async def test_a_missing_context_does_not_crash(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[]))

    assert await memories.recall(7, None, 5) == []
    patterns = fake.args_for("character_memories", "fetch")[-1][3]
    assert patterns == ["%"]


async def test_recall_counts_the_hit_on_the_session(monkeypatch):
    rows = [{"id": 11, "memory_type": "promise", "content": "the vault", "emotional_weight": 9,
             "recalled_count": 0, "created_at_game_day": 90}]
    fake = _install(monkeypatch, FakeDB(fetch=rows, fetchval=100))

    out = await memories.recall(7, "vault", 5)

    assert out == rows
    counted = fake.args_for("SET recalled_count", "execute")[0]
    assert counted == (100, 11, 5)
    sql = [s for s in fake.sql("execute") if "recalled_count" in s][0]
    assert "session_id=$3" in sql


async def test_the_recall_read_is_session_scoped_and_ordered(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[], fetchval=100))

    await memories.recall(7, "vault", 5)

    sql = fake.sql("fetch")[-1]
    assert "character_id=$1 AND session_id=$2" in sql
    assert "expires_at_game_day IS NULL OR expires_at_game_day > $3" in sql
    assert "ORDER BY emotional_weight DESC, recalled_count ASC LIMIT 5" in sql


# ── 3. The tick reports a count ──────────────────────────────────────────

async def test_the_tick_reports_a_number_not_a_status_tag(monkeypatch):
    _install(monkeypatch, FakeDB(fetchval=100, execute_tag="UPDATE 3"))

    out = await memories.run_tick(5)

    assert out == {"memories_expired": 3}


async def test_a_tick_that_expired_nothing_reports_zero(monkeypatch):
    _install(monkeypatch, FakeDB(fetchval=100, execute_tag="UPDATE 0"))

    assert await memories.run_tick(5) == {"memories_expired": 0}


async def test_the_tick_reports_a_crash_as_an_error(monkeypatch):
    seen = []
    monkeypatch.setattr("modules.memories.error", lambda mod, msg: seen.append(msg))

    async def boom(*_a, **_k):
        raise RuntimeError("memory rot")

    _install(monkeypatch, FakeDB())
    monkeypatch.setattr("modules.memories.Database.fetchval", boom)

    out = await memories.run_tick(5)

    assert "memory rot" in out["error"]
    assert any("memory rot" in m for m in seen), seen


# ── 4. The destructive window is validated ───────────────────────────────

@pytest.mark.parametrize("kwargs,match", [
    ({"age_days": -1}, "age_days cannot be negative"),
    ({"age_days": -14}, "age_days cannot be negative"),
    ({"min_count": 0}, "min_count must be at least 1"),
    ({"min_count": -5}, "min_count must be at least 1"),
])
async def test_consolidation_refuses_a_window_that_would_take_everything(monkeypatch, kwargs, match):
    fake = _install(monkeypatch, FakeDB())

    with pytest.raises(ValueError, match=match):
        await memories.consolidate_memories(5, **kwargs)

    assert not fake.calls, "a refused window still queried"


async def test_consolidation_rolls_up_only_above_the_count(monkeypatch):
    rows = [{"id": i, "character_id": 7, "content": f"minor thing {i}"} for i in range(3)]
    fake = _install(monkeypatch, FakeDB(fetch=rows, fetchval=100))

    out = await memories.consolidate_memories(5, min_count=10)

    assert out["consolidated"] == 0 and out["archived"] == 0
    assert out["characters"] == 1
    assert not fake.sql("execute")


# ── Contract the module claims ───────────────────────────────────────────

async def test_contract_storing_a_memory_writes_the_session_and_the_day(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchval=2244))

    await memories.store(7, "promise", "I will return for the vault.", ["vault"], 9, None, None, 5)

    written = fake.args_for("INSERT INTO maya_rp.character_memories", "execute")[0]
    assert written[0] == 5 and written[1] == 7 and written[2] == "promise"
    assert written[5] == 2244 and written[6] == ["vault"] and written[7] == 9


async def test_contract_the_inner_world_counts_by_type_and_flags_high_impact(monkeypatch):
    rows = [{"memory_type": "promise", "content": "the vault", "emotional_weight": 9},
            {"memory_type": "promise", "content": "the gate", "emotional_weight": 3},
            {"memory_type": "trauma", "content": "the fire", "emotional_weight": 10}]
    fake = _install(monkeypatch, FakeDB(fetch=rows))

    out = await memories.get_inner_world(7, 5)

    assert out["total_memories"] == 3
    assert out["memories_by_type"] == {"promise": 2, "trauma": 1}
    assert out["promises"] == 2 and out["traumas"] == 1
    assert [h["content"] for h in out["high_impact"]] == ["the vault", "the fire"]
    assert fake.args_for("character_memories", "fetch")[0] == (7, 5)


def test_contract_the_extractive_gist_keeps_six_memories_at_most():
    contents = [f"Thing {i}. More detail follows." for i in range(9)]

    gist = memories._extractive_gist(contents)

    assert gist.count("Thing") == 6
    assert gist.endswith(".")
