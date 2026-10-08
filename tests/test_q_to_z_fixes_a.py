"""Live-database tests for the Q-Z fixes in tech_tree, refit, slave_system, quest, war and weapon_design.

Each test names the defect it pins and fails on the code that carried it. Scratch session only
(900 + pid % 100, the slot `scratch_session` hands out). Sessions 3 and 5 are never written.

`weapons`, `weapon_blueprints` and `weapon_upgrades` are GLOBAL catalogue tables. Tests never commit to
them: the weapon tests run the module's transaction inside a transaction this file always rolls back,
and they replace `Database.execute` with a recorder so the pre-fix code, which wrote through the pool,
cannot leave a row behind when these tests fail.

Defects covered:

1. tech_tree.run_tick bound a float to `research_progress`, charged before the failing UPDATE, and
   judged every technology against the balance read once.
2. refit.install_module ran `ON CONFLICT (ship_id, slot_index)` with no unique constraint behind it,
   after the charge, and never checked the slot against `module_slots`.
3. slave_system bound floats to integer columns and added a float to a Decimal AVG.
4. quest.generate drew types the CHECK rejects; quest.complete read then wrote without a claim.
5. war.declare stored the typed fragment, so advance found no `faction_ships`; its faction UPDATE hit
   every LIKE match.
6. weapon_design accepted negative numbers, bound an untyped parameter into jsonb, nulled `damage` on a
   NULL effect_value, and charged outside the transaction that applied the effect.
7. slave_system.buy keyed crew_skills on slaves.id, was not atomic, assign never decremented, the market
   pool stuck after one roll, and a territory collected duplicate ongoing revolts.
8. Every public writer and tick of the six modules refuses a frozen campaign.
"""
from __future__ import annotations

import asyncio
import pathlib
import random
import re
import sys
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import Database  # noqa: E402
from core.ooc import FrozenSession  # noqa: E402
from modules import quest, refit, slave_system as ss, tech_tree, war, weapon_design as wd  # noqa: E402


# ── Fixtures ────────────────────────────────────────────────────────────

_SCRUB = [
    "DELETE FROM maya_rp.slave_training WHERE slave_id IN (SELECT id FROM maya_rp.slaves WHERE session_id=$1)",
    "DELETE FROM maya_rp.slave_births WHERE parent_slave_id IN (SELECT id FROM maya_rp.slaves WHERE session_id=$1)",
    "DELETE FROM maya_rp.slave_revolts WHERE session_id=$1",
    "DELETE FROM maya_rp.slave_market WHERE session_id=$1",
    "DELETE FROM maya_rp.slaves WHERE session_id=$1",
    "DELETE FROM maya_rp.crew_skills WHERE session_id=$1",
    "DELETE FROM maya_rp.crew_roster WHERE session_id=$1",
    "DELETE FROM maya_rp.scientist_assignments WHERE lab_id IN (SELECT rl.id FROM maya_rp.research_labs rl "
    "JOIN maya_rp.colonies c ON c.id=rl.colony_id WHERE c.session_id=$1)",
    "DELETE FROM maya_rp.research_labs WHERE colony_id IN (SELECT id FROM maya_rp.colonies WHERE session_id=$1)",
    "DELETE FROM maya_rp.colonies WHERE session_id=$1",
    "DELETE FROM maya_rp.ship_modules WHERE ship_id IN (SELECT id FROM maya_rp.ships WHERE session_id=$1)",
    "DELETE FROM maya_rp.ships WHERE session_id=$1",
    "DELETE FROM maya_rp.faction_ships WHERE session_id=$1",
    "DELETE FROM maya_rp.wars WHERE session_id=$1",
    "DELETE FROM maya_rp.factions WHERE session_id=$1",
    "DELETE FROM maya_rp.territory WHERE session_id=$1",
    "DELETE FROM maya_rp.technologies WHERE session_id=$1",
    "DELETE FROM maya_rp.quests WHERE session_id=$1",
    "DELETE FROM maya_rp.events WHERE session_id=$1",
    "DELETE FROM maya_rp.resources WHERE session_id=$1",
    "DELETE FROM maya_rp.sessions WHERE id=$1",
]


async def _scrub(sid: int) -> None:
    assert sid not in (3, 5), "tests never touch the frozen campaigns"
    for sql in _SCRUB:
        await Database.execute(sql, sid)


@pytest_asyncio.fixture
async def sid(scratch_session):
    """A scratch session row with a clean slate, removed in `finally` order after the test."""
    assert 900 <= scratch_session <= 999
    await Database.init()
    await _scrub(scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1,'Q-Z fixes scratch','active')",
        scratch_session)
    try:
        yield scratch_session
    finally:
        await _scrub(scratch_session)
        await Database.close()


async def _resources(sid: int, alloys: int = 100_000, credits: int = 100_000) -> None:
    await Database.execute(
        "INSERT INTO maya_rp.resources (session_id, alloys, credits, tech_score) VALUES ($1,$2,$3,0)",
        sid, alloys, credits)


async def _treasury(sid: int) -> tuple[int, int]:
    row = await Database.fetchrow("SELECT alloys, credits FROM maya_rp.resources WHERE session_id=$1", sid)
    return row["alloys"], row["credits"]


@pytest.fixture
def frozen(monkeypatch):
    """Session ids read as frozen reference data and maintenance is not armed."""
    import core.ooc as ooc
    import core.session as session_mod
    monkeypatch.setattr(session_mod, "is_frozen", lambda session_id: True)
    monkeypatch.setattr(ooc, "_maintenance_active", lambda: False)


def _spy_transaction(monkeypatch) -> list:
    """Count entries into `Database.transaction` while still running the real one."""
    entered: list = []
    real = Database.transaction

    @asynccontextmanager
    async def spy():
        entered.append(1)
        async with real() as conn:
            yield conn

    monkeypatch.setattr(Database, "transaction", spy)
    return entered


class _RollbackTx:
    """A `Database.transaction` stand-in that runs the module's writes and ALWAYS rolls back.

    `setup(conn)` runs first, `probe(conn)` runs after the body succeeds and its result lands in `seen`.
    `seen` stays None when the code under test never opened a transaction.
    """

    def __init__(self, setup=None, probe=None):
        self.setup, self.probe, self.seen = setup, probe, None

    @asynccontextmanager
    async def __call__(self):
        pool = await Database._ensure_pool()
        async with pool.acquire() as conn:
            tx = conn.transaction()
            await tx.start()
            try:
                if self.setup:
                    await self.setup(conn)
                yield conn
                if self.probe:
                    self.seen = await self.probe(conn)
            finally:
                await tx.rollback()


def _record_execute(monkeypatch) -> list:
    """Replace `Database.execute` with a recorder that writes nothing."""
    calls: list = []

    async def recorder(sql, *args):
        calls.append(" ".join(sql.split())[:80])
        return "UPDATE 1"

    monkeypatch.setattr(Database, "execute", recorder)
    return calls


# ── 1. tech_tree ────────────────────────────────────────────────────────

async def _tech(sid: int, name: str, progress: int = 5, tier: int = 1) -> int:
    return await Database.fetchval(
        "INSERT INTO maya_rp.technologies (session_id, name, field, tier, researched, research_progress) "
        "VALUES ($1,$2,'physics',$3,false,$4) RETURNING id", sid, name, tier, progress)


class TestTechTreeTick:
    async def test_progress_is_an_integer_and_the_charge_lands_with_it(self, sid):
        """The tick bound `5 + 10 + 1.0` to an integer column and returned {"error"} after paying."""
        await _resources(sid, alloys=10_000, credits=10_000)
        tech = await _tech(sid, "qz probe a")
        out = await tech_tree.run_tick(sid)
        assert out == {"active": 1, "completed": 0}, out
        progress = await Database.fetchval(
            "SELECT research_progress FROM maya_rp.technologies WHERE id=$1", tech)
        assert progress >= 16, f"progress did not advance: {progress}"
        assert await _treasury(sid) == (9_500, 9_750), "one tier-1 technology costs 500a/250c"

    async def test_each_technology_is_checked_against_the_balance_the_last_one_left(self, sid):
        """Resources were read once: with 700 alloys both 500-alloy technologies passed the check."""
        await _resources(sid, alloys=700, credits=10_000)
        first = await _tech(sid, "qz probe b1", progress=5)
        second = await _tech(sid, "qz probe b2", progress=6)
        await tech_tree.run_tick(sid)
        alloys, _ = await _treasury(sid)
        assert alloys == 200, f"two technologies were charged from 700 alloys: {alloys}"
        moved = await Database.fetch(
            "SELECT id FROM maya_rp.technologies WHERE id = ANY($1) AND research_progress > ALL(ARRAY[6])",
            [first, second])
        assert len(moved) == 1, f"exactly one technology can be paid for, got {len(moved)}"

    async def test_a_failing_tick_logs_at_error_level_and_reports_the_error(self, sid, monkeypatch):
        """The orchestrator reads {"error"} as a failed module; the tick must also leave an error log."""
        seen = []

        async def boom(*args, **kwargs):
            raise RuntimeError("tech query died")

        monkeypatch.setattr(Database, "fetch", boom)
        monkeypatch.setattr(tech_tree, "error", lambda module, message: seen.append(message))
        out = await tech_tree.run_tick(sid)
        assert "tech query died" in out["error"], out
        assert seen, "no error-level log line"


class TestTechTreeBuildLab:
    async def test_a_percent_sign_does_not_match_every_colony(self, sid):
        """`LIKE '%%%'` matched any colony, so build_lab("%") built on an arbitrary one."""
        await _resources(sid, credits=5_000)
        await Database.execute(
            "INSERT INTO maya_rp.colonies (session_id, name, population, status) VALUES ($1,'Qz Colony',0,'active')",
            sid)
        out = await tech_tree.build_lab("%", "lab", "physics", sid)
        assert "not found" in out.get("error", ""), out
        assert (await _treasury(sid))[1] == 5_000, "credits were charged for a wildcard match"

    async def test_two_builds_on_2000_credits_charge_once(self, sid):
        """The balance was read, then charged: both builds passed the read and drove credits to -2000."""
        await _resources(sid, credits=2_000)
        await Database.execute(
            "INSERT INTO maya_rp.colonies (session_id, name, population, status) VALUES ($1,'Qz Colony',0,'active')",
            sid)
        outs = await asyncio.gather(
            tech_tree.build_lab("Qz Colony", "lab a", "physics", sid),
            tech_tree.build_lab("Qz Colony", "lab b", "physics", sid))
        built = [o for o in outs if "lab_id" in o]
        assert len(built) == 1, outs
        assert (await _treasury(sid))[1] == 0, "credits must land on exactly 0"


class TestTechTreeFrozen:
    async def test_every_writer_and_the_tick_refuse(self, sid, frozen):
        """A frozen campaign is reference data: none of these may reach a row."""
        for call in (lambda: tech_tree.run_tick(sid),
                     lambda: tech_tree.build_lab("x", "y", "physics", sid),
                     lambda: tech_tree.assign_scientist("x", 1, "physics", sid)):
            with pytest.raises(FrozenSession):
                await call()


# ── 2. refit ────────────────────────────────────────────────────────────

async def _refit_world(sid: int, tier: int = 2) -> dict:
    cls = await Database.fetchrow(
        "SELECT class_name, module_slots FROM maya_rp.ship_classes WHERE module_slots >= 2 "
        "ORDER BY module_slots LIMIT 1")
    mod = await Database.fetchrow(
        "SELECT name, cost_alloys, cost_credits FROM maya_rp.modules WHERE tier_min <= $1 "
        "AND (tier_max IS NULL OR tier_max >= $1) ORDER BY id LIMIT 1", tier)
    await _resources(sid, alloys=1_000_000, credits=1_000_000)
    ship = await Database.fetchval(
        "INSERT INTO maya_rp.ships (session_id, name, tier, sub_class, status, hull, speed) "
        "VALUES ($1,'Qz Refit Ship',$2,$3,'active',100,50) RETURNING id", sid, tier, cls["class_name"])
    return {"ship": ship, "slots": cls["module_slots"], "module": mod["name"],
            "alloys": mod["cost_alloys"], "credits": mod["cost_credits"]}


class TestRefit:
    async def test_installing_into_an_occupied_slot_replaces_it_and_charges_each_time(self, sid):
        """`ON CONFLICT (ship_id, slot_index)` named a constraint that does not exist: every install raised."""
        w = await _refit_world(sid)
        first = await refit.install_module("Qz Refit", w["module"], 1, sid)
        second = await refit.install_module("Qz Refit", w["module"], 1, sid)
        assert first.get("installed") and second.get("installed"), (first, second)
        rows = await Database.fetchval("SELECT COUNT(*) FROM maya_rp.ship_modules WHERE ship_id=$1", w["ship"])
        assert rows == 1, f"slot 1 holds {rows} rows"
        alloys, credits = await _treasury(sid)
        assert alloys == 1_000_000 - 2 * first["cost_alloys"], alloys
        assert credits == 1_000_000 - 2 * first["cost_credits"], credits

    async def test_a_slot_above_the_class_limit_is_refused_without_a_charge(self, sid):
        """slot_index was never compared with module_slots."""
        w = await _refit_world(sid)
        out = await refit.install_module("Qz Refit", w["module"], w["slots"] + 1, sid)
        assert "module slots" in out.get("error", ""), out
        assert await _treasury(sid) == (1_000_000, 1_000_000), "refused install was charged"
        assert await Database.fetchval(
            "SELECT COUNT(*) FROM maya_rp.ship_modules WHERE ship_id=$1", w["ship"]) == 0

    async def test_install_runs_in_one_transaction(self, sid, monkeypatch):
        """The charge, the slot write and the event were three pool statements."""
        w = await _refit_world(sid)
        entered = _spy_transaction(monkeypatch)
        out = await refit.install_module("Qz Refit", w["module"], 1, sid)
        assert out.get("installed"), out
        assert len(entered) == 1, f"transactions opened: {len(entered)}"

    async def test_a_percent_sign_does_not_match_every_ship(self, sid):
        """LIKE on user text without ESCAPE: "%" matched the first ship."""
        w = await _refit_world(sid)
        out = await refit.install_module("%", w["module"], 1, sid)
        assert "not found" in out.get("error", ""), out

    async def test_a_failed_charge_leaves_the_slot_empty(self, sid):
        """Charge is the last statement of the transaction: a short treasury rolls the slot back."""
        w = await _refit_world(sid)
        await Database.execute(
            "UPDATE maya_rp.resources SET alloys=$2 WHERE session_id=$1", sid, w["alloys"] - 1)
        out = await refit.install_module("Qz Refit", w["module"], 1, sid)
        assert "error" in out, out
        assert await Database.fetchval(
            "SELECT COUNT(*) FROM maya_rp.ship_modules WHERE ship_id=$1", w["ship"]) == 0

    async def test_frozen_campaign_is_refused(self, sid, frozen):
        for call in (lambda: refit.install_module("x", "y", 1, sid),
                     lambda: refit.upgrade_ship("x", sid),
                     lambda: refit.run_tick(sid)):
            with pytest.raises(FrozenSession):
                await call()


# ── 3 + 7. slave_system ─────────────────────────────────────────────────

async def _territory(sid: int, pop: int = 1000, slaves: int = 300, faction: str = "Qz Test") -> int:
    return await Database.fetchval(
        "INSERT INTO maya_rp.territory (session_id, system_name, controlling_faction, population, "
        "slave_population, morale) VALUES ($1,'Qz System',$2,$3,$4,50) RETURNING id", sid, faction, pop, slaves)


async def _slave(sid: int, loyalty: int = 50, to: int | None = None, health: int = 80) -> int:
    return await Database.fetchval(
        "INSERT INTO maya_rp.slaves (session_id, name, strength, intelligence, loyalty, health, status, "
        "assigned_to, assigned_id) VALUES ($1,'Qz Slave',6,4,$2,$3,'active',$4,$5) RETURNING id",
        sid, loyalty, health, "territory" if to else None, to)


async def _market(sid: int, territory: int, price: int = 1000, talent: str | None = "tactics") -> int:
    return await Database.fetchval(
        "INSERT INTO maya_rp.slave_market (session_id, territory_id, slave_name, species, gender, age, "
        "strength, intelligence, price, availability, price_tier, hidden_talent, functional_role, "
        "clearance_level) VALUES ($1,$2,'Qz Crew','Human','F',25,5,5,$3,true,'common',$4,'gunner',1) "
        "RETURNING id", sid, territory, price, talent)


class TestSlaveTickIntegers:
    async def test_revolt_risk_is_an_int_and_survives_a_decimal_average(self, sid):
        """AVG(loyalty) is Decimal: `float + Decimal` raised, and the float risk could not bind either."""
        tid = await _territory(sid)
        await _slave(sid, loyalty=30, to=tid)
        risk = await ss._revolt_risk(tid, sid)
        assert isinstance(risk, int), f"risk is {type(risk).__name__}"
        assert risk == 19, risk
        stored = await Database.fetchval("SELECT slave_revolt_risk FROM maya_rp.territory WHERE id=$1", tid)
        assert stored == 19, stored

    async def test_the_tick_binds_integers_for_training_health_and_loyalty(self, sid):
        """progress, health and loyalty were floats; the first bind aborted the tick with {"error"}."""
        tid = await _territory(sid, slaves=0)
        slave = await _slave(sid, to=tid)
        await Database.execute(
            "INSERT INTO maya_rp.slave_training (slave_id, training_type, progress) VALUES ($1,'gunner',0)", slave)
        out = await ss.run_tick(sid)
        assert "error" not in out, out
        progress = await Database.fetchval("SELECT progress FROM maya_rp.slave_training WHERE slave_id=$1", slave)
        assert progress >= 1, f"training did not advance: {progress}"

    def test_a_fractional_delta_keeps_its_expected_value(self):
        """Plain round() turns a 0.25 health loss into 0 every tick and stops the decay."""
        mean = sum(ss._stoch(0.25) for _ in range(8000)) / 8000
        assert 0.18 < mean < 0.32, f"mean {mean}"
        assert all(isinstance(ss._stoch(random.uniform(-2, 2)), int) for _ in range(50))

    async def test_a_failing_tick_logs_at_error_level(self, sid, monkeypatch):
        seen = []

        async def boom(*args, **kwargs):
            raise RuntimeError("slave query died")

        monkeypatch.setattr(Database, "fetch", boom)
        monkeypatch.setattr(ss, "error", lambda module, message: seen.append(message))
        out = await ss.run_tick(sid)
        assert "slave query died" in out["error"], out
        assert seen, "no error-level log line"


class TestSlaveBuy:
    async def test_the_talent_lands_on_the_new_crew_member_not_on_the_slave_id(self, sid):
        """crew_skills.crew_id was given slaves.id, so the skill hit another roster row or none."""
        await _resources(sid, credits=5_000)
        market = await _market(sid, await _territory(sid))
        out = await ss.cmd(sid, "buy", {"market_id": market})
        assert out.get("slave_id"), out
        crew = await Database.fetchval("SELECT id FROM maya_rp.crew_roster WHERE session_id=$1", sid)
        skills = await Database.fetch(
            "SELECT crew_id, skill_name FROM maya_rp.crew_skills WHERE session_id=$1", sid)
        assert [(r["crew_id"], r["skill_name"]) for r in skills] == [(crew, "tactics")], skills

    async def test_a_failure_after_the_inserts_rolls_back_the_charge_and_the_claim(self, sid, monkeypatch):
        """The charge committed first, so a late error kept the credits and the crew went unrecorded."""
        await _resources(sid, credits=5_000)
        market = await _market(sid, await _territory(sid))

        async def boom(*args, **kwargs):
            raise RuntimeError("log write died")

        monkeypatch.setattr(ss, "_log", boom)
        with pytest.raises(RuntimeError):
            await ss.cmd(sid, "buy", {"market_id": market})
        assert (await _treasury(sid))[1] == 5_000, "credits were kept after a failed purchase"
        assert await Database.fetchval(
            "SELECT availability FROM maya_rp.slave_market WHERE id=$1", market) is True
        assert await Database.fetchval("SELECT COUNT(*) FROM maya_rp.slaves WHERE session_id=$1", sid) == 0

    async def test_two_buyers_of_one_market_row_get_one_slave(self, sid):
        """The availability read and the release were separate statements."""
        await _resources(sid, credits=50_000)
        market = await _market(sid, await _territory(sid))
        outs = await asyncio.gather(
            ss.cmd(sid, "buy", {"market_id": market}), ss.cmd(sid, "buy", {"market_id": market}))
        assert sum(1 for o in outs if o.get("slave_id")) == 1, outs
        assert (await _treasury(sid))[1] == 49_000, "the row was paid for twice"


class TestSlaveAssign:
    async def test_reassigning_a_slave_decrements_the_territory_it_left(self, sid):
        """slave_population and productivity only ever grew: the old territory kept counting the slave."""
        a = await _territory(sid, slaves=0)
        b = await _territory(sid, slaves=0)
        slave = await _slave(sid)
        assert (await ss.cmd(sid, "assign", {"slave_id": slave, "target_type": "territory", "target_id": a}))["success"]
        assert (await ss.cmd(sid, "assign", {"slave_id": slave, "target_type": "territory", "target_id": b}))["success"]
        pop_a = await Database.fetchval("SELECT slave_population FROM maya_rp.territory WHERE id=$1", a)
        pop_b = await Database.fetchval("SELECT slave_population FROM maya_rp.territory WHERE id=$1", b)
        assert (pop_a, pop_b) == (0, 1), (pop_a, pop_b)
        mult_a = await Database.fetchval("SELECT slave_productivity_mult FROM maya_rp.territory WHERE id=$1", a)
        assert float(mult_a) == 1.0, f"productivity stayed at {mult_a}"

    async def test_assigning_to_the_same_territory_twice_counts_once(self, sid):
        a = await _territory(sid, slaves=0)
        slave = await _slave(sid)
        for _ in range(2):
            await ss.cmd(sid, "assign", {"slave_id": slave, "target_type": "territory", "target_id": a})
        assert await Database.fetchval("SELECT slave_population FROM maya_rp.territory WHERE id=$1", a) == 1


class TestSlaveMarketAndRevolt:
    async def test_the_pool_roll_is_per_slot(self, sid, monkeypatch):
        """The first roll overwrote `pool`: one ex-commander roll filled the whole market."""
        tid = await _territory(sid)
        rolls = iter([0.99, 0.1, 0.1])
        real = random.random
        monkeypatch.setattr(ss.random, "random", lambda: next(rolls, 0.1))
        try:
            await ss._generate_market(sid, tid, 3)
        finally:
            monkeypatch.setattr(ss.random, "random", real)
        tiers = [r["price_tier"] for r in await Database.fetch(
            "SELECT price_tier FROM maya_rp.slave_market WHERE session_id=$1 ORDER BY id", sid)]
        assert tiers == ["ex_commander", "common", "common"], tiers

    async def test_a_territory_in_revolt_does_not_start_a_second_one(self, sid):
        """Each hit above the risk line inserted a new 'ongoing' row and halved the population again."""
        tid = await _territory(sid, slaves=100)
        await Database.execute(
            "INSERT INTO maya_rp.slave_revolts (session_id, territory_id, size, severity, outcome) "
            "VALUES ($1,$2,10,1,'ongoing')", sid, tid)
        started = await ss._trigger_revolt(sid, tid)
        assert started is False, "a second revolt started"
        assert await Database.fetchval(
            "SELECT COUNT(*) FROM maya_rp.slave_revolts WHERE territory_id=$1", tid) == 1
        assert await Database.fetchval("SELECT slave_population FROM maya_rp.territory WHERE id=$1", tid) == 100


class TestSlaveFrozen:
    async def test_writers_and_the_tick_refuse_but_reads_do_not(self, sid, frozen):
        for action, params in (("assign", {"slave_id": 1, "target_type": "x", "target_id": 1}),
                               ("train", {"slave_id": 1}), ("market", {"territory_id": 1}),
                               ("market_shop", {}), ("buy", {"market_id": 1}),
                               ("revolt_risk", {"territory_id": 1}), ("suppress", {"revolt_id": 1}),
                               ("breed", {"parent_a": 1, "parent_b": 2})):
            with pytest.raises(FrozenSession):
                await ss.cmd(sid, action, params)
        with pytest.raises(FrozenSession):
            await ss.run_tick(sid)
        assert "slaves" in await ss.cmd(sid, "list", {})
        assert "total" in await ss.cmd(sid, "stats", {})


# ── 4. quest ────────────────────────────────────────────────────────────

class TestQuest:
    async def test_every_generated_type_satisfies_the_check_constraint(self, sid, monkeypatch):
        """'science', 'delivery' and 'defense' violate quests_quest_type_check: 3 draws in 7 raised."""
        definition = await Database.fetchval(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname='quests_quest_type_check'")
        allowed = set(re.findall(r"'(\w+)'::text", definition))
        assert set(quest.QUEST_TYPES) <= allowed, sorted(set(quest.QUEST_TYPES) - allowed)
        real_choice = random.choice
        for qtype in quest.QUEST_TYPES:
            monkeypatch.setattr(
                quest.random, "choice", lambda seq, q=qtype: q if seq is quest.QUEST_TYPES else real_choice(seq))
            out = await quest.generate(sid)
            assert out["type"] == qtype and out["id"], out

    async def test_completion_claims_the_quest_inside_one_transaction(self, sid, monkeypatch):
        """Read-then-pay-then-mark ran as three pool statements with no claim."""
        await _resources(sid, alloys=0, credits=0)
        qid = await Database.fetchval(
            "INSERT INTO maya_rp.quests (session_id, title, quest_type, reward_alloy, reward_credit, status) "
            "VALUES ($1,'qz','combat',100,200,'active') RETURNING id", sid)
        entered = _spy_transaction(monkeypatch)
        out = await quest.complete(qid, sid)
        assert out == {"completed": True, "alloys": 100, "credits": 200}, out
        assert len(entered) == 1, f"transactions opened: {len(entered)}"

    async def test_two_simultaneous_completions_pay_once(self, sid):
        """Both calls read 'active' before either marked it completed, and both paid."""
        await _resources(sid, alloys=0, credits=0)
        qid = await Database.fetchval(
            "INSERT INTO maya_rp.quests (session_id, title, quest_type, reward_alloy, reward_credit, status) "
            "VALUES ($1,'qz','combat',100,200,'active') RETURNING id", sid)
        outs = await asyncio.gather(quest.complete(qid, sid), quest.complete(qid, sid))
        assert sum(1 for o in outs if o.get("completed")) == 1, outs
        assert await _treasury(sid) == (100, 200), "the reward was paid twice"

    async def test_a_session_without_a_treasury_leaves_the_quest_open(self, sid):
        qid = await Database.fetchval(
            "INSERT INTO maya_rp.quests (session_id, title, quest_type, reward_alloy, reward_credit, status) "
            "VALUES ($1,'qz','combat',100,200,'active') RETURNING id", sid)
        out = await quest.complete(qid, sid)
        assert "No treasury row" in out["error"], out
        assert await Database.fetchval("SELECT status FROM maya_rp.quests WHERE id=$1", qid) == "active"

    async def test_frozen_campaign_is_refused(self, sid, frozen):
        for call in (lambda: quest.generate(sid), lambda: quest.complete(1, sid), lambda: quest.run_tick(sid)):
            with pytest.raises(FrozenSession):
                await call()


# ── 5. war ──────────────────────────────────────────────────────────────

async def _faction(sid: int, name: str) -> int:
    return await Database.fetchval(
        "INSERT INTO maya_rp.factions (session_id, name, standing) VALUES ($1,$2,'neutral') RETURNING id",
        sid, name)


class TestWar:
    async def test_the_war_stores_the_resolved_faction_name(self, sid):
        """The typed fragment 'setia qz' was stored, so a second declare with the full name slipped past."""
        await _faction(sid, "Setia Qz Empire")
        out = await war.declare("setia qz", "border", "tribute", sid)
        assert out["opponent"] == "Setia Qz Empire", out
        stored = await Database.fetchval("SELECT opponent_faction FROM maya_rp.wars WHERE id=$1", out["war_id"])
        assert stored == "Setia Qz Empire", stored
        again = await war.declare("Setia Qz Empire", "again", "again", sid)
        assert "already running" in again.get("error", ""), again

    async def test_advance_finds_the_opponents_ships(self, sid):
        """With the raw fragment stored, faction_ships matched nothing and the enemy weighed 1."""
        await _faction(sid, "Setia Qz Empire")
        out = await war.declare("setia qz", "border", "tribute", sid)
        await Database.execute(
            "INSERT INTO maya_rp.faction_ships (session_id, faction_name, ship_name, class_name, ship_type, "
            "tier, mass, hull, speed, crew, status, power_rating) "
            "VALUES ($1,'Setia Qz Empire','S','C','T',1,1,1,1,1,'active',1000)", sid)
        step = await war.advance(out["war_id"], sid)
        assert step["power_ratio"] < 0.1, f"enemy power ignored: ratio {step['power_ratio']}"

    async def test_only_the_resolved_faction_turns_hostile(self, sid):
        """The UPDATE re-ran LIKE '%fragment%' and flagged every faction whose name contained it."""
        await _faction(sid, "Qz Fleet")
        other = await _faction(sid, "Qz Fleet Reserve")
        await war.declare("Qz Fleet", "border", "tribute", sid)
        standing = await Database.fetchval("SELECT standing FROM maya_rp.factions WHERE id=$1", other)
        assert standing == "neutral", f"bystander faction is now {standing}"

    async def test_a_percent_sign_matches_no_faction(self, sid):
        await _faction(sid, "Qz Fleet")
        out = await war.declare("%", "border", "tribute", sid)
        assert "No faction matching" in out.get("error", ""), out
        assert await Database.fetchval("SELECT COUNT(*) FROM maya_rp.wars WHERE session_id=$1", sid) == 0

    async def test_a_failing_tick_logs_at_error_level(self, sid, monkeypatch):
        seen = []

        async def boom(*args, **kwargs):
            raise RuntimeError("war query died")

        monkeypatch.setattr(Database, "fetch", boom)
        monkeypatch.setattr(war, "error", lambda module, message: seen.append(message))
        out = await war.run_tick(sid)
        assert "war query died" in out["error"], out
        assert seen, "no error-level log line"

    async def test_frozen_campaign_is_refused(self, sid, frozen):
        for call in (lambda: war.declare("x", "y", "z", sid), lambda: war.advance(1, sid),
                     lambda: war.tick_wars(sid), lambda: war.run_tick(sid)):
            with pytest.raises(FrozenSession):
                await call()


# ── 6. weapon_design (global tables: every write is rolled back or recorded) ──

_BP = "qz probe weapon"


def _fake_blueprint(monkeypatch, kind: str) -> None:
    """Make the blueprint read answer a fixed row, so no catalogue row has to exist."""
    real = Database.fetchrow

    async def fetchrow(sql, *args):
        if "FROM maya_rp.weapon_blueprints" in sql and args and str(args[0]).lower() == _BP:
            return {"id": 1, "name": _BP, "category": kind, "base_damage": 5, "base_range": 10,
                    "slot_size": "L", "tier_required": 1, "alloy_cost": 10, "credit_cost": 20,
                    "research_cost": 0}
        return await real(sql, *args)

    monkeypatch.setattr(Database, "fetchrow", fetchrow)


class TestWeaponDesignValidation:
    @pytest.mark.parametrize("damage,range_m,tier", [(-10, 5, 1), (0, 5, 1), (5, 0, 1), (5, 5, -1), (5, 5, 0)])
    async def test_non_positive_numbers_are_refused_before_any_write(self, sid, monkeypatch, damage, range_m, tier):
        """cost = damage*200 + ... went negative, so the 'charge' refunded the treasury and the row went global."""
        await _resources(sid, credits=1_000)
        calls = _record_execute(monkeypatch)
        out = await wd.design_blueprint("qz neg probe", "Special", damage, range_m, "L", tier, sid)
        assert "positive" in out.get("error", ""), out
        assert calls == [], f"writes reached the pool: {calls}"

    async def test_a_non_positive_quantity_is_refused_before_any_write(self, sid, monkeypatch):
        """qty=-5 priced the order at a negative number and refunded the treasury."""
        await _resources(sid, credits=1_000)
        kind = await Database.fetchval("SELECT kind FROM maya_rp.weapon_kinds LIMIT 1")
        _fake_blueprint(monkeypatch, kind)
        calls = _record_execute(monkeypatch)
        out = await wd.produce_weapons(_BP, -5, sid)
        assert "positive" in out.get("error", ""), out
        assert calls == [], f"writes reached the pool: {calls}"

    async def test_design_charges_and_inserts_in_one_transaction(self, sid, monkeypatch):
        await _resources(sid, credits=100_000)
        calls = _record_execute(monkeypatch)

        async def probe(conn):
            return (await conn.fetchval("SELECT credits FROM maya_rp.resources WHERE session_id=$1", sid),
                    await conn.fetchval("SELECT COUNT(*) FROM maya_rp.weapon_blueprints WHERE name='qz tx probe'"))

        tx = _RollbackTx(probe=probe)
        monkeypatch.setattr(Database, "transaction", tx)
        out = await wd.design_blueprint("qz tx probe", "Special", 2, 3, "L", 1, sid)
        assert out.get("name") == "qz tx probe", out
        assert tx.seen == (100_000 - (2 * 200 + 3 * 50 + 500), 1), f"probe saw {tx.seen}; pool writes {calls}"


class TestWeaponProduce:
    async def test_the_catalogue_gets_one_row_however_many_are_ordered(self, sid, monkeypatch):
        """DESIGN DECISION: `weapons` is global with no quantity column. qty=3 inserted 3 identical rows."""
        await _resources(sid, alloys=1_000, credits=1_000)
        kind = await Database.fetchval("SELECT kind FROM maya_rp.weapon_kinds LIMIT 1")
        _fake_blueprint(monkeypatch, kind)
        calls = _record_execute(monkeypatch)

        async def probe(conn):
            return (await conn.fetchval("SELECT COUNT(*) FROM maya_rp.weapons WHERE LOWER(name)=$1", _BP),
                    await conn.fetchrow("SELECT alloys, credits FROM maya_rp.resources WHERE session_id=$1", sid))

        tx = _RollbackTx(probe=probe)
        monkeypatch.setattr(Database, "transaction", tx)
        out = await wd.produce_weapons(_BP, 3, sid)
        assert out.get("produced") == 3, out
        assert tx.seen is not None, f"no transaction opened; pool writes {calls}"
        count, res = tx.seen
        assert count == 1, f"{count} catalogue rows"
        assert (res["alloys"], res["credits"]) == (970, 940), dict(res)


def _fake_upgrade(monkeypatch, up_id: int, effect_type: str, value, cost: int = 10) -> None:
    real = Database.fetchrow

    async def fetchrow(sql, *args):
        if "FROM maya_rp.weapon_upgrades" in sql:
            return {"id": up_id, "upgrade_name": "qz probe", "effect_type": effect_type,
                    "effect_value": value, "tier_required": 1, "cost": cost, "applied_at": None}
        return await real(sql, *args)

    monkeypatch.setattr(Database, "fetchrow", fetchrow)


async def _upgrade_tx(monkeypatch, sid: int, effect_type: str, value, cost: int = 10) -> tuple[_RollbackTx, int]:
    weapon = await Database.fetchval("SELECT id FROM maya_rp.weapons ORDER BY id LIMIT 1")
    up_id = await Database.fetchval("SELECT COALESCE(MAX(id), 0) + 1000000 FROM maya_rp.weapon_upgrades")

    async def setup(conn):
        await conn.execute(
            "INSERT INTO maya_rp.weapon_upgrades (id, weapon_id, upgrade_name, effect_type, effect_value, "
            "tier_required, cost) VALUES ($1,$2,'qz probe',$3,$4,1,$5)", up_id, weapon, effect_type, value, cost)
        await conn.execute("UPDATE maya_rp.weapons SET special_rules=NULL WHERE id=$1", weapon)

    async def probe(conn):
        w = await conn.fetchrow("SELECT damage, special_rules FROM maya_rp.weapons WHERE id=$1", weapon)
        applied = await conn.fetchval("SELECT applied_at FROM maya_rp.weapon_upgrades WHERE id=$1", up_id)
        credits = await conn.fetchval("SELECT credits FROM maya_rp.resources WHERE session_id=$1", sid)
        return {"damage": w["damage"], "rules": w["special_rules"], "applied": applied, "credits": credits}

    tx = _RollbackTx(setup=setup, probe=probe)
    _fake_upgrade(monkeypatch, up_id, effect_type, value, cost)
    monkeypatch.setattr(Database, "transaction", tx)
    return tx, weapon



class TestWeaponUpgrade:
    async def test_a_float_effect_value_is_rounded_for_the_integer_column(self, sid, monkeypatch):
        """`damage + 2.6` bound a float to an integer parameter and raised after the charge."""
        await _resources(sid, credits=1_000)
        before = await Database.fetchval("SELECT damage FROM maya_rp.weapons ORDER BY id LIMIT 1")
        _record_execute(monkeypatch)
        tx, weapon = await _upgrade_tx(monkeypatch, sid, "damage", 2.6)
        out = await wd.apply_upgrade(weapon, "qz probe", None, sid)
        assert "error" not in out, out
        assert tx.seen is not None, "no transaction opened"
        assert tx.seen["damage"] == before + 3, tx.seen
        assert tx.seen["applied"] is not None and tx.seen["credits"] == 990, tx.seen

    async def test_a_null_effect_value_counts_as_zero(self, sid, monkeypatch):
        """`COALESCE(damage,0) + NULL` is NULL and violated NOT NULL on weapons.damage."""
        await _resources(sid, credits=1_000)
        before = await Database.fetchval("SELECT damage FROM maya_rp.weapons ORDER BY id LIMIT 1")
        _record_execute(monkeypatch)
        tx, weapon = await _upgrade_tx(monkeypatch, sid, "damage", None)
        out = await wd.apply_upgrade(weapon, "qz probe", None, sid)
        assert "error" not in out, out
        assert tx.seen is not None, "no transaction opened"
        assert tx.seen["damage"] == before, tx.seen

    async def test_a_special_rule_binds_a_typed_parameter(self, sid, monkeypatch):
        """`jsonb_build_object($1::text, $2)` left $2 untyped and PostgreSQL refused to prepare it."""
        await _resources(sid, credits=1_000)
        _record_execute(monkeypatch)
        tx, weapon = await _upgrade_tx(monkeypatch, sid, "special", 3.0)
        out = await wd.apply_upgrade(weapon, "qz probe", None, sid)
        assert "error" not in out, out
        assert tx.seen is not None, "no transaction opened"
        assert "qz probe" in str(tx.seen["rules"]), tx.seen

    async def test_a_failing_effect_does_not_keep_the_charge(self, sid, monkeypatch):
        """The charge went through the pool first: an effect that raised left the credits debited."""
        await _resources(sid, credits=1_000)
        _, weapon = await _upgrade_tx(monkeypatch, sid, "damage", 1e10)
        with pytest.raises(Exception):
            await wd.apply_upgrade(weapon, "qz probe", None, sid)
        assert await Database.fetchval("SELECT credits FROM maya_rp.resources WHERE session_id=$1", sid) == 1_000


class TestWeaponFrozen:
    async def test_writers_and_the_tick_refuse(self, sid, frozen):
        for call in (lambda: wd.design_blueprint("qz frozen", "Special", 1, 1, "L", 1, sid),
                     lambda: wd.produce_weapons("qz frozen", 1, sid),
                     lambda: wd.apply_upgrade(1, "qz frozen", None, sid),
                     lambda: wd.run_tick(sid)):
            with pytest.raises(FrozenSession):
                await call()
