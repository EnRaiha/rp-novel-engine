"""Module review tests for modules/darkops.py.

Defects covered:

1. `run_op` charged the alloys and credits and THEN updated the faction by name.
   A misspelled target matched no faction, the cost was already gone, and the
   result still said the operation ran. The faction is resolved before anything
   is spent, and the fear write targets it by id.
2. Nothing in the repo wrote to `maya_rp.dark_ops` — the table held 0 rows — so
   `list_darkops`, which is the whole point of the log, could never show an
   operation the engine had run. A finished operation records itself now.

Checked and found correct: the operation is validated against VALID_OPS before
anything else; affordability is checked against this session's own resources
row; the cost table and the morality table cover the same seven operations; fear
lands on both the faction and the realm; and the log read is session-scoped and
capped.

No database: every test drives a fake Database.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

import pytest

import modules.darkops as darkops

#: Scratch campaign: sessions 3 and 5 are frozen, and the writers refuse them.
SID = 900 + os.getpid() % 100


class FakeDB:
    def __init__(self, rows=None, fetchrow=None, execute_tag="UPDATE 1"):
        self.row_map = rows or {}
        self.fetchrow_value = fetchrow
        self.execute_tag = execute_tag
        self.calls = []

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", " ".join(sql.split()), args))
        for marker, value in self.row_map.items():
            if marker in sql:
                return value
        return self.fetchrow_value

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", " ".join(sql.split()), args))
        return []

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


FACTION = {"id": 6, "name": "The Den"}
TREASURY = {"alloys": 100_000, "credits": 100_000}


def _install(monkeypatch, fake):
    for name in ("fetchrow", "fetch", "execute", "transaction"):
        monkeypatch.setattr("modules.darkops.Database." + name, getattr(fake, name))
    return fake


def _ready(monkeypatch, **over):
    rows = {"FROM maya_rp.factions": over.get("faction", FACTION),
            "UPDATE maya_rp.resources": over.get("treasury", TREASURY)}
    return _install(monkeypatch, FakeDB(rows=rows, execute_tag=over.get("tag", "UPDATE 1")))


# ── 1. The target is checked before the cost is taken ───────────────────

async def test_a_misspelled_target_costs_nothing(monkeypatch):
    fake = _ready(monkeypatch, faction=None)

    out = await darkops.run_op("sabotage", "Nobody At All", SID)

    assert "No faction matching" in out["error"]
    assert not fake.args_for("UPDATE maya_rp.resources"), "the cost was taken anyway"
    assert not fake.args_for("INSERT INTO maya_rp.dark_ops", "execute")


async def test_the_faction_lookup_prefers_an_exact_name(monkeypatch):
    fake = _ready(monkeypatch)
    monkeypatch.setattr("modules.darkops.random.randint", lambda a, b: b)

    await darkops.run_op("sabotage", "The Den", SID)

    sql = fake.sql("fetchrow")[0]
    assert "session_id=$1" in sql and "ORDER BY id LIMIT 1" in sql
    assert fake.args_for("FROM maya_rp.factions", "fetchrow")[0] == (SID, "%The Den%")


async def test_an_unknown_operation_is_refused_before_the_lookup(monkeypatch):
    fake = _ready(monkeypatch)

    out = await darkops.run_op("care_bears", "The Den", SID)

    assert "Unknown: care_bears" in out["error"]
    assert not fake.sql("fetchrow")


async def test_an_unaffordable_operation_is_refused(monkeypatch):
    fake = _ready(monkeypatch, treasury=None)

    out = await darkops.run_op("planet_crack", "The Den", SID)

    assert "Need 10000a/5000c" in out["error"]
    assert not fake.sql("execute"), "an unaffordable operation wrote effects"


async def test_the_fear_write_targets_the_faction_by_id(monkeypatch):
    fake = _ready(monkeypatch)
    monkeypatch.setattr("modules.darkops.random.randint", lambda a, b: b)

    await darkops.run_op("sabotage", "The Den", SID)

    fear = fake.args_for("fear_of_player=COALESCE", "execute")[0]
    assert fear[2] == 6 and fear[3] == SID, fear
    assert "LOWER(name)" not in fake.sql("execute")[0]


# ── 2. The operation is recorded ────────────────────────────────────────

async def test_a_finished_operation_is_written_to_the_log(monkeypatch):
    fake = _ready(monkeypatch)
    monkeypatch.setattr("modules.darkops.random.randint", lambda a, b: b)

    out = await darkops.run_op("assassinate", "The Den", SID)

    logged = fake.args_for("INSERT INTO maya_rp.dark_ops ", "execute")
    assert logged, "the operation was never recorded"
    # the INSERT passes eight values: 'faction' and NOW() are literals
    args = logged[0]
    assert args[0] == SID
    assert args[1] == "The Den" and args[2] == "assassinate"
    assert args[6] == out["outcome"] and args[7].startswith("assassinate")


async def test_the_log_read_is_session_scoped(monkeypatch):
    fake = _install(monkeypatch, FakeDB())

    await darkops.list_darkops(SID)

    sql = fake.sql("fetch")[0]
    assert "session_id=$1" in sql and "LIMIT 15" in sql


# ── Contract the module claims ──────────────────────────────────────────

def test_contract_every_valid_op_is_priced_and_scored():
    assert set(darkops.VALID_OPS) == set(darkops.OP_COSTS) == set(darkops.MORALITY_COST)
    for op, (alloys, credits, rep, fear) in darkops.OP_COSTS.items():
        assert alloys > 0 and credits > 0, op
        assert rep < 0, op
        assert 0 <= fear <= 100, op


async def test_contract_an_exposed_operation_costs_twice_the_reputation(monkeypatch):
    fake = _ready(monkeypatch)
    monkeypatch.setattr("modules.darkops.random.randint", lambda a, b: b)   # chance 50, roll 100: top tail of the failing rolls → exposed

    out = await darkops.run_op("sabotage", "The Den", SID)

    assert out["outcome"] == "exposed"
    assert out["rep_delta"] == darkops.OP_COSTS["sabotage"][2] * 2


async def test_contract_run_tick_answers_ready():
    assert await darkops.run_tick(SID) == {"status": "darkops_ready"}
