"""Module review tests for modules/pregnancy.py.

Defects covered:

1. `status()` attached `days_pregnant`, `days_to_due` and `progress_pct` to
   `active` rows only, so a pregnancy lost its day count, ETA and percentage at
   exactly the moment it became `due_soon` — the final 30 days. It covers both
   live states now.
2. `_roll_birth` marked the birth with `WHERE id=$4` and no session.
3. `register` accepted a blank mother name (every birth event would then read
   "Birth — ") and a `gestation_days` below 1, which dates the due day at or
   before conception so the next tick delivers it.
4. The docstring promised "newest first" while the query orders births last and
   everything by due day. It describes what it does now.

Checked and found correct: every read and write carries session_id; the
trimester boundaries are exact at 90/180/270 days; a pregnancy past its due day
is delivered once because the birth write flips it out of the `active, due_soon`
selection; `progress_pct` is capped at 100 and `days_to_due` never goes
negative; and `events.importance` is nullable with a default, so the birth event
insert is legal without it.

No database: every test drives a fake Database.
"""
from __future__ import annotations

import pytest

import modules.pregnancy as preg


class FakeDB:
    def __init__(self, fetch=None, fetchrow=None, fetchval=100, execute_tag="UPDATE 1"):
        self.fetch_rows = fetch if fetch is not None else []
        self.fetchrow_value = fetchrow
        self.fetchval_value = fetchval
        self.execute_tag = execute_tag
        self.calls = []

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", " ".join(sql.split()), args))
        return self.fetch_rows

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", " ".join(sql.split()), args))
        return self.fetchrow_value

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
        monkeypatch.setattr("modules.pregnancy.Database." + name, getattr(fake, name))
    return fake


def _row(**over):
    row = {"id": 7, "mother_name": "Seraphina", "father_name": "King Izzat",
           "conceived_game_day": 100, "due_game_day": 370, "gestation_days": 270,
           "trimester": 1, "status": "active", "baby_name": None, "baby_gender": None,
           "notes": "", "birthed_game_day": None}
    row.update(over)
    return row


# ── 1. The report covers due_soon ───────────────────────────────────────

@pytest.mark.parametrize("state", ["active", "due_soon"])
async def test_progress_fields_survive_the_due_soon_flag(monkeypatch, state):
    _install(monkeypatch, FakeDB(fetch=[_row(status=state)], fetchval=360))

    out = await preg.status(5)

    assert out[0]["days_pregnant"] == 260
    assert out[0]["days_to_due"] == 10
    assert out[0]["progress_pct"] == round(260 / 270 * 100), out[0]


async def test_a_birthed_row_carries_no_progress_fields(monkeypatch):
    _install(monkeypatch, FakeDB(fetch=[_row(status="birthed", baby_name="Aisyah",
                                              baby_gender="female", birthed_game_day=370)],
                                 fetchval=400))

    out = await preg.status(5)

    assert out[0]["baby_name"] == "Aisyah"
    assert "days_pregnant" not in out[0]


async def test_progress_never_exceeds_one_hundred_or_goes_negative(monkeypatch):
    late = _row(conceived_game_day=100, due_game_day=200, gestation_days=270, status="due_soon")
    _install(monkeypatch, FakeDB(fetch=[late], fetchval=400))

    out = await preg.status(5)

    assert out[0]["progress_pct"] == 100
    assert out[0]["days_to_due"] == 0
    assert out[0]["days_pregnant"] == 300


async def test_the_report_is_session_scoped(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[], fetchval=100))

    await preg.status(5)

    assert fake.args_for("pregnancies", "fetch")[-1] == (5,)
    assert "session_id=$1" in fake.sql("fetch")[-1]


# ── 2 + 3. Register and the birth write ─────────────────────────────────

async def test_register_dates_the_due_day_from_gestation(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchval=100))

    pid = await preg.register(5, "Seraphina", 11, None, 270, "King Izzat")

    assert pid == 100
    insert = fake.args_for("INSERT INTO maya_rp.pregnancies", "fetchval")[0]
    assert insert[0] == 5 and insert[4] == 100 and insert[5] == 370


@pytest.mark.parametrize("name", [None, "", "   "])
async def test_register_refuses_a_blank_mother_name(monkeypatch, name):
    fake = _install(monkeypatch, FakeDB())

    with pytest.raises(ValueError, match="mother_name must be a non-empty string"):
        await preg.register(5, name)

    assert not fake.calls


@pytest.mark.parametrize("days", [0, -30])
async def test_register_refuses_a_gestation_below_one_day(monkeypatch, days):
    fake = _install(monkeypatch, FakeDB())

    with pytest.raises(ValueError, match="gestation_days must be at least 1"):
        await preg.register(5, "Seraphina", gestation_days=days)

    assert not fake.calls


async def test_the_birth_write_carries_the_session(monkeypatch):
    row = _row(due_game_day=300, conceived_game_day=30)
    fake = _install(monkeypatch, FakeDB(fetch=[row], fetchval=300))

    out = await preg.advance(5)

    assert len(out["births"]) == 1
    written = fake.args_for("SET status='birthed'", "execute")[0]
    assert written[0] in ("male", "female")
    assert written[3] == 7 and written[4] == 5
    assert "AND session_id=$5" in [s for s in fake.sql("execute") if "birthed" in s][0]


# ── Contract the module claims ──────────────────────────────────────────

@pytest.mark.parametrize("days,trimester", [
    (0, 1), (89, 1), (90, 2), (179, 2), (180, 3), (269, 3), (270, 3), (900, 3),
])
def test_contract_the_trimester_boundaries_are_exact(days, trimester):
    assert preg._trimester_for(days) == trimester


async def test_contract_the_advance_flags_due_soon_inside_thirty_days(monkeypatch):
    soon = _row(id=1, conceived_game_day=100, due_game_day=110, trimester=1)
    far = _row(id=2, conceived_game_day=100, due_game_day=300, trimester=1)
    fake = _install(monkeypatch, FakeDB(fetch=[soon, far], fetchval=100))

    out = await preg.advance(5)

    # only the due-soon row changes: the far one is already trimester 1 and active
    assert out == {"checked": 2, "updated": 1, "births": []}
    written = {a[2]: (a[0], a[1]) for a in fake.args_for("SET trimester=$1", "execute")}
    assert written == {1: (1, "due_soon")}, written


async def test_contract_a_birth_leaves_the_tracking_selection(monkeypatch):
    due = _row(due_game_day=100, conceived_game_day=10)
    fake = _install(monkeypatch, FakeDB(fetch=[due], fetchval=100))

    out = await preg.advance(5)

    assert out["births"][0]["game_day"] == 100
    assert len(fake.sql("fetch")) == 1, "the birth should not also be updated as tracking"
    event = fake.args_for("INSERT INTO maya_rp.events", "execute")[0]
    assert event[0] == 5 and "Birth —" in event[1]


async def test_run_tick_reports_a_crash_as_an_error(monkeypatch):
    seen = []
    monkeypatch.setattr("modules.pregnancy.error", lambda mod, msg: seen.append(msg))

    async def boom(*_a, **_k):
        raise RuntimeError("no mothers")

    _install(monkeypatch, FakeDB())
    monkeypatch.setattr("modules.pregnancy.Database.fetchval", boom)

    out = await preg.run_tick(5)

    assert "no mothers" in out["error"]
    assert any("no mothers" in m for m in seen), seen
