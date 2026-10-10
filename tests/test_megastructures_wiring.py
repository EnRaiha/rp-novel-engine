"""Megastructure wiring: a build answers an error, refuses a foreign site and refuses a repeat.

Three defects live here. A treasury emptied between the affordability read and the charge raised out
of the verb instead of answering `{"error": ...}`. No ownership check meant a site could hang off
another campaign's world. No duplicate guard meant one call charged twice and left two sites of one
type building at once.

A fourth sits in the verb that reads the catalogue. `check_gate` answers one text per reason, and
`mega types` read only whether the answer was truthy: a catalogue value that names no
`research_projects` row and a project that exists but is locked both printed as `(locked)`, so a
catalogue fault read as a lock. `TestTheGateReason` drives that verb from a stub catalogue, because
every live gate resolves today. `TestTheCli` pins the live reasons against the rows themselves.

`mega status`, `mega ports` and `mega advance` carry a test each: the first two are read only, and
`advance` runs on a scratch site. Those three are coverage for verbs wired elsewhere, so they pass
on the tree before the gate reason lands.

Every row belongs to a scratch session (900-999) and is removed in a `finally`. Sessions 3 and 5 are
never written. The real CLI runs as a subprocess wherever its whole output is the subject.
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from core import research_gate  # noqa: E402
from core.db import Database  # noqa: E402
from modules import _economy, megastructures_ports as mp  # noqa: E402
from scripts import cli  # noqa: E402

WORLDFORGE = 3      # phase 1: fuel 20000, alloys 80000; 600 days
RINGWORLD = 2       # phase 1 names `food`, which is not a ledger column
SPACEPORT = 1       # the port type whose name is `Spaceport`
RESOURCES = ("credits", "alloys", "fuel", "dream_essence", "rare_earth", "starsteel",
             "void_crystal", "aetherium")


def _run(*args: str) -> subprocess.CompletedProcess:
    """The real CLI as a subprocess. A verb's output exists only once the process has printed it."""
    env = {**os.environ, "DEEPSEEK_API_KEY": "test-key"}
    return subprocess.run([sys.executable, "scripts/cli.py", *args], cwd=ROOT,
                          capture_output=True, text=True, env=env, timeout=120)


def _run_text(*args: str) -> str:
    """Both streams: a verb that answers exits 0, and a refusal says so on stderr."""
    out = _run(*args)
    return out.stdout + out.stderr


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
    """Child rows first: `resources_session_id_fkey` and `territory_session_id_fkey` are NO ACTION,
    so the campaign row has to wait for both. A port hangs off its territory and goes first."""
    await Database.execute(
        "DELETE FROM maya_rp.megastructure_construction WHERE session_id = $1", session_id)
    await Database.execute("DELETE FROM maya_rp.ports WHERE session_id = $1", session_id)
    await Database.execute("DELETE FROM maya_rp.story_log WHERE session_id = $1", session_id)
    await Database.execute("DELETE FROM maya_rp.territory WHERE session_id = $1", session_id)
    await Database.execute("DELETE FROM maya_rp.resources WHERE session_id = $1", session_id)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", session_id)


async def _site(session_id, type_id=WORLDFORGE):
    """One site of this campaign at phase 1 with no progress, for the two verbs that read sites."""
    return await Database.fetchval(
        "INSERT INTO maya_rp.megastructure_construction"
        " (session_id, megastructure_type_id, current_phase, progress_pct, status)"
        " VALUES ($1, $2, 1, 0, 'construction') RETURNING id", session_id, type_id)


async def _progress(site_id):
    return await Database.fetchval(
        "SELECT progress_pct FROM maya_rp.megastructure_construction WHERE id = $1", site_id)


async def _port(session_id, system_name, name):
    """One port in its own territory.

    `maya_rp.port_overview` joins `territory`, so a port without one is invisible to `mega ports`,
    and the territory's `system_name` is what the port line prints back.
    """
    territory = await Database.fetchval(
        "INSERT INTO maya_rp.territory (session_id, system_name, controlling_faction)"
        " VALUES ($1, $2, 'Setia Empire') RETURNING id", session_id, system_name)
    return await Database.fetchval(
        "INSERT INTO maya_rp.ports (session_id, territory_id, port_type_id, name, level, status)"
        " VALUES ($1, $2, $3, $4, 1, 'active') RETURNING id",
        session_id, territory, SPACEPORT, name)


async def _gate_reason(gate):
    """The reason `mega types` must print for one catalogue gate, read from the rows it names.

    The oracle is the catalogue data and not `check_gate`: a name no `research_projects` row carries
    is a catalogue miss, a row with `unlocked` false is a lock, and an unlocked row opens.
    """
    row = await Database.fetchrow(
        "SELECT unlocked FROM maya_rp.research_projects WHERE name = $1", gate)
    if row is None:
        return "catalogue-miss"
    return "unlocked" if row["unlocked"] else "locked"


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
    """A scratch campaign with an empty treasury, for the CLI verbs that read.

    The ledger row exists and holds zero, so the verb answers per row: `no ledger row` would be the
    answer for a campaign the engine has never funded, which is a different fact.

    The slot is cleared before it is seeded. A run killed mid-test leaves a site or a port behind,
    and several tests here assert the count the verb prints.
    """
    await Database.init()
    await _wipe(scratch_campaign)
    try:
        await _seed(scratch_campaign)
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
        return _run_text("mega", "types", f"--session={session_id}")

    async def test_mega_types_names_each_gate_its_cost_and_the_ledger(self, cli_session):
        """Read only: the catalogue and the campaign's ledger row, nothing written.

        The gate text and the reason both come from the live rows, so migration 140 rewriting a slug
        to its project name does not move this assertion, and neither does unlocking the project.
        """
        await Database.init()
        gate = await Database.fetchval(
            "SELECT research_required FROM maya_rp.megastructure_types WHERE id = $1", WORLDFORGE)
        reason = await _gate_reason(gate)
        printed = self._types(cli_session)

        assert "#3 Worldforge" in printed, printed
        assert f"research {gate} ({reason})" in printed, printed
        assert "phase 1 {'fuel': 20000, 'alloys': 80000}" in printed, printed
        assert "total days 600" in printed, printed
        assert "ledger short:" in printed, printed
        await Database.close()

    def test_a_megastructure_that_cannot_be_paid_reports_the_ledger(self, cli_session):
        """Ringworld is the one type the ledger can never charge, whatever the treasury holds."""
        lines = [line for line in self._types(cli_session).splitlines() if "#2 Ringworld" in line]

        assert lines, "Ringworld is missing from the catalogue output"
        assert "ledger short:" in lines[0] and "food" in lines[0].split("ledger short:")[1], lines[0]

    async def test_mega_status_prints_the_rows_it_counted(self, cli_session):
        """The default verb lists this campaign's sites and its ports, one line each."""
        site = await _site(cli_session)
        system, name = f"wiring system {cli_session}", f"Wiring Port {cli_session}"
        port = await _port(cli_session, system, name)

        out = _run("mega", "status", f"--session={cli_session}")
        printed = out.stdout + out.stderr
        site_line = f"#{site} Worldforge · phase 1 · 0% · construction · no territory"

        assert out.returncode == 0, printed
        assert "megastructures: 1" in printed, printed
        assert site_line in printed, printed
        assert "ports: 1" in printed, printed
        assert f"#{port} {name} · Spaceport · L1 · active · {system}" in printed, printed

    async def test_mega_ports_lists_the_ports_and_not_the_sites(self, cli_session):
        """`ports` answers the port rows: no site exists here, and no site line is printed."""
        system, name = f"wiring system {cli_session}", f"Wiring Port {cli_session}"
        port = await _port(cli_session, system, name)

        out = _run("mega", "ports", f"--session={cli_session}")
        printed = out.stdout + out.stderr

        assert out.returncode == 0, printed
        assert "ports: 1" in printed, printed
        assert f"#{port} {name} · Spaceport · L1 · active · {system}" in printed, printed
        assert "megastructures:" not in printed, printed

    async def test_mega_advance_moves_a_scratch_site(self, cli_session):
        """`advance <days>` moves this campaign's site by the share of phase 1 the days buy.

        Phase 1 of the type read here takes `days`, so half of them is half the phase. The days are
        read from the catalogue rather than pinned, because that catalogue is global and a migration
        rewrites it. One tick stays under 100%, so the site neither advances a phase nor charges it.
        """
        site = await _site(cli_session)
        days = await Database.fetchval(
            "SELECT (construction_phases -> 0 ->> 'time_days')::int"
            " FROM maya_rp.megastructure_types WHERE id = $1", WORLDFORGE)

        out = _run("mega", "advance", str(days / 2), f"--session={cli_session}")
        printed = out.stdout + out.stderr

        assert out.returncode == 0, printed
        assert "advanced: 1" in printed, printed
        assert await _progress(site) == 50, printed


# ── the gate reason, against a stub catalogue ───────────────────────────────────────────────────────
#
# The live catalogue resolves every value it holds today, so the missing-project branch cannot be
# produced against it without writing a global catalogue row. These stubs answer the two refusals
# `core.research_gate.check_gate` returns, in the wording that module owns.

MISSING_GATE = "Ghost Blueprint"    # names no `research_projects` row
LOCKED_GATE = "Iron Foundry"        # a row that exists with `unlocked` false
PHASES = json.dumps([{"time_days": 200, "cost": {"fuel": 20000}},
                     {"time_days": 400, "cost": {"alloys": 150000}}])


class _CliDatabase:
    """`Database` during one `mega types` call: the ledger read answers, nothing else is reached.

    The verb reads the ledger row and closes the pool. Any other statement is outside this subject
    and raises here rather than touching a campaign.
    """

    async def init(self):
        return None

    async def close(self):
        return None

    async def fetchrow(self, sql, *args):
        return {"present": 1}

    async def fetch(self, sql, *args):
        raise AssertionError(f"unexpected read: {' '.join(sql.split())}")

    async def fetchval(self, sql, *args):
        raise AssertionError(f"unexpected read: {' '.join(sql.split())}")

    async def execute(self, sql, *args):
        raise AssertionError(f"mega types wrote a row: {' '.join(sql.split())}")

    def transaction(self):
        raise AssertionError("mega types opened a transaction")


def _catalogue(rows):
    """`get_megastructure_types` answering one stub catalogue."""
    async def read():
        return rows
    return read


def _gate(refusals):
    """`check_gate` answering the refusal text that value earns, or None when the gate is open."""
    async def check(requirement, conn=None):
        return refusals.get(requirement)
    return check


async def _open_ledger(session_id, cost):
    """`_check_afford` answering that the campaign can pay: the gate token is the subject here."""
    return True, ""


def _gate_line(printed: str, gate: str) -> str:
    """The one catalogue line that names this gate."""
    lines = [line for line in printed.splitlines() if f" {gate} (" in line]
    assert len(lines) == 1, printed
    return lines[0]


def _types_output(monkeypatch, capsys, rows, refusals) -> str:
    """Run `mega types` in process against a stub catalogue and return what it printed.

    `Database`, the catalogue reader, the gate and the affordability read are replaced, so no
    statement leaves this process and the reason printed per row is the only thing under test.
    """
    monkeypatch.setattr(cli, "Database", _CliDatabase())
    monkeypatch.setattr(cli, "SID", 918)     # no statement reaches a campaign; the id is just a value
    monkeypatch.setattr(mp, "get_megastructure_types", _catalogue(rows))
    monkeypatch.setattr(research_gate, "check_gate", _gate(refusals))
    monkeypatch.setattr(_economy, "_check_afford", _open_ledger)
    own = cli.sys.argv
    cli.sys.argv = ["cli.py", "mega", "types"]
    try:
        asyncio.run(cli.cmd_mega())
    finally:
        cli.sys.argv = own
    return capsys.readouterr().out


def _catalogue_row(row_id: int, name: str, gate: str) -> dict:
    """One `megastructure_types` row as asyncpg hands it over: `construction_phases` is JSON text."""
    return {"id": row_id, "name": name, "fantasy_tier": "mythic", "research_required": gate,
            "construction_phases": PHASES}


class TestTheGateReason:
    """`mega types` prints which gate refused. One word for two reasons was the defect."""

    def test_a_catalogue_value_that_names_no_project_reads_as_a_miss(self, monkeypatch, capsys):
        """The value names no `research_projects` row, so the row is a miss and not a lock."""
        printed = _types_output(
            monkeypatch, capsys, [_catalogue_row(901, "Ghostframe", MISSING_GATE)],
            {MISSING_GATE: research_gate.CATALOGUE_MISS.format(MISSING_GATE)})

        assert "(catalogue-miss)" in _gate_line(printed, MISSING_GATE), printed
        assert "(locked)" not in printed, printed

    def test_a_project_that_exists_and_is_locked_reads_as_locked(self, monkeypatch, capsys):
        """The lock keeps its token, and the miss beside it proves the two reasons differ.

        Both rows print `(locked)` before the fix, so the miss row is what makes this pair read.
        """
        printed = _types_output(
            monkeypatch, capsys,
            [_catalogue_row(901, "Ghostframe", MISSING_GATE),
             _catalogue_row(902, "Ironworks", LOCKED_GATE)],
            {MISSING_GATE: research_gate.CATALOGUE_MISS.format(MISSING_GATE),
             LOCKED_GATE: research_gate.LOCKED.format(LOCKED_GATE)})

        assert "(locked)" in _gate_line(printed, LOCKED_GATE), printed
        assert "(catalogue-miss)" in _gate_line(printed, MISSING_GATE), printed

    def test_a_refusal_this_verb_does_not_know_is_not_called_locked(self, monkeypatch, capsys):
        """A third refusal claims no lock: the verb repeats what it read, never a guessed reason."""
        printed = _types_output(
            monkeypatch, capsys, [_catalogue_row(901, "Ghostframe", MISSING_GATE)],
            {MISSING_GATE: f'Research "{MISSING_GATE}" is dormant.'})

        assert "(gated)" in _gate_line(printed, MISSING_GATE), printed
        assert "(locked)" not in printed, printed
