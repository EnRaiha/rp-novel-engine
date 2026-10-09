"""Module review tests for modules/logistics.py.

Defects covered:

1. `transport` read the game day with `SELECT COALESCE(game_day,1) …` and used the
   RESULT: for a session that does not exist the fetchval returns None, the
   COALESCE being inside the SQL, and `$6+3` wrote a NULL `arrive_day`. The
   mission was never delivered and nothing said so. Both reads go through
   `_game_day` now.
2. `transport` accepted a second mission for a cargo row that was already in
   transit. Two missions arrived, and the later one overwrote the first
   delivery's destination. It is refused now.
3. The delivery write in `run_tick` matched the cargo on id alone, so a cargo row
   that is not in this session was reported as delivered. It reports what it
   moved.

Checked and found correct, and the docstrings already record an earlier pass:
`create_cargo` refuses a non-positive quantity and an empty location type;
`transport` refuses a cargo that is not in this session, a destination that is
missing either half, and a missing ship; the mission carries the session; and the
delivery query is session-scoped.

Reported to the lead, not fixed: `transport` does not check that
`transport_ship_id` exists in this session. There is no foreign key on that
column, so the mission will accept any id and the ship's absence only shows when
something tries to find the hull.

No database: every test drives a fake Database.
"""
from __future__ import annotations

import pytest

import modules.logistics as log


class FakeDB:
    def __init__(self, fetch=None, fetchval=100, execute_tag="UPDATE 1"):
        self.fetch_rows = fetch if fetch is not None else []
        self.fetchval_value = fetchval
        self.execute_tag = execute_tag
        self.calls = []

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", " ".join(sql.split()), args))
        return self.fetch_rows

    async def fetchval(self, sql, *args):
        self.calls.append(("fetchval", " ".join(sql.split()), args))
        if callable(self.fetchval_value):
            return self.fetchval_value(sql, args)
        return self.fetchval_value

    async def execute(self, sql, *args):
        self.calls.append(("execute", " ".join(sql.split()), args))
        return self.execute_tag

    def transaction(self):
        fake = self

        class _Tx:
            async def __aenter__(self):
                return fake

            async def __aexit__(self, *exc):
                return False

        return _Tx()

    def sql(self, kind=None):
        return [c[1] for c in self.calls if kind is None or c[0] == kind]

    def args_for(self, needle, kind=None):
        return [c[2] for c in self.calls
                if needle in c[1] and (kind is None or c[0] == kind)]


def _install(monkeypatch, fake):
    for name in ("fetch", "fetchval", "execute"):
        monkeypatch.setattr("modules.logistics.Database." + name, getattr(fake, name))
    monkeypatch.setattr("modules.logistics.Database.transaction", fake.transaction)
    return fake


# ── 1. A missing session cannot write a NULL arrival ────────────────────

async def test_a_missing_session_still_dates_the_arrival(monkeypatch):
    def answers(sql, args):
        if "game_day" in sql:
            return None            # the session does not exist
        if "transport_missions" in sql and "SELECT 1" in sql:
            return None            # not already in transit
        return 55                  # the new mission id

    fake = _install(monkeypatch, FakeDB(fetchval=answers))

    out = await log.transport(7, "sector", 3, 12, 5)

    assert out["mission_id"] == 55
    insert = fake.args_for("INSERT INTO maya_rp.transport_missions", "fetchval")[0]
    assert insert[5] == 1, "the arrival day was built from a NULL game day"


async def test_an_unknown_cargo_is_refused(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchval=None))

    out = await log.transport(7, "sector", 3, 12, 5)

    assert "does not exist in session 5" in out["error"]
    assert not fake.args_for("INSERT INTO maya_rp.transport_missions", "fetchval")


# ── 2. One cargo, one mission ───────────────────────────────────────────

async def test_a_second_mission_for_the_same_cargo_is_refused(monkeypatch):
    def answers(sql, args):
        if "SELECT 1 FROM maya_rp.cargo" in sql:
            return 1
        if "transport_missions" in sql:
            return 1               # already in transit
        return 300

    fake = _install(monkeypatch, FakeDB(fetchval=answers))

    out = await log.transport(7, "sector", 3, 12, 5)

    assert "already in transit" in out["error"]
    assert not fake.args_for("INSERT INTO maya_rp.transport_missions", "fetchval")
    guard = [s for s in fake.sql("fetchval") if "transport_missions" in s][0]
    assert "status='in_transit'" in guard


async def test_a_destination_needs_both_halves(monkeypatch):
    fake = _install(monkeypatch, FakeDB())

    assert "both a type and an id" in (await log.transport(7, "", 3, 12, 5))["error"]
    assert "both a type and an id" in (await log.transport(7, "sector", None, 12, 5))["error"]
    assert not fake.calls


async def test_a_missing_ship_is_refused(monkeypatch):
    def answers(sql, args):
        return 1 if "SELECT 1 FROM maya_rp.cargo" in sql else None

    fake = _install(monkeypatch, FakeDB(fetchval=answers))

    out = await log.transport(7, "sector", 3, None, 5)

    assert out["error"] == "a transport ship is required"
    assert not fake.args_for("INSERT INTO maya_rp.transport_missions", "fetchval")


# ── 3. Delivery reports what it moved ───────────────────────────────────

async def test_a_delivery_moves_the_cargo_and_says_so(monkeypatch):
    rows = [{"id": 1, "cargo_id": 7, "dest_type": "sector", "dest_id": 3}]
    fake = _install(monkeypatch, FakeDB(fetch=rows, fetchval=100, execute_tag="UPDATE 1"))

    out = await log.run_tick(5)

    assert out == {"deliveries": 1, "cargo_moved": 1}
    moved = fake.args_for("UPDATE maya_rp.cargo", "execute")[0]
    assert moved == ("sector", 3, 7, 5)
    assert "session_id=$4" in fake.sql("execute")[0]


async def test_a_delivery_for_missing_cargo_is_named_not_claimed(monkeypatch):
    seen = []
    monkeypatch.setattr("modules.logistics.info", lambda mod, msg: seen.append(msg))
    rows = [{"id": 1, "cargo_id": 7, "dest_type": "sector", "dest_id": 3}]
    fake = _install(monkeypatch, FakeDB(fetch=rows, fetchval=100, execute_tag="UPDATE 0"))

    out = await log.run_tick(5)

    assert out == {"deliveries": 1, "cargo_moved": 0}
    assert any("NOT set" in m for m in seen), seen


async def test_the_delivery_query_is_session_scoped(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[], fetchval=100))

    await log.run_tick(5)

    sql = fake.sql("fetch")[0]
    assert "session_id=$1" in sql and "status='in_transit'" in sql
    assert fake.args_for("transport_missions", "fetch")[0] == (5, 100)


# ── Contract an earlier pass already set ────────────────────────────────

@pytest.mark.parametrize("qty", [0, -1, None])
async def test_create_cargo_refuses_a_non_positive_quantity(monkeypatch, qty):
    fake = _install(monkeypatch, FakeDB())

    out = await log.create_cargo("grain", qty, "sector", 3, 5)

    assert "greater than zero" in out["error"]
    assert not fake.calls


async def test_create_cargo_refuses_a_nowhere_location(monkeypatch):
    fake = _install(monkeypatch, FakeDB())

    out = await log.create_cargo("grain", 5, "   ", 3, 5)

    assert "location_type is required" in out["error"]
    assert not fake.calls


async def test_create_cargo_writes_the_session_and_the_trimmed_type(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchval=42))

    out = await log.create_cargo("grain", 5, " sector ", 3, 5)

    assert out == {"cargo_id": 42, "item": "grain", "qty": 5, "at": "sector:3"}
    insert = fake.args_for("INSERT INTO maya_rp.cargo", "fetchval")[0]
    assert insert == (5, "grain", 5, "sector", 3)
