"""Module review tests for modules/infrastructure.py.

Defects covered:

1. The module used `Config.SESSION_ID` in two functions and never imported
   `Config`, so `list_infrastructure()` and `get_infrastructure(id)` with no
   session raised NameError instead of defaulting.
2. `run_tick` defaulted to the literal session 3 — the frozen reference
   campaign — while Config.SESSION_ID resolves to the active arc.
3. `upgrade_infrastructure` wrote the new level with `WHERE id = $3` alone. It now claims
   the level with `WHERE id = $2 AND session_id = ... AND level = $3` and charges on the
   same transaction connection.
4. `run_production_tick` credited `resources` and then logged the payout into
   `infrastructure_production` whether or not the UPDATE matched a row, so a
   session with no `resources` row logged production that never landed.
5. One malformed `effects` value aborted the whole tick: every other instance in
   the session stopped producing because of one bad row.
6. `build_infrastructure` took `territory_id` and `sector_id` on trust. Both
   tables carry a session, so a build in this campaign could hang off another
   campaign's world, and the cost is charged before the insert.

Checked and found correct, so the row is not silent about what it looked at:
`research_projects` carries no session_id — it is the global tech catalogue, so
its unfiltered name lookup is right (this was nearly filed as a defect);
`infrastructure_types` is global too; `infrastructure_production` has no
session_id and reaches the campaign through its instance; the affordability
check runs before every deduction, so a session with no `resources` row is
refused rather than charged; only whitelisted resource columns are interpolated
into SQL; and the resource alias maps `alloy_production` onto the `alloys`
column.

No database: every test drives a fake Database.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

import modules.infrastructure as infra


class FakeDB:
    def __init__(self, fetch=None, fetchrow=None, fetchval=None, execute_tag="UPDATE 1"):
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
        if callable(self.fetchrow_value):
            return self.fetchrow_value(sql, args)
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


class _Tx:
    """Stands in for `Database.transaction()`: yields the given connection."""

    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


def _install(monkeypatch, fake):
    for name in ("fetch", "fetchrow", "fetchval", "execute"):
        monkeypatch.setattr("modules.infrastructure.Database." + name, getattr(fake, name))
    monkeypatch.setattr("modules.infrastructure.Database.transaction", lambda: _Tx(fake))
    return fake


def _instance(sid=1, effects=None, bonus=1.0):
    return {"id": sid, "session_id": 5, "production_bonus": bonus,
            "effects": effects if effects is not None else {"alloy_production": 100},
            "category": "mining", "status": "active"}


# ── 1. Config is imported ────────────────────────────────────────────────

async def test_list_infrastructure_defaults_to_the_engine_session(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[]))
    monkeypatch.setenv("RP_SESSION", "77")

    await infra.list_infrastructure()

    assert fake.args_for("infrastructure_overview", "fetch")[0] == (77,)


async def test_get_infrastructure_defaults_to_the_engine_session(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchrow=None))
    monkeypatch.setenv("RP_SESSION", "77")

    assert await infra.get_infrastructure(9) == {}
    assert fake.args_for("infrastructure_overview", "fetchrow")[0] == (9, 77)


# ── 2. The tick default ──────────────────────────────────────────────────

async def test_run_tick_defaults_to_the_engine_session(monkeypatch):
    seen = []

    async def produce(session_id, *_args, **_kwargs):
        seen.append(session_id)
        return {"produced": {}}

    monkeypatch.setattr("modules.infrastructure.run_production_tick", produce)
    monkeypatch.setenv("RP_SESSION", "77")

    await infra.run_tick()

    assert seen == [77]


async def test_run_tick_reports_a_crash_as_an_error(monkeypatch):
    async def boom(*_a, **_k):
        raise RuntimeError("smelter fire")

    monkeypatch.setattr("modules.infrastructure.run_production_tick", boom)
    monkeypatch.setattr("modules.infrastructure.error", lambda *_: None)

    out = await infra.run_tick(5)

    assert "smelter fire" in out["error"]


# ── 3. The upgrade write is scoped ───────────────────────────────────────

async def test_upgrade_writes_by_id_and_session(monkeypatch):
    inst = {"id": 3, "session_id": 5, "level": 2, "name": "Foundry",
            "infrastructure_type_id": 1}

    def fetchrow(sql, args):
        if "RETURNING level" in sql:
            return {"level": 3, "production_bonus": Decimal("1.2")}
        return inst if "infrastructure_instances" in sql else {"category": "mining"}

    fake = _install(monkeypatch, FakeDB(fetchrow=fetchrow))
    charged_on = []

    async def deduct(session_id, cost, conn=None):
        charged_on.append(conn)
        return dict(cost)

    monkeypatch.setattr("modules.infrastructure._deduct_resources", deduct)

    out = await infra.upgrade_infrastructure(5, 3)

    assert out["new_level"] == 3
    assert out["bonus"] == pytest.approx(1.2)
    assert fake.args_for("RETURNING level", "fetchrow")[0] == (3, 5, 2)
    assert "session_id = $2" in [s for s in fake.sql("fetchrow") if "RETURNING level" in s][0]
    assert charged_on == [fake], "the charge left the claim's transaction"


async def test_upgrade_refuses_an_instance_from_another_campaign(monkeypatch):
    _install(monkeypatch, FakeDB(fetchrow=None))

    out = await infra.upgrade_infrastructure(5, 3)

    assert "not found in session 5" in out["error"]


# ── 4. Production is counted only when it lands ──────────────────────────

async def test_production_with_no_resources_row_is_reported_not_logged(monkeypatch):
    seen = []
    monkeypatch.setattr("modules.infrastructure.error", lambda mod, msg: seen.append(msg))
    fake = _install(monkeypatch, FakeDB(fetch=[_instance()], execute_tag="UPDATE 0"))

    out = await infra.run_production_tick(5)

    assert out["produced"] == {}
    assert out["unlanded"] == {"alloys": 50}          # 100 × 1.0 × 0.5 days
    assert not fake.args_for("infrastructure_production", "execute"), "phantom payout logged"
    assert any("NOT credited" in m for m in seen), seen


async def test_production_that_lands_is_logged(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[_instance()], execute_tag="UPDATE 1"))

    out = await infra.run_production_tick(5)

    assert out["produced"] == {"alloys": 50}
    assert out["unlanded"] == {}
    credit = fake.args_for("SET alloys = alloys + $1", "execute")[0]
    assert credit == (50, 5)
    logged = fake.args_for("infrastructure_production", "execute")
    assert logged and logged[0] == (1, "alloys", 50)


async def test_production_uses_the_bonus_and_the_day_length(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[_instance(bonus=2.0)], execute_tag="UPDATE 1"))

    out = await infra.run_production_tick(5, game_days=2.0)

    assert out["produced"] == {"alloys": 400}          # 100 × 2.0 × 2.0
    assert fake.args_for("SET alloys = alloys + $1", "execute")[0] == (400, 5)


async def test_only_production_keys_pay_out(monkeypatch):
    effects = {"mining_mult": 1.2, "dream_essence": 1, "alloy_production": 40}
    fake = _install(monkeypatch, FakeDB(fetch=[_instance(effects=effects)], execute_tag="UPDATE 1"))

    out = await infra.run_production_tick(5, game_days=1.0)

    assert out["produced"] == {"alloys": 40}, out


async def test_an_unknown_resource_column_is_not_paid(monkeypatch):
    effects = {"unobtainium_production": 999, "alloy_production": 10}
    fake = _install(monkeypatch, FakeDB(fetch=[_instance(effects=effects)], execute_tag="UPDATE 1"))

    out = await infra.run_production_tick(5, game_days=1.0)

    assert out["produced"] == {"alloys": 10}
    assert not any("unobtainium" in s for s in fake.sql("execute"))


# ── 5. One bad row does not stop the fleet ───────────────────────────────

async def test_a_malformed_effects_row_is_skipped_and_named(monkeypatch):
    seen = []
    monkeypatch.setattr("modules.infrastructure.error", lambda mod, msg: seen.append(msg))
    rows = [_instance(1, effects="not json at all"), _instance(2, effects={"alloy_production": 100})]
    fake = _install(monkeypatch, FakeDB(fetch=rows, execute_tag="UPDATE 1"))

    out = await infra.run_production_tick(5)

    assert out["skipped"] == [1]
    assert out["produced"] == {"alloys": 50}, "the good instance stopped producing"
    assert any("instance 1" in m for m in seen), seen


# ── 6. Placement is checked before the charge ────────────────────────────

async def test_build_refuses_a_territory_from_another_campaign(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchrow={"id": 1, "name": "Mine", "category": "mining",
                                                  "build_cost_credits": 100}, 
                                        fetchval=None))
    charged = []

    async def deduct(session_id, cost):
        charged.append(cost)
        return dict(cost)

    monkeypatch.setattr("modules.infrastructure._deduct_resources", deduct)

    out = await infra.build_infrastructure(5, 1, territory_id=42)

    assert "not in session 5" in out["error"], out
    assert not charged, "a refused placement still charged the treasury"
    assert not fake.args_for("INSERT INTO maya_rp.infrastructure_instances", "execute")


async def test_build_refuses_a_sector_from_another_campaign(monkeypatch):
    _install(monkeypatch, FakeDB(fetchrow={"id": 1, "name": "Mine", "category": "mining",
                                           "build_cost_credits": 100},
                                 fetchval=None))

    out = await infra.build_infrastructure(5, 1, sector_id=7)

    assert "not in session 5" in out["error"], out


async def test_build_accepts_placement_owned_by_this_session(monkeypatch):
    it = {"id": 1, "name": "Mine", "category": "mining", "build_cost_credits": 100}
    fake = _install(monkeypatch, FakeDB(fetchrow=None, fetchval=1, execute_tag="UPDATE 1"))
    monkeypatch.setattr("modules.infrastructure.Database.fetchrow",
                        FakeDB(fetchrow=it).fetchrow)
    tx_conn = FakeDB(fetchrow={"id": 9})
    monkeypatch.setattr("modules.infrastructure.Database.transaction", lambda: _Tx(tx_conn))
    charged_on = []

    async def deduct(session_id, cost, conn=None):
        charged_on.append(conn)
        return dict(cost)

    monkeypatch.setattr("modules.infrastructure._deduct_resources", deduct)

    out = await infra.build_infrastructure(5, 1, territory_id=42, name="Deep Mine")

    assert out["name"] == "Deep Mine" and out["category"] == "mining"
    assert out["infrastructure_id"] == 9
    assert "Territory 42 is not in session" not in str(out)
    owns = fake.args_for("FROM maya_rp.territory", "fetchval")
    assert owns and owns[0] == (42, 5)
    assert charged_on == [tx_conn], "the charge left the build's transaction"
    assert tx_conn.args_for("INSERT INTO maya_rp.infrastructure_instances", "fetchrow")


# ── Contract the module claims ───────────────────────────────────────────

def test_contract_resource_alias_maps_the_catalogue_spelling():
    assert infra._resource_column("alloy_production") == "alloys"
    assert infra._resource_column("rare_earth_production") == "rare_earth"
    assert infra._resource_column("unobtainium_production") is None


def test_contract_jsonb_helper_takes_strings_and_objects():
    assert infra._j('{"a": 1}') == {"a": 1}
    assert infra._j({"a": 1}) == {"a": 1}
    assert infra._j(None) == {}


async def test_contract_the_types_catalogue_is_read_in_order(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[{"id": 1, "category": "mining"}]))

    out = await infra.get_types_by_category("mining")

    assert out == [{"id": 1, "category": "mining"}]
    sql = fake.sql("fetch")[0]
    assert "ORDER BY fantasy_tier, name" in sql
    assert fake.args_for("infrastructure_types", "fetch")[0] == ("mining",)
