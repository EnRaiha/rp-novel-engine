"""Module review tests for modules/roll_theater.py (2026-10-03).

Every database call is stubbed, so these tests write nothing to the live
campaign: no rows in session 5, no rows anywhere else.
"""
from __future__ import annotations

import asyncio

import pytest

import modules.roll_theater as rt
from modules.roll_theater import TIER_ICONS, FLAVOR


def _run(coro):
    return asyncio.run(coro)


class _StubDB:
    """Answers the statements roll_theater issues, and records the writes."""

    def __init__(self, pool=None, bets=(), resources_row=None, game_day=10):
        self.pool = pool
        self.bets = list(bets)
        self.resources_row = resources_row
        self.game_day = game_day
        self.writes = []
        self.credits_writes = []

    async def fetchrow(self, sql, *args):
        if "roll_pools" in sql:
            return self.pool
        if "resources" in sql:
            self.credits_writes.append(args)
            return self.resources_row
        return None

    async def fetch(self, sql, *args):
        if "pool_bets" in sql:
            return self.bets
        return []

    async def fetchval(self, sql, *args):
        return self.game_day

    async def execute(self, sql, *args):
        self.writes.append((sql, args))
        return "INSERT 0 1"

    def wrote_credits(self):
        return self.credits_writes


# ── Telegram dice: one emoji, one d100 ──────────────────────────────────


def test_telegram_dice_maps_deterministically():
    """The dice emoji carries the entropy; the mapping must not roll again."""
    for face in range(1, 7):
        assert len({rt.parse_telegram_dice(face) for _ in range(50)}) == 1
        assert 1 <= rt.parse_telegram_dice(face) <= 100


def test_telegram_dice_band_midpoints():
    assert rt.parse_telegram_dice(1) == 3
    assert rt.parse_telegram_dice(2) == 23
    assert rt.parse_telegram_dice(3) == 50
    assert rt.parse_telegram_dice(4) == 70
    assert rt.parse_telegram_dice(5) == 88
    assert rt.parse_telegram_dice(6) == 98
    assert rt.tier_of(rt.parse_telegram_dice(1), 70) == "fumble"
    assert rt.tier_of(rt.parse_telegram_dice(6), 70) == "crit"


def test_telegram_dice_clamps_out_of_range():
    assert rt.parse_telegram_dice(0) == rt.parse_telegram_dice(1)
    assert rt.parse_telegram_dice(99) == rt.parse_telegram_dice(6)


# ── Ripples only follow the tiers that deserve one ──────────────────────


@pytest.fixture
def planted(monkeypatch):
    """Record every seed core.consequences.plant receives."""
    import core.consequences as consequences

    calls = []

    async def fake_plant(seed):
        calls.append(seed)

    monkeypatch.setattr(consequences, "plant", fake_plant)
    return calls


def test_ripple_skips_success_crit_and_unknown_tiers(planted):
    for tier in ("success", "crit", "raw", "bogus", ""):
        _run(rt.plant_ripple(5, "battle", tier, 70))
    assert planted == []


def test_ripple_plants_partial_and_fumble_with_weight(planted):
    _run(rt.plant_ripple(5, "battle", "partial", 70))
    _run(rt.plant_ripple(5, "battle", "fumble", 70))
    assert len(planted) == 2
    assert planted[0]["session_id"] == 5
    assert planted[0]["trigger"] == "battle_roll_partial"
    assert planted[0]["effects"][0]["delta"] == -1
    assert planted[1]["effects"][0]["delta"] == -2


def test_ripple_effect_names_a_live_column_and_a_delay(planted):
    """`morale` is not a resources column, and a missing delay never fires."""
    _run(rt.plant_ripple(5, "battle", "fumble", 70))
    _run(rt.plant_ripple(5, "economy", "fumble", 70))
    battle_effect = planted[0]["effects"][0]
    economy_effect = planted[1]["effects"][0]
    assert battle_effect["target"] == "aggregate_morale"
    assert economy_effect["target"] == "credits"
    for effect in (battle_effect, economy_effect):
        assert effect["delay_ticks"] <= 5, "a ripple nobody waits for never lands"


# ── Pool input validation ───────────────────────────────────────────────


def test_open_pool_rejects_empty_name_and_nonpositive_dc(monkeypatch):
    monkeypatch.setattr(rt, "Database", _StubDB())
    with pytest.raises(ValueError):
        _run(rt.open_pool(5, "   ", 70))
    with pytest.raises(ValueError):
        _run(rt.open_pool(5, "The King's Roll", 0))


# ── Pool resolution reports the money it moved ──────────────────────────


def test_resolve_pool_reports_net_house_keeps_and_crown_fee(monkeypatch):
    pool = {"id": 1, "pool_name": "The King's Roll", "credits_in_pool": 1000}
    bets = [
        {"id": 1, "bettor_name": "A", "bet_credits": 500, "bet_side": "king"},
        {"id": 2, "bettor_name": "B", "bet_credits": 500, "bet_side": "house"},
    ]
    stub = _StubDB(pool=pool, bets=bets, resources_row={"credits": 1500})
    monkeypatch.setattr(rt, "Database", stub)

    res = _run(rt.resolve_pool(5, king_won=True))

    assert res["paid"] == 900          # 500 x 1.8
    assert res["house_keeps"] == 100   # pool 1000 minus 900 paid
    assert res["crown_fee"] == 50
    assert res["crown_credited"] is True
    assert stub.wrote_credits() == [(50, 5)]


def test_resolve_pool_reports_an_underwater_pool_as_a_loss(monkeypatch):
    """A 1.8x payout on the winning side can exceed the whole pool."""
    pool = {"id": 2, "pool_name": "Upset", "credits_in_pool": 1000}
    bets = [
        {"id": 3, "bettor_name": "A", "bet_credits": 600, "bet_side": "king"},
        {"id": 4, "bettor_name": "B", "bet_credits": 400, "bet_side": "house"},
    ]
    stub = _StubDB(pool=pool, bets=bets, resources_row={"credits": 1500})
    monkeypatch.setattr(rt, "Database", stub)

    res = _run(rt.resolve_pool(5, king_won=True))

    assert res["paid"] == 1080
    assert res["house_keeps"] == -80   # the house lost 80, it did not keep 400
    assert res["crown_fee"] == 0
    assert stub.wrote_credits() == []


def test_resolve_pool_says_when_no_resources_row_exists(monkeypatch):
    pool = {"id": 3, "pool_name": "Empty Crown", "credits_in_pool": 1000}
    bets = [{"id": 5, "bettor_name": "A", "bet_credits": 500, "bet_side": "king"}]
    stub = _StubDB(pool=pool, bets=bets, resources_row=None)
    monkeypatch.setattr(rt, "Database", stub)
    logged = []
    monkeypatch.setattr(rt, "info", lambda *a: logged.append(a))

    res = _run(rt.resolve_pool(5, king_won=True))

    assert res["paid"] == 900
    assert res["crown_credited"] is False
    assert any("no resources row" in line[-1] for line in logged)


def test_resolve_pool_without_an_open_pool_reports_nothing_moved(monkeypatch):
    monkeypatch.setattr(rt, "Database", _StubDB(pool=None))
    assert _run(rt.resolve_pool(5, king_won=True)) == {"resolved": False}


# ── The fallback flavor line is taken, and said out loud ────────────────


def test_memorialize_reports_the_local_gen_failure(monkeypatch):
    stub = _StubDB(game_day=2253)
    monkeypatch.setattr(rt, "Database", stub)
    logged = []
    monkeypatch.setattr(rt, "info", lambda *a: logged.append(a))

    import modules.local_gen as local_gen

    async def boom(*args, **kwargs):
        raise RuntimeError("no GPU")

    monkeypatch.setattr(local_gen, "generate", boom)

    name = _run(rt.memorialize(3, "battle", 100, 100, 70))

    assert "the Battlefield" in name
    hall = [args for sql, args in stub.writes if "roll_hall" in sql]
    assert len(hall) == 1
    assert "Rolled 100 against 70" in hall[0][5]
    assert any("Local flavor line unavailable" in line[-1] for line in logged)


# ── The module's own contract ───────────────────────────────────────────


def test_every_tier_the_roller_can_return_has_an_icon_and_flavor():
    domains = list(FLAVOR) + ["unknown_domain"]
    seen = set()
    for dc in (10, 50, 70, 90):
        for total in range(1, 101):
            tier = rt.tier_of(total, dc)
            seen.add(tier)
            assert tier in TIER_ICONS
            for domain in domains:
                assert rt.flavor(domain, tier, total) != ""
    assert seen == {"fumble", "fail", "partial", "success", "crit"}
