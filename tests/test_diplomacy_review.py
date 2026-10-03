"""Module review tests for modules/diplomacy.py.

Defects covered:

1. `run_tick` was scoped NOWHERE. `treaties` and `envoys` carry no session of
   their own — they reach it through `factions` — and the tick:
     · expired every campaign's treaties (`UPDATE treaties … WHERE expires_at<NOW()`),
     · processed every campaign's envoys,
     · let a live-arc faction pick its treaty target from the frozen campaign
       (`SELECT … FROM factions WHERE id!=$1`),
     · decayed EVERY faction's reputation in the database every tick.
   All four carry the session now, through a subquery for the treaty rows.
2. `run_tick(session_id: int = 3)` defaulted to the frozen reference campaign
   while Config.SESSION_ID resolves to the active arc — and the module did not
   import Config at all.
3. `resolve_intent` answered `success: True` for an action it did not recognise:
   the unknown verb fell through to "contact made with nothing changed". It is
   refused by name now, with the supported actions listed.
4. The faction lookup matched `LIKE %name%` with `LIMIT 1` and no ORDER BY, so a
   partial name picked whichever row PostgreSQL returned first. It is ordered.
5. Both faction writes in `resolve_intent` matched on id alone.

Checked and found correct: the treaty existence checks are inherently in-session
because both ids come from a session-scoped list; the AI action roll is
frequency-scaled by elapsed game days; a war treaty is never signed twice; an
unrecognised `standing` contributes no envoy modifier; and the "declare war"
branch is idempotent because the improve branch checks the current standing.

No database: every test drives a fake Database.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import modules.diplomacy as dip


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
        monkeypatch.setattr("modules.diplomacy.Database." + name, getattr(fake, name))
    return fake


async def _tick(monkeypatch, success=True, **kw):
    if "fetchrow" not in kw:
        kw["fetchrow"] = {"last_tick_at": {"last_tick_at": "x"}}
    fake = _install(monkeypatch, FakeDB(**kw))
    monkeypatch.setattr("modules.diplomacy.calc_game_days", lambda when: 1.0)
    monkeypatch.setattr("modules.diplomacy.random.random", lambda: 0.0 if success else 1.0)
    await dip.run_tick(5)
    return fake


# ── 1 + 2. The tick is scoped, and defaults to the engine session ───────

async def test_the_tick_defaults_to_the_engine_session(monkeypatch):
    seen = []

    async def fetchrow(sql, *args):
        seen.append(args)
        return None

    _install(monkeypatch, FakeDB())
    monkeypatch.setattr("modules.diplomacy.Config.SESSION_ID", 77)
    monkeypatch.setattr("modules.diplomacy.Database.fetchrow", fetchrow)

    await dip.run_tick()

    assert seen == [(77,)]


async def test_the_treaty_expiry_is_bound_to_the_campaign(monkeypatch):
    fake = await _tick(monkeypatch)

    sql = [s for s in fake.sql("execute") if "UPDATE treaties" in s][0]
    assert sql.count("SELECT id FROM factions WHERE session_id=$1") == 2, sql
    assert fake.args_for("UPDATE treaties", "execute")[0] == (5,)


async def test_the_envoy_pass_is_bound_to_the_sending_faction(monkeypatch):
    started = datetime.now(timezone.utc) - timedelta(days=400)
    envoy = {"id": 1, "faction_id": 2, "target_faction_id": 3, "started_at": started,
             "duration_days": 1, "status": "active", "standing": "friendly"}
    fake = await _tick(monkeypatch, fetch=[envoy])

    sql = [s for s in fake.sql("fetch") if "envoys" in s][0]
    assert "f.session_id=$1" in sql
    assert fake.args_for("envoys", "fetch")[0] == (5,)


async def test_the_ai_target_list_is_bound_to_the_campaign(monkeypatch):
    faction = {"id": 2, "name": "Iron Concord", "reputation": 0}
    fake = await _tick(monkeypatch, fetch={"envoys": [], "*": [faction]})

    targets = [s for s in fake.sql("fetch") if "id!=$1" in s]
    assert targets and "session_id=$2" in targets[0], targets
    assert fake.args_for("id!=$1", "fetch")[0] == (2, 5)


async def test_the_reputation_drift_is_bound_to_the_campaign(monkeypatch):
    fake = await _tick(monkeypatch)

    drift = [s for s in fake.sql("execute") if "sign(reputation)" in s][0]
    assert "session_id=$1" in drift, drift
    assert fake.args_for("sign(reputation)", "execute")[0] == (5,)


async def test_an_envoy_that_has_not_finished_is_left_alone(monkeypatch):
    started = datetime.now(timezone.utc)
    envoy = {"id": 1, "faction_id": 2, "target_faction_id": 3, "started_at": started,
             "duration_days": 30, "status": "active", "standing": "neutral"}
    fake = await _tick(monkeypatch, fetch=[envoy])

    assert not [s for s in fake.sql("execute") if "UPDATE envoys" in s]


async def test_a_due_envoy_resolves_and_moves_the_standing(monkeypatch):
    started = datetime.now(timezone.utc) - timedelta(days=90)
    envoy = {"id": 1, "faction_id": 2, "target_faction_id": 3, "started_at": started,
             "duration_days": 1, "status": "active", "standing": "friendly"}
    fake = await _tick(monkeypatch, fetch=[envoy], success=True)

    resolved = fake.args_for("UPDATE envoys", "execute")
    assert resolved and resolved[0][0] == "completed"
    moved = fake.args_for("UPDATE factions SET standing=$1, reputation=reputation+5", "execute")
    assert moved and moved[0] == ("allied", 3, 5)


async def test_the_tick_stops_when_the_session_has_no_clock(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchrow=None))

    await dip.run_tick(5)

    assert not fake.calls[1:], "the tick ran without a last_tick_at"


# ── 3. An unknown action is refused ─────────────────────────────────────

@pytest.mark.parametrize("action", ["befriend", "sabotage", "alliance?", ""])
async def test_an_unknown_action_is_refused_not_reported_as_success(monkeypatch, action):
    fake = _install(monkeypatch, FakeDB(fetchrow={"id": 1, "name": "Iron Concord",
                                                  "standing": "neutral", "reputation": 0}))

    out = await dip.resolve_intent(5, action, "Iron Concord")

    assert out["success"] is False
    assert "Unknown diplomatic action" in out["narrative_hook"]
    assert not fake.sql("execute")


async def test_a_known_action_still_reaches_the_faction(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchrow={"id": 1, "name": "Iron Concord",
                                                  "standing": "hostile", "reputation": 0}))

    out = await dip.resolve_intent(5, "ally", "Iron Concord")

    assert out["success"] is True and out["standing_change"] == "allied"
    written = fake.args_for("SET standing=$1", "execute")[0]
    assert written == ("allied", 1, 5)


@pytest.mark.parametrize("action", ["war", "declare war", "declare_war"])
async def test_declaring_war_is_understood_in_every_spelling(monkeypatch, action):
    fake = _install(monkeypatch, FakeDB(fetchrow={"id": 1, "name": "Iron Concord",
                                                  "standing": "neutral", "reputation": 0}))

    out = await dip.resolve_intent(5, action, "Iron Concord")

    assert out["standing_change"] == "enemy"
    assert fake.args_for("SET standing='enemy'", "execute")[0] == (1, 5)


# ── 4 + 5. The lookup and the writes ────────────────────────────────────

async def test_the_faction_lookup_is_ordered_and_session_scoped(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchrow=None))

    await dip.resolve_intent(5, "talk", "Iron")

    sql = fake.sql("fetchrow")[0]
    assert "session_id=$1" in sql and "ORDER BY id LIMIT 1" in sql
    assert fake.args_for("factions", "fetchrow")[0] == (5, "%Iron%")


async def test_a_missing_faction_says_so(monkeypatch):
    _install(monkeypatch, FakeDB(fetchrow=None))

    out = await dip.resolve_intent(5, "talk", "Nobody")

    assert out["success"] is False and "No faction found" in out["narrative_hook"]


async def test_an_already_allied_faction_is_not_re_written(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchrow={"id": 1, "name": "Iron Concord",
                                                  "standing": "allied", "reputation": 0}))

    out = await dip.resolve_intent(5, "ally", "Iron Concord")

    assert out["standing_change"] == "allied"
    assert not fake.sql("execute"), "an unchanged standing was written anyway"
