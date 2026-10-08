"""Module review tests for modules/espionage.py.

Defects covered:

1. `run_espionage` rolled a mission and never recorded it. `list_espionage_log`
   reads `espionage_missions` and the tick resolves its stale rows, so nothing
   the live `cli.py misc espionage` door ran could ever appear in the log. It
   writes the mission row now.
2. `fac["reputation"] // 10` raised TypeError when the faction's reputation is
   NULL, which the column allows.
3. The loot credit was unconditional. A session with no `resources` row (session
   5 has none) was told it looted, and the new mission row would have said the
   same. The credit is checked and the reported loot is what landed.
4. A partial faction name matched with `LIKE` and no ORDER BY, so the target was
   whichever row PostgreSQL returned first.
5. The stale-resolution write matched on id alone, and the tick logged its crash
   at info level.

No database: every test drives a fake Database.
"""
from __future__ import annotations

import json
import os

import pytest

import modules.espionage as espionage

#: Scratch campaign: sessions 3 and 5 are frozen, and the writers refuse them.
SID = 900 + os.getpid() % 100


class FakeDB:
    def __init__(self, fetch=None, fetchrow=None, execute_tag="UPDATE 1"):
        self.fetch_rows = fetch if fetch is not None else []
        self.fetchrow_value = fetchrow
        self.execute_tag = execute_tag
        self.calls = []

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", " ".join(sql.split()), args))
        return self.fetch_rows

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", " ".join(sql.split()), args))
        return self.fetchrow_value

    async def execute(self, sql, *args):
        self.calls.append(("execute", " ".join(sql.split()), args))
        return self.execute_tag

    def sql(self, kind=None):
        return [c[1] for c in self.calls if kind is None or c[0] in (kind,)]
    def args_for(self, needle, kind=None):
        return [c[2] for c in self.calls
                if needle in c[1] and (kind is None or c[0] == kind)]


def _install(monkeypatch, fake):
    for name in ("fetch", "fetchrow", "execute"):
        monkeypatch.setattr("modules.espionage.Database." + name, getattr(fake, name))
    return fake


FACTION = {"id": 24, "name": "Raiding Den Reavers", "reputation": 30}


def _roll(monkeypatch, roll: int, noise: int = 0):
    """Pin the three draws in order: the noise, the mission roll, then the loot
    (which takes the top of its band so the assertion is exact)."""
    def randint(a, b):
        if (a, b) == (-15, 15):
            return noise
        if (a, b) == (1, 100):
            return roll
        return b
    monkeypatch.setattr(espionage.random, "randint", randint)


# ── 1. The mission is recorded ───────────────────────────────────────────

async def test_a_run_is_written_to_the_mission_log(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchrow=FACTION, execute_tag="UPDATE 1"))
    _roll(monkeypatch, 100)          # a high roll on a 70 base is still a failure-free path

    out = await espionage.run_espionage("Reavers", "scout_fleet", "Vane", SID)

    logged = fake.args_for("INSERT INTO maya_rp.espionage_missions ", "execute")
    assert logged, "the mission was never recorded"
    args = logged[0]
    assert args[0] == SID and args[1] == 24 and args[2] == "scout_fleet" and args[3] == "Vane"
    assert args[5] == out["outcome"]
    assert json.loads(args[6]) == {"alloys": out["loot_alloys"], "credits": out["loot_credits"]}
    assert args[7] == out["rep_delta"]
    assert args[8] == out["narrative"]


async def test_an_unknown_faction_is_not_recorded(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchrow=None))

    out = await espionage.run_espionage("Nobody", "scout_fleet", "Vane", SID)

    assert "not found" in out["error"]
    assert not fake.sql("execute")


async def test_an_unknown_mission_is_not_recorded(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchrow=FACTION))

    out = await espionage.run_espionage("Reavers", "steal_moon", "Vane", SID)

    assert "Unknown mission" in out["error"]
    assert not fake.sql("execute")


# ── 2. A NULL reputation does not crash ──────────────────────────────────

async def test_a_null_reputation_mission_still_runs(monkeypatch):
    faction = dict(FACTION, reputation=None)
    fake = _install(monkeypatch, FakeDB(fetchrow=faction, execute_tag="UPDATE 1"))
    _roll(monkeypatch, 100)

    out = await espionage.run_espionage("Reavers", "sabotage", "Vane", SID)

    assert out["outcome"] in ("critical_failure", "failure"), out
    assert fake.args_for("espionage_missions", "execute")


# ── 3. Loot is what landed ───────────────────────────────────────────────

async def test_loot_is_reported_only_when_it_banks(monkeypatch):
    seen = []
    monkeypatch.setattr("modules.espionage.info", lambda mod, msg: seen.append(msg))
    fake = _install(monkeypatch, FakeDB(fetchrow=FACTION, execute_tag="UPDATE 0"))
    _roll(monkeypatch, 30)           # above the critical band, at or below success

    out = await espionage.run_espionage("Reavers", "steal_resources", "Vane", SID)

    assert out["outcome"] == "success"
    assert out["loot_alloys"] == 0 and out["loot_credits"] == 0, "loot that never landed was claimed"
    assert any("NOT banked" in m for m in seen), seen
    logged_after = fake.args_for("espionage_missions", "execute")[-1]
    assert json.loads(logged_after[6]) == {"alloys": 0, "credits": 0}


async def test_loot_that_lands_is_reported(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchrow=FACTION, execute_tag="UPDATE 1"))
    _roll(monkeypatch, 30)

    out = await espionage.run_espionage("Reavers", "steal_resources", "Vane", SID)

    assert out["outcome"] == "success"
    assert out["loot_alloys"] == 2000 and out["loot_credits"] == 1000
    banked = fake.args_for("alloys=alloys+$1", "execute")[0]
    assert banked == (2000, 1000, SID)


# ── 4. The faction lookup is deterministic ───────────────────────────────

async def test_the_faction_lookup_prefers_an_exact_name(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchrow=FACTION, execute_tag="UPDATE 1"))
    _roll(monkeypatch, 30)

    await espionage.run_espionage("Raiding Den Reavers", "scout_fleet", "Vane", SID)

    sql = fake.sql("fetchrow")[0]
    assert "ESCAPE '\\' ORDER BY (LOWER(name)=LOWER($3)) DESC, id LIMIT 1" in sql, sql
    assert fake.args_for("FROM maya_rp.factions", "fetchrow")[0] == (SID, "%Raiding Den Reavers%", "Raiding Den Reavers")


# ── 5. The stale tick ────────────────────────────────────────────────────

async def test_the_stale_resolution_is_session_scoped(monkeypatch):
    rows = [{"id": 11, "mission_type": "scout_fleet", "agent_name": "Vane"},
            {"id": 12, "mission_type": "sabotage", "agent_name": "Kesh"}]
    fake = _install(monkeypatch, FakeDB(fetch=rows))

    out = await espionage.run_tick(SID)

    assert out == {"resolved_stale": 2}
    writes = fake.args_for("SET outcome=$1", "execute")
    assert writes == [("went_dark", 11, SID), ("compromised", 12, SID)]
    sql = fake.sql("fetch")[0]
    assert "session_id=$1" in sql and "resolved_at IS NULL" in sql


async def test_run_tick_reports_a_crash_as_an_error(monkeypatch):
    seen = []
    monkeypatch.setattr("modules.espionage.error", lambda mod, msg: seen.append(msg))

    async def boom(*_a, **_k):
        raise RuntimeError("dead drop lost")

    _install(monkeypatch, FakeDB())
    monkeypatch.setattr("modules.espionage.Database.fetch", boom)

    out = await espionage.run_tick(SID)

    assert "dead drop lost" in out["error"]
    assert any("dead drop lost" in m for m in seen), seen


# ── Contract the module claims ───────────────────────────────────────────

async def test_contract_the_log_reads_the_newest_fifteen_for_this_session(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[{"mission_type": "sabotage"}]))

    out = await espionage.list_espionage_log(SID)

    assert out == [{"mission_type": "sabotage"}]
    sql = fake.sql("fetch")[0]
    assert "em.session_id=$1" in sql and "LIMIT 15" in sql
    assert fake.args_for("espionage_missions", "fetch")[0] == (SID,)
