"""Module review tests for modules/quest.py.

Defects covered:

1. `complete` did not require `status='active'`, so completing the same quest
   twice paid the reward twice: the read matched any status and the payout ran
   before anything looked at it. An already-completed quest is refused now.
2. The payout had no check that the credit landed, so a session with no
   `resources` row (session 5 has none) was told it had been paid. The quest is
   left open when the treasury is missing, rather than marked completed for
   nothing.
3. The status write matched on id alone.

Checked and found correct: generation writes the session and the rewards into the
row it returns; the reward columns are the singular spellings the table actually
has; the reward read is session-scoped; and the tick is a stub that only reports
ready.

No database: every test drives a fake Database.
"""
from __future__ import annotations

import pytest

import modules.quest as quest


class FakeDB:
    def __init__(self, fetchrow=None, fetchval=1, execute_tag="UPDATE 1"):
        self.fetchrow_value = fetchrow
        self.fetchval_value = fetchval
        self.execute_tag = execute_tag
        self.calls = []

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
    for name in ("fetchrow", "fetchval", "execute"):
        monkeypatch.setattr("modules.quest.Database." + name, getattr(fake, name))
    return fake


ACTIVE = {"id": 4, "status": "active", "reward_alloy": 2500, "reward_credit": 7000}


# ── 1. A quest pays once ────────────────────────────────────────────────

async def test_an_active_quest_pays_and_completes(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchrow=ACTIVE))

    out = await quest.complete(4, 5)

    assert out == {"completed": True, "alloys": 2500, "credits": 7000}
    paid = fake.args_for("alloys=alloys+$1", "execute")[0]
    assert paid == (2500, 7000, 5)
    done = fake.args_for("SET status='completed'", "execute")[0]
    assert done == (4, 5)


@pytest.mark.parametrize("status", ["completed", "available", "accepted", "failed"])
async def test_a_quest_that_is_not_active_pays_nothing(monkeypatch, status):
    fake = _install(monkeypatch, FakeDB(fetchrow=dict(ACTIVE, status=status)))

    out = await quest.complete(4, 5)

    assert "not active" in out["error"], out
    assert not fake.args_for("alloys=alloys+$1", "execute"), "a second payout went out"
    assert not fake.args_for("SET status='completed'", "execute")


async def test_a_missing_quest_is_answered(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchrow=None))

    assert await quest.complete(999, 5) == {"error": "Quest not found"}
    assert not fake.sql("execute")


# ── 2. The payout has to land ───────────────────────────────────────────

async def test_a_session_without_a_treasury_is_not_told_it_was_paid(monkeypatch):
    seen = []
    monkeypatch.setattr("modules.quest.info", lambda mod, msg: seen.append(msg))
    fake = _install(monkeypatch, FakeDB(fetchrow=ACTIVE, execute_tag="UPDATE 0"))

    out = await quest.complete(4, 5)

    assert "No treasury row" in out["error"], out
    assert not fake.args_for("SET status='completed'", "execute"), "marked done with no payout"
    assert any("NOT paid" in m for m in seen), seen


# ── Contract the module claims ──────────────────────────────────────────

async def test_contract_generation_writes_the_session_and_the_rewards(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchval=77))

    out = await quest.generate(5)

    assert out["id"] == 77
    assert out["type"] in quest.QUEST_TYPES
    insert = fake.args_for("INSERT INTO maya_rp.quests", "fetchval")[0]
    assert insert[0] == 5 and insert[2] == out["type"]
    assert insert[4] == out["rewards"]["alloys"] and insert[5] == out["rewards"]["credits"]


def test_contract_every_quest_type_is_named():
    assert len(quest.QUEST_TYPES) == len(set(quest.QUEST_TYPES))
    assert "combat" in quest.QUEST_TYPES and "trade" in quest.QUEST_TYPES


async def test_contract_run_tick_is_a_stub():
    assert await quest.run_tick(5) == {"status": "quest_ready"}
