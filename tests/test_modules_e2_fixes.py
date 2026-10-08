"""Fixes for the Q-Z modules, wave 3 group E2 (ship_generation through wreck_assembly).

Each test names one defect the finding list recorded and fails on the code before the fix.

Sessions 3 and 5 are frozen reference data and are never written. Live-database tests use two scratch
sessions (900 + pid % 100, and 50 above it), insert their own `maya_rp.sessions` row, and delete every row
they create in FK order in `finally`. Global catalogue tables (ship_classes, modules, weapons,
stealth_unit_types, research_projects, strategic_resources) are never written: tests that would need a
catalogue row use a fake `Database` or patch `generate_ship`.

Guardrail tests are pure.
"""
from __future__ import annotations

import ast
import asyncio
import contextlib
import json
import os
import pathlib
import random
import sys
import types

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import ooc  # noqa: E402
from core.db import Database  # noqa: E402
from modules import (  # noqa: E402
    guardrails, research, secrets, ship_building, ship_generation, ship_modules, siege, stealth,
    tactics, themes, university, victory, wreck_assembly, world_react,
)

SID = 900 + os.getpid() % 100
SID2 = 900 + (os.getpid() + 50) % 100

MODULE_FILES = (
    "ship_generation", "ship_building", "ship_modules", "research", "secrets", "guardrails", "siege",
    "stealth", "tactics", "themes", "university", "victory", "world_react", "wreck_assembly",
)


# ── helpers ──────────────────────────────────────────────────────────────


async def _open(*sids):
    await Database.init()
    for sid in sids:
        await Database.execute(
            "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1,'E2 fixes scratch','active')"
            " ON CONFLICT (id) DO NOTHING", sid)


async def _wipe(*sids):
    """Delete every row a test here can create, children first."""
    for sid in sids:
        await Database.execute(
            "DELETE FROM maya_rp.combat_stats WHERE ship_id IN "
            "(SELECT id FROM maya_rp.ships WHERE session_id=$1)", sid)
        for table in ("events", "ships", "crew_roster", "wreck_inventory", "material_stockpiles",
                      "resources", "anti_cloak_grids", "stealth_units", "sieges", "territory",
                      "secrets"):
            await Database.execute(f"DELETE FROM maya_rp.{table} WHERE session_id=$1", sid)
        await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", sid)


async def _count(table, sid):
    return await Database.fetchval(f"SELECT COUNT(*) FROM maya_rp.{table} WHERE session_id=$1", sid)


class _Tripwire:
    """A `Database` stand-in that records every call. A refused call must record none."""

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        async def call(*args, **kwargs):
            self.calls.append((name, args))
            raise AssertionError(f"Database.{name} was reached")
        return call

    @contextlib.asynccontextmanager
    async def transaction(self):
        self.calls.append(("transaction", ()))
        raise AssertionError("Database.transaction was reached")
        yield


class _RecordingDB:
    """Fake pool and transaction connection that keep separate records.

    `pool` holds statements run on the pool, `conn` holds those run inside `transaction()`.
    """

    def __init__(self, rows=None, vals=None, fetches=None):
        self.rows = rows or {}
        self.vals = vals or {}
        self.fetches = fetches or {}
        self.pool = []
        self.conn = []
        self.tx_open = False
        outer = self

        class Conn:
            async def fetchrow(self, sql, *a):
                outer.conn.append((sql, a))
                return outer._lookup(outer.rows, sql)

            async def fetchval(self, sql, *a):
                outer.conn.append((sql, a))
                return outer._lookup(outer.vals, sql)

            async def fetch(self, sql, *a):
                outer.conn.append((sql, a))
                return outer._lookup(outer.fetches, sql) or []

            async def execute(self, sql, *a):
                outer.conn.append((sql, a))
                return "UPDATE 1"

        self._Conn = Conn

    @staticmethod
    def _lookup(table, sql):
        for marker, value in table.items():
            if marker in sql:
                return value
        return None

    async def fetchrow(self, sql, *a):
        self.pool.append((sql, a))
        return self._lookup(self.rows, sql)

    async def fetchval(self, sql, *a):
        self.pool.append((sql, a))
        return self._lookup(self.vals, sql)

    async def fetch(self, sql, *a):
        self.pool.append((sql, a))
        return self._lookup(self.fetches, sql) or []

    async def execute(self, sql, *a):
        self.pool.append((sql, a))
        return "UPDATE 1"

    @contextlib.asynccontextmanager
    async def transaction(self):
        yield self._Conn()


# ── F13: sessions 3 and 5 are read-only reference data ───────────────────


class TestFrozenSessionsAreRefused:
    """Every writer and tick resolved `Config.SESSION_ID` and wrote with no freeze check."""

    @pytest.fixture(autouse=True)
    def _freeze(self, monkeypatch):
        monkeypatch.setattr("core.session.is_frozen", lambda sid: True)
        monkeypatch.setattr("core.ooc._maintenance_active", lambda: False)

    CASES = [
        (ship_generation, lambda: ship_generation.run_tick(SID)),
        (ship_building, lambda: ship_building.build_ship("Corvette", 1, "warship", "n", session_id=SID)),
        (ship_building, lambda: ship_building.assign_crew_to_ship(SID, 1, 2)),
        (ship_building, lambda: ship_building.run_tick(SID)),
        (ship_modules, lambda: ship_modules.install_module(1, "Void Drive", session_id=SID)),
        (research, lambda: research.run_tick(SID)),
        (secrets, lambda: secrets.plant("guilt", 1, "c", session_id=SID)),
        (secrets, lambda: secrets.check_discovery("deep bond conversation", SID)),
        (secrets, lambda: secrets.run_tick(SID)),
        (guardrails, lambda: guardrails.run_tick(SID)),
        (siege, lambda: siege.start_siege("Kappa", SID)),
        (siege, lambda: siege.advance_siege(1, SID)),
        (siege, lambda: siege.run_tick(SID)),
        (stealth, lambda: stealth.build_spy("Shadow Probe", "s", SID)),
        (stealth, lambda: stealth.deploy_spy("s", "lane", SID)),
        (stealth, lambda: stealth.hack("s", "op", "t", SID)),
        (stealth, lambda: stealth.build_anticloak("Kappa", 1, SID)),
        (tactics, lambda: tactics.run_tick(SID)),
        (themes, lambda: themes.run_tick(SID)),
        (university, lambda: university.run_tick(SID)),
        (victory, lambda: victory.run_tick(SID)),
        (world_react, lambda: world_react.propagate("major_treaty", {}, SID)),
        (world_react, lambda: world_react.surface(1, SID)),
        (wreck_assembly, lambda: wreck_assembly.add_wreck(SID, "w", 1, 10, 10, "x")),
        (wreck_assembly, lambda: wreck_assembly.assemble(SID, "n", [1, 2])),
    ]

    @pytest.mark.parametrize("module,call", CASES, ids=[
        f"{m.__name__.split('.')[-1]}-{i}" for i, (m, _) in enumerate(CASES)])
    async def test_a_frozen_session_is_refused_before_any_database_call(self, monkeypatch, module, call):
        """The call must raise FrozenSession and reach the database zero times."""
        wire = _Tripwire()
        monkeypatch.setattr(module, "Database", wire)

        with pytest.raises(ooc.FrozenSession):
            await call()

        assert wire.calls == [], f"{module.__name__} touched the database for a frozen session: {wire.calls}"


class TestNoConfigSessionFallback:
    """`Config.SESSION_ID` is fixed at import; a long-lived process kept the session it started on."""

    @pytest.mark.parametrize("name", MODULE_FILES)
    def test_the_module_does_not_read_config_session_id(self, name):
        tree = ast.parse((ROOT / "modules" / f"{name}.py").read_text())
        uses = [n.lineno for n in ast.walk(tree)
                if isinstance(n, ast.Attribute) and n.attr == "SESSION_ID"
                and isinstance(n.value, ast.Name) and n.value.id == "Config"]
        assert uses == [], f"modules/{name}.py still reads Config.SESSION_ID at lines {uses}"


# ── F8: generation and building ──────────────────────────────────────────


class TestRollModules:
    def test_a_ship_never_carries_the_same_module_twice(self):
        """Pass two walked the pool again and re-added modules pass one had picked."""
        pool = [{"id": i, "name": f"M{i}", "category": "shield" if i < 3 else "engine", "grade": 3 - i % 3,
                 "effect_type": "e", "effect_value": 1.0, "cost_alloys": 0, "cost_credits": 0}
                for i in range(6)]
        for _ in range(60):
            picked = ship_generation.roll_modules(6, pool)
            ids = [m["module_id"] for m in picked]
            assert len(ids) == len(set(ids)), f"duplicate module ids {ids}"
            assert len(ids) >= 2, f"the first pass picked one module per category: {ids}"

    def test_a_pool_smaller_than_the_slots_fills_only_what_exists(self):
        pool = [{"id": 1, "name": "A", "category": "c", "grade": 1, "effect_type": "e",
                 "effect_value": 1.0, "cost_alloys": 0, "cost_credits": 0}]
        for _ in range(30):
            picked = ship_generation.roll_modules(4, pool)
            assert [m["module_id"] for m in picked] == [1], f"one module was repeated to fill slots: {picked}"


class TestRollWeapons:
    def test_slot_indexes_are_unique_across_size_groups(self):
        """The index restarted at 0 for every size group, so "2XH 2H" gave two mounts at index 0."""
        pool = [{"id": i, "name": f"W{i}", "kind": "k", "slot_size": size, "damage": 1, "range_m": 1}
                for i, size in enumerate(["XH", "XH", "H", "H"])]
        armaments = ship_generation.roll_weapons([("XH", 2), ("H", 2)], pool)
        indexes = [a["slot_index"] for a in armaments]
        assert len(armaments) == 4
        assert sorted(indexes) == [0, 1, 2, 3], f"slot indexes collide or skip: {indexes}"


class TestBuildShip:
    SHIP = {"name": "E2 Runner", "class_name": "E2 Class", "ship_type": "warship", "class_id": 1,
            "tier": 1, "mass": 1000, "length_m": 80, "hull": 400, "speed": 90, "crew": 12,
            "total_alloy_cost": 100, "total_credit_cost": 200, "armaments": [], "modules": []}

    async def _seed(self):
        await _open(SID)
        await Database.execute(
            "INSERT INTO maya_rp.resources (session_id, alloys, credits) VALUES ($1, 1000, 1000)", SID)
        await Database.execute(
            "INSERT INTO maya_rp.material_stockpiles (session_id, material_name, quantity, reserved) "
            "VALUES ($1, 'Alloy Ingot', 100, 0)", SID)

    async def test_the_built_ship_carries_its_class_as_sub_class(self, monkeypatch):
        """sub_class was omitted, so `install_module` (which joins class_name = sub_class) saw 0 slots."""
        async def fake_generate(*a, **k):
            return dict(self.SHIP)
        monkeypatch.setattr(ship_building, "generate_ship", fake_generate)
        try:
            await self._seed()
            out = await ship_building.build_ship("E2 Class", 1, "warship", "E2 Runner", session_id=SID)
            assert "ship_id" in out, out
            sub = await Database.fetchval("SELECT sub_class FROM maya_rp.ships WHERE id=$1", out["ship_id"])
            assert sub == "E2 Class", f"sub_class is {sub!r}"
            alloys = await Database.fetchval("SELECT alloys FROM maya_rp.resources WHERE session_id=$1", SID)
            assert alloys == 900, f"the build charged {1000 - alloys} alloys, expected 100"
        finally:
            await _wipe(SID)
            await Database.close()

    async def test_a_build_that_raises_after_the_debit_spends_nothing(self, monkeypatch):
        """Debits were pool statements before the insert: an error after them kept the alloys, credits and stock."""
        bad = dict(self.SHIP, speed=None)       # `ship["speed"] > 80` raises after the hull row is written

        async def fake_generate(*a, **k):
            return dict(bad)
        monkeypatch.setattr(ship_building, "generate_ship", fake_generate)
        try:
            await self._seed()
            with pytest.raises(TypeError):
                await ship_building.build_ship("E2 Class", 1, "warship", "E2 Runner", session_id=SID)
            row = await Database.fetchrow(
                "SELECT alloys, credits FROM maya_rp.resources WHERE session_id=$1", SID)
            stock = await Database.fetchval(
                "SELECT quantity FROM maya_rp.material_stockpiles WHERE session_id=$1", SID)
            assert (row["alloys"], row["credits"]) == (1000, 1000), f"treasury spent: {dict(row)}"
            assert stock == 100, f"stockpile spent: {stock}"
            assert await _count("ships", SID) == 0, "a hull row survived the failed build"
        finally:
            await _wipe(SID)
            await Database.close()

    async def test_every_debit_runs_on_the_transaction_connection(self, monkeypatch):
        """A statement on the pool inside `Database.transaction()` is outside the rollback."""
        async def fake_generate(*a, **k):
            return dict(self.SHIP)
        monkeypatch.setattr(ship_building, "generate_ship", fake_generate)
        db = _RecordingDB(rows={"FROM maya_rp.resources": {"alloys": 10 ** 6, "credits": 10 ** 6},
                                "UPDATE maya_rp.resources": {"session_id": SID},
                                "UPDATE maya_rp.material_stockpiles": {"id": 1}},
                          vals={"INSERT INTO maya_rp.ships": 7},
                          fetches={"FROM maya_rp.material_stockpiles": [{"id": 1, "available": 500}]})
        monkeypatch.setattr(ship_building, "Database", db)

        out = await ship_building.build_ship("E2 Class", 1, "warship", "E2 Runner", session_id=SID)

        assert out["ship_id"] == 7, out
        assert db.pool == [], f"statements ran on the pool: {db.pool}"
        assert any("UPDATE maya_rp.resources" in sql for sql, _ in db.conn), "no guarded debit"


class TestCrewShortage:
    async def test_the_shortage_counts_empty_berths_not_ships(self):
        """`shortage` was ships minus free crew: two free crew "covered" two ships of any size."""
        try:
            await _open(SID)
            for n in range(2):
                await Database.execute(
                    "INSERT INTO maya_rp.ships (session_id, name, status, crew_required, crew_current) "
                    "VALUES ($1, $2, 'undercrewed', 10, 0)", SID, f"E2 Hull {n}")
            for n in range(2):
                await Database.execute(
                    "INSERT INTO maya_rp.crew_roster (session_id, name, status) VALUES ($1, $2, 'active')",
                    SID, f"E2 Crew {n}")
            out = await ship_building.crew_shortage_report(SID)
            assert out["berths_unfilled"] == 20, out
            assert out["shortage"] == 18, f"20 empty berths less 2 free crew is 18: {out}"
            assert out["status"] == "SHORTAGE", out
        finally:
            await _wipe(SID)
            await Database.close()


# ── F9: research ─────────────────────────────────────────────────────────


class TestResearchCosts:
    def test_a_json_text_cost_is_decoded(self):
        """jsonb arrives as text (no codec); `isinstance(costs, dict)` was False, so costed projects started free."""
        assert research.parse_costs('{"Titanium": 50}', "P") == {"Titanium": 50}

    def test_an_unreadable_cost_is_not_free(self):
        assert research.parse_costs("{not json", "P") is None
        assert research.parse_costs('["Titanium"]', "P") is None
        assert research.parse_costs('{"Titanium": 1.5}', "P") is None

    def test_no_cost_is_an_empty_dict(self):
        assert research.parse_costs(None) == {}

    async def test_a_costed_project_in_text_form_waits_for_the_pool(self, monkeypatch):
        """With the cost left as text the affordability check was skipped and the project started."""
        project = {"qid": 6, "id": 9, "name": "Deep Mining", "duration_days": 10, "progress_pct": 0,
                   "resource_costs": '{"Titanium": 50}', "bonus_type": None, "bonus_value": None}
        db = _RecordingDB(rows={"last_tick_at": {"last_tick_at": "x"},
                                "rq.status='active'": None,
                                "rq.status='pending'": project,
                                "resource_inventory": {"avail": 10}})
        monkeypatch.setattr(research, "Database", db)
        monkeypatch.setattr(research, "calc_game_days", lambda when: 1.0)

        await research.run_tick(SID)

        assert not [s for s, _ in db.conn if "SET status='active'" in s], "a project started without paying"
        assert not [s for s, _ in db.conn if "ri.quantity-$1" in s], "a debit ran for an unaffordable project"

    async def test_start_and_debit_share_one_transaction(self, monkeypatch):
        project = {"qid": 6, "id": 9, "name": "Deep Mining", "duration_days": 10, "progress_pct": 0,
                   "resource_costs": '{"Titanium": 5}', "bonus_type": None, "bonus_value": None}
        db = _RecordingDB(rows={"last_tick_at": {"last_tick_at": "x"},
                                "rq.status='active'": None,
                                "rq.status='pending'": project,
                                "resource_inventory": {"avail": 10, "resource_id": 1},
                                "WHERE rq.id=$1": project})
        monkeypatch.setattr(research, "Database", db)
        monkeypatch.setattr(research, "calc_game_days", lambda when: 1.0)

        await research.run_tick(SID)

        on_conn = " ".join(s for s, _ in db.conn)
        assert "ri.quantity-$1" in on_conn and "SET status='active'" in on_conn, on_conn
        assert not [s for s, _ in db.pool if "ri.quantity-$1" in s], "the debit ran on the pool"

    async def test_a_null_last_tick_is_named_not_skipped_in_silence(self, monkeypatch):
        """A NULL stamp returned with no trace, so research looked healthy while it never advanced."""
        seen = []
        db = _RecordingDB(rows={"last_tick_at": {"last_tick_at": None}})
        monkeypatch.setattr(research, "Database", db)
        monkeypatch.setattr(research, "warn", lambda mod, msg: seen.append(msg))

        await research.run_tick(SID)

        assert seen and "last_tick_at is NULL" in seen[0], seen


# ── F11: secrets ─────────────────────────────────────────────────────────


class TestSecretsDiscovery:
    async def _plant(self, trigger, **kw):
        return await secrets.plant("guilt", None, "E2 secret", trigger=trigger, session_id=SID, **kw)

    async def test_an_empty_trigger_reveals_nothing(self):
        """`"" .split("_")` gave an empty token, `"" in text` is true, and `0 >= 0` revealed on any context."""
        try:
            await _open(SID)
            await self._plant("")
            out = await secrets.check_discovery("anything at all", SID)
            assert out == [], f"an empty trigger revealed on any context: {out}"
        finally:
            await _wipe(SID)
            await Database.close()

    async def test_stopword_tokens_do_not_count_as_a_match(self):
        """"in" and "of" matched inside almost any text, so "in_of" revealed on "nothing in particular"."""
        try:
            await _open(SID)
            await self._plant("in_of")
            out = await secrets.check_discovery("nothing in particular", SID)
            assert out == [], f"two-letter tokens revealed a secret: {out}"
        finally:
            await _wipe(SID)
            await Database.close()

    async def test_a_real_trigger_still_reveals(self):
        try:
            await _open(SID)
            await self._plant("deep_bond_conversation")
            out = await secrets.check_discovery("a deep and honest conversation about the bond", SID)
            assert [d["content"] for d in out] == ["E2 secret"], out
        finally:
            await _wipe(SID)
            await Database.close()

    async def test_a_null_context_does_not_crash(self):
        """`context.lower()` raised AttributeError on None."""
        try:
            await _open(SID)
            await self._plant("investigation")
            assert await secrets.check_discovery(None, SID) == []
        finally:
            await _wipe(SID)
            await Database.close()

    async def test_the_auto_reveal_day_works_in_check_discovery(self):
        """The SELECT omitted `auto_reveal_game_day`, so the auto-reveal branch could never fire."""
        try:
            await _open(SID)
            await self._plant("investigation", auto_reveal_day=1)
            out = await secrets.check_discovery("nothing relevant", SID)
            assert len(out) == 1, f"a secret past its auto-reveal day stayed hidden: {out}"
        finally:
            await _wipe(SID)
            await Database.close()


class TestSecretTemplates:
    def test_the_organisation_is_drawn_at_use_not_at_import(self):
        """`f"...{random.choice(...)}"` ran once at import: every personal_past secret named the same org."""
        assert "{org}" in secrets.SECRET_TEMPLATES["personal_past"][0]
        random.seed(7)
        orgs = set()
        for _ in range(300):
            text = secrets.draw_template("personal_past")
            assert "{org}" not in text, text
            if text.startswith("was once part of"):
                orgs.add(text.split()[4].rstrip("."))
        assert orgs == set(secrets.PAST_ORGS), f"organisations drawn: {orgs}"


# ── F12: guardrails (pure) ───────────────────────────────────────────────


class TestGenerationGuardrail:
    @pytest.mark.parametrize("text", [
        "under-age", "Under  Age girl", "UNDERAGE", "under_age", "ｕｎｄｅｒａｇｅ", "under​age",
        "non consensual", "non-consensual", "Non_Consensual", "nonconsensual", "NON   CONSENSUAL",
        "child  abuse", "child-abuse", "Child_Abuse", "childabuse", "abused the children", "abuse of a child",
    ])
    def test_spelling_variants_are_blocked(self, text):
        """The list was literal: only "underage", "non-consensual" and "child abuse" in that exact spelling."""
        out = guardrails.check_generation(f"The scene: {text} follows.")
        assert out["allowed"] is False, f"{text!r} passed the generation gate"

    @pytest.mark.parametrize("text", [
        "underage", "non-consensual", "child abuse", "a minor_in_ the ledger", "a Minor_In_ the ledger",
    ])
    def test_no_existing_block_is_weakened(self, text):
        assert guardrails.check_generation(text)["allowed"] is False, f"{text!r} used to be blocked"

    @pytest.mark.parametrize("text", [
        "She took a minor in engineering at the academy.",
        "The captain stood under the agenda board.",
        "He was well under 18 minutes late.",
        "Consent was given freely and the crew agreed.",
        "",
        None,
    ])
    def test_ordinary_prose_still_passes(self, text):
        assert guardrails.check_generation(text)["allowed"] is True, f"{text!r} was blocked"

    def test_the_reason_names_the_rule(self):
        assert guardrails.check_generation("under-age").get("reason", "").endswith("underage")
        assert guardrails.check_generation("a minor_in_ x")["reason"].endswith("minor_in_")

    async def test_the_action_gate_sees_through_fullwidth_and_invisible_characters(self):
        """check_action compared raw lowercase text, so "ｍｉｎｄ control" and "mind​ control" passed."""
        for action in ("ｍｉｎｄ control the captain", "mind​ control the captain"):
            out = await guardrails.check_action(action)
            assert out["allowed"] is False, f"{action!r} passed"


# ── F13: LIKE escaping, error level ──────────────────────────────────────


class TestLikeEscaping:
    async def test_a_module_name_with_an_underscore_is_matched_literally(self, monkeypatch):
        """`Void_Drive` was a pattern: `_` matched the space in "Void Drive"."""
        db = _RecordingDB(rows={"FROM maya_rp.ships s": {"id": 4, "name": "Maw", "tier": 5,
                                                        "sub_class": "C", "module_slots": 2}},
                          vals={"count(*) FROM maya_rp.modules": 0})
        monkeypatch.setattr(ship_modules, "Database", db)

        with pytest.raises(ValueError, match="No module named"):
            await ship_modules.install_module(4, "Void_Drive", session_id=SID)

        counts = [(sql, a) for sql, a in db.pool if "count(*) FROM maya_rp.modules" in sql]
        assert counts and "ESCAPE" in counts[0][0], counts
        assert counts[0][1][0] == "%Void\\_Drive%", counts[0][1]

    async def test_a_spy_name_with_a_percent_is_matched_literally(self, monkeypatch):
        db = _RecordingDB()
        monkeypatch.setattr(stealth, "Database", db)

        out = await stealth.deploy_spy("100%", "lane", SID)

        assert "not found" in out["error"], out
        sql, args = db.pool[0]
        assert "ESCAPE" in sql and args[1] == "%100\\%%", (sql, args)

    async def test_the_install_duplicate_check_compares_ids_not_names(self, monkeypatch):
        """A second ILIKE on the name made "Drive" and "Quiet Drive" collide as duplicates."""
        db = _RecordingDB(rows={"FROM maya_rp.ships s": {"id": 4, "name": "Maw", "tier": 5,
                                                        "sub_class": "C", "module_slots": 3},
                                "SELECT * FROM maya_rp.modules": {"id": 45, "name": "Void Drive",
                                                                  "category": "void", "tier_min": 1,
                                                                  "tier_max": 9},
                                "FOR UPDATE": {"id": 4}},
                          vals={"count(*) FROM maya_rp.modules": 1, "count(*) FROM maya_rp.ship_modules": 0,
                                "INSERT INTO maya_rp.ship_modules": 1})
        monkeypatch.setattr(ship_modules, "Database", db)

        await ship_modules.install_module(4, "Void Drive", session_id=SID)

        dup = [(s, a) for s, a in db.conn if "FROM maya_rp.ship_modules WHERE ship_id" in s and "module_id" in s]
        assert dup and dup[0][1] == (4, 45), f"duplicate check is not by module id: {dup}"
        assert all("ILIKE" not in s for s, _ in db.conn), "a name pattern ran inside the install"
        assert db.pool and not [s for s, _ in db.pool if "INSERT INTO maya_rp.ship_modules" in s]


class TestTickErrorsAreLoggedAsErrors:
    async def test_a_university_tick_error_goes_through_core_log_error(self, monkeypatch):
        """The handler called `info`, so a broken tick never reached the error stream."""
        seen = []
        monkeypatch.setattr(university, "error", lambda mod, msg: seen.append(msg), raising=True)

        class Boom:
            async def fetchval(self, *a):
                raise RuntimeError("connection reset")
        monkeypatch.setattr(university, "Database", Boom())

        out = await university.run_tick(SID)

        assert "connection reset" in out["error"], out
        assert seen and "connection reset" in seen[0], seen


# ── F14: stealth, university, siege ──────────────────────────────────────


class TestAnticloak:
    async def test_a_second_grid_on_the_same_system_is_refused_and_uncharged(self):
        """`ON CONFLICT DO NOTHING` named no target and the table has no unique key: it never fired."""
        try:
            await _open(SID)
            await Database.execute(
                "INSERT INTO maya_rp.resources (session_id, alloys) VALUES ($1, 100000)", SID)
            first = await stealth.build_anticloak("E2 System", 1, SID)
            second = await stealth.build_anticloak("e2 system", 1, SID)
            assert "error" not in first, first
            assert "already has an active anti-cloak grid" in second.get("error", ""), second
            assert await _count("anti_cloak_grids", SID) == 1, "a duplicate grid row was created"
            alloys = await Database.fetchval("SELECT alloys FROM maya_rp.resources WHERE session_id=$1", SID)
            assert alloys == 90000, f"the second build charged alloys: {alloys}"
        finally:
            await _wipe(SID)
            await Database.close()

    async def test_the_debit_and_the_grid_insert_share_one_transaction(self, monkeypatch):
        db = _RecordingDB(rows={"FROM maya_rp.resources": {"alloys": 10 ** 6},
                                "UPDATE maya_rp.resources": {"alloys": 1}})
        monkeypatch.setattr(stealth, "Database", db)

        out = await stealth.build_anticloak("Kappa", 2, SID)

        assert out["cost"] == 25000, out
        assert db.pool == [], f"statements ran on the pool: {db.pool}"
        assert any("INSERT INTO maya_rp.anti_cloak_grids" in s for s, _ in db.conn)
        assert any("alloys>=$1" in s for s, _ in db.conn), "the debit was not guarded"


class TestSpyBuild:
    async def test_the_debit_is_guarded_and_shares_the_insert_transaction(self, monkeypatch):
        unit = {"id": 4, "name": "Shadow Probe", "base_cost_alloys": 5000, "cloak_level": 3, "max_lanes": 2}
        db = _RecordingDB(rows={"FROM maya_rp.stealth_unit_types": unit,
                                "FROM maya_rp.resources": {"alloys": 10 ** 6},
                                "UPDATE maya_rp.resources": {"alloys": 1}},
                          vals={"count(*) FROM maya_rp.stealth_unit_types": 1})
        monkeypatch.setattr(stealth, "Database", db)

        out = await stealth.build_spy("Shadow Probe", "E2 Spy", SID)

        assert out["name"] == "E2 Spy", out
        assert [s for s, _ in db.pool if "resources" in s or "stealth_units" in s] == [], db.pool
        assert any("alloys>=$1" in s for s, _ in db.conn), "the debit was not guarded"
        assert any("INSERT INTO maya_rp.stealth_units" in s for s, _ in db.conn)


class TestUniversityDayZero:
    async def test_day_zero_is_not_a_graduation_day(self, monkeypatch):
        """`0 % 30 == 0`: a campaign with no game day graduated scientists on its first tick."""
        db = _RecordingDB()
        # run_tick reads, in order: projects, finished, campuses, labs, research rate, game day
        answers = iter([10, 6, 4, 1, 2.5, 0])

        async def fetchval(sql, *a):
            return next(answers)
        monkeypatch.setattr(db, "fetchval", fetchval)
        monkeypatch.setattr(university, "Database", db)

        out = await university.run_tick(SID)

        assert out["graduated"] == 0, f"graduated on day 0: {out}"
        assert db.conn == [] and db.pool == [], "day 0 wrote rows"


class TestSiege:
    async def _territory(self, name="E2 Kappa", sid=SID):
        return await Database.fetchval(
            "INSERT INTO maya_rp.territory (session_id, system_name, controlling_faction, status) "
            "VALUES ($1, $2, 'Iron Concord', 'contested') RETURNING id", sid, name)

    async def _siege(self, territory_id=None, *, phase=1, max_phases=5, attacker=1, defender=1000,
                     damage=0, casualties=0, status="active", name="E2 Kappa"):
        return await Database.fetchval(
            "INSERT INTO maya_rp.sieges (session_id, territory_id, target_system, target_faction, "
            "attacker_power, defender_power, phase, max_phases, damage_dealt, casualties_taken, status) "
            "VALUES ($1,$2,$3,'Iron Concord',$4,$5,$6,$7,$8,$9,$10) RETURNING id",
            SID, territory_id, name, attacker, defender, phase, max_phases, damage, casualties, status)

    @pytest.fixture
    def low_dice(self, monkeypatch):
        """Every roll takes the low end: the rolls are the module's only randomness."""
        monkeypatch.setattr(siege, "random", types.SimpleNamespace(randint=lambda a, b: a))

    async def test_a_siege_on_its_last_phase_ends_instead_of_breaking_the_phase_check(self, low_dice):
        """phase 5 + 1 = 6 violated CHECK (phase <= 5): the siege raised on every tick and never ended."""
        try:
            await _open(SID)
            sid = await self._siege(phase=5, max_phases=5)
            out = await siege.advance_siege(sid, SID)
            assert out["status"] == "stalemate", out
            row = await Database.fetchrow("SELECT phase, status FROM maya_rp.sieges WHERE id=$1", sid)
            assert (row["phase"], row["status"]) == (5, "stalemate"), dict(row)
        finally:
            await _wipe(SID)
            await Database.close()

    async def test_a_rout_on_the_last_phase_is_a_rout_not_a_stalemate(self, low_dice):
        """Stalemate was tested before routed: 3000 men lost on the last phase read as a stalemate."""
        try:
            await _open(SID)
            sid = await self._siege(phase=4, max_phases=4, casualties=2950)
            out = await siege.advance_siege(sid, SID)
            assert out["status"] == "routed", out
        finally:
            await _wipe(SID)
            await Database.close()

    async def test_two_concurrent_advances_pay_the_victory_once(self, monkeypatch):
        """The status test was a read; the write had none, so both calls captured and paid the loot."""
        monkeypatch.setattr(siege, "random", types.SimpleNamespace(randint=lambda a, b: a))
        try:
            await _open(SID)
            await Database.execute("INSERT INTO maya_rp.resources (session_id, alloys) VALUES ($1, 0)", SID)
            tid = await self._territory()
            sid = await self._siege(tid, attacker=10 ** 9, defender=1000, damage=1900, max_phases=5)
            results = await asyncio.gather(siege.advance_siege(sid, SID), siege.advance_siege(sid, SID))
            won = [r for r in results if r.get("status") == "victory"]
            assert len(won) == 1, f"victory resolved {len(won)} times: {results}"
            alloys = await Database.fetchval("SELECT alloys FROM maya_rp.resources WHERE session_id=$1", SID)
            assert alloys == 1000, f"loot paid more than once: {alloys}"
        finally:
            await _wipe(SID)
            await Database.close()

    async def test_the_capturing_faction_is_the_module_constant(self, monkeypatch):
        """'Setia Empire' was a literal inside the capture statement."""
        monkeypatch.setattr(siege, "random", types.SimpleNamespace(randint=lambda a, b: a))
        monkeypatch.setattr(siege, "ATTACKER_FACTION", "E2 Banner")
        try:
            await _open(SID)
            tid = await self._territory()
            sid = await self._siege(tid, attacker=10 ** 9, defender=1000, damage=1900)
            out = await siege.advance_siege(sid, SID)
            assert out["status"] == "victory", out
            faction = await Database.fetchval(
                "SELECT controlling_faction FROM maya_rp.territory WHERE id=$1", tid)
            assert faction == "E2 Banner", faction
        finally:
            await _wipe(SID)
            await Database.close()

    async def test_a_second_siege_on_the_same_territory_is_refused(self):
        """Two active sieges on one system split its damage and each could capture it."""
        try:
            await _open(SID)
            await self._territory("E2 Kappa")
            first = await siege.start_siege("E2 Kappa", SID)
            second = await siege.start_siege("E2 Kappa", SID)
            assert "siege_id" in first, first
            assert "already under siege" in second.get("error", ""), second
            assert await _count("sieges", SID) == 1
        finally:
            await _wipe(SID)
            await Database.close()

    async def test_the_siege_stores_the_territory_name_not_the_fragment_typed(self):
        """A siege started on "kappa" stored "kappa", and the capture's `system_name = 'kappa'` hit nothing."""
        try:
            await _open(SID)
            await self._territory("E2 Kappa Prime")
            out = await siege.start_siege("kappa pri", SID)
            assert out["system"] == "E2 Kappa Prime", out
            stored = await Database.fetchval(
                "SELECT target_system FROM maya_rp.sieges WHERE id=$1", out["siege_id"])
            assert stored == "E2 Kappa Prime", stored
        finally:
            await _wipe(SID)
            await Database.close()

    async def test_an_underscore_in_the_system_name_is_not_a_wildcard(self):
        try:
            await _open(SID)
            await self._territory("E2 KappaAx")
            out = await siege.start_siege("E2 Kappa_x", SID)
            assert "not found" in out.get("error", ""), f"`_` matched another character: {out}"
        finally:
            await _wipe(SID)
            await Database.close()

    async def test_an_ambiguous_fragment_is_refused(self):
        try:
            await _open(SID)
            await self._territory("E2 Alpha One")
            await self._territory("E2 Alpha Two")
            out = await siege.start_siege("E2 Alpha", SID)
            assert "ambiguous" in out.get("error", ""), out
        finally:
            await _wipe(SID)
            await Database.close()

    async def test_the_tick_skips_a_siege_another_tick_already_resolved(self, monkeypatch):
        """An advance that lost the race returned {"error"}; the tick wrote an event "Siege None: None"."""
        async def lost(siege_id, session_id=None):
            return {"error": "Siege 1 not found or resolved"}
        monkeypatch.setattr(siege, "advance_siege", lost)
        db = _RecordingDB(fetches={"FROM maya_rp.sieges": [{"id": 1}]})
        monkeypatch.setattr(siege, "Database", db)

        out = await siege.run_tick(SID)

        assert out == {"sieges_advanced": 0}, out
        assert not [s for s, _ in db.pool if "INSERT INTO maya_rp.events" in s], db.pool


# ── F10: wreck assembly ──────────────────────────────────────────────────


class TestWreckAssembly:
    async def _wreck(self, name, hull, power, status="available"):
        return await Database.fetchval(
            "INSERT INTO maya_rp.wreck_inventory (session_id, name, tier, hull, power_rating, sub_class, status) "
            "VALUES ($1,$2,3,$3,$4,'Corvette',$5) RETURNING id", SID, name, hull, power, status)

    async def test_a_used_wreck_cannot_be_assembled_again(self):
        """The wrecks were read, the ship built, and only then marked used."""
        try:
            await _open(SID)
            a = await self._wreck("E2 A", 400, 100)
            b = await self._wreck("E2 B", 200, 80, status="used")
            out = await wreck_assembly.assemble(SID, "E2 Ship", [a, b])
            assert "error" in out, out
            assert await _count("ships", SID) == 0, "a ship was built from a used wreck"
            status = await Database.fetchval("SELECT status FROM maya_rp.wreck_inventory WHERE id=$1", a)
            assert status == "available", "the rolled-back claim left a wreck marked used"
        finally:
            await _wipe(SID)
            await Database.close()

    async def test_two_assemblies_of_the_same_wrecks_build_one_ship(self):
        """No claim and no `status='available'` guard on the write: both built from the same hulls."""
        try:
            await _open(SID)
            a = await self._wreck("E2 A", 400, 100)
            b = await self._wreck("E2 B", 200, 80)
            results = await asyncio.gather(
                wreck_assembly.assemble(SID, "E2 Ship 1", [a, b]),
                wreck_assembly.assemble(SID, "E2 Ship 2", [a, b]))
            built = [r for r in results if "ship_id" in r]
            assert len(built) == 1, f"{len(built)} ships built from one set of wrecks: {results}"
            assert await _count("ships", SID) == 1
        finally:
            await _wipe(SID)
            await Database.close()

    async def test_a_duplicate_wreck_id_is_refused(self):
        try:
            await _open(SID)
            a = await self._wreck("E2 A", 400, 100)
            out = await wreck_assembly.assemble(SID, "E2 Ship", [a, a])
            assert "error" in out, out
            assert await _count("ships", SID) == 0
        finally:
            await _wipe(SID)
            await Database.close()


# ── Smaller fixes that share a module with the above ─────────────────────


class TestWorldReactAtomic:
    async def test_reactions_are_inserted_on_one_transaction_connection(self, monkeypatch):
        """Each insert was a pool statement, so a failure halfway left a partial set queued."""
        db = _RecordingDB(vals={"game_day": 10})
        monkeypatch.setattr(world_react, "Database", db)

        out = await world_react.propagate("massacre", {"count": 12, "faction": "F", "location": "L"}, SID)

        assert len(out) == 2
        inserts = [s for s, _ in db.conn if "INSERT INTO maya_rp.world_reactions" in s]
        assert len(inserts) == 2 and not [s for s, _ in db.pool if "world_reactions" in s], (db.conn, db.pool)


class TestVictoryAtomic:
    async def test_the_tracking_writes_share_one_transaction(self, monkeypatch):
        db = _RecordingDB(
            fetches={"factions": [{"c": 4, "a": 2}]},
            rows={"COUNT(*) AS t FROM territory": {"t": 10}, "credits": {"credits": 5},
                  "research_projects": {"t": 10, "u": 5}, "reputation": {"reputation": 0}})
        monkeypatch.setattr(victory, "Database", db)

        out = await victory.run_tick(SID)

        assert out["session_id"] == SID
        assert len([s for s, _ in db.conn if "UPDATE victory_tracking" in s]) == 6
        assert not [s for s, _ in db.pool if "victory_tracking" in s], "a tracking write ran on the pool"


class TestTacticsAndThemes:
    async def test_the_tactics_tick_reads_through_the_resolved_session(self, monkeypatch):
        """With no session passed the tick fell back to the import-time id."""
        monkeypatch.setenv("RP_SESSION", str(SID))
        seen = []

        async def fetch(sql, *a):
            seen.append(a)
            return []
        monkeypatch.setattr(tactics.Database, "fetch", fetch)

        out = await tactics.run_tick()

        assert out["ship_count"] == 0 and seen == [(SID,)], (out, seen)

    async def test_the_theme_tick_stores_json_text_cast_to_jsonb(self, monkeypatch):
        db = _RecordingDB()
        monkeypatch.setattr(themes, "Database", db)
        monkeypatch.setattr(themes, "detect", lambda sid: _async([{"theme": "trust", "score": 3}]))

        await themes.run_tick(SID)

        sql, args = db.pool[-1]
        assert "$2::jsonb" in sql and json.loads(args[1]) == [{"theme": "trust", "score": 3}], (sql, args)


async def _async(value):
    return value
