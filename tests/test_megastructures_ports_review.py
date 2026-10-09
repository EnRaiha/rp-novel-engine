"""Megastructures & Ports review: what reading the module in full turned up.

The tick took a session and never put it in its read, and the port upgrade resolved its port by id
alone. Nothing here writes to session 3, and every row this file creates in session 5 is removed in a
`finally`.
"""
from __future__ import annotations

import inspect
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
from asyncpg.exceptions import PostgresError  # noqa: E402

from core.db import Database  # noqa: E402
from modules import megastructures_ports as mp  # noqa: E402

SESSION = 5
TYPE_ID = 1          # Dyson Sphere: two phases, phase 1 costs fuel, alloys and dream essence
PORT_TYPE_ID = 1     # Spaceport: upgrades large_spaceport, shipyard
UPGRADE = "large_spaceport"


async def _construction(session_id=SESSION, progress=0, phase=1):
    return await Database.fetchval(
        "INSERT INTO maya_rp.megastructure_construction "
        "(session_id, megastructure_type_id, current_phase, progress_pct, status, started_at) "
        "VALUES ($1, $2, $3, $4, 'construction', NOW()) RETURNING id",
        session_id, TYPE_ID, phase, progress)


async def _port(session_id=SESSION, level=1):
    return await Database.fetchval(
        "INSERT INTO maya_rp.ports (session_id, port_type_id, name, level, status) "
        "VALUES ($1, $2, 'review port', $3, 'active') RETURNING id",
        session_id, PORT_TYPE_ID, level)


async def _drop_construction(cid):
    await Database.execute("DELETE FROM maya_rp.megastructure_construction WHERE id = $1", cid)


async def _drop_port(pid):
    await Database.execute("DELETE FROM maya_rp.port_upgrades WHERE port_id = $1", pid)
    await Database.execute("DELETE FROM maya_rp.ports WHERE id = $1", pid)


class _RecordingDatabase:
    """Answers one unfinished site and keeps every value the tick binds for `progress_pct`.

    A long-run rate needs thousands of ticks, which is a rate at which the pool would dominate the
    run. Nothing is lost by leaving it out: asyncpg truncates on encode, so the value bound here is
    the last point at which a fractional step can survive, and the read and the write are the whole
    of the path this test measures.
    """

    def __init__(self):
        self.written = []

    async def fetch(self, sql, *args):
        return [{"id": 1, "status": "construction", "current_phase": 1, "progress_pct": 0,
                 "construction_phases": [{"phase": 1, "cost": {}, "time_days": 365}],
                 "name": "Dyson Sphere"}]

    async def execute(self, sql, *args):
        self.written.append(args[0])


class TestTheTickStaysInItsCampaign:
    async def test_advancing_ignores_another_campaign(self):
        """One phase is 365 game days, so 365 days in one call is the call that would pause it."""
        await Database.init()
        cid = await _construction(progress=0)
        try:
            await mp.advance_megastructure(7, 365.0)
            status = await Database.fetchval(
                "SELECT status FROM maya_rp.megastructure_construction WHERE id = $1", cid)
            assert status == "construction", "another campaign's tick paused this construction site"
        finally:
            await _drop_construction(cid)
            await Database.close()

    async def test_advancing_its_own_site_reports_what_it_did(self):
        await Database.init()
        cid = await _construction(progress=0)
        try:
            tally = await mp.advance_megastructure(SESSION, 365.0)
            assert tally == {"advanced": 1, "paused": 1, "completed": 0}, tally
            row = await Database.fetchrow(
                "SELECT status, progress_pct FROM maya_rp.megastructure_construction WHERE id = $1", cid)
            assert row["status"] == "paused", dict(row)
        finally:
            await _drop_construction(cid)
            await Database.close()

    async def test_a_sub_one_percent_step_reaches_the_integer_column(self, scratch_session, monkeypatch):
        """Two pinned draws through the real column: 0.137 rounds up once, then rounds down.

        The write truncates nothing in Python, so the loss happens at the column: asyncpg binds a
        float into `progress_pct` as an integer without raising (measured: 0.25 stores 0), and one
        tick against a 365-day phase is 0.137. The old expectation here was `progress == 0`, which
        is that truncation.
        """
        import random

        await Database.init()
        await _seed_session(scratch_session)
        try:
            cid = await _construction(scratch_session, progress=0)

            monkeypatch.setattr(random, "random", lambda: 0.0)      # the fraction rounds up
            await mp.advance_megastructure(scratch_session, 0.5)
            progress = await Database.fetchval(
                "SELECT progress_pct FROM maya_rp.megastructure_construction WHERE id = $1", cid)
            assert progress == 1, "a sub-1% step was truncated to nothing"

            monkeypatch.setattr(random, "random", lambda: 0.999)    # and the next one rounds down
            await mp.advance_megastructure(scratch_session, 0.5)
            progress = await Database.fetchval(
                "SELECT progress_pct FROM maya_rp.megastructure_construction WHERE id = $1", cid)
            assert progress == 1, "the step was counted twice"
        finally:
            await _drop_session(scratch_session)
            await Database.close()

    async def test_a_short_tick_keeps_the_long_run_rate(self, monkeypatch):
        """0.5 game days against a 365-day phase is 0.137% of the phase, and the column is INTEGER.

        One draw decides nothing: rounding up is correct 13.7% of the time. Seeded, over many
        ticks, the mean is the check. A mean of 0 is the truncation (`int()` in Python, or the
        column's own encode); a mean of 1 is an unconditional round up.
        """
        import random

        recorder = _RecordingDatabase()
        monkeypatch.setattr(mp, "Database", recorder)
        random.seed(20261009)
        ticks = 40_000
        for _ in range(ticks):
            await mp.advance_megastructure(7, 0.5)

        assert len(recorder.written) == ticks, "the tick did not reach its write"
        rate = sum(recorder.written) / ticks
        assert abs(rate - (0.5 / 365) * 100) < 0.02, f"the long-run rate drifted: {rate}"

    async def test_the_tick_does_not_default_to_the_frozen_campaign(self):
        default = inspect.signature(mp.run_tick).parameters["session_id"].default
        assert default is None, default

    async def test_a_failing_tick_is_logged_as_a_fault(self, monkeypatch):
        seen = []

        async def boom(session_id, game_days=0.5):
            raise RuntimeError("construction query died")

        monkeypatch.setattr(mp, "advance_megastructure", boom)
        monkeypatch.setattr(mp, "error", lambda module, message: seen.append(message))
        out = await mp.run_tick(SESSION)
        assert "construction query died" in out["error"], out
        assert seen, "a failing tick printed and said nothing at fault level"


class TestThePorts:
    async def test_upgrading_another_campaigns_port_is_refused(self):
        await Database.init()
        pid = await _port()
        try:
            out = await mp.upgrade_port(7, pid, UPGRADE)
            assert "not found in session 7" in out.get("error", ""), out
            level = await Database.fetchval("SELECT level FROM maya_rp.ports WHERE id = $1", pid)
            assert level == 1, "another campaign raised this port"
        finally:
            await _drop_port(pid)
            await Database.close()

    async def test_a_port_without_the_upgrade_is_refused(self):
        await Database.init()
        pid = await _port()
        try:
            out = await mp.upgrade_port(SESSION, pid, "orbital_cathedral")
            assert "not available" in out.get("error", ""), out
        finally:
            await _drop_port(pid)
            await Database.close()


class TestTheStatusReaders:
    async def test_both_readers_answer_without_a_session_argument(self):
        """`Config` is read here and the module never imported it: the default path was NameError."""
        await Database.init()
        try:
            assert await mp.get_megastructure_status() == []
            assert await mp.get_port_overview() == []
        finally:
            await Database.close()

    async def test_a_construction_in_another_session_is_invisible(self):
        await Database.init()
        cid = await _construction()
        try:
            assert await mp.get_megastructure_status(7) == []
            assert len(await mp.get_megastructure_status(SESSION)) == 1
        finally:
            await _drop_construction(cid)
            await Database.close()


class TestTheDoors:
    async def test_an_unknown_type_is_refused(self):
        await Database.init()
        try:
            out = await mp.start_construction(SESSION, 999999999)
            assert "not found" in out["error"], out
        finally:
            await Database.close()


# ── the phase-1 charge ───────────────────────────────────────────────────────


class _GateOpenDatabase:
    """Answers the research gate; every other statement still runs on the real pool.

    All six `megastructure_types` name a `research_required` project and none of those names exists
    in the live `research_projects` catalogue, so the gate refuses every type before the charge. The
    seeded alternative is a global row in the live tech catalogue, which this test will not write.
    """

    @staticmethod
    async def fetchrow(sql, *args):
        if "research_projects" in sql:
            return {"unlocked": True}
        return await Database.fetchrow(sql, *args)

    @staticmethod
    async def execute(sql, *args):
        return await Database.execute(sql, *args)

    @staticmethod
    def transaction():
        return Database.transaction()


async def _seed_session(session_id: int) -> None:
    """`resources.session_id` and `megastructure_construction.session_id` both carry a FK to `sessions`."""
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1, 'mega charge review', 'active')"
        " ON CONFLICT (id) DO NOTHING", session_id)


async def _drop_session(session_id: int) -> None:
    """`resources_session_id_fkey` is the one FK to `sessions` here with no ON DELETE CASCADE."""
    for table in ("resources", "megastructure_construction", "story_log"):
        await Database.execute(f"DELETE FROM maya_rp.{table} WHERE session_id = $1", session_id)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", session_id)


class TestTheCharge:
    """The debit and the construction row are one unit of work, and the row takes a naive timestamp.

    `estimated_completion` is TIMESTAMP WITHOUT TIME ZONE and asyncpg raises DataError on a tz-aware
    value for it, so the charge used to commit on the pool and the insert then raised: the credits
    were spent and no construction row existed. Sessions 3 and 5 are frozen reference, so every row
    here belongs to `scratch_session`.
    """

    async def test_a_construction_is_paid_for_and_recorded(self, scratch_session, monkeypatch):
        """TYPE_ID phase 1 costs 100000 alloys, 50000 fuel and 100 dream essence, once."""
        monkeypatch.setattr(mp, "Database", _GateOpenDatabase)
        await Database.init()
        await _seed_session(scratch_session)
        try:
            await Database.execute(
                "INSERT INTO maya_rp.resources (session_id, credits, alloys, fuel, dream_essence) "
                "VALUES ($1, 0, 200000, 100000, 200)", scratch_session)
            out = await mp.start_construction(scratch_session, TYPE_ID)
            assert "error" not in out, out
            status = await Database.fetchval(
                "SELECT status FROM maya_rp.megastructure_construction WHERE session_id = $1",
                scratch_session)
            assert status == "construction", "the charge committed with no construction row"
            row = await Database.fetchrow(
                "SELECT alloys, fuel, dream_essence FROM maya_rp.resources WHERE session_id = $1",
                scratch_session)
            assert (row["alloys"], row["fuel"], row["dream_essence"]) == (100000, 50000, 100), dict(row)
        finally:
            await _drop_session(scratch_session)
            await Database.close()

    async def test_a_failed_insert_leaves_the_treasury_whole(self, scratch_session, monkeypatch):
        """Sector 999999999 breaks `megastructure_construction_sector_id_fkey` after the debit.

        The base class is caught so this test stays about the rollback: a tz-aware timestamp also
        raises a `PostgresError` from the same insert, and the sibling test owns that property.
        """
        monkeypatch.setattr(mp, "Database", _GateOpenDatabase)
        await Database.init()
        await _seed_session(scratch_session)
        try:
            await Database.execute(
                "INSERT INTO maya_rp.resources (session_id, credits, alloys, fuel, dream_essence) "
                "VALUES ($1, 0, 200000, 100000, 200)", scratch_session)
            with pytest.raises(PostgresError):
                await mp.start_construction(scratch_session, TYPE_ID, sector_id=999999999)
            row = await Database.fetchrow(
                "SELECT alloys, fuel, dream_essence FROM maya_rp.resources WHERE session_id = $1",
                scratch_session)
            assert (row["alloys"], row["fuel"], row["dream_essence"]) == (200000, 100000, 200), \
                "the insert failed but the phase-1 charge stayed committed"
            sites = await Database.fetchval(
                "SELECT count(*) FROM maya_rp.megastructure_construction WHERE session_id = $1",
                scratch_session)
            assert sites == 0, sites
        finally:
            await _drop_session(scratch_session)
            await Database.close()

    async def test_the_completion_is_bound_naive(self, monkeypatch):
        """The insert binds a naive datetime: the column is TIMESTAMP WITHOUT TIME ZONE."""
        recorded = {}

        class _Conn:
            async def fetchrow(self, sql, *args):
                recorded["estimated"] = args[4]
                return {"id": 1}

        class _Transaction:
            async def __aenter__(self):
                return _Conn()

            async def __aexit__(self, *exc):
                return False

        # The INSERT is answered on both paths: the transaction connection when the charge and the
        # insert share one, the pool when they do not. This test owns the timestamp alone.
        class _StubDatabase:
            async def fetchrow(self, sql, *args):
                if "INSERT INTO maya_rp.megastructure_construction" in sql:
                    recorded["estimated"] = args[4]
                    return {"id": 1}
                return {"id": TYPE_ID, "name": "Dyson Sphere", "research_required": None,
                        "construction_phases": [{"phase": 1, "cost": {}, "time_days": 365}]}

            def transaction(self):
                return _Transaction()

        async def _afford(session_id, costs, conn=None):
            return True, ""

        async def _charge(session_id, costs, conn=None):
            return costs

        async def _logged(*args, **kwargs):
            return None

        monkeypatch.setattr(mp, "Database", _StubDatabase())
        monkeypatch.setattr(mp, "_check_afford", _afford)
        monkeypatch.setattr(mp, "_deduct_resources", _charge)
        monkeypatch.setattr(mp, "_log", _logged)

        out = await mp.start_construction(7, TYPE_ID)
        assert "error" not in out, out
        assert recorded["estimated"].tzinfo is None, "a tz-aware value cannot enter a naive column"


# ── the paused site ──────────────────────────────────────────────────────────


async def _paused_construction(session_id, progress=100):
    """A site that reached the phase boundary and could not pay for the next phase."""
    return await Database.fetchval(
        "INSERT INTO maya_rp.megastructure_construction "
        "(session_id, megastructure_type_id, current_phase, progress_pct, status, started_at) "
        "VALUES ($1, $2, 1, $3, 'paused', NOW()) RETURNING id",
        session_id, TYPE_ID, progress)


class TestThePausedSite:
    """A paused site left the tick's read set for good, so the treasury recovering changed nothing.

    The read filtered on `mc.status = 'construction'`, and the only writes to that column are
    `paused` and `completed`: nothing put a site back, so the eleven paused and repair rows in the
    reference campaign could never move again. Every row here belongs to `scratch_session`.

    Dyson Sphere phase 2 costs 200000 alloys and 1000 rare earth, and takes 730 days.
    """

    async def test_a_paused_site_resumes_when_the_next_phase_is_affordable(self, scratch_session):
        await Database.init()
        await _seed_session(scratch_session)
        try:
            await Database.execute(
                "INSERT INTO maya_rp.resources (session_id, credits, alloys, fuel, dream_essence,"
                " rare_earth) VALUES ($1, 0, 250000, 0, 0, 1000)", scratch_session)
            cid = await _paused_construction(scratch_session)

            await mp.advance_megastructure(scratch_session, 365.0)

            row = await Database.fetchrow(
                "SELECT current_phase, progress_pct, status FROM maya_rp.megastructure_construction"
                " WHERE id = $1", cid)
            assert (row["current_phase"], row["progress_pct"], row["status"]) == (2, 0, "construction"), \
                dict(row)
            left = await Database.fetchrow(
                "SELECT alloys, rare_earth FROM maya_rp.resources WHERE session_id = $1",
                scratch_session)
            assert (left["alloys"], left["rare_earth"]) == (50000, 0), \
                f"phase 2 was not charged exactly once: {dict(left)}"

            # The resumed site keeps building, and a tick inside phase 2 charges nothing.
            await mp.advance_megastructure(scratch_session, 365.0)
            row = await Database.fetchrow(
                "SELECT current_phase, progress_pct, status FROM maya_rp.megastructure_construction"
                " WHERE id = $1", cid)
            assert (row["current_phase"], row["progress_pct"], row["status"]) == (2, 50, "construction"), \
                dict(row)
            left = await Database.fetchrow(
                "SELECT alloys, rare_earth FROM maya_rp.resources WHERE session_id = $1",
                scratch_session)
            assert (left["alloys"], left["rare_earth"]) == (50000, 0), \
                f"a phase the site already paid for was charged again: {dict(left)}"
        finally:
            await _drop_session(scratch_session)
            await Database.close()

    async def test_a_paused_site_that_still_cannot_afford_stays_paused(self, scratch_session):
        """The resume rides on the phase the site can pay for, and one stall is logged once.

        Folding the resume into the progress write instead flipped the site back to `construction`
        on a tick that could not pay, so the next tick paused it again: one stall, two entries.
        """
        await Database.init()
        await _seed_session(scratch_session)
        try:
            await Database.execute(
                "INSERT INTO maya_rp.resources (session_id, credits, alloys, fuel, dream_essence,"
                " rare_earth) VALUES ($1, 0, 1000, 0, 0, 0)", scratch_session)
            cid = await _paused_construction(scratch_session)

            await mp.advance_megastructure(scratch_session, 365.0)
            await mp.advance_megastructure(scratch_session, 365.0)

            row = await Database.fetchrow(
                "SELECT current_phase, progress_pct, status FROM maya_rp.megastructure_construction"
                " WHERE id = $1", cid)
            assert (row["current_phase"], row["progress_pct"], row["status"]) == (1, 100, "paused"), \
                dict(row)
            left = await Database.fetchval(
                "SELECT alloys FROM maya_rp.resources WHERE session_id = $1", scratch_session)
            assert left == 1000, "an unaffordable phase was charged"
            entries = await Database.fetchval(
                "SELECT count(*) FROM maya_rp.story_log WHERE session_id = $1"
                " AND category = 'megastructure'", scratch_session)
            assert entries == 0, f"an already-paused site logged its stall {entries} times"
        finally:
            await _drop_session(scratch_session)
            await Database.close()
