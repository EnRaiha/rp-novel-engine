"""Group A-D modules (alchemy, academy, duel, corporations, exoscience, encounters, adventures, agnes,
archaeology, artifacts, auto_queue, conversation_log, crew_career, disasters, epilogue, event_catalog):
the defects fixed in wave 3.

Defects covered:

1. H4: no writer or tick refused a frozen campaign (sessions 3 and 5 are reference data).
2. L1: omitted sessions fell back to `Config.SESSION_ID`, fixed at import.
3. H5: check-then-spend races. A stale snapshot stands in for the concurrent caller, so each test is
   deterministic: the DB row already holds the state the other caller left, and the function under test
   reads the snapshot taken before it.
4. M4: `sell_blueprint` credited the player for a buyer that does not exist or cannot pay.
5. L2: unescaped `LIKE` in alchemy, exoscience and auto_queue.
6. L3: a NULL reward or payout wiped the treasury (`credits + NULL`).
7. L4: duel `KeyError` on a stake with no value, NULL `power_rating` / `hull`, and a second consequence
   seed planted for the same event on every encounters tick.

Scratch sessions only: `900 + pid % 100` and `900 + (pid + 50) % 100`. Sessions 3 and 5 are never
written. No test writes a GLOBAL catalogue table: recipes, research projects, campuses and programs are
read through a patched `Database.fetchrow` or a fake. Every row created here is removed in `finally`
or by the autouse fixture.
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys
from contextlib import asynccontextmanager
from decimal import Decimal

import pytest
import pytest_asyncio

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import ooc  # noqa: E402
from core.db import Database  # noqa: E402
from modules import (  # noqa: E402
    academy, adventures, agnes, alchemy, archaeology, artifacts, auto_queue, conversation_log,
    corporations, crew_career, disasters, duel, encounters, epilogue, event_catalog, exoscience,
)

SID = 900 + os.getpid() % 100
OTHER = 900 + (os.getpid() + 50) % 100

#: Tables this file writes, children first. Every one carries a `session_id` column.
_TABLES = (
    "news_articles", "events", "duels", "crew_skills", "crew_xp_log", "consequence_seeds", "artifacts",
    "dig_sites", "anomalies_catalog", "sectors", "science_missions", "active_disasters", "crew_roster",
    "production_queue", "auto_queue", "material_stockpiles", "corporate_contracts", "corporations",
    "factions", "ships", "resources",
)


@pytest_asyncio.fixture(autouse=True)
async def world():
    """Create both scratch sessions, and remove every row they own in FK order afterwards."""
    await Database.init()
    for sid in (SID, OTHER):
        await Database.execute(
            "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1,'d2 fixes scratch','active')"
            " ON CONFLICT (id) DO NOTHING", sid)
    yield
    await Database.init()
    for sid in (SID, OTHER):
        for table in _TABLES:
            await Database.execute(f"DELETE FROM maya_rp.{table} WHERE session_id = $1", sid)
        await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", sid)


# ── helpers ──────────────────────────────────────────────────────────────

async def _credits(sid: int = SID):
    return await Database.fetchval("SELECT credits FROM maya_rp.resources WHERE session_id=$1", sid)


async def _treasury(credits: int | None, sid: int = SID) -> None:
    await Database.execute(
        "INSERT INTO maya_rp.resources (session_id, credits) VALUES ($1,$2)", sid, credits)


async def _count(table: str, sid: int = SID, where: str = "TRUE") -> int:
    return await Database.fetchval(
        f"SELECT COUNT(*) FROM maya_rp.{table} WHERE session_id=$1 AND {where}", sid)


def _stale(monkeypatch, marker: str, rows, kind: str = "fetchrow") -> None:
    """Make `Database.<kind>` answer `rows` for SQL containing `marker`.

    The snapshot a concurrent caller took before the other caller committed. Statements run on a
    transaction connection do not go through `Database`, so they see the real, current row.
    """
    original = getattr(Database, kind)

    async def patched(sql, *args):
        if marker in sql:
            return rows
        return await original(sql, *args)

    monkeypatch.setattr(Database, kind, patched)


@pytest.fixture
def frozen(monkeypatch):
    """Every session reads as frozen and maintenance is off."""
    monkeypatch.setattr("core.session.is_frozen", lambda sid: True)
    monkeypatch.setattr("core.ooc._maintenance_active", lambda: False)


class _ForbiddenDB:
    """Any database access fails the test: a frozen refusal must come before the first query."""

    def _no(self, *_a, **_k):
        raise AssertionError("the database was touched while the session was frozen")

    fetch = fetchrow = fetchval = execute = transaction = _no


# ── 1. H4: every writer and tick refuses a frozen campaign ───────────────

_OPPONENT = {"name": "Eagle", "tier": 1, "hull": 10, "power": 10}

_WRITERS = [
    (alchemy, "transmute", lambda: alchemy.transmute("x", 1, SID)),
    (alchemy, "run_tick", lambda: alchemy.run_tick(SID)),
    (academy, "enroll_crew", lambda: academy.enroll_crew(1, 1, 1, SID)),
    (academy, "run_tick", lambda: academy.run_tick(SID)),
    (duel, "challenge", lambda: duel.challenge(SID, 1, _OPPONENT, {"type": "favor"})),
    (duel, "resolve", lambda: duel.resolve(SID, 1)),
    (duel, "run_tick", lambda: duel.run_tick(SID)),
    (corporations, "charter_company", lambda: corporations.charter_company("n", "mining", None, SID)),
    (corporations, "issue_directive", lambda: corporations.issue_directive(1, "privateering", None, 30, SID)),
    (corporations, "run_tick", lambda: corporations.run_tick(SID)),
    (corporations, "sell_blueprint", lambda: corporations.sell_blueprint(SID, 1)),
    (exoscience, "run_tick", lambda: exoscience.run_tick(SID)),
    (exoscience, "start_mission", lambda: exoscience.start_mission("survey", SID)),
    (exoscience, "generate_anomaly", lambda: exoscience.generate_anomaly("Kappa", SID)),
    (encounters, "log_event", lambda: encounters.log_event(SID, "t", "t", "d")),
    (encounters, "run_tick", lambda: encounters.run_tick(SID)),
    (adventures, "resolve", lambda: adventures.resolve("pirate", "success", SID)),
    (adventures, "run_tick", lambda: adventures.run_tick(SID)),
    (agnes, "run_tick", lambda: agnes.run_tick(SID)),
    (archaeology, "seed_sites", lambda: archaeology.seed_sites(SID, 1)),
    (archaeology, "excavate", lambda: archaeology.excavate(1, SID)),
    (archaeology, "run_tick", lambda: archaeology.run_tick(SID)),
    (artifacts, "discover", lambda: artifacts.discover(SID)),
    (artifacts, "equip", lambda: artifacts.equip(1, 1, SID)),
    (artifacts, "award_medal", lambda: artifacts.award_medal(SID, "Rika")),
    (artifacts, "run_tick", lambda: artifacts.run_tick(SID)),
    (auto_queue, "run_tick", lambda: auto_queue.run_tick(SID)),
    (conversation_log, "log", lambda: conversation_log.log(1, "brass vault key", session_id=SID)),
    (crew_career, "award", lambda: crew_career.award(1, 10, "drill", SID)),
    (crew_career, "assign_specialization", lambda: crew_career.assign_specialization(1, "artisan", SID)),
    (crew_career, "promote_crew", lambda: crew_career.promote_crew(1, SID)),
    (crew_career, "run_tick", lambda: crew_career.run_tick(SID)),
    (disasters, "tick_disasters", lambda: disasters.tick_disasters(SID)),
    (disasters, "run_tick", lambda: disasters.run_tick(SID)),
    (epilogue, "run_tick", lambda: epilogue.run_tick(SID)),
    (event_catalog, "run_tick", lambda: event_catalog.run_tick(SID)),
]


class TestFrozenSessionsRefuseWrites:
    @pytest.mark.parametrize("module,name,call", _WRITERS, ids=[f"{m.__name__.split('.')[-1]}.{n}" for m, n, _ in _WRITERS])
    async def test_a_frozen_session_is_refused_before_the_first_query(self, monkeypatch, frozen, module, name, call):
        """Pre-fix: no writer or tick checked the freeze; a tick swallowed the error into its dict."""
        monkeypatch.setattr(module, "Database", _ForbiddenDB(), raising=False)

        with pytest.raises(ooc.FrozenSession):
            await call()

    async def test_a_frozen_session_is_refused_with_no_row_written(self, monkeypatch, frozen):
        """The real pool, not a stub: a refused `discover` and `award_medal` leave the tables empty."""
        for call in (lambda: artifacts.discover(SID), lambda: artifacts.award_medal(SID, "Rika"),
                     lambda: encounters.log_event(SID, "t", "t", "d")):
            with pytest.raises(ooc.FrozenSession):
                await call()
        assert await _count("artifacts") == 0, "an artifact was written into a frozen session"
        assert await _count("events") == 0, "an event was written into a frozen session"


# ── 2. L1: an omitted session resolves per call, not from the import-time Config ─────

class _Recorder:
    """Records every statement's arguments and answers just enough for the callers below."""

    def __init__(self):
        self.args = []

    def _note(self, args):
        self.args.append(args)

    async def fetch(self, sql, *args):
        self._note(args)
        return []

    async def fetchrow(self, sql, *args):
        self._note(args)
        return None

    async def fetchval(self, sql, *args):
        self._note(args)
        return 7

    async def execute(self, sql, *args):
        self._note(args)
        return "UPDATE 1"

    @asynccontextmanager
    async def transaction(self):
        yield self


_OMITTED = [
    (adventures, lambda: adventures.resolve("pirate", "success")),
    (adventures, lambda: adventures.generate()),
    (artifacts, lambda: artifacts.discover()),
    (artifacts, lambda: artifacts.list_artifacts()),
    (crew_career, lambda: crew_career.talent_shortage()),
    (epilogue, lambda: epilogue.generate()),
]


class TestOmittedSessionResolvesPerCall:
    @pytest.mark.parametrize("module,call", _OMITTED, ids=[f"{m.__name__.split('.')[-1]}-{i}" for i, (m, _) in enumerate(_OMITTED)])
    async def test_an_omitted_session_follows_rp_session(self, monkeypatch, module, call):
        """Pre-fix: the call used `Config.SESSION_ID`, so RP_SESSION and the active arc were ignored."""
        rec = _Recorder()
        monkeypatch.setattr(module, "Database", rec)
        monkeypatch.setenv("RP_SESSION", str(SID))

        await call()

        assert rec.args and all(SID in a for a in rec.args if a), \
            f"a statement ran against another session: {rec.args}"


# ── 3. alchemy ───────────────────────────────────────────────────────────

def _recipe(inputs: dict, outputs: dict, name: str = "d2 recipe", rate: float = 1.0) -> dict:
    return {"id": 0, "name": name, "category": "d2", "inputs": inputs, "outputs": outputs,
            "catalyst": None, "success_rate": rate, "tech_tier": 1, "lore_text": ""}


async def _pile(material: str, quantity, sid: int = SID) -> int:
    return await Database.fetchval(
        "INSERT INTO maya_rp.material_stockpiles (session_id, material_name, quantity) "
        "VALUES ($1,$2,$3) RETURNING id", sid, material, Decimal(str(quantity)))


async def _held(material: str, sid: int = SID) -> Decimal:
    # `fetchrow`, not `fetchval`: the stale-snapshot test patches `fetchval` for this table.
    row = await Database.fetchrow(
        "SELECT COALESCE(SUM(quantity),0) AS held FROM maya_rp.material_stockpiles "
        "WHERE session_id=$1 AND material_name=$2", sid, material)
    return row["held"]


class TestAlchemy:
    async def test_a_float_input_spanning_two_piles_does_not_leave_earlier_materials_consumed(self, monkeypatch):
        """Pre-fix: `1.5 - Decimal('1')` raised TypeError on the first Gold pile, after Zinc was already taken."""
        await _pile("Zinc", 10)
        await _pile("Gold", 1)
        await _pile("Gold", 1)
        _stale(monkeypatch, "FROM maya_rp.alchemy_recipes", _recipe({"Zinc": 1, "Gold": 1.5}, {"Alloy": 2}))

        out = await alchemy.transmute("d2 recipe", 1, SID)

        assert out["successes"] == 1, out
        assert await _held("Zinc") == 9 and await _held("Gold") == Decimal("0.5")
        assert await _held("Alloy") == 2

    async def test_stock_that_vanished_after_the_availability_read_is_not_minted_from(self, monkeypatch):
        """Pre-fix: a stale availability count passed, nothing was consumed, and the outputs were granted."""
        _stale(monkeypatch, "FROM maya_rp.material_stockpiles", 10, kind="fetchval")
        _stale(monkeypatch, "FROM maya_rp.alchemy_recipes", _recipe({"Zinc": 1}, {"Alloy": 5}))

        out = await alchemy.transmute("d2 recipe", 1, SID)

        assert "Need 1 Zinc" in out.get("error", ""), out
        assert await _held("Alloy") == 0, "outputs were granted for inputs that were never held"

    async def test_a_percent_sign_in_the_recipe_name_matches_literally(self):
        """Pre-fix: `%` matched every recipe, so the first catalogue row was brewed."""
        out = await alchemy.transmute("%", 1, SID)

        assert out == {"error": "Recipe '%' not found"}, out

    async def test_an_underscore_in_the_recipe_name_matches_literally(self):
        out = await alchemy.transmute("_____", 1, SID)

        assert "not found" in out.get("error", ""), out


# ── 4. academy (campuses and programs are global: a stateful fake stands in) ─────

class _Academy:
    """A one-slot campus. Every method yields so two concurrent callers interleave."""

    def __init__(self, used=9, maximum=10):
        self.used, self.maximum = used, maximum
        self.enrolled, self.certs, self.claims = [], [], 0

    @asynccontextmanager
    async def transaction(self):
        yield self

    async def fetchrow(self, sql, *args):
        await asyncio.sleep(0)
        if "crew_roster" in sql:
            return {"id": args[0]}
        if "academy_campuses" in sql:
            return {"id": 1, "name": "Mastika", "student_slots_used": self.used, "max_students": self.maximum}
        if "training_programs" in sql:
            return {"id": 5, "name": "Navigation", "duration": 100, "field": "nav",
                    "skill_bonus": 1, "graduates_receive": "Navigator"}
        return None

    async def fetchval(self, sql, *args):
        await asyncio.sleep(0)
        if "UPDATE maya_rp.academy_campuses" in sql and "RETURNING" in sql:
            if self.used < self.maximum:
                self.used += 1
                return 1
            return None
        if "UPDATE maya_rp.enrolled_crew" in sql and "graduated=true" in sql:
            self.claims += 1
            return 900 if self.claims == 1 else None
        return None

    async def execute(self, sql, *args):
        await asyncio.sleep(0)
        if "INSERT INTO maya_rp.enrolled_crew" in sql:
            self.enrolled.append(args)
        elif "student_slots_used=COALESCE(student_slots_used,0)+1" in sql:
            self.used += 1
        elif "INSERT INTO maya_rp.certifications" in sql:
            self.certs.append(args)
        return "OK"

    async def fetch(self, sql, *args):
        await asyncio.sleep(0)
        return [{"id": 900, "crew_id": 77, "program_id": 5, "campus_id": 1, "progress": 90,
                 "target_progress": 100}]


class TestAcademy:
    async def test_two_enrolments_for_the_last_slot_admit_one(self, monkeypatch):
        """Pre-fix: both read 9 of 10, both inserted, and the campus ended at 11."""
        fake = _Academy()
        monkeypatch.setattr(academy, "Database", fake)

        results = await asyncio.gather(
            academy.enroll_crew(1, 5, 1, SID), academy.enroll_crew(2, 5, 1, SID))

        assert sorted("error" in r for r in results) == [False, True], results
        assert len(fake.enrolled) == 1, "the campus took two students for one slot"
        assert fake.used == 10

    async def test_two_ticks_graduate_one_enrolment_once(self, monkeypatch):
        """Pre-fix: both ticks read the enrolment ungraduated and both awarded the certificate."""
        fake = _Academy()
        monkeypatch.setattr(academy, "Database", fake)
        monkeypatch.setattr(academy.random, "randint", lambda a, b: b)

        await asyncio.gather(academy.run_tick(SID), academy.run_tick(SID))

        assert len(fake.certs) == 1, f"the certificate was awarded {len(fake.certs)} times"


# ── 5. duel ──────────────────────────────────────────────────────────────

async def _ship(sid: int = SID, **fields) -> int:
    row = {"name": "Blizzard Zero", "ship_type": "frigate", "hull": 400, "hull_current": 400,
           "power_rating": 100, "status": "active", "sub_class": "Corvette", "tier": 3, **fields}
    cols = ", ".join(row)
    marks = ", ".join(f"${i + 2}" for i in range(len(row)))
    return await Database.fetchval(
        f"INSERT INTO maya_rp.ships (session_id, {cols}) VALUES ($1, {marks}) RETURNING id",
        sid, *row.values())


async def _duel(ship_id: int, stakes_type="credits", stakes_value="5000", power=100) -> int:
    return await Database.fetchval(
        "INSERT INTO maya_rp.duels (session_id, player_ship_id, opponent_name, opponent_tier, opponent_hull,"
        " opponent_power, stakes_type, stakes_value, venue, status) "
        "VALUES ($1,$2,'Eagle',3,400,$3,$4,$5,'Open Space','pending') RETURNING id",
        SID, ship_id, power, stakes_type, stakes_value)


class TestDuel:
    async def test_a_duel_another_caller_already_resolved_pays_no_second_stake(self, monkeypatch):
        """Pre-fix: the stale `pending` read rolled again, paid the stake again and wrote a second event."""
        await _treasury(10_000)
        ship = await _ship()
        duel_id = await _duel(ship)
        monkeypatch.setattr(duel.random, "randint", lambda a, b: 1)
        first = await duel.resolve(SID, duel_id)
        assert first["result"] == "victory_clean", first
        paid = await _credits()
        row = dict(await Database.fetchrow("SELECT * FROM maya_rp.duels WHERE id=$1", duel_id))
        row["status"] = "pending"
        _stale(monkeypatch, "FROM maya_rp.duels", row)

        second = await duel.resolve(SID, duel_id)

        assert "error" in second, second
        assert await _credits() == paid, "the stake was paid twice"
        assert await _count("events", where="event_type='duel'") == 1, "a second duel event was written"

    async def test_an_error_after_the_claim_restores_pending_and_the_stake(self, monkeypatch):
        """Pre-fix: the status, hull and stake were committed statement by statement."""
        await _treasury(10_000)
        ship = await _ship()
        duel_id = await _duel(ship)
        monkeypatch.setattr(duel.random, "randint", lambda a, b: 1)

        def explode(module, message):
            if message.startswith(f"Duel {duel_id}:"):
                raise RuntimeError("late failure")

        monkeypatch.setattr(duel, "info", explode)

        with pytest.raises(RuntimeError, match="late failure"):
            await duel.resolve(SID, duel_id)

        status = await Database.fetchval("SELECT status FROM maya_rp.duels WHERE id=$1", duel_id)
        assert status == "pending", f"the duel stayed {status!r} after a rolled-back resolve"
        assert await _credits() == 10_000, "the stake moved although the resolve failed"
        assert await Database.fetchval("SELECT hull_current FROM maya_rp.ships WHERE id=$1", ship) == 400

    async def test_a_favor_stake_without_a_value_is_registered(self):
        """Pre-fix: `stakes["value"]` raised KeyError for the shape the type check accepted."""
        ship = await _ship()

        out = await duel.challenge(SID, ship, _OPPONENT, {"type": "favor"})

        assert out["status"] == "pending", out
        stored = await Database.fetchval(
            "SELECT stakes_value FROM maya_rp.duels WHERE id=$1", out["duel_id"])
        assert stored == "0"

    async def test_null_power_and_hull_resolve_instead_of_raising(self, monkeypatch):
        """Pre-fix: `None / max(1, ep)` and `None * 0.1` raised TypeError."""
        ship = await _ship(power_rating=None, hull=None, hull_current=None)
        duel_id = await _duel(ship, stakes_type="favor", stakes_value="0", power=None)
        monkeypatch.setattr(duel.random, "randint", lambda a, b: 1)

        out = await duel.resolve(SID, duel_id)

        assert out.get("result") == "victory_clean", out
        assert out["hull_remaining"] == 0


# ── 6. corporations ──────────────────────────────────────────────────────

_PROJECT = {"id": 1, "name": "Redacted Drive", "blueprint_price": 10_000, "saleable": True, "unlocked": True}


def _buyer(name: str) -> str:
    return f"{name} {os.getpid()}"


async def _faction(name: str, treasury: int) -> None:
    await Database.execute(
        "INSERT INTO maya_rp.factions (session_id, name, treasury) VALUES ($1,$2,$3)", SID, name, treasury)


async def _treasury_of(name: str) -> int:
    return await Database.fetchval("SELECT treasury FROM maya_rp.factions WHERE name=$1", name)


class TestCorporations:
    async def test_a_buyer_that_does_not_exist_pays_nothing_and_the_player_is_not_credited(self, monkeypatch):
        """Pre-fix: the player was credited the full price and the missing buyer was never charged."""
        await _treasury(1_000)
        _stale(monkeypatch, "FROM maya_rp.research_projects", _PROJECT)

        out = await corporations.sell_blueprint(SID, 1, _buyer("Nobody"), 20)

        assert "error" in out, out
        assert await _credits() == 1_000, "money was minted for a nonexistent buyer"
        assert await _count("corporate_contracts") == 0

    async def test_a_buyer_that_cannot_afford_the_price_is_refused(self, monkeypatch):
        """Pre-fix: the buyer was clamped to 0 by GREATEST and the player got the full price."""
        name = _buyer("Poor")
        await _treasury(1_000)
        await _faction(name, 100)
        _stale(monkeypatch, "FROM maya_rp.research_projects", _PROJECT)

        out = await corporations.sell_blueprint(SID, 1, name, 20)

        assert "error" in out, out
        assert await _credits() == 1_000 and await _treasury_of(name) == 100

    async def test_a_player_without_a_treasury_row_rolls_the_buyer_charge_back(self, monkeypatch):
        """Pre-fix: the buyer was charged and the credit landed nowhere."""
        name = _buyer("Rich")
        await _faction(name, 50_000)
        _stale(monkeypatch, "FROM maya_rp.research_projects", _PROJECT)

        out = await corporations.sell_blueprint(SID, 1, name, 20)

        assert "error" in out, out
        assert await _treasury_of(name) == 50_000, "the buyer paid for a sale that never landed"
        assert await _count("corporate_contracts") == 0

    async def test_a_contract_another_tick_already_completed_pays_nothing(self, monkeypatch):
        """Pre-fix: the stale `active` read paid the contract a second time."""
        await _treasury(1_000)
        corp = await Database.fetchval(
            "INSERT INTO maya_rp.corporations (session_id, name, industry) VALUES ($1,'d2 corp','trade') RETURNING id", SID)
        con = await Database.fetchrow(
            "INSERT INTO maya_rp.corporate_contracts (session_id, corp_id, contract_type, payout_credits,"
            " payout_alloys, duration_days, days_remaining, status) "
            "VALUES ($1,$2,'privateering',500,0,1,1,'completed') RETURNING id", SID, corp)
        stale = {"id": con["id"], "corp_id": corp, "contract_type": "privateering", "target_system": None,
                 "payout_credits": 500, "payout_alloys": 0, "days_remaining": 1, "corp_name": "d2 corp",
                 "industry": "trade", "efficiency": 50, "standing": 50}
        _stale(monkeypatch, "FROM maya_rp.corporate_contracts cc", [stale], kind="fetch")

        out = await corporations.run_tick(SID)

        assert out["completed"] == 0, out
        assert await _credits() == 1_000, "a completed contract paid out twice"

    async def test_a_contract_with_a_null_payout_does_not_wipe_the_treasury(self):
        """Pre-fix: `credits + NULL` is NULL."""
        await _treasury(1_000)
        corp = await Database.fetchval(
            "INSERT INTO maya_rp.corporations (session_id, name, industry) VALUES ($1,'d2 corp','trade') RETURNING id", SID)
        await Database.execute(
            "INSERT INTO maya_rp.corporate_contracts (session_id, corp_id, contract_type, payout_credits,"
            " payout_alloys, duration_days, days_remaining, status) "
            "VALUES ($1,$2,'privateering',NULL,NULL,1,1,'active')", SID, corp)

        out = await corporations.run_tick(SID)

        assert out.get("completed") == 1, out
        assert await _credits() == 1_000, "a NULL payout wiped the treasury"


# ── 7. exoscience ────────────────────────────────────────────────────────

async def _mission(progress=99, target=100, reward=50, status="active") -> int:
    return await Database.fetchval(
        "INSERT INTO maya_rp.science_missions (session_id, mission_type, progress, target_progress,"
        " research_reward, status) VALUES ($1,'survey',$2,$3,$4,$5) RETURNING id",
        SID, progress, target, reward, status)


class TestExoscience:
    async def test_a_mission_another_tick_already_completed_pays_no_second_reward(self, monkeypatch):
        """Pre-fix: the stale `active` read completed the mission again and paid the reward again."""
        await _treasury(1_000)
        mission = await _mission(progress=100, status="completed")
        stale = {"id": mission, "mission_type": "survey", "progress": 99, "target_progress": 100,
                 "research_reward": 50}
        _stale(monkeypatch, "FROM maya_rp.science_missions", [stale], kind="fetch")

        out = await exoscience.run_tick(SID)

        assert out["missions_completed"] == 0, out
        assert await _credits() == 1_000, "the reward was paid twice"

    async def test_a_null_reward_does_not_wipe_the_treasury(self):
        """Pre-fix: `credits + NULL` is NULL."""
        await _treasury(1_000)
        await _mission(reward=None)

        out = await exoscience.run_tick(SID)

        assert out["missions_completed"] == 1, out
        assert await _credits() == 1_000

    async def test_a_completion_pays_the_reward_and_closes_the_mission_together(self):
        """Guards the new claim-then-pay transaction against the real table; passes pre-fix too."""
        await _treasury(1_000)
        mission = await _mission(reward=50)

        await exoscience.run_tick(SID)

        status = await Database.fetchval("SELECT status FROM maya_rp.science_missions WHERE id=$1", mission)
        assert (status, await _credits()) == ("completed", 1_050)

    async def test_an_underscore_in_the_location_matches_literally(self):
        """Pre-fix: `K_ppa` matched the sector `Kappa` through the LIKE wildcard."""
        sector = await Database.fetchval(
            "INSERT INTO maya_rp.sectors (session_id, name, x_coord, y_coord) VALUES ($1,'Kappa',1,1) RETURNING id", SID)

        out = await exoscience.generate_anomaly("K_ppa", SID)

        assert out["sector_id"] is None, f"the wildcard tied the anomaly to sector {sector}"
        exact = await exoscience.generate_anomaly("Kappa", SID)
        assert exact["sector_id"] == sector


# ── 8. encounters ────────────────────────────────────────────────────────

class TestEncounters:
    async def test_the_same_event_plants_one_consequence_seed(self, monkeypatch):
        """Pre-fix: the event stayed in the 5-event window and planted a new seed on every tick."""
        await Database.execute(
            "INSERT INTO maya_rp.events (session_id, event_type, title, importance) VALUES ($1,'battle','Big fight',6)", SID)
        # 0.04 passes the 5% seed roll and misses the 3% encounter roll.
        monkeypatch.setattr(encounters._r, "random", lambda: 0.04)

        async def introduce(*_a, **_k):
            return None

        monkeypatch.setattr("modules.chekhov.introduce", introduce)

        first = await encounters.run_tick(SID)
        second = await encounters.run_tick(SID)

        assert first["consequences_planted"] == 1 and second["consequences_planted"] == 0, (first, second)
        assert await _count("consequence_seeds") == 1, "a second seed was planted for the same event"
        tags = await Database.fetchval(
            "SELECT tags::text FROM maya_rp.events WHERE session_id=$1 AND title='Big fight'", SID)
        assert encounters.SEEDED_TAG in tags


# ── 9. archaeology ───────────────────────────────────────────────────────

class TestArchaeology:
    async def test_a_site_another_dig_already_depleted_yields_no_second_batch(self, monkeypatch):
        """Pre-fix: the stale read finished the site again and inserted its artifacts again."""
        site = await Database.fetchval(
            "INSERT INTO maya_rp.dig_sites (session_id, name, site_type, excavation_progress, max_progress,"
            " artifact_yield, status) VALUES ($1,'d2 site','ruins',100,100,2,'depleted') RETURNING id", SID)
        stale = {"id": site, "name": "d2 site", "site_type": "ruins", "difficulty": 1, "artifact_yield": 2,
                 "excavation_progress": 99, "max_progress": 100, "status": "undiscovered"}
        _stale(monkeypatch, "FROM maya_rp.dig_sites", stale)

        out = await archaeology.excavate(site, SID)

        assert out == {"error": "Site depleted"}, out
        assert await _count("artifacts") == 0, "a depleted site yielded artifacts again"

    async def test_a_dig_that_finishes_the_site_depletes_it_and_yields_together(self):
        """Guards the new locked dig transaction against the real tables; passes pre-fix too."""
        site = await Database.fetchval(
            "INSERT INTO maya_rp.dig_sites (session_id, name, site_type, excavation_progress, max_progress,"
            " artifact_yield, status) VALUES ($1,'d2 site','ruins',99,100,2,'undiscovered') RETURNING id", SID)

        out = await archaeology.excavate(site, SID)

        assert out == {"completed": True, "artifacts": 2}
        assert await _count("artifacts") == 2


# ── 10. crew_career ──────────────────────────────────────────────────────

async def _crew(xp=90, level=1) -> int:
    return await Database.fetchval(
        "INSERT INTO maya_rp.crew_roster (session_id, name, xp, level) VALUES ($1,'d2 crew',$2,$3) RETURNING id",
        SID, xp, level)


class TestCrewCareer:
    async def test_an_award_does_not_level_twice_from_a_stale_read(self, monkeypatch):
        """Pre-fix: a separate follow-up read saw the pre-level XP and the level-up was applied again."""
        crew = await _crew(xp=30, level=2)
        _stale(monkeypatch, "SELECT xp,level,role", {"xp": 130, "level": 1, "role": None})

        out = await crew_career.award(crew, 20, "drill", SID)

        assert out == {"leveled": False}, out
        row = await Database.fetchrow("SELECT xp, level FROM maya_rp.crew_roster WHERE id=$1", crew)
        assert (row["xp"], row["level"]) == (50, 2), dict(row)

    async def test_an_award_and_its_level_up_commit_together(self, monkeypatch):
        """Guards the new `UPDATE ... RETURNING` award statement against the real table; passes pre-fix too."""
        crew = await _crew(xp=90, level=1)
        monkeypatch.setattr(crew_career.random, "choice", lambda seq: "gunnery")

        out = await crew_career.award(crew, 20, "drill", SID)

        assert out["leveled"] is True, out
        row = await Database.fetchrow("SELECT xp, level FROM maya_rp.crew_roster WHERE id=$1", crew)
        assert (row["xp"], row["level"]) == (10, 2)
        assert await _count("crew_xp_log") == 1

    async def test_a_promotion_reads_the_locked_row_not_a_stale_snapshot(self, monkeypatch):
        """Pre-fix: the stale 250 XP at level 2 promoted a crew member who had already been promoted to 3."""
        crew = await _crew(xp=50, level=3)
        stale = {"id": crew, "xp": 250, "level": 2, "rank": "Specialist", "specialization": None}
        _stale(monkeypatch, "FROM maya_rp.crew_roster WHERE id=$1 AND session_id=$2", stale)

        out = await crew_career.promote_crew(crew, SID)

        assert out == {"leveled": False, "need": 250}, out
        row = await Database.fetchrow("SELECT xp, level FROM maya_rp.crew_roster WHERE id=$1", crew)
        assert (row["xp"], row["level"]) == (50, 3), dict(row)


# ── 11. disasters ────────────────────────────────────────────────────────

class TestDisasters:
    async def test_a_disaster_another_tick_already_resolved_deals_no_second_damage(self, monkeypatch):
        """Pre-fix: the stale `active` read applied the damage again."""
        await _treasury(1_000)
        disaster = await Database.fetchval(
            "INSERT INTO maya_rp.active_disasters (session_id, template_id, name, tick_started, ticks_remaining,"
            " severity, status) VALUES ($1,4,'d2 crash',1,0,10,'resolved') RETURNING id", SID)
        stale = {"id": disaster, "name": "d2 crash", "severity": 10, "ticks_remaining": 1,
                 "base_damage": 30.0, "category": "economic"}
        _stale(monkeypatch, "FROM maya_rp.active_disasters d", [stale], kind="fetch")

        events = await disasters.tick_disasters(SID)

        assert events == []
        assert await _credits() == 1_000, "a resolved disaster dealt damage again"

    async def test_a_tick_counts_down_and_damages_once(self):
        """Guards the new countdown statement (`CASE ... 'resolved'`) against the real table; passes pre-fix too."""
        await _treasury(1_000)
        disaster = await Database.fetchval(
            "INSERT INTO maya_rp.active_disasters (session_id, template_id, name, tick_started, ticks_remaining,"
            " severity, status) VALUES ($1,4,'d2 crash',1,2,10,'active') RETURNING id", SID)

        await disasters.tick_disasters(SID)
        mid = await Database.fetchrow("SELECT ticks_remaining, status FROM maya_rp.active_disasters WHERE id=$1", disaster)
        await disasters.tick_disasters(SID)
        end = await Database.fetchrow("SELECT ticks_remaining, status FROM maya_rp.active_disasters WHERE id=$1", disaster)

        assert (mid["ticks_remaining"], mid["status"]) == (1, "active")
        assert (end["ticks_remaining"], end["status"]) == (0, "resolved")
        assert await _credits() == 1_000 - 2 * 90


# ── 12. auto_queue ───────────────────────────────────────────────────────

class TestAutoQueue:
    async def test_an_underscore_in_the_prefix_matches_literally(self):
        """Pre-fix: `a_b-%` matched `axb-005`, so the new hull was numbered 002 instead of 001."""
        await Database.execute(
            "INSERT INTO maya_rp.production_queue (session_id, ship_name, ship_type, hull_class, status, priority,"
            " assigned_yard) VALUES ($1,'axb-005','frigate','light','completed',1,'d2 yard')", SID)
        await Database.execute(
            "INSERT INTO maya_rp.auto_queue (session_id, yard, ship_type, hull_class, quota, ship_name_prefix,"
            " priority, active) VALUES ($1,'d2 yard','frigate','light',1,'a_b-',1,TRUE)", SID)

        out = await auto_queue._yard_auto_queue(SID)

        assert out == {"orders": 1, "enqueued": 1}, out
        name = await Database.fetchval(
            "SELECT ship_name FROM maya_rp.production_queue WHERE session_id=$1 AND status='planned'", SID)
        assert name == "a_b-001", name
