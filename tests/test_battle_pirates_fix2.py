"""battle, pirates fix 2: power fits its column, and bounty, hoard and raid money move once and never below zero.

Unit tests stub `Database` and reach no database. Database tests write scratch session ids only (900-999),
pass the id explicitly, and pin `Config.SESSION_ID` to it. Sessions 3 and 5 are not touched.
"""
from __future__ import annotations

import asyncio
import pathlib
import random
import sys
import types
from decimal import Decimal

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest_asyncio  # noqa: E402

from core.config import Config  # noqa: E402
from core.db import Database  # noqa: E402
from modules import battle, pirates  # noqa: E402
from modules.battle import BattleEngine, BattleFleet, BattleShip, BattleState  # noqa: E402


# ── battle: unit tests on a stub Database ────────────────────────────────

class _Recorder:
    """Stand-in for `modules.battle.Database`: records every statement, returns canned rows."""

    def __init__(self, fetch=None, fetchval=None, fetchrow=None):
        self.fetch_rows = fetch if fetch is not None else []
        self.fetchval_value = fetchval
        self.fetchrow_rows = fetchrow or {}
        self.calls = []

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", " ".join(sql.split()), args))
        return self.fetch_rows

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", " ".join(sql.split()), args))
        for needle, value in self.fetchrow_rows.items():
            if needle in sql:
                return value
        return None

    async def fetchval(self, sql, *args):
        self.calls.append(("fetchval", " ".join(sql.split()), args))
        return self.fetchval_value

    async def execute(self, sql, *args):
        self.calls.append(("execute", " ".join(sql.split()), args))
        return "UPDATE 1"

    def args_for(self, needle, kind=None):
        return [c[2] for c in self.calls if needle in c[1] and (kind is None or c[0] == kind)]


def _stub_battle_db(monkeypatch, recorder):
    for name in ("fetch", "fetchrow", "fetchval", "execute"):
        monkeypatch.setattr("modules.battle.Database." + name, getattr(recorder, name))

    async def no_emit(*args, **kwargs):
        return None

    monkeypatch.setattr("modules.battle.EventBus.emit", no_emit)
    return recorder


def _ship(ship_id, rating):
    return BattleShip(id=ship_id, name=f"Hull {ship_id}", ship_type="frigate", hull=100, shield=50,
                      speed=10, evasion=0.1, combat_rating=rating, role="line")


async def test_resolve_binds_whole_capped_power(scratch_session, monkeypatch):
    rec = _stub_battle_db(monkeypatch, _Recorder())
    state = BattleState(
        battle_id=11, player=BattleFleet(faction="Setia Empire", ships=[_ship(1, 100.7), _ship(2, 3e9)]),
        enemy=BattleFleet(faction="Corsairs", ships=[]), terrain={}, session_id=scratch_session)

    await BattleEngine._resolve(state)

    _, player_power, enemy_power, battle_id = rec.args_for("UPDATE combat_results SET outcome", "execute")[0]
    assert isinstance(player_power, int) and isinstance(enemy_power, int), (player_power, enemy_power)
    assert player_power == 2_147_483_647 and enemy_power == 0 and battle_id == 11


async def test_init_binds_whole_power(scratch_session, monkeypatch):
    rec = _stub_battle_db(monkeypatch, _Recorder(fetchrow={"INSERT INTO combat_results": {"id": 11}}))
    fleet = BattleFleet(faction="Any", ships=[_ship(1, 10.5)])

    async def make_fleet(*args, **kwargs):
        return fleet

    async def save(*args, **kwargs):
        return None

    monkeypatch.setattr(BattleEngine, "_make_fleet", make_fleet)
    monkeypatch.setattr(BattleEngine, "_make_enemy_fleet", make_fleet)
    monkeypatch.setattr(BattleEngine, "_save", save)

    await BattleEngine.init(scratch_session, [1], "Corsairs", terrain_id=1)

    _, player_power, enemy_power = rec.args_for("INSERT INTO combat_results", "fetchrow")[0]
    assert isinstance(player_power, int) and isinstance(enemy_power, int), (player_power, enemy_power)
    assert player_power == 10 and enemy_power == 10


async def test_tick_binds_power_inside_the_column(scratch_session, monkeypatch):
    rec = _stub_battle_db(monkeypatch, _Recorder(
        fetch=[{"id": 1, "opponent_faction": "Corsairs", "phase": "clash"}], fetchval=3_000_000_000))
    monkeypatch.setattr(random, "random", lambda: 0.2)    # the war engages, no commander injury

    out = await battle.run_tick(scratch_session)

    assert out == {"engagements": 1}, out
    row = rec.args_for("INSERT INTO maya_rp.combat_results", "execute")[0]
    assert row[3] == 2_147_483_647 and row[4] == 2_147_483_647, row


def test_power_total_is_whole_and_inside_the_column():
    assert battle._power_total([_ship(1, 100.7), _ship(2, 0.9)]) == 101
    assert battle._power_total([_ship(1, 2_000_000_000.0), _ship(2, 10_999_633.0)]) == 2_010_999_633
    assert battle._power_total([_ship(1, 3e9)]) == battle.INT32_MAX
    assert battle._power_total([_ship(1, -5.0)]) == 0
    assert battle._power_total([]) == 0


# ── pirates: database tests on a scratch session ─────────────────────────

async def _wipe(session_id):
    await Database.execute("DELETE FROM maya_rp.pirate_alerts WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.factions WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.resources WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", session_id)


@pytest_asyncio.fixture
async def sid(scratch_session, monkeypatch):
    """A scratch session on game day 10 with no factions and no treasury row."""
    monkeypatch.setattr(Config, "SESSION_ID", scratch_session)
    await Database.init()
    await _wipe(scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status, game_day) "
        "VALUES ($1, 'battle pirates fix2', 'active', 10)", scratch_session)
    try:
        yield scratch_session
    finally:
        await _wipe(scratch_session)
        await Database.close()


async def _faction(session_id, tag, pirate, status="active", power=1000, treasury=0, strength="1.0"):
    """Faction names are unique across sessions, so the scratch id suffixes the name."""
    return await Database.fetchval(
        "INSERT INTO maya_rp.factions "
        "(session_id, name, is_pirate, status, pirate_fleet_power, treasury, economic_strength) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id",
        session_id, f"{tag} (fix2 {session_id})", pirate, status, power, treasury, Decimal(strength))


async def _base(faction_id, treasury, name):
    return await Database.fetchval(
        "INSERT INTO maya_rp.pirate_bases (faction_id, name, treasury, defenses, status) "
        "VALUES ($1,$2,$3,0,'active') RETURNING id", faction_id, name, treasury)


async def _bounty(faction_id, amount):
    return await Database.fetchval(
        "INSERT INTO maya_rp.pirate_bounties (pirate_faction_id, bounty_amount) VALUES ($1,$2) RETURNING id",
        faction_id, amount)


async def _fund(session_id, credits):
    await Database.execute("DELETE FROM maya_rp.resources WHERE session_id=$1", session_id)
    await Database.execute(
        "INSERT INTO maya_rp.resources (session_id, fuel, alloys, credits, population) "
        "VALUES ($1, 0, 0, $2, 0)", session_id, credits)


async def _credits(session_id):
    return await Database.fetchval("SELECT credits FROM maya_rp.resources WHERE session_id=$1", session_id)


async def _claimed_by(bounty_id):
    return await Database.fetchval("SELECT claimed_by FROM maya_rp.pirate_bounties WHERE id=$1", bounty_id)


async def _warm_pool(connections=4):
    """Open several pool connections now: a cold pool serves the second caller after the first one wrote."""
    await asyncio.gather(*(Database.fetchval("SELECT pg_sleep(0.1)") for _ in range(connections)))


def _slow_fetchrow(monkeypatch, needle):
    """Delay every `fetchrow` whose SQL holds `needle`, so two callers read before either writes."""
    real = Database.fetchrow

    async def slow(sql, *args):
        if needle in sql:
            await asyncio.sleep(0.2)
        return await real(sql, *args)

    monkeypatch.setattr(pirates.Database, "fetchrow", slow)


def _rng(monkeypatch, **overrides):
    """Replace `pirates.random` with a stub, so the patch does not reach the module every other caller shares."""
    stub = types.SimpleNamespace(random=random.random, randint=random.randint, choice=random.choice)
    for name, fn in overrides.items():
        setattr(stub, name, fn)
    monkeypatch.setattr(pirates, "random", stub)


async def _defeated_den_with_bounty(session_id, amount=2_000_000):
    den = await _faction(session_id, "Den", True, status="defeated")
    setia = await _faction(session_id, "Setia Empire", False)
    bounty = await _bounty(den, amount)
    return den, setia, bounty


async def test_a_second_claim_pays_nothing(sid):
    den, setia, bounty = await _defeated_den_with_bounty(sid)
    await _fund(sid, 0)

    first = await pirates.claim_bounty(sid, den)
    second = await pirates.claim_bounty(sid, den)

    assert first == {"success": True, "credits": 2_000_000}, first
    assert second["success"] is False and second["error"] == "No bounty available.", second
    assert await _credits(sid) == 2_000_000
    assert await _claimed_by(bounty) == setia


async def test_two_bounties_are_claimed_one_per_call(sid):
    den, setia, _ = await _defeated_den_with_bounty(sid, 1_000_000)
    await _bounty(den, 3_000_000)
    await _fund(sid, 0)

    paid = [(await pirates.claim_bounty(sid, den)).get("credits") for _ in range(3)]

    assert paid == [1_000_000, 3_000_000, None], paid
    assert await _credits(sid) == 4_000_000


async def test_a_non_pirate_faction_is_refused(sid):
    other = await _faction(sid, "Merchants", False, status="defeated")
    await _faction(sid, "Setia Empire", False)
    bounty = await _bounty(other, 2_000_000)
    await _fund(sid, 0)

    out = await pirates.claim_bounty(sid, other)

    assert out["success"] is False and "Not a pirate faction" in out["error"], out
    assert await _credits(sid) == 0
    assert await _claimed_by(bounty) is None


async def test_no_claimant_pays_nothing(sid):
    den = await _faction(sid, "Den", True, status="defeated")
    bounty = await _bounty(den, 2_000_000)
    await _fund(sid, 0)

    out = await pirates.claim_bounty(sid, den)

    assert out["success"] is False and "No Setia faction" in out["error"], out
    assert await _credits(sid) == 0
    assert await _claimed_by(bounty) is None


async def test_two_claims_at_once_pay_once(sid, monkeypatch):
    den, setia, bounty = await _defeated_den_with_bounty(sid)
    await _fund(sid, 0)
    await _warm_pool()
    _slow_fetchrow(monkeypatch, "bounty_amount")

    results = await asyncio.gather(pirates.claim_bounty(sid, den), pirates.claim_bounty(sid, den))

    assert sorted(r["success"] for r in results) == [False, True], results
    assert await _credits(sid) == 2_000_000
    assert await _claimed_by(bounty) == setia


async def test_two_raids_at_once_credit_the_hoard_once(sid, monkeypatch):
    den = await _faction(sid, "Den", True)
    base = await _base(den, 60_000_000, "fix2 Den Fringe")
    await _fund(sid, 0)
    _rng(monkeypatch, random=lambda: 0.0)
    await _warm_pool()
    _slow_fetchrow(monkeypatch, "pirate_bases")

    results = await asyncio.gather(
        pirates.raid_pirate_base(sid, base, attack_power=10_000_000),
        pirates.raid_pirate_base(sid, base, attack_power=10_000_000))

    assert sorted(r["success"] for r in results) == [False, True], results
    assert await _credits(sid) == 60_000_000
    assert await Database.fetchval("SELECT status FROM maya_rp.pirate_bases WHERE id=$1", base) == "destroyed"


async def test_take_credits_never_goes_below_zero(sid):
    await _fund(sid, 1000)
    assert await pirates._take_credits(sid, 50_000) == 1000
    assert await _credits(sid) == 0

    await _fund(sid, -50)
    assert await pirates._take_credits(sid, 50_000) == 0
    assert await _credits(sid) == -50

    await _fund(sid, 1000)
    taken = await asyncio.gather(pirates._take_credits(sid, 800), pirates._take_credits(sid, 800))
    assert set(taken) == {800, 200}, taken
    assert await _credits(sid) == 0

    await Database.execute("DELETE FROM maya_rp.resources WHERE session_id=$1", sid)
    assert await pirates._take_credits(sid, 800) is None


class _StaleBases:
    """`pirates.Database` stand-in: the base list is a stale snapshot, everything else reaches the database."""

    def __init__(self, bases):
        self.bases = bases

    async def fetch(self, sql, *args):
        if "pirate_bases" in sql:
            return self.bases
        return await Database.fetch(sql, *args)

    async def fetchrow(self, sql, *args):
        return await Database.fetchrow(sql, *args)

    async def fetchval(self, sql, *args):
        return await Database.fetchval(sql, *args)

    async def execute(self, sql, *args):
        return await Database.execute(sql, *args)


async def test_den_feeding_refuses_a_stale_snapshot(sid, monkeypatch):
    den = await _faction(sid, "Den", True)
    base = await _base(den, pirates.HOARD_FLOOR, "fix2 Den Floor")
    feeder = await _faction(sid, "Feeder", False)
    stale = [{"id": base, "treasury": pirates.HOARD_FLOOR + 10_000_000}]
    monkeypatch.setattr(pirates, "Database", _StaleBases(stale))
    _rng(monkeypatch, random=lambda: 0.0, randint=lambda a, b: 8_000_000)

    await pirates._den_feeding(sid)

    assert await Database.fetchval(
        "SELECT treasury FROM maya_rp.pirate_bases WHERE id=$1", base) == pirates.HOARD_FLOOR
    assert await Database.fetchval("SELECT treasury FROM maya_rp.factions WHERE id=$1", feeder) == 0
    assert await Database.fetchval("SELECT COUNT(*) FROM maya_rp.pirate_alerts WHERE session_id=$1", sid) == 0
