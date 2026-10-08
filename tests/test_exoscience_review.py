"""Module review tests for modules/exoscience.py.

Defects covered by this pass:

1. The mission and anomaly progress writes matched on id alone; they carry the
   session.
2. `generate_anomaly` resolved its sector with `LIKE %name% LIMIT 1` and no ORDER
   BY, so a partial name tied the anomaly to whichever sector PostgreSQL returned
   first. It is ordered.

Checked and found correct, and the docstrings record the earlier pass: the pace is
a digest of the row's identity and progress rather than `randint`, so the same
state advances the same way; a NULL `progress`, `target_progress`,
`data_collected` or `data_threshold` is read as its documented default instead of
killing the tick; a completion that cannot be paid is counted under
`rewards_unpaid` and warned about rather than reported as paid; `start_mission`
refuses a blank type; and `generate_anomaly` refuses a blank location and keeps
the raw location text in the description.

No database: every test drives a fake Database; its `transaction()` yields the fake itself. Every call uses a
scratch session id, because the frozen guard refuses sessions 3 and 5.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

import pytest

import modules.exoscience as exo

SID = 900 + os.getpid() % 100


class FakeDB:
    def __init__(self, fetch=None, fetchval=None, fetchrow=None):
        self.fetch_rows = fetch if fetch is not None else []
        self.fetchval_value = fetchval
        self.fetchrow_value = fetchrow
        self.calls = []

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", " ".join(sql.split()), args))
        if isinstance(self.fetch_rows, dict):
            for marker, value in self.fetch_rows.items():
                if marker != "*" and marker in sql:
                    return value
            return self.fetch_rows.get("*", [])
        return self.fetch_rows

    async def fetchval(self, sql, *args):
        self.calls.append(("fetchval", " ".join(sql.split()), args))
        if callable(self.fetchval_value):
            return self.fetchval_value(sql, args)
        return self.fetchval_value

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", " ".join(sql.split()), args))
        return self.fetchrow_value

    async def execute(self, sql, *args):
        self.calls.append(("execute", " ".join(sql.split()), args))
        return "UPDATE 1"

    @asynccontextmanager
    async def transaction(self):
        yield self

    def sql(self, kind=None):
        return [c[1] for c in self.calls if kind is None or c[0] == kind]

    def args_for(self, needle, kind=None):
        return [c[2] for c in self.calls
                if needle in c[1] and (kind is None or c[0] == kind)]


def _install(monkeypatch, fake):
    for name in ("fetch", "fetchval", "fetchrow", "execute", "transaction"):
        monkeypatch.setattr("modules.exoscience.Database." + name, getattr(fake, name))
    return fake


MISSION = {"id": 4, "mission_type": "survey", "progress": 10, "target_progress": 100,
           "research_reward": 500}
ANOMALY = {"id": 9, "name": "Void Echo", "data_collected": 10, "data_threshold": 100}


# ── 1. The progress writes are scoped ───────────────────────────────────

async def test_the_mission_write_carries_the_session(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch={"science_missions": [MISSION],
                                               "anomalies_catalog": []}, fetchval=1))

    out = await exo.run_tick(SID)

    assert out == {"missions_completed": 0, "anomalies_studied": 0}
    written = fake.args_for("UPDATE maya_rp.science_missions", "fetchval")[0]
    assert written[0] == 10 + exo._pace(SID, 4, 10)
    assert written[2] == 4 and written[3] == SID


async def test_the_anomaly_write_carries_the_session(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch={"science_missions": [],
                                               "anomalies_catalog": [ANOMALY]}, fetchval=None))

    await exo.run_tick(SID)

    written = fake.args_for("UPDATE maya_rp.anomalies_catalog", "execute")[0]
    assert written[1] == 9 and written[2] == SID


async def test_every_read_is_session_scoped(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[]))

    await exo.run_tick(SID)

    for sql in fake.sql("fetch"):
        assert "session_id=$1" in sql, sql
    assert fake.args_for("science_missions", "fetch")[0] == (SID,)


# ── 2. The sector lookup is deterministic ───────────────────────────────

async def test_the_sector_lookup_orders_its_match(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchval=lambda sql, args: 12 if "sectors" in sql else 77))

    out = await exo.generate_anomaly("Kappa", SID)

    sql = [s for s in fake.sql("fetchval") if "sectors" in s][0]
    assert "ORDER BY id LIMIT 1" in sql
    assert out["sector_id"] == 12 and out["anomaly_id"] == 77


@pytest.mark.parametrize("location", [None, "", "   "])
async def test_a_blank_location_is_refused(monkeypatch, location):
    fake = _install(monkeypatch, FakeDB())

    out = await exo.generate_anomaly(location, SID)

    assert "location is required" in out["error"]
    assert not fake.calls


# ── Contract the module claims ──────────────────────────────────────────

def test_contract_the_pace_is_stable_for_a_row_and_spread_across_rows():
    assert exo._pace(5, 1, 10) == exo._pace(5, 1, 10)
    paces = {exo._pace(5, i, 0) for i in range(60)}
    assert paces <= set(range(5, 16))
    assert len(paces) > 3, "the pace is supposed to keep some variety"


async def test_contract_a_completion_pays_once_and_counts_the_unpaid(monkeypatch):
    mission = dict(MISSION, progress=99, target_progress=100)
    fake = _install(monkeypatch, FakeDB(
        fetch={"science_missions": [mission], "anomalies_catalog": []},
        fetchval=lambda sql, args: 4 if "UPDATE maya_rp.science_missions" in sql else None))
    seen = []
    monkeypatch.setattr("modules.exoscience.warn", lambda mod, msg: seen.append(msg))

    out = await exo.run_tick(SID)

    assert out["missions_completed"] == 1 and out["rewards_unpaid"] == 1
    assert any("were not paid" in m for m in seen), seen


async def test_contract_a_null_progress_row_reads_as_zero(monkeypatch):
    mission = {"id": 4, "mission_type": "survey", "progress": None,
               "target_progress": None, "research_reward": 0}
    fake = _install(monkeypatch, FakeDB(
        fetch={"science_missions": [mission], "anomalies_catalog": []}, fetchval=1))

    await exo.run_tick(SID)

    written = fake.args_for("UPDATE maya_rp.science_missions", "fetchval")[0]
    assert written[0] == exo._pace(SID, 4, 0)


async def test_contract_start_mission_refuses_a_blank_type(monkeypatch):
    fake = _install(monkeypatch, FakeDB())

    out = await exo.start_mission("   ", SID)

    assert "mission_type is required" in out["error"]
    assert not fake.calls


async def test_contract_start_mission_prices_the_reward_at_five_per_point(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchval=31))

    out = await exo.start_mission("survey", SID)

    assert out["mission_id"] == 31 and out["reward"] == out["target"] * 5
    insert = fake.args_for("INSERT INTO maya_rp.science_missions", "fetchval")[0]
    assert insert[0] == SID and insert[1] == "survey"


async def test_contract_a_crash_is_reported_as_an_error(monkeypatch):
    seen = []
    monkeypatch.setattr("modules.exoscience.error", lambda mod, msg: seen.append(msg))

    async def boom(*_a, **_k):
        raise RuntimeError("lab fire")

    _install(monkeypatch, FakeDB())
    monkeypatch.setattr("modules.exoscience.Database.fetch", boom)

    out = await exo.run_tick(SID)

    assert "lab fire" in out["error"]
    assert any("lab fire" in m for m in seen), seen
