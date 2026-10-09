"""Pirate module review tests — one per defect found reading modules/pirates.py.

The module had one systematic defect and three local ones.

1. Session scope, everywhere. `pirate_bases` and `pirate_bounties` carry no
   session of their own; they reach it through `faction_id`, and `factions`
   carries `session_id`. Every read and write that skipped that column reached
   the frozen reference campaign from a live tick:
     · a live tick rebuilt the reference campaign's dens and filed the new
       hulls under the live session,
     · the 40M hoard floor was applied to both campaigns' pirate treasuries,
     · the sector raiders poured a reference-campaign hoard into a live-arc
       faction's treasury,
     · the strongest pirate of EITHER campaign raided the live arc and banked
       the loot,
     · a live-arc bounty claim could collect the reference campaign's 2,000,000C,
     · a live-arc raid could seize a reference-campaign base's hoard.
2. `run_tick` defaulted to session 3 — the frozen reference — while
   Config.SESSION_ID resolves to the active arc, and a crash was printed
   rather than returned to the orchestrator that counts failures.
3. `_generate_loot` fell back to the patrol table for any unknown threat, so
   "armada" loot could pay out as "patrol" (5K-25K instead of 500K-2M).
4. `_attack` handed the raid's own loot dict to `_apply_loot`, which CREDITS
   the treasury: a raid that also rolled items paid the victim back.
5. `claim_bounty` and `raid_pirate_base` marked the kill before checking that
   the credit landed.
6. `salvage_ship` returned zeros for an unknown class with nothing said, which
   is indistinguishable from "the wreck yielded nothing".

Every test drives a fake Database: nothing here writes to the live campaign.
"""
import random

import pytest

import modules.pirates as pirates


class FakeDB:
    def __init__(self, fetch=None, rows=None, fetchval=None, execute_tag="UPDATE 1"):
        self.fetch_rows = fetch if fetch is not None else []
        self.rows = rows or []            # ordered (marker, value) for fetchrow
        self.fetchval_value = fetchval
        self.execute_tag = execute_tag
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
        for marker, value in self.rows:
            if marker in sql:
                return value
        return None

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
        monkeypatch.setattr("modules.pirates.Database." + name, getattr(fake, name))
    return fake


def _quiet(monkeypatch):
    seen = []
    monkeypatch.setattr("modules.pirates.info", lambda mod, msg: seen.append(msg))
    return seen


# ── 2. run_tick: the live session, and a failure the orchestrator can see ──

async def test_run_tick_defaults_to_the_engine_session_not_the_frozen_id(monkeypatch):
    seen = []

    async def step(session_id):
        seen.append(session_id)

    for name in ("_spawn", "_attack", "_alerts", "_hoard_tick", "_den_feeding", "_den_regen"):
        monkeypatch.setattr("modules.pirates." + name, step)
    monkeypatch.setattr("modules.pirates.Config.SESSION_ID", 77)

    out = await pirates.run_tick()

    assert seen == [77] * 6, seen
    assert out == {"session_id": 77}


async def test_run_tick_returns_an_error_dict_the_orchestrator_counts(monkeypatch):
    async def boom(session_id):
        raise RuntimeError("den on fire")

    monkeypatch.setattr("modules.pirates._spawn", boom)
    monkeypatch.setattr("modules.pirates.error", lambda mod, msg: None)

    out = await pirates.run_tick(5)

    assert isinstance(out, dict) and "den on fire" in out["error"]


# ── 1. Session scope across the module ───────────────────────────────────

async def test_den_regen_reads_bases_through_their_faction_session(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[]))
    await pirates._den_regen(5)

    sql = [s for s in fake.sql("fetch") if "pirate_bases" in s][0]
    assert "JOIN maya_rp.factions" in sql and "f.session_id=$1" in sql
    assert fake.args_for("pirate_bases", "fetch")[0] == (5,)


async def test_den_regen_counts_leaders_in_this_session(monkeypatch):
    base = {"id": 1, "faction_id": 6, "regen_per_tick": 1, "fleet_cap": 300, "name": "Den Base"}
    fake = _install(monkeypatch, FakeDB(fetch=[base], fetchval=0))
    await pirates._den_regen(5)

    leader_sql = [s for s in fake.sql("fetchval") if "characters" in s][0]
    assert "session_id=$2" in leader_sql
    assert fake.args_for("characters")[0] == (6, 5)


async def test_hoard_tick_scopes_the_floor_and_the_bases(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[], fetchval=0))
    monkeypatch.setattr(pirates.random, "random", lambda: 1.0)

    await pirates._hoard_tick(5)

    floor_sql, floor_args = fake.calls[0][1], fake.calls[0][2]
    assert "session_id=$2" in floor_sql
    assert floor_args == (pirates.HOARD_FLOOR, 5)
    bases = [s for s in fake.sql("fetch") if "pirate_bases" in s][0]
    assert "f.session_id=$1" in bases


async def test_hoard_rebuild_stays_in_its_session(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[], fetchval=2))
    monkeypatch.setattr(pirates.random, "random", lambda: 0.0)
    monkeypatch.setattr("modules.pirates.Database.fetchrow",
                        FakeDB(rows=[("pirate_zones", {"system_id": 9})]).fetchrow)

    await pirates._hoard_tick(5)

    count = [s for s in fake.sql("fetchval") if "COUNT(*)" in s][0]
    assert "f.session_id=$1" in count
    assert fake.args_for("COUNT(*)")[0] == (5,)
    revive = [a for s, a in
              [(c[1], c[2]) for c in fake.calls if c[0] == "execute"]
              if "status='active'" in s and "treasury=$1" in s][0]
    assert revive[0] == pirates.HOARD_FLOOR and revive[1] == 5


async def test_den_feeding_moves_money_inside_one_campaign(monkeypatch):
    fake = _install(monkeypatch, FakeDB(
        rows=[("FROM maya_rp.factions", {"id": 6})],
        fetch={"FROM maya_rp.pirate_bases": [{"id": 1, "treasury": pirates.HOARD_FLOOR + 10_000_000}],
               "*": [{"id": 9, "name": "Iron Concord", "economic_strength": 1.0}]}))
    monkeypatch.setattr(pirates.random, "random", lambda: 0.0)      # the feeder bites
    monkeypatch.setattr(pirates.random, "randint", lambda a, b: a)  # smallest bite

    await pirates._den_feeding(5)

    den = [s for s in fake.sql("fetchrow") if "is_pirate=true" in s and "factions" in s]
    assert den and "session_id=$1" in den[0]
    assert fake.args_for("is_pirate=true", "fetchrow")[0] == (5,)
    # the feeders and their hoard must be the same campaign as the den
    feeders = [s for s in fake.sql("fetch") if "is_pirate=false" in s]
    assert feeders and "session_id=$1" in feeders[0], feeders
    assert fake.args_for("is_pirate=false", "fetch")[0] == (5,)
    assert fake.args_for("treasury=treasury-$1", "execute")[0] == (2_000_000, 1)
    assert fake.args_for("treasury=treasury+$1", "execute")[0] == (2_000_000, 9)


async def test_spawn_fleet_banks_power_on_this_campaigns_faction(monkeypatch):
    seen = _quiet(monkeypatch)
    fake = _install(monkeypatch, FakeDB(
        rows=[("pirate_fleet_templates", {"name": "Wolf Pack", "composition": {}, "total_power": 10})],
        execute_tag="UPDATE 1"))

    await pirates._spawn_fleet(5, 12, "Wolf Pack")

    pick = [s for s in fake.sql("fetchrow") if "is_pirate=true" in s][0]
    assert "session_id=$1" in pick
    assert fake.args_for("is_pirate=true", "fetchrow")[0] == (5,)
    assert any("no pirate faction" in m for m in seen), seen


async def test_attack_picks_a_raider_from_this_session(monkeypatch):
    fake = _install(monkeypatch, FakeDB(
        fetch=[{"id": 3, "system_name": "Kappa", "population": 1000}],
        rows=[("is_pirate=true", {"id": 6, "pirate_fleet_power": 10000})],
        execute_tag="UPDATE 0"))
    monkeypatch.setattr(pirates.random, "random", lambda: 0.99)   # no raid happens
    monkeypatch.setattr(pirates, "_generate_loot",
                        lambda *a, **k: _async({"credits": 0, "resources": {}, "items": [], "artifacts": []}))

    await pirates._attack(5)

    pick = [s for s in fake.sql("fetchrow") if "is_pirate=true" in s][0]
    assert "session_id=$1" in pick


async def test_alerts_sums_only_this_sessions_pirates(monkeypatch):
    fake = _install(monkeypatch, FakeDB(rows=[("SUM(pirate_fleet_power)", {"t": 6000})]))

    await pirates._alerts(5)

    sql = [s for s in fake.sql("fetchrow") if "SUM(pirate_fleet_power)" in s][0]
    assert "session_id=$1" in sql
    assert fake.args_for("SUM(pirate_fleet_power)")[0] == (5,)
    assert any("CRISIS" in a[1] for a in fake.args_for("INSERT INTO pirate_alerts", "execute"))


# ── 4. A raid must not pay its victim back ───────────────────────────────

async def test_raid_does_not_credit_the_victim_with_the_raids_own_loot(monkeypatch):
    _quiet(monkeypatch)
    fake = _install(monkeypatch, FakeDB(
        fetch=[{"id": 3, "system_name": "Kappa", "population": 1000}],
        rows=[("is_pirate=true", {"id": 6, "pirate_fleet_power": 10000}),
              ("FROM maya_rp.pirate_bases", {"id": 1})],
        execute_tag="UPDATE 1"))
    monkeypatch.setattr(pirates.random, "random", lambda: 0.0)     # raid succeeds
    monkeypatch.setattr(pirates, "_generate_loot", lambda *a, **k: _async(
        {"credits": 50000, "resources": {}, "items": ["spice"], "artifacts": []}))
    applied = []

    async def fake_apply(session_id, loot):
        applied.append((session_id, loot))

    monkeypatch.setattr(pirates, "_apply_loot", fake_apply)
    taken = _patch_take_credits(monkeypatch, 50000)
    _patch_decision_models(monkeypatch)

    await pirates._attack(5)

    assert taken == [(5, 50000)]
    assert applied and applied[0][1]["credits"] == 0, "the raid's credits were handed back"
    assert applied[0][1]["items"] == ["spice"]


async def test_raid_is_not_recorded_as_taken_when_no_treasury_row(monkeypatch):
    seen = _quiet(monkeypatch)
    fake = _install(monkeypatch, FakeDB(
        fetch=[{"id": 3, "system_name": "Kappa", "population": 1000}],
        rows=[("is_pirate=true", {"id": 6, "pirate_fleet_power": 10000})]))
    monkeypatch.setattr(pirates.random, "random", lambda: 0.0)
    monkeypatch.setattr(pirates, "_generate_loot", lambda *a, **k: _async(
        {"credits": 50000, "resources": {}, "items": [], "artifacts": []}))
    taken = _patch_take_credits(monkeypatch, None)
    _patch_decision_models(monkeypatch)

    await pirates._attack(5)

    assert taken == [(5, 50000)]
    raid_rows = fake.args_for("INSERT INTO pirate_raids", "execute")
    assert raid_rows and raid_rows[0][2] == 0          # loot_credits recorded as 0
    assert not fake.args_for("treasury=treasury+$1", "execute"), "banked money that never moved"
    assert any("NOT deducted" in m for m in seen), seen


# ── 3. An unknown threat is refused ──────────────────────────────────────

async def test_generate_loot_refuses_an_unknown_threat():
    with pytest.raises(ValueError, match="Unknown threat"):
        await pirates._generate_loot("armada_of_doom")


async def test_generate_loot_stays_inside_the_table_band(monkeypatch):
    monkeypatch.setattr(pirates.random, "random", lambda: 1.1)     # never roll loot
    out = await pirates._generate_loot("patrol")
    assert out == {"credits": 0, "resources": {}, "items": [], "artifacts": []}


# ── 1 + 5. Bounty and base raid: session, then the coffer ────────────────

async def test_claim_bounty_reaches_the_bounty_through_its_faction(monkeypatch):
    fake = _install(monkeypatch, FakeDB(
        rows=[("SELECT status FROM factions", {"status": "defeated"})], fetchval=1))
    paid = []

    async def pay(session_id, pirate_faction_id, claimant_id):
        paid.append((session_id, pirate_faction_id, claimant_id))
        return 2000000

    monkeypatch.setattr(pirates, "_pay_bounty", pay)

    out = await pirates.claim_bounty(5, 6)

    status_sql = [s for s in fake.sql("fetchrow") if "SELECT status FROM factions" in s][0]
    assert "session_id=$2" in status_sql and "is_pirate=true" in status_sql
    assert fake.args_for("SELECT status FROM factions")[0] == (6, 5)
    claimant_sql = [s for s in fake.sql("fetchval") if "Setia Empire%" in s][0]
    assert "session_id=$1" in claimant_sql
    assert paid == [(5, 6, 1)]
    assert out == {"success": True, "credits": 2000000}


async def test_claim_bounty_does_not_burn_the_bounty_when_no_coffer(monkeypatch):
    seen = _quiet(monkeypatch)
    _install(monkeypatch, FakeDB(
        rows=[("SELECT status FROM factions", {"status": "defeated"})], fetchval=1))

    async def pay(session_id, pirate_faction_id, claimant_id):
        raise pirates._NoCoffer(session_id)

    monkeypatch.setattr(pirates, "_pay_bounty", pay)

    out = await pirates.claim_bounty(5, 6)

    assert out["success"] is False and "treasury" in out["error"]
    assert any("NOT paid" in m for m in seen), seen


async def test_raid_base_is_scoped_to_the_campaign(monkeypatch):
    fake = _install(monkeypatch, FakeDB(rows=[], execute_tag="UPDATE 1"))

    out = await pirates.raid_pirate_base(5, 42)

    assert out["success"] is False and "not found" in out["error"]
    sql = [s for s in fake.sql("fetchrow") if "pirate_bases" in s][0]
    assert "f.session_id=$2" in sql
    assert fake.args_for("pirate_bases")[0] == (42, 5)


async def test_raid_base_leaves_the_base_standing_when_the_coffer_is_missing(monkeypatch):
    seen = _quiet(monkeypatch)
    base = {"id": 42, "name": "Den Fringe", "treasury": 60_000_000, "defenses": 10,
            "faction_id": 6, "pirate_fleet_power": 1000}
    _install(monkeypatch, FakeDB(rows=[("FROM maya_rp.pirate_bases", base)]))
    monkeypatch.setattr(pirates.random, "random", lambda: 0.0)    # the raid succeeds

    async def seize(session_id, base):
        raise pirates._NoCoffer(session_id)

    monkeypatch.setattr(pirates, "_seize_hoard", seize)

    out = await pirates.raid_pirate_base(5, 42, attack_power=10_000_000)

    assert out["success"] is False and "No treasury row" in out["error"]
    assert any("NOT seized" in m for m in seen), seen


async def test_raid_base_seizes_and_destroys_when_the_row_exists(monkeypatch):
    base = {"id": 42, "name": "Den Fringe", "treasury": 60_000_000, "defenses": 10,
            "faction_id": 6, "pirate_fleet_power": 1000}
    _install(monkeypatch, FakeDB(rows=[("FROM maya_rp.pirate_bases", base)]))
    monkeypatch.setattr(pirates.random, "random", lambda: 0.0)
    seized = []

    async def seize(session_id, base):
        seized.append((session_id, base["id"]))
        return 60_000_000

    monkeypatch.setattr(pirates, "_seize_hoard", seize)

    out = await pirates.raid_pirate_base(5, 42, attack_power=10_000_000)

    assert out["success"] is True and out["hoard_seized"] == 60_000_000
    assert seized == [(5, 42)]


# ── 6. salvage_ship says when the class is unknown ───────────────────────

async def test_salvage_names_the_class_it_could_not_find(monkeypatch):
    seen = _quiet(monkeypatch)
    _install(monkeypatch, FakeDB(rows=[]))

    out = await pirates.salvage_ship("no such class")

    assert out == {"credits": 0, "resources": {}, "components": [], "captured": False}
    assert any("no such class" in m for m in seen), seen


# ── Module contract ──────────────────────────────────────────────────────

def test_contract_loot_tables_cover_the_threat_names_the_tick_uses():
    # `_spawn` maps danger_level to these three; nothing else may be invented.
    assert {"patrol", "raiding", "invasion"} <= set(pirates.LOOT_TABLES)
    for name, table in pirates.LOOT_TABLES.items():
        lo, hi = table["credits"]
        assert 0 < lo < hi, name
        assert 0 < table["chance"] <= 1.0, name


async def test_contract_hoard_floor_is_only_takeable_above_the_floor(monkeypatch):
    base = {"id": 1, "treasury": pirates.HOARD_FLOOR}     # nothing above the floor
    fake = _install(monkeypatch, FakeDB(
        rows=[("FROM maya_rp.factions", {"id": 6})],
        fetch={"FROM maya_rp.pirate_bases": [base]}))
    monkeypatch.setattr(pirates.random, "random", lambda: 0.0)       # every feeder bites
    monkeypatch.setattr(pirates.random, "randint", lambda a, b: 8_000_000)

    await pirates._den_feeding(5)

    assert not fake.args_for("treasury=treasury-$1", "execute"), "the floor was eaten"


async def _async(value):
    return value


def _patch_take_credits(monkeypatch, result):
    """Stub `_take_credits` (it opens a transaction); return the list of (session_id, amount) calls."""
    calls = []

    async def take(session_id, amount):
        calls.append((session_id, amount))
        return result

    monkeypatch.setattr(pirates, "_take_credits", take)
    return calls


def _patch_decision_models(monkeypatch):
    """The ML hooks are read-only side notes; pin them so the raid maths is the subject."""
    import core.decision_models as dm

    async def detect(faction_id, session_id):
        return "free"

    async def log(*args, **kwargs):
        return None

    monkeypatch.setattr(dm, "detect_pirate_group", detect)
    monkeypatch.setattr(dm, "predict_pirate_policy",
                        lambda *a, **k: {"class": "check_first"})
    monkeypatch.setattr(dm, "predict_pirate_survival",
                        lambda *a, **k: {"class": "survive", "source": "stub", "probs": None})
    monkeypatch.setattr(dm, "log_decision", log)
