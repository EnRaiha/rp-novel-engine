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

No database: every test drives a fake Database. Session ids are scratch ids, never a frozen campaign.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

import pytest

import modules.quest as quest


SID = 900 + os.getpid() % 100


class _Conn:
    """Records the statements one transaction sends, as the fake Database used to."""

    def __init__(self, fake):
        self.fake = fake

    async def fetchrow(self, sql, *args):
        return await self.fake.fetchrow(sql, *args)

    async def fetchval(self, sql, *args):
        return await self.fake.fetchval(sql, *args)

    async def execute(self, sql, *args):
        return await self.fake.execute(sql, *args)


class FakeDB:
    """`quest` is the stored row. The claim UPDATE returns it only while its status is 'active'."""

    def __init__(self, quest=None, fetchval=1, execute_tag="UPDATE 1"):
        self.quest = quest
        self.fetchval_value = fetchval
        self.execute_tag = execute_tag
        self.calls = []
        self.rolled_back = False

    async def fetchrow(self, sql, *args):
        flat = " ".join(sql.split())
        self.calls.append(("fetchrow", flat, args))
        if self.quest is None:
            return None
        if flat.startswith("UPDATE maya_rp.quests"):
            return self.quest if self.quest["status"] == "active" else None
        return {"status": self.quest["status"]}

    async def fetchval(self, sql, *args):
        self.calls.append(("fetchval", " ".join(sql.split()), args))
        return self.fetchval_value

    async def execute(self, sql, *args):
        self.calls.append(("execute", " ".join(sql.split()), args))
        return self.execute_tag

    @asynccontextmanager
    async def transaction(self):
        try:
            yield _Conn(self)
        except BaseException:
            self.rolled_back = True
            raise

    def sql(self, kind=None):
        return [c[1] for c in self.calls if kind is None or c[0] == kind]

    def args_for(self, needle, kind=None):
        return [c[2] for c in self.calls
                if needle in c[1] and (kind is None or c[0] == kind)]


def _install(monkeypatch, fake):
    for name in ("fetchrow", "fetchval", "execute", "transaction"):
        monkeypatch.setattr("modules.quest.Database." + name, getattr(fake, name))
    return fake


ACTIVE = {"id": 4, "status": "active", "reward_alloy": 2500, "reward_credit": 7000}


# ── 1. A quest pays once ────────────────────────────────────────────────

async def test_an_active_quest_pays_and_completes(monkeypatch):
    fake = _install(monkeypatch, FakeDB(quest=ACTIVE))

    out = await quest.complete(4, SID)

    assert out == {"completed": True, "alloys": 2500, "credits": 7000}
    paid = fake.args_for("alloys=alloys+$1", "execute")[0]
    assert paid == (2500, 7000, SID)
    done = fake.args_for("SET status='completed'", "fetchrow")[0]
    assert done == (4, SID)


@pytest.mark.parametrize("status", ["completed", "available", "accepted", "failed"])
async def test_a_quest_that_is_not_active_pays_nothing(monkeypatch, status):
    fake = _install(monkeypatch, FakeDB(quest=dict(ACTIVE, status=status)))

    out = await quest.complete(4, SID)

    assert "not active" in out["error"], out
    assert not fake.args_for("alloys=alloys+$1", "execute"), "a second payout went out"


async def test_a_missing_quest_is_answered(monkeypatch):
    fake = _install(monkeypatch, FakeDB(quest=None))

    assert await quest.complete(999, SID) == {"error": "Quest not found"}
    assert not fake.sql("execute")


# ── 2. The payout has to land ───────────────────────────────────────────

async def test_a_session_without_a_treasury_is_not_told_it_was_paid(monkeypatch):
    seen = []
    monkeypatch.setattr("modules.quest.info", lambda mod, msg: seen.append(msg))
    fake = _install(monkeypatch, FakeDB(quest=ACTIVE, execute_tag="UPDATE 0"))

    out = await quest.complete(4, SID)

    assert "No treasury row" in out["error"], out
    assert fake.rolled_back, "the claim stayed committed with no payout"
    assert any("NOT paid" in m for m in seen), seen


# ── Contract the module claims ──────────────────────────────────────────

async def test_contract_generation_writes_the_session_and_the_rewards(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchval=77))

    out = await quest.generate(SID)

    assert out["id"] == 77
    assert out["type"] in quest.QUEST_TYPES
    insert = fake.args_for("INSERT INTO maya_rp.quests", "fetchval")[0]
    assert insert[0] == SID and insert[2] == out["type"]
    assert insert[4] == out["rewards"]["alloys"] and insert[5] == out["rewards"]["credits"]


def test_contract_every_quest_type_is_named():
    assert len(quest.QUEST_TYPES) == len(set(quest.QUEST_TYPES))
    assert "combat" in quest.QUEST_TYPES and "trade" in quest.QUEST_TYPES


async def test_contract_run_tick_is_a_stub():
    assert await quest.run_tick(SID) == {"status": "quest_ready"}
