"""Module review tests for modules/war.py.

Defects covered:

1. `tick_wars` advanced EVERY war row, including the ended ones: `list_wars`
   returns both, and `advance` adds casualties before it looks at the status. Two
   live session-3 wars sit at status='ended' with 8,048/2,821 and 1,140/624
   casualties, and those counters were growing on every tick forever. The tick
   asks for active wars only.
2. `declare` wrote a war row against a name it never checked: a misspelled
   opponent inserted the war, updated no faction, and reported success. It looks
   the faction up first, and refuses a second war against an opponent that
   already has one running.
3. The three writes in `advance` matched on id alone.
4. `run_tick` logged its crash at info level.
5. An unknown phase silently rewound the war to escalation; it says so now.

Checked and found correct: every power read is session-scoped, including the
enemy hull sum on `faction_ships`; the phase cycle stops at resolution; the
end-of-war event fires once because the block checks `status != 'ended'`; the
phase-advance roll is skipped once the war reaches the last phase; and the
winner is decided by the power ratio, not by a die.

Note for the lead, not fixed here: `declare` still sets the standing of EVERY
faction whose name matches the target (`LIKE %name%`, no LIMIT). Declaring war on
"The Den" therefore turns every faction whose name contains that string hostile.
Whether that is intended is a canon question.

No database: every test drives a fake Database.
"""
from __future__ import annotations

import pytest

import modules.war as war


class FakeDB:
    def __init__(self, fetch=None, fetchrow=None, fetchval=None, rows=None):
        self.fetch_rows = fetch if fetch is not None else []
        self.row_map = rows or {}
        self.fetchrow_value = fetchrow
        self.fetchval_value = fetchval
        self.calls = []

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", " ".join(sql.split()), args))
        if isinstance(self.fetch_rows, dict):
            for marker, value in self.fetch_rows.items():
                if marker != "*" and marker in sql:
                    return value
            return self.fetch_rows.get("*", [])
        return self.fetch_rows

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", " ".join(sql.split()), args))
        for marker, value in self.row_map.items():
            if marker in sql:
                return value
        return self.fetchrow_value

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
    for name in ("fetch", "fetchrow", "fetchval", "execute"):
        monkeypatch.setattr("modules.war.Database." + name, getattr(fake, name))
    return fake


WAR_ROW = {"id": 3, "session_id": 3, "opponent_faction": "The Den", "phase": "clash",
           "status": "active", "attacker_casualties": 10, "defender_casualties": 5,
           "casus_belli": "raid", "war_goal": "safety"}


# ── 1. An ended war stops taking casualties ─────────────────────────────

async def test_the_tick_asks_for_active_wars_only(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[]))

    await war.tick_wars(3)

    sql = fake.sql("fetch")[0]
    assert "status = 'active'" in sql, sql
    assert fake.args_for("FROM maya_rp.wars", "fetch")[0] == (3, True)


async def test_list_wars_still_returns_everything_by_default(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[]))

    await war.list_wars(3)

    assert fake.args_for("FROM maya_rp.wars", "fetch")[0] == (3, False)


# ── 2. declare checks its opponent ──────────────────────────────────────

async def test_declaring_war_on_a_name_that_does_not_exist_is_refused(monkeypatch):
    fake = _install(monkeypatch, FakeDB(rows={"FROM maya_rp.factions": None}))

    out = await war.declare("Nobody At All", "insult", "respect")

    assert "No faction matching" in out["error"]
    assert not fake.args_for("INSERT INTO maya_rp.wars", "fetchval")


async def test_a_second_war_against_the_same_opponent_is_refused(monkeypatch):
    fake = _install(monkeypatch, FakeDB(
        rows={"FROM maya_rp.factions": {"id": 6, "name": "The Den"}},
        fetchval=1))

    out = await war.declare("The Den", "raid", "safety")

    assert "already running" in out["error"]
    assert not fake.args_for("INSERT INTO maya_rp.wars", "fetchval")


async def test_a_blank_opponent_is_refused(monkeypatch):
    fake = _install(monkeypatch, FakeDB())

    with pytest.raises(ValueError, match="target_faction must be a non-empty string"):
        await war.declare("   ", "raid", "safety")

    assert not fake.calls


async def test_a_new_war_opens_at_escalation(monkeypatch):
    opponents = iter([{"id": 6, "name": "The Den"}])
    answers = iter([None, 2244, 91])      # no running war, game day, new id

    async def fetchrow(*_a, **_k):
        return next(opponents, None)

    async def fetchval(*_a, **_k):
        return next(answers, 0)

    fake = _install(monkeypatch, FakeDB())
    monkeypatch.setattr("modules.war.Database.fetchrow", fetchrow)
    monkeypatch.setattr("modules.war.Database.fetchval", fetchval)

    out = await war.declare("The Den", "raid", "safety", session_id=3)

    assert out == {"war_id": 91, "phase": "escalation", "opponent": "The Den"}
    turned = fake.args_for("SET standing='hostile'", "execute")[0]
    assert turned == (3, "%The Den%")


# ── 3 + 4 + 5. The advance writes, the log level, the unknown phase ─────

async def test_the_casualty_and_phase_writes_carry_the_session(monkeypatch):
    answers = iter([100, 100])

    async def fetchval(*_a, **_k):
        return next(answers)

    fake = _install(monkeypatch, FakeDB(rows={"FROM maya_rp.wars": WAR_ROW}))
    monkeypatch.setattr("modules.war.Database.fetchval", fetchval)
    monkeypatch.setattr("modules.war.random.random", lambda: 0.0)     # advance the phase

    out = await war.advance(3, 3)

    assert out["new_phase"] == "attrition"
    casualties = fake.args_for("attacker_casualties=attacker_casualties+$1", "execute")[0]
    assert casualties[2] == 3 and casualties[3] == 3
    phase = fake.args_for("SET phase=$1", "execute")[0]
    assert phase == ("attrition", 3, 3)


async def test_an_unknown_phase_is_named_and_still_advances(monkeypatch):
    seen = []
    monkeypatch.setattr("modules.war.info", lambda mod, msg: seen.append(msg))
    row = dict(WAR_ROW, phase="brouhaha")
    _install(monkeypatch, FakeDB(rows={"FROM maya_rp.wars": row}, fetchval=100))
    monkeypatch.setattr("modules.war.random.random", lambda: 1.0)

    out = await war.advance(3, 3)

    assert out["power_ratio"] == 1.0
    assert any("brouhaha" in m for m in seen), seen


async def test_the_end_of_war_fires_once(monkeypatch):
    row = dict(WAR_ROW, phase="turning_point")
    fake = _install(monkeypatch, FakeDB(rows={"FROM maya_rp.wars": row}, fetchval=100))
    monkeypatch.setattr("modules.war.random.random", lambda: 1.0)

    out = await war.advance(3, 3)

    assert out["ended"] is True and out["winner"] == "Player"
    assert len(fake.args_for("SET status='ended'", "execute")) == 1
    assert len(fake.args_for("war_end", "execute")) == 1


async def test_an_ended_war_does_not_re_announce_its_end(monkeypatch):
    row = dict(WAR_ROW, phase="resolution", status="ended")
    fake = _install(monkeypatch, FakeDB(rows={"FROM maya_rp.wars": row}, fetchval=100))

    out = await war.advance(3, 3)

    assert out["ended"] is True
    assert not fake.args_for("SET status='ended'", "execute")
    assert not fake.args_for("war_end", "execute")


async def test_a_missing_war_is_answered_not_crashed(monkeypatch):
    _install(monkeypatch, FakeDB(rows={"FROM maya_rp.wars": None}))

    assert await war.advance(99, 3) == {"error": "War not found"}


async def test_run_tick_reports_a_crash_as_an_error(monkeypatch):
    seen = []
    monkeypatch.setattr("modules.war.error", lambda mod, msg: seen.append(msg))

    async def boom(*_a, **_k):
        raise RuntimeError("no armies")

    _install(monkeypatch, FakeDB())
    monkeypatch.setattr("modules.war.Database.fetch", boom)

    out = await war.run_tick(3)

    assert "no armies" in out["error"]
    assert any("no armies" in m for m in seen), seen


# ── Contract the module claims ──────────────────────────────────────────

def test_contract_the_phase_ladder_runs_escalation_to_resolution():
    assert war.WAR_PHASES[0] == "escalation"
    assert war.WAR_PHASES[-1] == "resolution"
    assert len(set(war.WAR_PHASES)) == len(war.WAR_PHASES)


async def test_contract_the_powers_are_read_from_this_session(monkeypatch):
    fake = _install(monkeypatch, FakeDB(rows={"FROM maya_rp.wars": WAR_ROW}, fetchval=100))

    await war.advance(3, 3)

    for sql in fake.sql("fetchval"):
        if "power_rating" in sql:
            assert "session_id=$1" in sql, sql
    enemy = fake.args_for("faction_ships", "fetchval")[0]
    assert enemy == (3, "The Den")
