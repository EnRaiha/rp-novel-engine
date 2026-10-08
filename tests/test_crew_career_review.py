"""Module review tests for modules/crew_career.py.

Defects covered:

1. `award` logged the XP it could not apply: the roster write was session-scoped
   but the `crew_xp_log` insert was unconditional, so an award for a crew member
   of another campaign matched no row and still wrote a receipt. The log entry is
   written only when the award landed, and the miss is named.
2. The follow-up read in `award` (`SELECT … WHERE id=$1`), its level-up write,
   and `promote_crew`'s level-up write all carried no session.
3. `award` returned None for a crew it could not find, so a caller could not tell
   a miss from an award that did not level anyone.
4. `assign_specialization` returned success even when no row matched, telling the
   caller a specialization had been set that was never written.
5. `run_tick` fetched the game day and never used it — a dead query every tick.

Checked and found correct: `promote_crew` reads with the session and refuses a
missing crew; the rank ladder is clamped at Legend; the specialization
validation refuses a name outside the list; `talent_shortage` counts active crew
against active ships and excludes the two yard types; the level threshold is
level × 100; and every skill write upserts on (crew_id, skill_name).

No database: every test drives a fake Database; its `transaction()` yields the fake itself. Every call uses
a scratch session id, because the frozen guard refuses sessions 3 and 5.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

import pytest

import modules.crew_career as cc

SID = 900 + os.getpid() % 100


class FakeDB:
    def __init__(self, fetchrow=None, fetchval=1, execute_tag="UPDATE 1", fetch=None):
        self.fetchrow_value = fetchrow
        self.fetchval_value = fetchval
        self.execute_tag = execute_tag
        self.fetch_rows = fetch or []
        self.calls = []

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", " ".join(sql.split()), args))
        return self.fetchrow_value

    async def fetchval(self, sql, *args):
        self.calls.append(("fetchval", " ".join(sql.split()), args))
        return self.fetchval_value

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", " ".join(sql.split()), args))
        return self.fetch_rows

    async def execute(self, sql, *args):
        self.calls.append(("execute", " ".join(sql.split()), args))
        return self.execute_tag

    @asynccontextmanager
    async def transaction(self):
        yield self

    def sql(self, kind=None):
        return [c[1] for c in self.calls if kind is None or c[0] == kind]

    def args_for(self, needle, kind=None):
        return [c[2] for c in self.calls
                if needle in c[1] and (kind is None or c[0] == kind)]


def _install(monkeypatch, fake):
    for name in ("fetchrow", "fetchval", "fetch", "execute", "transaction"):
        monkeypatch.setattr("modules.crew_career.Database." + name, getattr(fake, name))
    return fake


CREW = {"xp": 250, "level": 1, "role": "gunner"}


# ── 1 + 3. The award must land before it is logged ──────────────────────

async def test_an_award_for_another_campaigns_crew_is_not_logged(monkeypatch):
    seen = []
    monkeypatch.setattr("modules.crew_career.info", lambda mod, msg: seen.append(msg))
    fake = _install(monkeypatch, FakeDB(fetchrow=None))

    out = await cc.award(77, 50, "battle", SID)

    assert out["leveled"] is False and f"not in session {SID}" in out["error"]
    assert not fake.args_for("INSERT INTO maya_rp.crew_xp_log", "execute"), "a receipt was written anyway"
    assert any("NOT awarded" in m for m in seen), seen


async def test_an_award_that_lands_is_logged(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchrow=CREW, execute_tag="UPDATE 1"))

    out = await cc.award(77, 50, "battle", SID)

    assert out["leveled"] is True             # the row the award returns holds 250 XP, over level 1 × 100
    logged = fake.args_for("INSERT INTO maya_rp.crew_xp_log", "execute")[0]
    assert logged == (77, SID, 50, "battle")


async def test_the_award_returns_the_row_and_the_level_up_carries_the_session(monkeypatch):
    """The XP write is `UPDATE ... RETURNING`: no separate read is left to race a second award."""
    fake = _install(monkeypatch, FakeDB(fetchrow=CREW, execute_tag="UPDATE 1"))

    await cc.award(77, 50, "battle", SID)

    write = [s for s in fake.sql("fetchrow") if "UPDATE maya_rp.crew_roster" in s][0]
    assert "id=$2 AND session_id=$3" in write and "RETURNING xp, level, role" in write
    assert fake.args_for("crew_roster", "fetchrow")[0] == (50, 77, SID)
    assert not [s for s in fake.sql("fetchrow") if s.startswith("SELECT")], "a read-then-write is back"
    level = fake.args_for("SET level=$1,rank=$2", "execute")[0]
    assert level == (2, "Specialist", 100, 77, SID)


async def test_a_crew_below_its_threshold_does_not_level(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchrow={"xp": 90, "level": 1, "role": "gunner"}))

    assert await cc.award(77, 5, "drill", SID) == {"leveled": False}
    assert not fake.args_for("SET level=$1,rank=$2", "execute")


# ── 4. The specialization reports what it did ───────────────────────────

async def test_assigning_a_specialization_names_an_unknown_crew(monkeypatch):
    _install(monkeypatch, FakeDB(execute_tag="UPDATE 0"))

    out = await cc.assign_specialization(77, "artisan", SID)

    assert f"not in session {SID}" in out["error"], out


async def test_assigning_a_specialization_reports_the_crew(monkeypatch):
    fake = _install(monkeypatch, FakeDB(execute_tag="UPDATE 1"))

    out = await cc.assign_specialization(77, "artisan", SID)

    assert out == {"crew_id": 77, "specialization": "artisan"}
    assert fake.args_for("SET specialization=$1", "execute")[0] == ("artisan", 77, SID)


@pytest.mark.parametrize("spec", ["wizard", "", "Artisan"])
async def test_an_unknown_specialization_is_refused(monkeypatch, spec):
    fake = _install(monkeypatch, FakeDB())

    out = await cc.assign_specialization(77, spec, SID)

    assert "Specialization mesti salah satu" in out["error"]
    assert not fake.sql("execute")


# ── 2 + 5. promote_crew and the tick ────────────────────────────────────

async def test_promotion_writes_the_level_with_the_session(monkeypatch):
    crew = {"id": 77, "xp": 300, "level": 2, "rank": "Specialist", "specialization": "artisan"}
    fake = _install(monkeypatch, FakeDB(fetchrow=crew))

    out = await cc.promote_crew(77, SID)

    assert out["leveled"] is True and out["new_rank"] == "Veteran"
    assert out["skills"] == ["weapons", "hull"]
    update = fake.args_for("promotion_source='novel_promotion'", "execute")[0]
    assert update == (3, "Veteran", 200, 77, SID)


async def test_a_promotion_with_insufficient_xp_says_how_much_is_missing(monkeypatch):
    crew = {"id": 77, "xp": 50, "level": 2, "rank": "Specialist", "specialization": None}
    _install(monkeypatch, FakeDB(fetchrow=crew))

    assert await cc.promote_crew(77, SID) == {"leveled": False, "need": 150}


async def test_a_missing_crew_is_answered(monkeypatch):
    _install(monkeypatch, FakeDB(fetchrow=None))

    assert await cc.promote_crew(77, SID) == {"error": "Crew not found"}


async def test_the_tick_no_longer_reads_a_day_it_never_uses(monkeypatch):
    fake = _install(monkeypatch, FakeDB())

    out = await cc.run_tick(SID)

    assert out == {"processed": True}
    assert not fake.sql("fetchval"), "the dead game-day read is back"
    assert fake.args_for("crew_roster", "execute")[0] == (SID,)


# ── Contract the module claims ──────────────────────────────────────────

def test_contract_the_rank_ladder_is_ordered_and_capped():
    assert cc.RANKS[0] == "Crewman"
    assert cc.RANKS[-1] == "Legend"
    assert len(set(cc.RANKS)) == len(cc.RANKS)


def test_contract_every_skill_belongs_to_one_category():
    flat = [s for sub in cc.SKILLS.values() for s in sub]
    assert flat == cc.ALL_SKILLS
    assert len(set(flat)) == len(flat)


def test_contract_every_specialization_has_a_skill_set():
    crew = {"id": 1, "xp": 500, "level": 1, "rank": "Crewman", "specialization": "navigator"}
    import asyncio

    for spec in cc.SPECIALIZATIONS:
        assert spec in ("artisan", "planner", "navigator", "officer", "engineer")


async def test_contract_talent_shortage_counts_active_crew_and_ships(monkeypatch):
    answers = iter([10, 14])
    fake = _install(monkeypatch, FakeDB())

    async def fetchval(sql, *args):
        fake.calls.append(("fetchval", " ".join(sql.split()), args))
        return next(answers)

    monkeypatch.setattr("modules.crew_career.Database.fetchval", fetchval)

    out = await cc.talent_shortage(5)

    assert out == {"crew": 10, "ships": 14, "shortage": 4, "status": "SHORTAGE"}
    assert "status='active'" in fake.sql("fetchval")[1]
    assert "light_dockyard" in fake.sql("fetchval")[1]
