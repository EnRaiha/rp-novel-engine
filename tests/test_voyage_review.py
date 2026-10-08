"""Voyage module review tests — one per defect found reading modules/voyage.py.

Defects covered, in the order they appear in the file:

1. `advance()` read wormhole stability with no session filter, so a same-named
   hole in another campaign decided whether this session's ships survived.
2. A wormhole collapse narrated the lost hulls and booked nothing: the voyage
   stayed 'arrived' with loss_ships NULL.
3. `black_hole_slingshot` read `hazard_level or 0.85`, so a hazard of 0 became
   85%, and the declared constant BLACK_HOLE_SLINGSHOT_DC was never used.
4. `_num`: `column or default` treats a real 0 as a missing value.
5. `hidden_thread_danger/margin/outcome` accepted any act and fell through to
   the catch-all branch — a typo read as a resolved run.
6. `hidden_thread_outcome` re-implemented the loss rule four times instead of
   calling `hidden_thread_loss`.
7. `compute_travel` read `if distance_ly:`, so an explicit distance of 0 fell
   through to the coordinate branch and raised when no coords were given.
8. `register` accepted negative levels and a negative cargo value; a negative
   prep level RAISED the danger.
9. `register` booked a gate toll, and `advance` a clean-run profit, without
   checking that the session has a resources row.

Every test drives a fake Database: nothing here writes to the live campaign. The writers refuse the
frozen sessions 3 and 5, so each call names a scratch id that no row backs.
"""
import math
import os
import random
from contextlib import asynccontextmanager

import pytest

import modules.voyage as voyage
from modules.voyage import (BLACK_HOLE_SLINGSHOT_DC, GRID_HOURS_PER_UNIT,
                            HIDDEN_THREAD_ESCAPE_LOSS_MAX,
                            HIDDEN_THREAD_RUN_LOSS_MAX,
                            HIDDEN_THREAD_RUN_LOSS_MIN,
                            advance, black_hole_slingshot, compute_travel,
                            hidden_thread_danger, hidden_thread_loss,
                            hidden_thread_margin, hidden_thread_outcome,
                            register, white_hole_events, wormhole_status)


#: A scratch session id. It is never 3 or 5, and the fake database means no row exists for it.
SCRATCH = 900 + os.getpid() % 100


class FakeDB:
    """Records every statement; answers by SQL substring.

    The writers run on the connection that `Database.transaction()` yields, so `transaction()` yields
    a `_Conn` that records into the same call list as the pool methods. `treasury` says whether the
    session has a `resources` row: the guarded debit and credit `RETURNING credits` answer a value when
    it does and None when it does not. The per-voyage arrival claim always answers the voyage id.
    """

    def __init__(self, fetchval=None, fetch=None, treasury=True):
        self.fetchval_rules = fetchval or {}
        self.fetch_rows = fetch if fetch is not None else []
        self.treasury = treasury
        self.calls = []

    @asynccontextmanager
    async def transaction(self):
        yield _Conn(self)

    def _record(self, kind, sql, args):
        self.calls.append((kind, " ".join(sql.split()), args))

    async def fetchval(self, sql, *args):
        self._record("fetchval", sql, args)
        for key, value in self.fetchval_rules.items():
            if key in sql:
                return value() if callable(value) else value
        return None

    async def fetchrow(self, sql, *args):
        self._record("fetchrow", sql, args)
        for key, value in self.fetchval_rules.items():
            if key in sql:
                return value() if callable(value) else value
        return None

    async def fetch(self, sql, *args):
        self._record("fetch", sql, args)
        return self.fetch_rows

    async def execute(self, sql, *args):
        self._record("execute", sql, args)
        return "OK"

    def sql(self, kind=None):
        return [c[1] for c in self.calls if kind is None or c[0] == kind]

    def args_for(self, needle):
        return [c[2] for c in self.calls if needle in c[1]]


class _Conn:
    """The connection a fake transaction yields. It records like the pool methods and adds the answers
    a real connection gives to the guarded treasury statements and the arrival claim."""

    def __init__(self, fake):
        self._fake = fake

    async def fetchval(self, sql, *args):
        norm = " ".join(sql.split())
        if "UPDATE maya_rp.resources" in norm:
            self._fake._record("fetchval", sql, args)
            return 1_000_000 if self._fake.treasury else None
        if "SELECT 1 FROM maya_rp.resources" in norm:
            self._fake._record("fetchval", sql, args)
            return 1 if self._fake.treasury else None
        if "SET status='arrived'" in norm:
            self._fake._record("fetchval", sql, args)
            return args[0]
        return await self._fake.fetchval(sql, *args)

    async def fetchrow(self, sql, *args):
        return await self._fake.fetchrow(sql, *args)

    async def fetch(self, sql, *args):
        return await self._fake.fetch(sql, *args)

    async def execute(self, sql, *args):
        return await self._fake.execute(sql, *args)


def _install(monkeypatch, fake) -> FakeDB:
    monkeypatch.setattr(voyage.Database, "transaction", fake.transaction)
    for name in ("fetchval", "fetchrow", "fetch", "execute"):
        monkeypatch.setattr(voyage.Database, name, getattr(fake, name))
    return fake


VOYAGE_ROW = {
    "id": 7, "voyage_name": "Ghostgate Run", "origin": "A", "destination": "B",
    "arrive_day": 100, "fleet_tag": "TEST", "ship_count": 12, "via_hidden": False,
    "act": "sneak", "guide": None, "prep_level": 0, "equip_level": 0,
    "knowledge_level": 0, "cargo_heat": 0, "cargo_value": 0, "danger_pct": None,
    "transit_kind": "wormhole", "transit_name": "Ghostgate Thread",
    "dilation_days": 0, "collapse_roll": None, "lane_type": "wormhole",
}

GATE = {"name": "Test Gate ↔ B", "distance": 10.0, "travel_time_hours": 24.0,
        "hidden": False, "lane_type": "gate", "toll_credits": 25000,
        "pirate_density": 0.05}


async def _fake_gate(z1, z2, session_id=None):
    return dict(GATE)


# ── 1. Session scope on the wormhole stability read ──────────────────────

async def test_advance_wormhole_stability_read_is_session_scoped(monkeypatch):
    fake = FakeDB(fetchval={"maya_rp.sessions": 100, "maya_rp.wormholes": 0.5},
                  fetch=[dict(VOYAGE_ROW)])
    _install(monkeypatch, fake)
    monkeypatch.setattr(voyage.random, "randint", lambda a, b: 99)

    await advance(session_id=SCRATCH)

    reads = [s for s in fake.sql("fetchval") if "maya_rp.wormholes" in s]
    assert len(reads) == 1, reads
    assert "session_id=$1" in reads[0]
    assert fake.args_for("maya_rp.wormholes")[0][0] == SCRATCH


# ── 2. A collapse books the hulls it narrates ────────────────────────────

async def test_advance_books_wormhole_collapse_loss(monkeypatch):
    fake = FakeDB(fetchval={"maya_rp.sessions": 100, "maya_rp.wormholes": 0.5},
                  fetch=[dict(VOYAGE_ROW)])
    _install(monkeypatch, fake)
    monkeypatch.setattr(voyage.random, "randint", lambda a, b: 10)  # ≤ 30% → collapse

    res = await advance(session_id=SCRATCH)

    assert res["collapses"] == 1
    assert res["lost"] == ["Ghostgate Run"]
    bookings = [(s, a) for s, a in
                [(c[1], c[2]) for c in fake.calls if c[0] == "execute"]
                if "status='lost'" in s]
    assert bookings, fake.sql("execute")
    assert bookings[0][1] == (12, 7)          # ship_count booked, by voyage id
    assert any("wormhole_collapse" in s for s in fake.sql("execute"))


async def test_advance_unknown_stability_does_not_collapse(monkeypatch):
    # No matching wormhole row in this session → stability unknown → hub-fed default.
    fake = FakeDB(fetchval={"maya_rp.sessions": 100}, fetch=[dict(VOYAGE_ROW)])
    _install(monkeypatch, fake)
    monkeypatch.setattr(voyage.random, "randint", lambda a, b: 10)

    res = await advance(session_id=SCRATCH)

    assert res["collapses"] == 0
    assert any("wormhole_arrival" in s for s in fake.sql("execute"))


# ── 3 + 4. NULL is missing, 0 is a value ─────────────────────────────────

async def test_slingshot_null_hazard_uses_the_declared_default(monkeypatch):
    row = {"id": 1, "name": "Unread Maw", "hazard_level": None,
           "slingshot_multiplier": 0.55, "time_dilation_ratio": 6.0,
           "sector": "X", "x_coord": 0, "y_coord": 0, "z_coord": 2}
    _install(monkeypatch, FakeDB(fetchval={"maya_rp.black_holes": row}))
    monkeypatch.setattr(voyage.random, "randint", lambda a, b: 99)

    b = await black_hole_slingshot("Unread Maw", session_id=5)

    assert b["pass_dc"] == int(BLACK_HOLE_SLINGSHOT_DC * 100) == 75


async def test_slingshot_zero_hazard_stays_zero(monkeypatch):
    row = {"id": 1, "name": "Tame Maw", "hazard_level": 0.0,
           "slingshot_multiplier": 0.0, "time_dilation_ratio": 0.0,
           "sector": "X", "x_coord": 0, "y_coord": 0, "z_coord": 2}
    _install(monkeypatch, FakeDB(fetchval={"maya_rp.black_holes": row}))
    monkeypatch.setattr(voyage.random, "randint", lambda a, b: 1)

    b = await black_hole_slingshot("Tame Maw", session_id=5)

    assert b["hazard_level"] == 0.0 and b["pass_dc"] == 0
    assert b["slingshot_multiplier"] == 0.0
    assert b["time_dilation_ratio"] == 0.0
    assert b["ok"] is True


# ── 5. An unknown act is refused, not defaulted ──────────────────────────

@pytest.mark.parametrize("call", [
    lambda: hidden_thread_danger(act="sneek", rng=random.Random(1)),
    lambda: hidden_thread_margin(act="sneek", rng=random.Random(1)),
    lambda: hidden_thread_outcome("sneek", True, 0, 0, 0, 10, random.Random(1)),
])
def test_unknown_act_raises(call):
    with pytest.raises(ValueError, match="act must be one of"):
        call()


# ── 6. One loss rule, not four ───────────────────────────────────────────

def test_outcome_delegates_to_the_shared_loss_rule():
    for seed in range(25):
        run = hidden_thread_outcome("run", True, 0, 0, 0, 100, random.Random(seed))
        same = hidden_thread_loss(
            100, random.Random(seed),
            band=(HIDDEN_THREAD_RUN_LOSS_MIN, HIDDEN_THREAD_RUN_LOSS_MAX))
        assert run["loss"] == same

        escape = hidden_thread_outcome("bribe", True, 0, 0, 0, 100, random.Random(seed))
        same_escape = hidden_thread_loss(
            100, random.Random(seed),
            band=(0.0, HIDDEN_THREAD_ESCAPE_LOSS_MAX), minimum=0)
        assert escape["loss"] == same_escape


def test_interdiction_always_books_a_hull():
    # minimum=1 is the interdiction rule: even a 0-ship row cannot lose 0.
    assert hidden_thread_loss(0, random.Random(3)) == 1
    assert hidden_thread_loss(1, random.Random(3)) >= 1


# ── 7. An explicit zero distance is a distance ───────────────────────────

async def test_compute_travel_zero_ly_is_not_missing():
    r = await compute_travel(distance_ly=0)
    assert r["mode"] == "ly" and r["travel_days"] == 0


async def test_compute_travel_zero_units_is_not_missing():
    r = await compute_travel(distance_units=0)
    assert r["mode"] == "units" and r["travel_days"] == 0


@pytest.mark.parametrize("kw", [{"distance_ly": -1}, {"distance_units": -1}])
async def test_compute_travel_rejects_negative_distance(kw):
    with pytest.raises(ValueError, match="cannot be negative"):
        await compute_travel(**kw)


# ── 8. register validates its inputs ─────────────────────────────────────

@pytest.mark.parametrize("kw,match", [
    ({"voyage_name": "  "}, "voyage_name is required"),
    ({"ship_count": -1}, "ship_count cannot be negative"),
    ({"cargo_value": -5}, "cargo_value cannot be negative"),
    ({"prep_level": -2}, "prep_level cannot be negative"),
    ({"equip_level": -2}, "equip_level cannot be negative"),
    ({"knowledge_level": -2}, "knowledge_level cannot be negative"),
    ({"cargo_heat": -2}, "cargo_heat cannot be negative"),
])
async def test_register_rejects_bad_input(monkeypatch, kw, match):
    _install(monkeypatch, FakeDB())
    params = {"voyage_name": "Bad Run", "distance_units": 10, "depart_day": 1, "session_id": SCRATCH}
    params.update(kw)
    with pytest.raises(ValueError, match=match):
        await register(**params)


# ── 9. Money movement reports what it did ────────────────────────────────

async def test_register_uncharged_toll_when_session_has_no_resources_row(monkeypatch):
    fake = FakeDB(fetchval={"INSERT INTO maya_rp.voyages": 42}, treasury=False)
    _install(monkeypatch, fake)
    monkeypatch.setattr(voyage, "gate_crossing", _fake_gate)

    r = await register("No Treasury", "20,250,3", "25,12,2",
                       distance_units=None, ship_count=4, session_id=SCRATCH)

    assert r["lane_type"] == "gate"
    assert r["toll_charged"] is False
    assert r["toll_paid"] == 0          # the treasury paid nothing, so nothing is booked


async def test_register_books_toll_when_the_row_exists(monkeypatch):
    fake = FakeDB(fetchval={"INSERT INTO maya_rp.voyages": 42}, treasury=True)
    _install(monkeypatch, fake)
    monkeypatch.setattr(voyage, "gate_crossing", _fake_gate)

    r = await register("Real Treasury", "20,250,3", "25,12,2", ship_count=4, session_id=SCRATCH)

    assert r["toll_charged"] is True
    assert r["toll_paid"] == int(25000 * voyage.GATE_INTERNAL_COST_SHARE) == 5000
    debits = fake.args_for("COALESCE(credits, 0) - $1")
    assert debits == [(5000, SCRATCH)], f"the toll was not charged to the scratch treasury: {debits}"


async def test_clean_run_does_not_claim_unbooked_profit(monkeypatch):
    row = dict(VOYAGE_ROW, via_hidden=True, lane_type="hidden_thread",
               transit_kind="regular", transit_name=None, act="sneak",
               cargo_value=1000, danger_pct=50)
    fake = FakeDB(fetchval={"maya_rp.sessions": 100}, fetch=[row], treasury=False)
    _install(monkeypatch, fake)
    monkeypatch.setattr(voyage.random, "randint", lambda a, b: 90)     # 90 > 50 → clean
    monkeypatch.setattr(voyage.random, "uniform", lambda a, b: 0.30)   # +0.10 sneak = 0.40

    res = await advance(session_id=SCRATCH)

    assert res["clean_runs"] == 1
    assert res["profit_credits"] == 0            # nothing moved, so nothing is claimed
    assert res["unbooked_credits"] == 400
    assert fake.args_for("COALESCE(credits, 0) + $1") == [(400, SCRATCH)]   # the credit was attempted, found no row
    event = [c[2] for c in fake.calls
             if c[0] == "execute" and "smuggle_profit" in c[1]]
    assert event and "NOT credited" in event[0][2]


async def test_clean_run_credits_when_the_row_exists(monkeypatch):
    row = dict(VOYAGE_ROW, via_hidden=True, lane_type="hidden_thread",
               transit_kind="regular", transit_name=None, act="sneak",
               cargo_value=1000, danger_pct=50)
    fake = FakeDB(fetchval={"maya_rp.sessions": 100}, fetch=[row], treasury=True)
    _install(monkeypatch, fake)
    monkeypatch.setattr(voyage.random, "randint", lambda a, b: 90)
    monkeypatch.setattr(voyage.random, "uniform", lambda a, b: 0.30)

    res = await advance(session_id=SCRATCH)

    assert res["profit_credits"] == 400
    assert res["unbooked_credits"] == 0
    assert fake.args_for("COALESCE(credits, 0) + $1") == [(400, SCRATCH)], "the profit was not credited to the treasury"


# ── Module contract ──────────────────────────────────────────────────────

async def test_contract_register_books_arrival_from_travel_days(monkeypatch):
    """register(): the clock advances by exactly ceil(travel_days).

    48 units at GRID_HOURS_PER_UNIT=24 → 1152h → 48.0 days → arrives day 58.
    """
    fake = FakeDB(fetchval={"INSERT INTO maya_rp.voyages": 42})
    _install(monkeypatch, fake)

    r = await register("Contract Run", distance_units=48, depart_day=10,
                       fleet_tag="TEST", ship_count=3, session_id=SCRATCH)

    assert r["travel_days"] == pytest.approx(48 * GRID_HOURS_PER_UNIT / 24.0)
    assert r["arrive_day"] == 10 + int(math.ceil(r["travel_days"])) == 58
    assert r["status"] == "in_transit"
    insert = [s for s in fake.sql("fetchval") if "INSERT INTO maya_rp.voyages" in s]
    assert insert and "in_transit" in insert[0]


async def test_contract_advance_marks_due_voyages_and_reports_names(monkeypatch):
    """advance(): status='in_transit' AND arrive_day <= game_day is the due set."""
    row = dict(VOYAGE_ROW, transit_kind="regular", transit_name=None,
               lane_type="standard", ship_count=3)
    fake = FakeDB(fetchval={"maya_rp.sessions": 100}, fetch=[row])
    _install(monkeypatch, fake)
    monkeypatch.setattr(voyage.random, "randint", lambda a, b: 100)  # no pirate in 100

    res = await advance(session_id=SCRATCH)

    due = [s for s in fake.sql("fetch") if "status='in_transit'" in s]
    assert due and "session_id=$1" in due[0] and "arrive_day <= $2" in due[0], due
    assert fake.args_for("status='in_transit' AND arrive_day <= $2")[0] == (SCRATCH, 100)
    # each due voyage is claimed on the transaction's connection: id 7 of the scratch session
    claim = fake.args_for("SET status='arrived'")
    assert claim == [(7, SCRATCH)], claim
    assert res["arrivals"] == 1 and res["arrived"] == ["Ghostgate Run"]
    assert res["lost"] == []


async def test_contract_list_reads_filter_by_session(monkeypatch):
    """Every read that lists session-owned state names session_id."""
    fake = FakeDB(fetch=[], fetchval={"maya_rp.black_holes": None})
    _install(monkeypatch, fake)

    await wormhole_status(5)
    await white_hole_events(5)
    with pytest.raises(ValueError):
        await black_hole_slingshot("Nope", session_id=5)

    reads = fake.sql("fetch") + fake.sql("fetchval") + fake.sql("fetchrow")
    assert reads
    for sql in reads:
        assert "session_id=$1" in sql, sql
        assert fake.args_for(sql)[0][0] == 5
