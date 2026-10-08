"""Module review tests for modules/chekhov.py.

Defects covered:

1. `payoff` ran `WHERE id=$3` with no session filter, so a payoff could land on
   another campaign's element, and it returned nothing either way.
2. `introduce` accepted a negative `payoff_window`, which dates the deadline
   before the element was introduced so it is overdue on arrival.

Checked and reported rather than changed: `payoff` has no caller anywhere in
the repo. `introduce` is called from encounters and `get_prompt` from the master
briefing, so the tracker records and reads but never settles an element. Wiring
it needs a turn-boundary caller outside this module.

No database: every test drives a fake Database.
"""
from __future__ import annotations

import os

import pytest

import modules.chekhov as chekhov

#: Scratch campaign: sessions 3 and 5 are frozen, and the writers refuse them.
SID = 900 + os.getpid() % 100


class FakeDB:
    def __init__(self, fetch=None, fetchval=7, execute_tag="UPDATE 1"):
        self.fetch_rows = fetch if fetch is not None else []
        self.fetchval_value = fetchval
        self.execute_tag = execute_tag
        self.calls = []

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", " ".join(sql.split()), args))
        return self.fetch_rows

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
    for name in ("fetch", "fetchval", "execute"):
        monkeypatch.setattr("modules.chekhov.Database." + name, getattr(fake, name))
    return fake


# ── 1. The payoff write is scoped and reports ────────────────────────────

async def test_payoff_carries_the_session(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchval=40))

    assert await chekhov.payoff(3, "recovered", SID) is True

    sql = fake.sql("execute")[0]
    assert "id=$3 AND session_id=$4" in sql, sql
    assert fake.args_for("SET status='paid'", "execute")[0] == ("recovered", 40, 3, SID)


async def test_payoff_says_when_the_element_is_not_in_this_session(monkeypatch):
    seen = []
    monkeypatch.setattr("modules.chekhov.info", lambda mod, msg: seen.append(msg))
    _install(monkeypatch, FakeDB(execute_tag="UPDATE 0"))

    assert await chekhov.payoff(3, "recovered", SID) is False
    assert any(f"not in session {SID}" in m for m in seen), seen


# ── 2. introduce validates its window ────────────────────────────────────

async def test_introduce_dates_the_deadline_from_the_window(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchval=100))

    elem_id = await chekhov.introduce("artifact", "the brass key", "high", 15, SID)

    assert elem_id == 100
    insert = fake.args_for("INSERT INTO maya_rp.chekhov_elements", "fetchval")[0]
    assert insert[4] == 100 and insert[5] == 115        # introduced day, deadline


async def test_introduce_refuses_a_negative_window(monkeypatch):
    _install(monkeypatch, FakeDB())

    with pytest.raises(ValueError, match="payoff_window cannot be negative"):
        await chekhov.introduce("artifact", "the brass key", payoff_window=-3, session_id=SID)


# ── Contract the module claims ───────────────────────────────────────────

async def test_contract_overdue_is_unpaid_and_past_its_deadline(monkeypatch):
    rows = [{"id": 1, "element_type": "artifact", "description": "key",
             "importance": "high", "introduced_game_day": 10, "payoff_deadline": 20}]
    fake = _install(monkeypatch, FakeDB(fetch=rows, fetchval=40))

    out = await chekhov.get_overdue(SID)

    assert out == rows
    sql = fake.sql("fetch")[0]
    assert "status='unpaid'" in sql and "payoff_deadline<=$2" in sql
    assert fake.args_for("chekhov_elements", "fetch")[0] == (SID, 40)


async def test_contract_the_prompt_lists_at_most_five_and_marks_the_urgent(monkeypatch):
    rows = [{"id": i, "element_type": "artifact", "description": f"item {i}",
             "importance": "high" if i == 0 else "low",
             "introduced_game_day": 10, "payoff_deadline": 20} for i in range(7)]
    _install(monkeypatch, FakeDB(fetch=rows, fetchval=40))

    prompt = await chekhov.get_prompt(SID)

    assert prompt.startswith("[UNPAID NARRATIVE ELEMENTS]")
    assert len([line for line in prompt.splitlines() if line.strip().startswith(("⚠", "○"))]) == 5
    assert "⚠ artifact: item 0" in prompt
    assert "item 5" not in prompt


async def test_contract_an_empty_tracker_returns_no_prompt(monkeypatch):
    _install(monkeypatch, FakeDB(fetch=[], fetchval=40))

    assert await chekhov.get_prompt(SID) == ""


async def test_contract_the_tick_counts_what_is_overdue(monkeypatch):
    rows = [{"id": 1}, {"id": 2}]
    _install(monkeypatch, FakeDB(fetch=rows, fetchval=40))

    assert await chekhov.run_tick(SID) == {"overdue": 2}
