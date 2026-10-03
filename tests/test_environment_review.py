"""Module review tests for modules/environment.py.

No new defect found in this pass. The row says so and names what was checked.

Checked and found correct, and the docstrings record the earlier pass:
- `generate_details` reads morale with an explicit NULL test, so a crew at zero is
  described as mutinous rather than as one that runs like clockwork;
- the recent-combat read is session-scoped and the death tells are reachable
  because the casualty count is read;
- the pacing read is session-scoped and NULL tension is not an error;
- the location tells only fire for a catalogued location, so an unknown or missing
  location adds nothing rather than crashing;
- the tell list is shuffled and capped at four;
- `current_weather` is a pure function of the game day, with the modifier drawn
  from its own table.

Reported to the lead: `TELLS["prosperity"]` is written and never read, so those
three tells can never appear. It is a missing condition (what would mark a
prosperous ship?), not a broken one, so the table stays.

No database: every test drives a fake Database.
"""
from __future__ import annotations

import pytest

import modules.environment as env


class FakeDB:
    def __init__(self, fetchval=None, fetchrow=None):
        self.fetchval_value = fetchval
        self.fetchrow_value = fetchrow
        self.calls = []

    async def fetchval(self, sql, *args):
        self.calls.append(("fetchval", " ".join(sql.split()), args))
        return self.fetchval_value

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", " ".join(sql.split()), args))
        return self.fetchrow_value

    def sql(self, kind=None):
        return [c[1] for c in self.calls if kind is None or c[0] == kind]


def _install(monkeypatch, fake):
    for name in ("fetchval", "fetchrow"):
        monkeypatch.setattr("modules.environment.Database." + name, getattr(fake, name))
    return fake


def _row(sql, **over):
    """One answer for both fetchrow calls: counts and tension in one dict.

    The module reads `fights`/`casualties` from the combat query and `tension`
    from the pacing query, and the fake answers both.
    """
    row = {"fights": 0, "casualties": 0, "tension": 0}
    row.update(over)
    return row


async def test_morale_bands_pick_their_own_tell(monkeypatch):
    for morale, expected in ((90, env.TELLS["morale"][0][2]),
                             (60, env.TELLS["morale"][1][2]),
                             (30, env.TELLS["morale"][2][2]),
                             (10, env.TELLS["morale"][3][2])):
        _install(monkeypatch, FakeDB(fetchval=morale, fetchrow=_row("x")))
        monkeypatch.setattr(env.random, "choice", lambda seq: seq[0])
        monkeypatch.setattr(env.random, "shuffle", lambda seq: None)

        out = await env.generate_details("nowhere", 5)

        assert out[0] in expected, (morale, out)


async def test_a_zero_morale_ship_is_described_as_mutinous_not_routine(monkeypatch):
    _install(monkeypatch, FakeDB(fetchval=0, fetchrow=_row("x")))
    monkeypatch.setattr(env.random, "choice", lambda seq: seq[0])

    out = await env.generate_details("nowhere", 5)

    assert out[0] == env.TELLS["morale"][3][2][0]


async def test_a_recent_fight_with_casualties_adds_both_tells(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchval=50,
                                        fetchrow={"fights": 2, "casualties": 3, "tension": 0}))
    monkeypatch.setattr(env.random, "choice", lambda seq: seq[0])
    monkeypatch.setattr(env.random, "shuffle", lambda seq: None)

    out = await env.generate_details("nowhere", 5)

    assert env.TELLS["combat"][0][2][0] in out
    assert env.TELLS["death"][0][2][0] in out
    assert all("session_id=$1" in s for s in fake.sql())


async def test_a_fight_without_casualties_adds_no_memorial(monkeypatch):
    _install(monkeypatch, FakeDB(fetchval=50,
                                 fetchrow={"fights": 1, "casualties": 0, "tension": 0}))
    monkeypatch.setattr(env.random, "choice", lambda seq: seq[0])
    monkeypatch.setattr(env.random, "shuffle", lambda seq: None)

    out = await env.generate_details("nowhere", 5)

    assert env.TELLS["combat"][0][2][0] in out
    assert env.TELLS["death"][0][2][0] not in out


async def test_high_tension_adds_the_tension_tell(monkeypatch):
    _install(monkeypatch, FakeDB(fetchval=50,
                                 fetchrow={"fights": 0, "casualties": 0, "tension": 8}))
    monkeypatch.setattr(env.random, "choice", lambda seq: seq[0])
    monkeypatch.setattr(env.random, "shuffle", lambda seq: None)

    out = await env.generate_details("nowhere", 5)

    assert env.TELLS["tension"][0][2][0] in out


async def test_a_catalogued_location_adds_its_own_tell(monkeypatch):
    _install(monkeypatch, FakeDB(fetchval=50,
                                 fetchrow={"fights": 0, "casualties": 0, "tension": 0}))
    monkeypatch.setattr(env.random, "choice", lambda seq: seq[0])
    monkeypatch.setattr(env.random, "shuffle", lambda seq: None)

    out = await env.generate_details("brig", 5)

    assert env.LOCATION_TELLS["brig"][0] in out


async def test_an_unknown_location_adds_nothing(monkeypatch):
    _install(monkeypatch, FakeDB(fetchval=50,
                                 fetchrow={"fights": 0, "casualties": 0, "tension": 0}))
    monkeypatch.setattr(env.random, "choice", lambda seq: seq[0])
    monkeypatch.setattr(env.random, "shuffle", lambda seq: None)

    out = await env.generate_details(None, 5)

    # morale 50 lands in the routine band, and no other condition fires
    assert out == [env.TELLS["morale"][1][2][0]]
    assert out == ["Routine. The ship runs like clockwork."]


async def test_the_details_are_capped_at_four(monkeypatch):
    _install(monkeypatch, FakeDB(fetchval=90,
                                 fetchrow={"fights": 3, "casualties": 9, "tension": 9}))

    out = await env.generate_details("garden", 5)

    assert len(out) == 4


def test_contract_the_weather_is_deterministic_per_day():
    first = env.current_weather(5, 12)
    second = env.current_weather(5, 12)

    assert first == second
    assert first["weather"] in env.WEATHER
    assert first["voyage_mod"] == env.WEATHER_MOD[first["weather"]]


def test_contract_every_weather_has_a_modifier():
    assert set(env.WEATHER) == set(env.WEATHER_MOD)
    assert env.current_weather(None, 0)["game_day"] == 0


def test_contract_every_tell_band_is_ordered_and_bounded():
    for lo, hi, tells in env.TELLS["morale"]:
        assert lo < hi
        assert tells
    bands = [(lo, hi) for lo, hi, _ in env.TELLS["morale"]]
    assert bands == sorted(bands, reverse=True)


async def test_contract_run_tick_reports_todays_weather(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchval=7))

    out = await env.run_tick(5)

    assert out["status"] == "on_demand" and out["game_day"] == 7
    assert out["weather"] == env.current_weather(5, 7)["weather"]
    assert fake.sql("fetchval")[0].endswith("WHERE id=$1")
