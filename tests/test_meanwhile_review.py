"""Module review tests for modules/meanwhile.py.

Defects covered:

1. The raid cut marked its intel reported with
   `WHERE session_id=$1 AND faction_name=$2 AND target_system=$3`, not by the row
   it read. The live table holds three undetected `Gale Runner Freebooters` raids
   at system 433-472, so one POV cut marked all three as detected and the other
   two could never be reported. It marks by id now.
2. `enemy_power` and `ticks_remaining` are nullable columns and the narrative
   formats both with `:,`. A NULL would raise TypeError inside the cut.

Checked and found correct: every read and write carries session_id; the cut
respects the pacing mode and the 15% roll; the raid branch only takes raids
within 5 ticks; secrets and the hostile-faction fallback are session-scoped; and
a missing player location falls through to the atmosphere scene instead of
crashing.

No database: every test drives a fake Database.
"""
from __future__ import annotations

import pytest

import modules.meanwhile as meanwhile


class FakeDB:
    def __init__(self, rows=None, fetch=None, fetchval=None):
        self.row_map = rows or {}
        self.fetch_rows = fetch if fetch is not None else []
        self.fetchval_value = fetchval
        self.calls = []

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", " ".join(sql.split()), args))
        for marker, value in self.row_map.items():
            if marker in sql:
                return value
        return None

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", " ".join(sql.split()), args))
        return self.fetch_rows

    async def fetchval(self, sql, *args):
        self.calls.append(("fetchval", " ".join(sql.split()), args))
        return self.fetchval_value

    async def execute(self, sql, *args):
        self.calls.append(("execute", " ".join(sql.split()), args))
        return "UPDATE 1"

    def sql(self, kind=None):
        return [c[1] for c in self.calls if kind is None or c[0] == kind]

    def args_for(self, needle, kind=None):
        return [c[2] for c in self.calls
                if needle in c[1] and (kind is None or c[0] == kind)]


def _install(monkeypatch, fake):
    for name in ("fetchrow", "fetch", "fetchval", "execute"):
        monkeypatch.setattr("modules.meanwhile.Database." + name, getattr(fake, name))
    return fake


def _always(monkeypatch):
    """Fire the 15% cut and keep the pacing mode out of the way."""
    monkeypatch.setattr(meanwhile.random, "random", lambda: 0.0)

    class Pacing:
        @staticmethod
        async def get_mode(session_id):
            return {"mode": "engaged"}

    monkeypatch.setattr("core.pacing.PacingDirector", Pacing)


RAID = {"id": 4211, "faction_name": "Gale Runner Freebooters",
        "target_system": "433-472", "enemy_power": 512_000, "ticks_remaining": 3}


# ── 1. The raid cut marks the row it read ────────────────────────────────

async def test_the_raid_cut_marks_exactly_the_row_it_read(monkeypatch):
    _always(monkeypatch)
    fake = _install(monkeypatch, FakeDB(rows={"incoming_raids": RAID}))

    out = await meanwhile.generate(5)

    assert out["type"] == "enemy_pov"
    marked = fake.args_for("UPDATE maya_rp.incoming_raids", "execute")[0]
    assert marked == (5, 4211)
    sql = fake.sql("execute")[0]
    assert "faction_name" not in sql and "target_system" not in sql, sql


async def test_the_raid_cut_names_the_target_and_the_power(monkeypatch):
    _always(monkeypatch)
    _install(monkeypatch, FakeDB(rows={"incoming_raids": RAID}))

    out = await meanwhile.generate(5)

    assert "Gale Runner Freebooters" in out["location"]
    assert "Target: 433-472" in out["narrative"]
    assert "512,000" in out["narrative"]
    assert "Impact in 3 ticks" in out["narrative"]
    assert out["relevance"] == "Intel revealed. Defensive deployment required."


@pytest.mark.parametrize("power,ticks", [(None, 3), (512_000, None), (None, None)])
async def test_a_null_power_or_deadline_does_not_break_the_cut(monkeypatch, power, ticks):
    _always(monkeypatch)
    raid = dict(RAID, enemy_power=power, ticks_remaining=ticks)
    _install(monkeypatch, FakeDB(rows={"incoming_raids": raid}))

    out = await meanwhile.generate(5)

    assert out["type"] == "enemy_pov"
    assert f"Power: {power or 0:,}." in out["narrative"]
    assert f"Impact in {ticks or 0} ticks." in out["narrative"]


# ── Contract the module claims ───────────────────────────────────────────

async def test_no_cut_fires_on_most_turns(monkeypatch):
    monkeypatch.setattr(meanwhile.random, "random", lambda: 0.99)
    fake = _install(monkeypatch, FakeDB())

    assert await meanwhile.generate(5) is None
    assert not fake.calls


@pytest.mark.parametrize("mode", ["intimate", "downtime"])
async def test_a_quiet_mode_suppresses_the_cut(monkeypatch, mode):
    monkeypatch.setattr(meanwhile.random, "random", lambda: 0.0)

    class Pacing:
        @staticmethod
        async def get_mode(session_id):
            return {"mode": mode}

    monkeypatch.setattr("core.pacing.PacingDirector", Pacing)
    fake = _install(monkeypatch, FakeDB())

    assert await meanwhile.generate(5) is None
    assert not fake.calls


async def test_a_secret_cut_uses_the_dramatic_irony_feed(monkeypatch):
    _always(monkeypatch)
    fake = _install(monkeypatch, FakeDB(rows={"incoming_raids": None}))

    async def irony(session_id):
        return [{"holder": "Captain Vane", "content": "the vault is empty"}]

    monkeypatch.setattr("modules.secrets.get_dramatic_irony", irony)

    out = await meanwhile.generate(5)

    assert out["type"] == "secret"
    assert out["characters"] == ["Captain Vane"]
    assert "the vault is empty" in out["narrative"]


async def test_a_hostile_faction_cut_is_session_scoped(monkeypatch):
    _always(monkeypatch)
    fake = _install(monkeypatch, FakeDB(
        rows={"incoming_raids": None, "standing='hostile'": {"name": "Iron Concord"}}))

    async def no_irony(session_id):
        return []

    monkeypatch.setattr("modules.secrets.get_dramatic_irony", no_irony)

    out = await meanwhile.generate(5)

    assert out["type"] == "enemy"
    assert "Iron Concord" in out["location"]
    sql = [s for s in fake.sql("fetchrow") if "standing='hostile'" in s][0]
    assert "session_id=$1" in sql
    assert fake.args_for("standing='hostile'", "fetchrow")[0] == (5,)


async def test_the_atmosphere_cut_avoids_the_players_own_location(monkeypatch):
    _always(monkeypatch)
    fake = _install(monkeypatch, FakeDB(rows={}))

    async def no_irony(session_id):
        return []

    async def location(session_id):
        return {"location": "bridge"}

    monkeypatch.setattr("modules.secrets.get_dramatic_irony", no_irony)
    monkeypatch.setattr("modules.locations.get_player_location", location)
    monkeypatch.setattr(meanwhile.random, "choice", lambda seq: sorted(seq)[0])

    out = await meanwhile.generate(5)

    assert out["type"] == "atmosphere"
    assert out["location"] != "bridge"
    assert out["location"] == "cargo bay"
    assert "Someone moved the crates" in out["narrative"]
