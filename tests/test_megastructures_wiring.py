"""Megastructure wiring: a build answers an error, refuses a foreign site and refuses a repeat.

Three defects live here. A treasury emptied between the affordability read and the charge raised out
of the verb instead of answering `{"error": ...}`. No ownership check meant a site could hang off
another campaign's world. No duplicate guard meant one call charged twice and left two sites of one
type building at once.

Every row belongs to a scratch session (900-999) and is removed in a `finally`. Sessions 3 and 5 are
never written. `mega types` runs the real CLI as a subprocess: it is read only, and the CLI is the
only level at which the verb's output is visible.
"""
from __future__ import annotations

import asyncio
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from core.db import Database  # noqa: E402
from modules import megastructures_ports as mp  # noqa: E402

WORLDFORGE = 3      # phase 1: fuel 20000, alloys 80000; 600 days
RINGWORLD = 2       # phase 1 names `food`, which is not a ledger column
RESOURCES = ("credits", "alloys", "fuel", "dream_essence", "rare_earth", "starsteel",
             "void_crystal", "aetherium")


async def _seed(session_id, **cols):
    """The campaign row and its treasury. Every column not named starts at 0."""
    unknown = set(cols) - set(RESOURCES)
    assert not unknown, unknown
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1, 'mega wiring test', 'active')"
        " ON CONFLICT (id) DO NOTHING", session_id)
    await Database.execute("DELETE FROM maya_rp.resources WHERE session_id = $1", session_id)
    marks = ", ".join(f"${n}" for n in range(2, len(RESOURCES) + 2))
    await Database.execute(
        f"INSERT INTO maya_rp.resources (session_id, {', '.join(RESOURCES)}) VALUES ($1, {marks})",
        session_id, *(cols.get(name, 0) for name in RESOURCES))


async def _wipe(session_id):
    """Child rows first: `resources_session_id_fkey` does not cascade."""
    await Database.execute(
        "DELETE FROM maya_rp.megastructure_construction WHERE session_id = $1", session_id)
    await Database.execute("DELETE FROM maya_rp.story_log WHERE session_id = $1", session_id)
    await Database.execute("DELETE FROM maya_rp.resources WHERE session_id = $1", session_id)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", session_id)


async def _sites(session_id):
    return await Database.fetch(
        "SELECT id, megastructure_type_id, status FROM maya_rp.megastructure_construction"
        " WHERE session_id = $1 ORDER BY id", session_id)


async def _balance(session_id, name):
    return await Database.fetchval(
        f"SELECT {name} FROM maya_rp.resources WHERE session_id = $1", session_id)


class _GateOpen:
    """The research gate answers open; every other statement runs on the real pool.

    `research_projects` is one global catalogue this file does not write, so the gate is opened here
    rather than by a live `unlocked` flag, which migration 140 can move.
    """

    @staticmethod
    async def fetchrow(sql, *args):
        if "research_projects" in sql:
            return {"unlocked": True}
        return await Database.fetchrow(sql, *args)

    @staticmethod
    async def fetch(sql, *args):
        return await Database.fetch(sql, *args)

    @staticmethod
    async def fetchval(sql, *args):
        return await Database.fetchval(sql, *args)

    @staticmethod
    async def execute(sql, *args):
        return await Database.execute(sql, *args)

    @staticmethod
    def transaction():
        return Database.transaction()


@pytest.fixture
async def funded(scratch_campaign, monkeypatch):
    """A scratch campaign with a Worldforge-sized treasury, and the gate open."""
    monkeypatch.setattr(mp, "Database", _GateOpen)
    await Database.init()
    await _seed(scratch_campaign, credits=1_000_000, alloys=200_000, fuel=100_000)
    try:
        yield scratch_campaign
    finally:
        await _wipe(scratch_campaign)
        await Database.close()


@pytest.fixture
async def empty_ledger(scratch_campaign, monkeypatch):
    """A scratch campaign whose treasury is an empty row: the charge cannot be paid."""
    monkeypatch.setattr(mp, "Database", _GateOpen)
    await Database.init()
    await _seed(scratch_campaign)
    try:
        yield scratch_campaign
    finally:
        await _wipe(scratch_campaign)
        await Database.close()


@pytest.fixture
async def cli_session(scratch_campaign):
    """A scratch campaign with an empty treasury, for the read-only CLI verbs.

    The ledger row exists and holds zero, so the verb answers per row: `no ledger row` would be the
    answer for a campaign the engine has never funded, which is a different fact.
    """
    await Database.init()
    await _seed(scratch_campaign)
    try:
        yield scratch_campaign
    finally:
        await _wipe(scratch_campaign)
        await Database.close()


class TestTheCharge:
    async def test_a_funded_build_charges_once_and_creates_one_site(self, funded):
        out = await mp.start_construction(funded, WORLDFORGE)

        assert "error" not in out, out
        assert out["charged"] == {"fuel": 20000, "alloys": 80000}, out
        assert await _balance(funded, "fuel") == 80000
        assert await _balance(funded, "alloys") == 120000
        assert await _balance(funded, "credits") == 1000000, "an unnamed resource moved"
        rows = await _sites(funded)
        assert len(rows) == 1 and rows[0]["megastructure_type_id"] == WORLDFORGE, rows

    async def test_a_treasury_that_moved_under_the_read_returns_an_error(self, empty_ledger,
                                                                        monkeypatch):
        """The affordability read passed and the charge did not: the verb answers, it does not raise."""
        async def stale_ok(*args, **kwargs):
            return True, ""

        monkeypatch.setattr(mp, "_check_afford", stale_ok)

        out = await mp.start_construction(empty_ledger, WORLDFORGE)

        assert "error" in out and "Insufficient resources" in out["error"], out
        assert await _sites(empty_ledger) == [], "a refused charge left a construction row"

    async def test_a_foreign_territory_is_refused_and_nothing_is_charged(self, funded):
        """Territory 999999999 belongs to no session, so it is not this campaign's to build on."""
        out = await mp.start_construction(funded, WORLDFORGE, territory_id=999999999)

        assert out["error"] == f"Territory 999999999 is not in session {funded}.", out
        assert await _balance(funded, "alloys") == 200000
        assert await _sites(funded) == []

    async def test_a_foreign_sector_is_refused_and_nothing_is_charged(self, funded):
        out = await mp.start_construction(funded, WORLDFORGE, sector_id=999999999)

        assert out["error"] == f"Sector 999999999 is not in session {funded}.", out
        assert await _balance(funded, "fuel") == 100000
        assert await _sites(funded) == []

    async def test_a_second_site_of_one_type_is_refused_and_charges_once(self, funded):
        first = await mp.start_construction(funded, WORLDFORGE)
        assert "error" not in first, first

        out = await mp.start_construction(funded, WORLDFORGE)

        assert out["error"] == (f"Worldforge is already under construction"
                                f" (site #{first['construction_id']})."), out
        assert await _balance(funded, "alloys") == 120000, "the repeat charged a second time"
        assert len(await _sites(funded)) == 1

    async def test_two_builds_at_once_make_one_site(self, funded, monkeypatch):
        """The duplicate read sits behind a row lock, so two calls that arrive together charge once.

        The slow charge holds the first transaction open long enough for the second call to reach the
        same guard.
        """
        real = mp._deduct_resources

        async def slow(session_id, costs, conn=None):
            await asyncio.sleep(0.2)
            return await real(session_id, costs, conn=conn)

        monkeypatch.setattr(mp, "_deduct_resources", slow)

        first, second = await asyncio.wait_for(
            asyncio.gather(
                mp.start_construction(funded, WORLDFORGE),
                mp.start_construction(funded, WORLDFORGE)),
            timeout=30)

        errors = [out["error"] for out in (first, second) if "error" in out]
        assert len(errors) == 1 and "already under construction" in errors[0], (first, second)
        assert await _balance(funded, "alloys") == 120000, "the pair charged twice"
        assert await _balance(funded, "fuel") == 80000, "the pair charged twice"
        assert len(await _sites(funded)) == 1

    async def test_a_resource_the_ledger_lacks_names_itself(self, funded):
        """Ringworld phase 1 charges `food`, which `maya_rp.resources` has no column for."""
        out = await mp.start_construction(funded, RINGWORLD)

        assert "error" in out and "food" in out["error"], out
        assert await _balance(funded, "alloys") == 200000
        assert await _sites(funded) == []


class TestTheCli:
    @staticmethod
    def _types(session_id: int) -> str:
        env = {**os.environ, "DEEPSEEK_API_KEY": "test-key"}
        out = subprocess.run(
            [sys.executable, "scripts/cli.py", "mega", "types", f"--session={session_id}"],
            cwd=ROOT, capture_output=True, text=True, env=env, timeout=120)
        return out.stdout + out.stderr

    async def test_mega_types_names_each_gate_its_cost_and_the_ledger(self, cli_session):
        """Read only: the catalogue and the campaign's ledger row, nothing written.

        The gate text is read from the catalogue, so migration 140 rewriting a slug to its project
        name does not move this assertion.
        """
        await Database.init()
        gate = await Database.fetchval(
            "SELECT research_required FROM maya_rp.megastructure_types WHERE id = $1", WORLDFORGE)
        printed = self._types(cli_session)

        assert "#3 Worldforge" in printed, printed
        assert f"research {gate} (locked)" in printed, printed
        assert "phase 1 {'fuel': 20000, 'alloys': 80000}" in printed, printed
        assert "total days 600" in printed, printed
        assert "ledger short:" in printed, printed
        await Database.close()

    def test_a_megastructure_that_cannot_be_paid_reports_the_ledger(self, cli_session):
        """Ringworld is the one type the ledger can never charge, whatever the treasury holds."""
        lines = [line for line in self._types(cli_session).splitlines() if "#2 Ringworld" in line]

        assert lines, "Ringworld is missing from the catalogue output"
        assert "ledger short:" in lines[0] and "food" in lines[0].split("ledger short:")[1], lines[0]
