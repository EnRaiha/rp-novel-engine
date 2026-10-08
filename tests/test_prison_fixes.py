"""Live-database tests for the modules/prison.py defect wave.

Defects covered, each asserted on the stored rows and not only on the return value:

1. `broken` was missing from five status filters, so a broken prisoner did not count toward cell
   capacity, did not roll to escape, did not age, and was not offered for conversion. The next
   `interrogate` also wrote `interrogated` over `broken`.
2. `interrogate`, `execute_conversion`, `record_death` and `initiate_intimacy` had no status guard:
   dead and recruited prisoners were interrogated, recruited, killed again and bedded.
3. `secrecy` was not checked against the log's CHECK, and the prisoner UPDATE committed before the
   log INSERT raised, leaving a counted interrogation with no log row.
4. `execute_conversion` inserted a crew row on every successful roll, wrote ship 1 (another
   campaign's hull), and ignored the path requirement.
5. `apply_countermeasure` checked the balance and deducted in two statements, so concurrent calls
   overdrew.
6. `assign_cell` reported success for a prisoner that does not exist.
8. `feed_intel_to_investigation` attached intel to a prisoner of another campaign.
9. `run_tick` eligibility rows carried no `prisoner_id`.
10. `upgrade_security` logged a cost it never charged and accepted a downgrade.
11. Every writer reached the frozen reference campaigns 3 and 5.

Scratch sessions: 900 + pid % 100 (the slot `scratch_session` hands out) and the next slot. Sessions
3 and 5 are never written. Every row this file creates is removed in the fixture's `finally`.
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import sys

import pytest
import pytest_asyncio

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import ooc  # noqa: E402
from core.db import Database  # noqa: E402
from modules import prison  # noqa: E402


async def _purge(session_id: int) -> None:
    """Remove one scratch session's rows in foreign-key order."""
    q = Database.execute
    await q("DELETE FROM maya_rp.interrogation_log WHERE session_id=$1", session_id)
    await q("DELETE FROM maya_rp.escape_countermeasures WHERE session_id=$1", session_id)
    await q("DELETE FROM maya_rp.prisoner_intel_pipeline WHERE prisoner_id IN "
            "(SELECT id FROM maya_rp.prisoners WHERE session_id=$1)", session_id)
    await q("DELETE FROM maya_rp.clues WHERE session_id=$1", session_id)
    await q("DELETE FROM maya_rp.crew_roster WHERE session_id=$1", session_id)
    await q("DELETE FROM maya_rp.prisoners WHERE session_id=$1", session_id)
    await q("DELETE FROM maya_rp.ships WHERE session_id=$1", session_id)
    await q("DELETE FROM maya_rp.resources WHERE session_id=$1", session_id)
    await q("DELETE FROM maya_rp.sessions WHERE id=$1", session_id)


@pytest_asyncio.fixture
async def world(scratch_session):
    """Two scratch campaigns with a `sessions` row each. Yields `(sid, other_sid)`."""
    sid = scratch_session
    other = 900 + ((os.getpid() + 1) % 100)
    await Database.init()
    try:
        for s in (sid, other):
            await _purge(s)
            await Database.execute(
                "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1,'Prison fixes scratch','active')", s)
        yield sid, other
    finally:
        for s in (sid, other):
            await _purge(s)
        await Database.close()


async def _prisoner(sid: int, **over) -> int:
    cols = {
        "session_id": sid,
        "name": "fix prisoner",
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
    return await Database.fetchval(
        f"INSERT INTO maya_rp.prisoners ({keys}) VALUES ({marks}) RETURNING id", *cols.values())


async def _ship(sid: int, name: str, capacity: int) -> int:
    return await Database.fetchval(
        "INSERT INTO maya_rp.ships (session_id, name, cell_capacity) VALUES ($1,$2,$3) RETURNING id",
        sid, name, capacity)


async def _credits(sid: int, amount: int) -> None:
    await Database.execute(
        "INSERT INTO maya_rp.resources (session_id, credits) VALUES ($1,$2) "
        "ON CONFLICT (session_id) DO UPDATE SET credits = $2", sid, amount)


async def _col(pid: int, column: str):
    return await Database.fetchval(f"SELECT {column} FROM maya_rp.prisoners WHERE id=$1", pid)


async def _count(table: str, sid: int) -> int:
    return await Database.fetchval(f"SELECT count(*) FROM maya_rp.{table} WHERE session_id=$1", sid)


#: Meets the `stockholm` requirement (intimacy path + 8 held sessions) with a held status.
STOCKHOLM = {"intimacy_path": "stockholm", "held_sessions": 8}


class TestBrokenPrisonerIsStillHeld:
    async def test_a_broken_prisoner_fills_a_cell(self, world):
        """Pre-fix: the capacity filter skipped `broken`, so the cell read free and took a second prisoner."""
        sid, _ = world
        hull = await _ship(sid, "fix brig", 1)
        await _prisoner(sid, status="broken", cell_ship_id=hull)
        fresh = await _prisoner(sid)
        cap = await prison.get_fleet_capacity(sid)
        assert cap["per_ship"][hull]["used"] == 1, f"broken prisoner not counted: {cap['per_ship'][hull]}"
        out = await prison.assign_cell(fresh, sid)
        assert out["assigned"] is False, f"a full cell took a second prisoner: {out}"
        assert await _col(fresh, "cell_ship_id") is None, "the second prisoner landed in the full cell"

    async def test_interrogating_a_broken_prisoner_keeps_it_broken(self, world, monkeypatch):
        """Pre-fix: an unbroken roll wrote `interrogated` over `broken`."""
        sid, _ = world
        pid = await _prisoner(sid, status="broken")
        monkeypatch.setattr(prison.random, "random", lambda: 0.99)
        out = await prison.interrogate(pid, "standard", session_id=sid)
        assert out["success"] is True, out
        assert await _col(pid, "status") == "broken", "the next interrogation downgraded the broken prisoner"
        assert await _col(pid, "interrogations_count") == 1, "the interrogation was not counted"

    async def test_a_broken_prisoner_rolls_to_escape(self, world, monkeypatch):
        """Pre-fix: process_escapes selected only captured/holding."""
        sid, _ = world
        pid = await _prisoner(sid, status="broken", escape_risk_pct=50)
        monkeypatch.setattr(prison.random, "random", lambda: 0.0)
        out = await prison.process_escapes(sid)
        assert [e["name"] for e in out["escaped"]] == ["fix prisoner"], out
        assert await _col(pid, "status") == "escaped"

    async def test_a_broken_prisoner_ages_and_is_offered_for_conversion(self, world, monkeypatch):
        """Pre-fix: the tick aged and listed captured/holding/interrogated only."""
        sid, _ = world
        pid = await _prisoner(sid, status="broken", escape_risk_pct=0, **STOCKHOLM)
        monkeypatch.setattr(prison.random, "random", lambda: 0.999)
        out = await prison.run_tick(sid)
        assert await _col(pid, "held_sessions") == 9, "the broken prisoner did not age"
        assert [c["prisoner_id"] for c in out["conversion_eligible"]] == [pid], out["conversion_eligible"]


class TestStatusGuards:
    @pytest.mark.parametrize("status", ["dead", "recruited"])
    async def test_interrogating_a_gone_prisoner_is_refused(self, world, status):
        """Pre-fix: a dead or recruited prisoner was interrogated and rewritten as `interrogated`."""
        sid, _ = world
        pid = await _prisoner(sid, status=status)
        out = await prison.interrogate(pid, "standard", session_id=sid)
        assert out["success"] is False, f"{status} prisoner was interrogated: {out}"
        assert await _col(pid, "status") == status, "the refused interrogation rewrote the status"
        assert await _col(pid, "interrogations_count") == 0
        assert await _count("interrogation_log", sid) == 0, "a refused interrogation wrote a log row"

    @pytest.mark.parametrize("status", ["dead", "recruited"])
    async def test_converting_a_gone_prisoner_makes_no_crew(self, world, monkeypatch, status):
        """Pre-fix: a dead prisoner who met the requirement was recruited."""
        sid, _ = world
        pid = await _prisoner(sid, status=status, **STOCKHOLM)
        monkeypatch.setattr(prison.random, "random", lambda: 0.0)
        out = await prison.execute_conversion(pid, "stockholm", sid)
        assert out["converted"] is False, out
        assert await _col(pid, "status") == status
        assert await _count("crew_roster", sid) == 0, "a crew row was made from a gone prisoner"

    async def test_recording_a_death_twice_is_refused(self, world):
        """Pre-fix: `dead` was written over `recruited`, killing crew."""
        sid, _ = world
        pid = await _prisoner(sid, status="recruited")
        out = await prison.record_death(pid, "execution", sid)
        assert out and "error" in out, f"a recruited prisoner was killed: {out}"
        assert await _col(pid, "status") == "recruited"
        assert await _col(pid, "death_cause") is None

    async def test_intimacy_with_a_dead_prisoner_is_refused(self, world):
        """Pre-fix: the lookup read only the id, so a dead prisoner took the intimacy flag."""
        sid, _ = world
        pid = await _prisoner(sid, status="dead")
        out = await prison.initiate_intimacy(pid, "fear", session_id=sid)
        assert out["success"] is False and out["reason"] == "prisoner_not_held", out
        assert await _col(pid, "intimacy_flag") is False, "intimacy was written onto a dead prisoner"


class TestSecrecyIsChecked:
    async def test_an_invalid_secrecy_is_refused_before_any_write(self, world):
        """Pre-fix: the prisoner UPDATE committed, then the log INSERT raised CheckViolation."""
        sid, _ = world
        pid = await _prisoner(sid)
        out = await prison.interrogate(pid, "standard", secrecy="top_secret", session_id=sid)
        assert out["success"] is False, out
        assert "top_secret" in out["error"], out
        assert out["available"] == ["hidden", "public", "witnessed"], out
        assert await _col(pid, "interrogations_count") == 0, "the count moved on a refused interrogation"
        assert await _col(pid, "status") == "captured"
        assert await _count("interrogation_log", sid) == 0

    async def test_interrogation_count_and_log_row_land_together(self, world):
        """The count moves by one and exactly one log row exists."""
        sid, _ = world
        pid = await _prisoner(sid, interrogations_count=2)
        out = await prison.interrogate(pid, "standard", secrecy="witnessed", session_id=sid)
        assert out["secrecy"] == "witnessed", out
        assert await _col(pid, "interrogations_count") == 3
        assert await _count("interrogation_log", sid) == 1


class TestConversionIsOnce:
    async def test_two_conversions_make_one_crew_row(self, world, monkeypatch):
        """Pre-fix: every successful roll inserted a crew row."""
        sid, _ = world
        pid = await _prisoner(sid, **STOCKHOLM)
        monkeypatch.setattr(prison.random, "random", lambda: 0.0)
        first = await prison.execute_conversion(pid, "stockholm", sid)
        second = await prison.execute_conversion(pid, "stockholm", sid)
        assert first["converted"] is True, first
        assert second["converted"] is False, f"the second call converted again: {second}"
        assert await _count("crew_roster", sid) == 1, "one prisoner became two crew members"
        assert await _col(pid, "status") == "recruited"

    async def test_concurrent_conversions_make_one_crew_row(self, world, monkeypatch):
        """Pre-fix: both callers passed the roll and both inserted."""
        sid, _ = world
        pid = await _prisoner(sid, **STOCKHOLM)
        monkeypatch.setattr(prison.random, "random", lambda: 0.0)
        outs = await asyncio.gather(*[prison.execute_conversion(pid, "stockholm", sid) for _ in range(3)])
        assert sum(1 for o in outs if o["converted"]) == 1, outs
        assert await _count("crew_roster", sid) == 1

    async def test_the_crew_row_takes_a_ship_of_the_session(self, world, monkeypatch):
        """Pre-fix: a prisoner with no cell was written onto ship 1, which belongs to another campaign."""
        sid, _ = world
        hull = await _ship(sid, "fix flagship", 0)
        pid = await _prisoner(sid, **STOCKHOLM)
        monkeypatch.setattr(prison.random, "random", lambda: 0.0)
        out = await prison.execute_conversion(pid, "stockholm", sid)
        assert out["converted"] is True, out
        ship = await Database.fetchval("SELECT ship_id FROM maya_rp.crew_roster WHERE session_id=$1", sid)
        assert ship == hull, f"crew landed on ship {ship}, expected the session's ship {hull}"

    async def test_a_session_with_no_ship_writes_no_ship(self, world, monkeypatch):
        """Pre-fix: ship_id fell back to the literal 1."""
        sid, _ = world
        pid = await _prisoner(sid, **STOCKHOLM)
        monkeypatch.setattr(prison.random, "random", lambda: 0.0)
        out = await prison.execute_conversion(pid, "stockholm", sid)
        assert out["converted"] is True, out
        ship = await Database.fetchval("SELECT ship_id FROM maya_rp.crew_roster WHERE session_id=$1", sid)
        assert ship is None, f"crew was assigned ship {ship} from nowhere"

    async def test_a_path_the_prisoner_does_not_meet_is_refused(self, world, monkeypatch):
        """Pre-fix: any valid path name converted any prisoner once the roll passed."""
        sid, _ = world
        pid = await _prisoner(sid, resistance=90)
        monkeypatch.setattr(prison.random, "random", lambda: 0.0)
        out = await prison.execute_conversion(pid, "persuasion", sid)
        assert out["converted"] is False and out["reason"] == "not_eligible", out
        assert await _col(pid, "status") == "captured"
        assert await _count("crew_roster", sid) == 0


class TestCountermeasureCannotOverdraw:
    async def test_concurrent_countermeasures_charge_once(self, world):
        """Pre-fix: each caller passed the balance check before any deducted, and GREATEST(0) hid the overdraw."""
        sid, _ = world
        await _credits(sid, 10)
        pids = [await _prisoner(sid, escape_risk_pct=50) for _ in range(4)]
        outs = await asyncio.gather(*[prison.apply_countermeasure(p, "cell_inspection", sid) for p in pids])
        applied = [o for o in outs if o["applied"]]
        assert len(applied) == 1, f"{len(applied)} countermeasures paid for 10 credits: {outs}"
        assert await Database.fetchval(
            "SELECT credits FROM maya_rp.resources WHERE session_id=$1", sid) == 0
        assert await _count("escape_countermeasures", sid) == 1, "an unpaid countermeasure was logged"
        reduced = [p for p in pids if await _col(p, "escape_risk_pct") != 50]
        assert len(reduced) == 1, "an unpaid countermeasure lowered a risk"


class TestAssignCell:
    async def test_a_missing_prisoner_is_not_reported_assigned(self, world):
        """Pre-fix: the UPDATE matched no row and the function still answered `assigned: True`."""
        sid, _ = world
        hull = await _ship(sid, "fix brig", 3)
        out = await prison.assign_cell(999999999, sid)
        assert out["assigned"] is False, f"a prisoner that does not exist was assigned: {out}"
        assert out["ship_id"] is None
        assert hull and await _count("prisoners", sid) == 0

    async def test_a_prisoner_of_another_campaign_is_not_assigned(self, world):
        sid, other = world
        await _ship(sid, "fix brig", 3)
        foreign = await _prisoner(other)
        out = await prison.assign_cell(foreign, sid)
        assert out["assigned"] is False, out
        assert await _col(foreign, "cell_ship_id") is None


class TestIntelStaysInTheCampaign:
    async def test_a_prisoner_of_another_campaign_is_refused(self, world):
        """Pre-fix: the pipeline insert took the prisoner id alone."""
        sid, other = world
        foreign = await _prisoner(other)
        out = await prison.feed_intel_to_investigation(foreign, 1, "stolen intel", sid)
        assert out is None, f"intel was attached to another campaign's prisoner: {out}"
        assert await Database.fetchval(
            "SELECT count(*) FROM maya_rp.prisoner_intel_pipeline WHERE prisoner_id=$1", foreign) == 0
        assert await _count("clues", sid) == 0, "a clue was created for a refused transfer"


class TestTickRows:
    async def test_eligible_rows_name_their_prisoner(self, world, monkeypatch):
        """Pre-fix: rows were bare check_conversion dicts, so the caller could not tell who qualified."""
        sid, _ = world
        pid = await _prisoner(sid, escape_risk_pct=0, **STOCKHOLM)
        monkeypatch.setattr(prison.random, "random", lambda: 0.999)
        out = await prison.run_tick(sid)
        rows = out["conversion_eligible"]
        assert [r.get("prisoner_id") for r in rows] == [pid], rows
        assert rows[0]["path"] == "stockholm"


class TestUpgradeSecurityCharges:
    async def test_the_logged_cost_leaves_the_session(self, world):
        """Pre-fix: the ledger row said 100 credits and the treasury kept them."""
        sid, _ = world
        await _credits(sid, 500)
        pid = await _prisoner(sid)
        out = await prison.upgrade_security(pid, "maximum", 2, sid)
        assert out["cell_security"] == "maximum", out
        assert await Database.fetchval(
            "SELECT credits FROM maya_rp.resources WHERE session_id=$1", sid) == 400
        assert await Database.fetchval(
            "SELECT cost_credits FROM maya_rp.escape_countermeasures WHERE prisoner_id=$1", pid) == 100

    async def test_a_session_that_cannot_pay_changes_nothing(self, world):
        sid, _ = world
        await _credits(sid, 40)
        pid = await _prisoner(sid)
        out = await prison.upgrade_security(pid, "maximum", 2, sid)
        assert "error" in out and "cannot pay" in out["error"], out
        assert await _col(pid, "cell_security") == "standard", "an unpaid upgrade moved the level"
        assert await Database.fetchval(
            "SELECT credits FROM maya_rp.resources WHERE session_id=$1", sid) == 40
        assert await _count("escape_countermeasures", sid) == 0

    async def test_a_downgrade_is_refused(self, world):
        """Pre-fix: `isolated` to `minimal` was applied and reported as an upgrade."""
        sid, _ = world
        pid = await _prisoner(sid, cell_security="isolated")
        out = await prison.upgrade_security(pid, "minimal", 0, sid)
        assert "error" in out, f"security was lowered: {out}"
        assert await _col(pid, "cell_security") == "isolated"

    async def test_negative_guards_cannot_mint_credits(self, world):
        sid, _ = world
        await _credits(sid, 100)
        pid = await _prisoner(sid)
        out = await prison.upgrade_security(pid, "maximum", -4, sid)
        assert "error" in out, out
        assert await Database.fetchval(
            "SELECT credits FROM maya_rp.resources WHERE session_id=$1", sid) == 100


#: One call per public writer. Each takes `(sid, pid)`.
WRITERS = {
    "resolve_capture": lambda sid, pid: prison.resolve_capture(2, "Iron Concord", session_id=sid),
    "interrogate": lambda sid, pid: prison.interrogate(pid, "standard", session_id=sid),
    "execute_conversion": lambda sid, pid: prison.execute_conversion(pid, "stockholm", sid),
    "record_death": lambda sid, pid: prison.record_death(pid, "execution", sid),
    "feed_intel_to_investigation": lambda sid, pid: prison.feed_intel_to_investigation(pid, 1, "intel", sid),
    "initiate_intimacy": lambda sid, pid: prison.initiate_intimacy(pid, "fear", session_id=sid),
    "assign_cell": lambda sid, pid: prison.assign_cell(pid, sid),
    "process_escapes": lambda sid, pid: prison.process_escapes(sid),
    "upgrade_security": lambda sid, pid: prison.upgrade_security(pid, "maximum", 1, sid),
    "apply_countermeasure": lambda sid, pid: prison.apply_countermeasure(pid, "cell_inspection", sid),
    "run_tick": lambda sid, pid: prison.run_tick(sid),
}


class TestFrozenCampaignIsReference:
    @pytest.mark.parametrize("writer", sorted(WRITERS))
    async def test_every_writer_is_refused_and_writes_nothing(self, world, monkeypatch, writer):
        """Pre-fix: no prison writer checked the freeze, so sessions 3 and 5 took prisoners and credits."""
        import core.session as session_mod

        sid, _ = world
        await _credits(sid, 500)
        await _ship(sid, "fix brig", 3)
        pid = await _prisoner(sid, escape_risk_pct=50, **STOCKHOLM)
        before = dict(await Database.fetchrow("SELECT * FROM maya_rp.prisoners WHERE id=$1", pid))
        prisoners_before = await _count("prisoners", sid)

        monkeypatch.setattr(session_mod, "is_frozen", lambda s: True)
        monkeypatch.setattr(ooc, "_maintenance_active", lambda: False)
        monkeypatch.setattr(prison.random, "random", lambda: 0.0)
        with pytest.raises(ooc.FrozenSession):
            await WRITERS[writer](sid, pid)

        after = dict(await Database.fetchrow("SELECT * FROM maya_rp.prisoners WHERE id=$1", pid))
        assert after == before, f"{writer} changed the prisoner before it was refused"
        assert await _count("prisoners", sid) == prisoners_before, f"{writer} inserted prisoners"
        assert await Database.fetchval(
            "SELECT credits FROM maya_rp.resources WHERE session_id=$1", sid) == 500, f"{writer} spent credits"
        for table in ("interrogation_log", "escape_countermeasures", "crew_roster", "clues"):
            assert await _count(table, sid) == 0, f"{writer} wrote {table}"
