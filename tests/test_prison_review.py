"""Prison module review: what reading `modules/prison.py` in full turned up.

Five classes of defect, one class per group of tests below. Nothing here mutates session 3, and every
row this file creates in session 5 is removed in a `finally`.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from core.config import Config  # noqa: E402
from core.db import Database  # noqa: E402
from modules import prison  # noqa: E402

SESSION = 5


async def _prisoner(**over):
    cols = {
        "session_id": SESSION,
        "name": "review prisoner",
        "faction": "Iron Concord",
        "rank": "Private",
        "intel_value": 10,
        "resistance": 50,
        "status": "captured",
        "cell_security": "standard",
        "interrogations_count": 0,
        "intel_extracted": "[]",
        "secrets_jsonb": "[]",
        "escape_risk_pct": 15,
        "held_sessions": 0,
    }
    cols.update(over)
    keys = ", ".join(cols)
    marks = ", ".join(f"${i + 1}" for i in range(len(cols)))
    return await Database.fetchrow(
        f"INSERT INTO maya_rp.prisoners ({keys}) VALUES ({marks}) RETURNING id", *cols.values())


async def _ship(name, capacity):
    return await Database.fetchval(
        "INSERT INTO maya_rp.ships (session_id, name, cell_capacity) VALUES ($1, $2, $3) "
        "RETURNING id", SESSION, name, capacity)


async def _drop_prisoner(pid):
    await Database.execute("DELETE FROM maya_rp.interrogation_log WHERE prisoner_id = $1", pid)
    await Database.execute("DELETE FROM maya_rp.escape_countermeasures WHERE prisoner_id = $1", pid)
    await Database.execute("DELETE FROM maya_rp.prisoner_intel_pipeline WHERE prisoner_id = $1", pid)
    await Database.execute("DELETE FROM maya_rp.prisoners WHERE id = $1", pid)


async def _drop_ship(sid):
    await Database.execute("UPDATE maya_rp.prisoners SET cell_ship_id = NULL WHERE cell_ship_id = $1", sid)
    await Database.execute("DELETE FROM maya_rp.ships WHERE id = $1", sid)


#: Marks the `resources` row this file makes. Session 5 has none, and a campaign row for it would
#: carry the real treasury, so only this exact figure is ever deleted.
MARKER = 987654321


async def _resources(credits):
    await Database.execute(
        "INSERT INTO maya_rp.resources (session_id, credits, research_points) VALUES ($1, $2, 0)",
        SESSION, credits)


async def _drop_resources(*credits):
    await Database.execute(
        "DELETE FROM maya_rp.resources WHERE session_id = $1 AND credits = ANY($2::bigint[])",
        SESSION, list(credits))


class TestConversionAnswersInsteadOfCrashing:
    async def test_an_unknown_prisoner_gets_an_answer(self, monkeypatch):
        """`p` was bound only inside `if row`, so a roll that passed reached `p.get` unbound."""
        await Database.init()
        try:
            monkeypatch.setattr(prison.random, "random", lambda: 0.0)
            out = await prison.execute_conversion(999999999, "stockholm", SESSION)
            assert out["converted"] is False
            assert out["reason"] == "prisoner_not_found", out
        finally:
            await Database.close()


class TestTheWriteStaysInTheCampaign:
    async def test_record_death_leaves_another_campaign_alone(self):
        await Database.init()
        row = await _prisoner()
        try:
            out = await prison.record_death(row["id"], "execution", 3)
            assert out is None
            status = await Database.fetchval(
                "SELECT status FROM maya_rp.prisoners WHERE id = $1", row["id"])
            assert status == "captured", "a death in another campaign killed this prisoner"
        finally:
            await _drop_prisoner(row["id"])
            await Database.close()

    async def test_upgrade_security_logs_the_session_it_was_given(self, monkeypatch):
        """The ledger row named Config.SESSION_ID, not the session the caller passed."""
        await Database.init()
        row = await _prisoner()
        try:
            monkeypatch.setattr(Config, "SESSION_ID", 999)
            out = await prison.upgrade_security(row["id"], "maximum", 0, SESSION)
            assert out["cell_security"] == "maximum"
            logged = await Database.fetch(
                "SELECT session_id FROM maya_rp.escape_countermeasures WHERE prisoner_id = $1", row["id"])
            assert [r["session_id"] for r in logged] == [SESSION], logged
        finally:
            await _drop_prisoner(row["id"])
            await Database.close()

    async def test_process_escapes_rolls_against_its_own_session(self, monkeypatch):
        """The risk call took no session, so the default campaign answered for every other one."""
        await Database.init()
        row = await _prisoner(escape_risk_pct=100, cell_security="minimal")
        try:
            monkeypatch.setattr(Config, "SESSION_ID", 999)
            monkeypatch.setattr(prison.random, "random", lambda: 0.0)
            out = await prison.process_escapes(SESSION)
            assert out["errors"] == [], out
            assert [e["name"] for e in out["escaped"]] == ["review prisoner"], out
            status = await Database.fetchval(
                "SELECT status FROM maya_rp.prisoners WHERE id = $1", row["id"])
            assert status == "escaped"
        finally:
            await _drop_prisoner(row["id"])
            await Database.close()

    async def test_run_tick_finds_eligibility_in_the_session_it_was_given(self, monkeypatch):
        await Database.init()
        row = await _prisoner(resistance=0, interrogations_count=3,
                              last_interrogation_method="brutal", escape_risk_pct=0,
                              cell_security="isolated")
        try:
            monkeypatch.setattr(Config, "SESSION_ID", 999)
            out = await prison.run_tick(SESSION)
            paths = [c["path"] for c in out["conversion_eligible"]]
            assert paths == ["broken"], out["conversion_eligible"]
        finally:
            await _drop_prisoner(row["id"])
            await Database.close()


class TestSilentFallbacks:
    async def test_interrogate_refuses_a_tier_it_does_not_have(self):
        await Database.init()
        row = await _prisoner()
        try:
            out = await prison.interrogate(row["id"], "soft", session_id=SESSION)
            assert out["success"] is False
            assert "soft" in out["error"]
            assert out["available"] == ["brutal", "enhanced", "standard"]
            ran = await Database.fetchval(
                "SELECT interrogations_count FROM maya_rp.prisoners WHERE id = $1", row["id"])
            assert ran == 0, "a tier that does not exist still ran an interrogation"
        finally:
            await _drop_prisoner(row["id"])
            await Database.close()

    async def test_upgrade_security_refuses_a_level_it_does_not_have(self):
        await Database.init()
        row = await _prisoner()
        try:
            out = await prison.upgrade_security(row["id"], "maximum-security", 0, SESSION)
            assert "error" in out, out
            assert out["available"] == ["isolated", "maximum", "minimal", "standard"]
            level = await Database.fetchval(
                "SELECT cell_security FROM maya_rp.prisoners WHERE id = $1", row["id"])
            assert level == "standard", "an unknown level silently became standard"
        finally:
            await _drop_prisoner(row["id"])
            await Database.close()

    async def test_countermeasure_names_a_measure_it_does_not_have(self):
        await Database.init()
        try:
            out = await prison.apply_countermeasure(999999999, "no-such-measure", SESSION)
            assert out["applied"] is None
            assert "unknown countermeasure" in out["error"], out
            assert "cell_inspection" in out["available"]
        finally:
            await Database.close()

    async def test_countermeasure_names_a_prisoner_it_does_not_have(self):
        await Database.init()
        try:
            out = await prison.apply_countermeasure(999999999, "cell_inspection", SESSION)
            assert out["applied"] is None
            assert "not found" in out["error"], out
        finally:
            await Database.close()

    async def test_intimacy_names_a_path_it_does_not_have(self):
        await Database.init()
        try:
            out = await prison.initiate_intimacy(999999999, "bribery", session_id=SESSION)
            assert out["success"] is False
            assert "unknown intimacy path" in out["reason"], out
            assert out["available"] == ["fear", "seduction", "stockholm"]
        finally:
            await Database.close()

    async def test_intimacy_names_a_prisoner_it_does_not_have(self):
        await Database.init()
        try:
            out = await prison.initiate_intimacy(999999999, "fear", session_id=SESSION)
            assert out["success"] is False
            assert out["reason"] == "prisoner_not_found", out
        finally:
            await Database.close()


class TestCountermeasureCostsMoney:
    async def test_the_cost_leaves_the_session(self):
        await Database.init()
        row = await _prisoner(escape_risk_pct=50)
        await _resources(MARKER)
        try:
            out = await prison.apply_countermeasure(row["id"], "surveillance", SESSION)
            assert out["applied"] == "surveillance", out
            assert out["charged"] == {"credits": 15}, out
            credits = await Database.fetchval(
                "SELECT credits FROM maya_rp.resources WHERE session_id = $1", SESSION)
            assert credits == MARKER - 15
            ledger = await Database.fetchval(
                "SELECT cost_credits FROM maya_rp.escape_countermeasures WHERE prisoner_id = $1",
                row["id"])
            assert ledger == 15
        finally:
            await _drop_prisoner(row["id"])
            await _drop_resources(MARKER, MARKER - 15)
            await Database.close()

    async def test_a_session_that_cannot_pay_is_told_so(self):
        await Database.init()
        row = await _prisoner(escape_risk_pct=50)
        await _resources(5)
        try:
            out = await prison.apply_countermeasure(row["id"], "cell_inspection", SESSION)
            assert out["applied"] is None, out
            assert "cannot pay" in out["error"], out
            assert out["charged"] == {}
            credits = await Database.fetchval(
                "SELECT credits FROM maya_rp.resources WHERE session_id = $1", SESSION)
            assert credits == 5
            risk = await Database.fetchval(
                "SELECT escape_risk_pct FROM maya_rp.prisoners WHERE id = $1", row["id"])
            assert risk == 50, "an unaffordable measure still changed the risk"
            logged = await Database.fetchval(
                "SELECT count(*) FROM maya_rp.escape_countermeasures WHERE prisoner_id = $1",
                row["id"])
            assert logged == 0
        finally:
            await _drop_prisoner(row["id"])
            await _drop_resources(5)
            await Database.close()


class TestCellCapacityIsRead:
    async def test_a_full_hull_takes_nobody(self):
        await Database.init()
        big = await _ship("review hulk", 2)
        small = await _ship("review skiff", 1)
        held = [await _prisoner(cell_ship_id=big), await _prisoner(cell_ship_id=big),
                await _prisoner(cell_ship_id=small)]
        fresh = await _prisoner()
        try:
            cap = await prison.get_fleet_capacity(SESSION)
            assert cap["per_ship"][big]["used"] == 2
            assert cap["per_ship"][big]["available"] == 0
            assert cap["per_ship"][small]["used"] == 1

            out = await prison.assign_cell(fresh["id"], SESSION)
            assert out["assigned"] is False, out
            landed = await Database.fetchval(
                "SELECT cell_ship_id FROM maya_rp.prisoners WHERE id = $1", fresh["id"])
            assert landed is None, "a prisoner was assigned to a full hull"
        finally:
            for r in held + [fresh]:
                await _drop_prisoner(r["id"])
            await _drop_ship(big)
            await _drop_ship(small)
            await Database.close()

    async def test_capacity_arithmetic_holds_for_every_hull(self):
        await Database.init()
        hull = await _ship("review brig", 4)
        held = [await _prisoner(cell_ship_id=hull), await _prisoner(cell_ship_id=hull)]
        try:
            cap = await prison.get_fleet_capacity(SESSION)
            for sid, row in cap["per_ship"].items():
                assert row["available"] == row["capacity"] - row["used"], (sid, row)
            assert cap["used"] == sum(r["used"] for r in cap["per_ship"].values())
            assert cap["available"] == cap["total"] - cap["used"]
            assert cap["per_ship"][hull]["available"] == 2
        finally:
            for r in held:
                await _drop_prisoner(r["id"])
            await _drop_ship(hull)
            await Database.close()

    async def test_a_free_hull_takes_the_prisoner(self):
        await Database.init()
        hull = await _ship("review brig", 1)
        fresh = await _prisoner()
        try:
            out = await prison.assign_cell(fresh["id"], SESSION)
            assert out["assigned"] is True, out
            assert out["ship_id"] == hull
            assert out["cells_free"] == 0
        finally:
            await _drop_prisoner(fresh["id"])
            await _drop_ship(hull)
            await Database.close()


class TestEscapeRiskIsReproducible:
    async def test_the_same_state_and_draw_answer_the_same(self, monkeypatch):
        # If the function rolls for itself, these two draws disagree and the answers differ.
        draws = iter([0.90, 0.10, 0.90, 0.10])
        monkeypatch.setattr(prison.random, "random", lambda: next(draws))
        await Database.init()
        row = await _prisoner(escape_risk_pct=40)
        try:
            first = await prison.calculate_escape_risk(row["id"], session_id=SESSION, roll=0.10)
            second = await prison.calculate_escape_risk(row["id"], session_id=SESSION, roll=0.10)
            assert first == second, (first, second)
            assert first["will_escape"] is True, first
            later = await prison.calculate_escape_risk(row["id"], session_id=SESSION, roll=0.30)
            assert later["will_escape"] is False, later
            assert later["probability"] == first["probability"]
        finally:
            await _drop_prisoner(row["id"])
            await Database.close()


class TestZeroIsAValue:
    """`x or default` read every legitimate 0 as a missing value."""

    async def test_resistance_zero_reaches_the_broken_path(self):
        await Database.init()
        row = await _prisoner(resistance=0, interrogations_count=3,
                              last_interrogation_method="brutal")
        try:
            out = await prison.check_conversion(row["id"], SESSION)
            assert out is not None and out["path"] == "broken", out
        finally:
            await _drop_prisoner(row["id"])
            await Database.close()

    async def test_resistance_zero_is_not_charged_a_resistance_penalty(self):
        await Database.init()
        row = await _prisoner(resistance=0, intel_value=10)
        try:
            out = await prison.interrogate(row["id"], "standard", session_id=SESSION)
            assert out["intel_yield"] == 3, out
        finally:
            await _drop_prisoner(row["id"])
            await Database.close()

    async def test_resistance_zero_opens_the_seduction_path(self):
        await Database.init()
        row = await _prisoner(resistance=0)
        try:
            paths = await prison.get_available_intimacy_paths(row["id"], session_id=SESSION)
            assert "seduction" in paths, paths
        finally:
            await _drop_prisoner(row["id"])
            await Database.close()

    async def test_a_zero_risk_is_a_zero_risk(self):
        await Database.init()
        row = await _prisoner(escape_risk_pct=0)
        try:
            out = await prison.calculate_escape_risk(row["id"], session_id=SESSION, roll=0.5)
            assert out["probability"] == 0, out
            assert out["will_escape"] is False, out
        finally:
            await _drop_prisoner(row["id"])
            await Database.close()

    async def test_a_countermeasure_does_not_raise_a_zero_risk(self):
        await Database.init()
        row = await _prisoner(escape_risk_pct=0)
        try:
            out = await prison.apply_countermeasure(row["id"], "ally_interrogation", SESSION)
            assert out["applied"] == "ally_interrogation", out
            assert out["new_risk"] == 0, out
        finally:
            await _drop_prisoner(row["id"])
            await Database.close()


class TestTheRiskLookupSpeaks:
    async def test_a_failed_lookup_is_logged(self, monkeypatch):
        seen = []

        async def boom(*args, **kwargs):
            raise RuntimeError("db gone")

        monkeypatch.setattr(prison.Database, "fetchrow", boom)
        monkeypatch.setattr(prison, "error", lambda module, message: seen.append(message))
        out = await prison._handle_intimacy_risk("assassin", 1, SESSION)
        assert out["type"] == "combat_interrupt"
        assert seen, "the lookup failed and nothing said so"
        assert "db gone" in seen[0]
