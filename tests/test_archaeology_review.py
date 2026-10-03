"""Module review tests for modules/archaeology.py.

Defects covered by this pass:

1. `seed_sites` accepted a negative `count`, which quietly created nothing rather
   than reporting the bad argument.
2. Both progress writes in `excavate` matched the dig site on id alone.

Checked and found correct, and the docstrings record the earlier pass: the dig
ends at the row's own `max_progress` rather than a literal 100; the artifact
insert names the columns the table actually has and files its origin in the
description; a depleted site refuses further digs; a NULL `max_progress`,
`difficulty` or `artifact_yield` falls back rather than crashing; the sector read
is session-scoped; and the tick is a stub.

Reported to the lead, not fixed: `seed_sites` picks a sector with
`random.choice(sectors)` and no session filter beyond the read, so it is fine, but
a campaign with no sectors stores NULL for `sector_id`. Whether a site may exist
without a sector is a canon question.

No database: every test drives a fake Database.
"""
from __future__ import annotations

import pytest

import modules.archaeology as arch


class FakeDB:
    def __init__(self, fetch=None, fetchrow=None, fetchval=1, execute_tag="UPDATE 1"):
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


def _install(monkeypatch, fake):
    for name in ("fetch", "fetchrow", "fetchval", "execute"):
        monkeypatch.setattr("modules.archaeology.Database." + name, getattr(fake, name))
    return fake


SITE = {"id": 251, "name": "Veiled_Ziggurat_404", "site_type": "vault", "difficulty": 5,
        "artifact_yield": 2, "excavation_progress": 450, "max_progress": 500,
        "status": "undiscovered"}


# ── 1. The seed count is checked ────────────────────────────────────────

async def test_a_negative_seed_count_is_refused(monkeypatch):
    fake = _install(monkeypatch, FakeDB())

    with pytest.raises(ValueError, match="count cannot be negative"):
        await arch.seed_sites(5, -3)

    assert not fake.calls


async def test_seeding_writes_the_session_and_a_sector(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[{"id": 12, "name": "Kappa"}], fetchval=901))

    out = await arch.seed_sites(5, 2)

    assert [s["id"] for s in out] == [901, 901]
    insert = fake.args_for("INSERT INTO maya_rp.dig_sites", "fetchval")[0]
    assert insert[0] == 5 and insert[5] == 12
    assert insert[2] in arch.SITE_TYPES


async def test_seeding_without_a_sector_still_works(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[], fetchval=7))

    out = await arch.seed_sites(5, 1)

    assert out[0]["id"] == 7
    assert fake.args_for("INSERT INTO maya_rp.dig_sites", "fetchval")[0][5] is None


# ── 2. The progress writes are scoped ───────────────────────────────────

async def test_an_incomplete_dig_writes_progress_with_the_session(monkeypatch):
    site = dict(SITE, excavation_progress=100)
    fake = _install(monkeypatch, FakeDB(fetchrow=site))
    monkeypatch.setattr(arch.random, "randint", lambda a, b: a)

    out = await arch.excavate(251, 5)

    assert out["completed"] is False
    written = fake.args_for("SET excavation_progress=$1", "execute")[0]
    assert written[1] == 251 and written[2] == 5
    assert out["progress"] == 100 + arch.random.randint(10, 25) + (10 - 5) * 2


async def test_a_completed_dig_depletes_the_site_and_yields_artifacts(monkeypatch):
    # one more dig from 490 clears the site's own ceiling of 500
    fake = _install(monkeypatch, FakeDB(fetchrow=dict(SITE, excavation_progress=490)))
    monkeypatch.setattr(arch.random, "randint", lambda a, b: b)

    out = await arch.excavate(251, 5)

    assert out == {"completed": True, "artifacts": 2}
    depleted = fake.args_for("SET status='depleted'", "execute")[0]
    assert depleted[0] == 500, "the site is completed at ITS ceiling, not a literal 100"
    assert depleted[2] == 5
    assert len(fake.args_for("INSERT INTO maya_rp.artifacts", "execute")) == 2


async def test_a_depleted_site_refuses_another_dig(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchrow=dict(SITE, status="depleted")))

    assert await arch.excavate(251, 5) == {"error": "Site depleted"}
    assert not fake.sql("execute")


async def test_a_site_from_another_campaign_is_not_found(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchrow=None))

    assert await arch.excavate(251, 5) == {"error": "Site not found"}
    assert fake.args_for("dig_sites", "fetchrow")[0] == (251, 5)


# ── Contract an earlier pass already set ────────────────────────────────

async def test_a_null_ceiling_falls_back_to_one_hundred(monkeypatch):
    site = dict(SITE, max_progress=None, excavation_progress=95)
    _install(monkeypatch, FakeDB(fetchrow=site))
    monkeypatch.setattr(arch.random, "randint", lambda a, b: b)

    out = await arch.excavate(251, 5)

    assert out["completed"] is True


async def test_a_null_difficulty_and_yield_do_not_crash(monkeypatch):
    site = dict(SITE, difficulty=None, artifact_yield=None, excavation_progress=0)
    _install(monkeypatch, FakeDB(fetchrow=site))

    out = await arch.excavate(251, 5)

    assert out["completed"] is False
    assert "progress" in out


def test_contract_the_name_pool_is_deep_enough_to_stay_varied():
    assert len(arch.PREFIXES) >= 8 and len(arch.SUFFIXES) >= 8
    assert len(set(arch.PREFIXES)) == len(arch.PREFIXES)
    assert len(set(arch.SUFFIXES)) == len(arch.SUFFIXES)


def test_contract_every_site_type_is_named():
    assert len(set(arch.SITE_TYPES)) == len(arch.SITE_TYPES)
    assert "ruins" in arch.SITE_TYPES and "derelict" in arch.SITE_TYPES


async def test_contract_run_tick_is_a_stub():
    assert await arch.run_tick(5) == {"status": "archaeology_ready"}
