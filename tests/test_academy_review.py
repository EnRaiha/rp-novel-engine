"""Module review tests for modules/academy.py.

Defects covered:

1. `enroll_crew` took the crew id on trust. `enrolled_crew` carries no session
   of its own, so an unqualified id enrolled the OTHER campaign's crew member
   into this one's academy, spent this campaign's campus slot, and granted a
   certification against a roster row in session 3.
2. A second enrolment for the same crew and program was accepted: it held a
   campus slot for the whole program and relied on the certification upsert to
   hide the duplicate.
3. The graduation XP write to `crew_roster` matched on id alone.
4. `run_tick` logged its crash at info level.

Checked and found correct, so the row is not silent about what it looked at:
`academy_campuses` and `training_programs` carry no session_id — they are global
catalogues, so their unfiltered lookups are right; `certifications` does carry
one and the insert sets it; the enrolled query joins `crew_roster` on its
session; an enrolment whose program row has vanished is closed instead of
retrying every tick; and a campus at its slot ceiling refuses the enrolment.

No database: every test drives a fake Database.
"""
from __future__ import annotations

import pytest

import modules.academy as academy


class FakeDB:
    def __init__(self, fetch=None, fetchrow=None, fetchval=None, execute_tag="UPDATE 1"):
        self.fetch_rows = fetch if fetch is not None else []
        self.fetchrow_map = fetchrow or {}
        self.fetchval_value = fetchval
        self.execute_tag = execute_tag
        self.calls = []

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", " ".join(sql.split()), args))
        return self.fetch_rows

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", " ".join(sql.split()), args))
        for marker, value in self.fetchrow_map.items():
            if marker in sql:
                return value
        return None

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
        monkeypatch.setattr("modules.academy.Database." + name, getattr(fake, name))
    return fake


CAMPUS = {"id": 1, "name": "Mastika Academy", "student_slots_used": 2, "max_students": 10}
PROGRAM = {"id": 5, "name": "Navigation", "duration": 120}


# ── 1. The crew belongs to this session ─────────────────────────────────

async def test_enrol_refuses_another_campaigns_crew(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchrow={"crew_roster": None, "academy_campuses": CAMPUS}))

    out = await academy.enroll_crew(77, 5, 1, 5)

    assert "not found in session 5" in out["error"], out
    assert not fake.args_for("INSERT INTO maya_rp.enrolled_crew", "execute")
    sql = [s for s in fake.sql("fetchrow") if "crew_roster" in s][0]
    assert "session_id=$2" in sql
    assert fake.args_for("crew_roster", "fetchrow")[0] == (77, 5)


async def test_a_crew_in_this_session_enrols(monkeypatch):
    fake = _install(monkeypatch, FakeDB(
        fetchrow={"crew_roster": {"id": 77}, "academy_campuses": CAMPUS,
                  "training_programs": PROGRAM},
        fetchval=None))

    out = await academy.enroll_crew(77, 5, 1, 5)

    assert out == {"crew_id": 77, "program": "Navigation", "campus": "Mastika Academy"}
    inserted = fake.args_for("INSERT INTO maya_rp.enrolled_crew", "execute")[0]
    assert inserted == (77, 5, 1, 120)


async def test_a_full_campus_refuses_the_enrolment(monkeypatch):
    full = dict(CAMPUS, student_slots_used=10)
    fake = _install(monkeypatch, FakeDB(
        fetchrow={"crew_roster": {"id": 77}, "academy_campuses": full}))

    out = await academy.enroll_crew(77, 5, 1, 5)

    assert out["error"] == "Campus full"
    assert not fake.sql("execute")


# ── 2. No double enrolment ───────────────────────────────────────────────

async def test_a_second_enrolment_for_the_same_program_is_refused(monkeypatch):
    fake = _install(monkeypatch, FakeDB(
        fetchrow={"crew_roster": {"id": 77}, "academy_campuses": CAMPUS,
                  "training_programs": PROGRAM},
        fetchval=1))

    out = await academy.enroll_crew(77, 5, 1, 5)

    assert "already enrolled" in out["error"], out
    assert not fake.args_for("student_slots_used=COALESCE", "execute")


# ── 3. The graduation writes ─────────────────────────────────────────────

ENROLMENT = {"id": 900, "crew_id": 77, "program_id": 5, "campus_id": 1,
             "progress": 90, "target_progress": 100}


async def test_graduation_scopes_the_xp_write_to_the_session(monkeypatch):
    fake = _install(monkeypatch, FakeDB(
        fetch=[ENROLMENT],
        fetchrow={"training_programs": {"name": "Navigation", "field": "navigation",
                                        "skill_bonus": 3, "graduates_receive": "Navigator"}}))
    monkeypatch.setattr(academy.random, "randint", lambda a, b: b)

    out = await academy.run_tick(5)

    assert out == {"enrolled": 1, "graduated": 1}
    xp = fake.args_for("SET xp=COALESCE", "execute")[0]
    assert xp == (30, 77, 5)
    assert "session_id=$3" in [s for s in fake.sql("execute") if "SET xp=" in s][0]
    cert = fake.args_for("INSERT INTO maya_rp.certifications", "execute")[0]
    assert cert[0] == 5 and cert[2] == "Navigator"


async def test_graduation_closes_an_enrolment_whose_program_vanished(monkeypatch):
    seen = []
    monkeypatch.setattr("modules.academy.info", lambda mod, msg: seen.append(msg))
    fake = _install(monkeypatch, FakeDB(fetch=[ENROLMENT], fetchrow={}))
    monkeypatch.setattr(academy.random, "randint", lambda a, b: b)

    out = await academy.run_tick(5)

    assert out == {"enrolled": 1, "graduated": 0}
    closed = fake.args_for("SET graduated=true WHERE id=$1", "execute")
    assert closed == [(900,)]
    assert any("no program" in m for m in seen), seen


async def test_progress_advances_without_graduating_below_the_target(monkeypatch):
    early = dict(ENROLMENT, progress=0, target_progress=500)
    fake = _install(monkeypatch, FakeDB(fetch=[early], fetchrow={}))
    monkeypatch.setattr(academy.random, "randint", lambda a, b: a)

    out = await academy.run_tick(5)

    assert out == {"enrolled": 1, "graduated": 0}
    assert fake.args_for("SET progress=$1 WHERE id=$2", "execute")[0] == (20, 900)


async def test_the_enrolment_read_joins_the_roster_on_this_session(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[], fetchrow={}))

    await academy.run_tick(5)

    sql = fake.sql("fetch")[0]
    assert "cr.session_id=$1" in sql and "ec.graduated=false" in sql


async def test_run_tick_reports_a_crash_as_an_error(monkeypatch):
    seen = []
    monkeypatch.setattr("modules.academy.error", lambda mod, msg: seen.append(msg))

    async def boom(*_args, **_kwargs):
        raise RuntimeError("no campus")

    _install(monkeypatch, FakeDB())
    monkeypatch.setattr("modules.academy.Database.fetch", boom)

    out = await academy.run_tick(5)

    assert "no campus" in out["error"]
    assert any("no campus" in m for m in seen), seen
