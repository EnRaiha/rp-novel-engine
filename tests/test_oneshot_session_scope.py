"""The three one-shot scripts take `--session`, report by default, and write one campaign only.

`setia_governor_model.py` and `redo_faction_model.py` took their session from `Config.SESSION_ID`,
which is fixed when the process starts, and wrote every campaign the read reached. Both now run
through `scripts/_oneshot.py` like the nine scripts before them: a required `--session`, a dry run by
default, and `guard` on the write path.

The rebuild's own scoped DELETE and INSERT are proven against a live scratch row in
`tests/test_oneshots_fix.py::test_rebuild_production_apply_rolls_back`, inside a transaction that never
commits, so this file leaves that path alone.

Every row lives in a scratch campaign (900-999). Sessions 3 and 5 are never written.
"""
from __future__ import annotations

import contextlib
import importlib
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

from core.db import Database  # noqa: E402
from tests.conftest import _clear_session_rows, scratch_id  # noqa: E402

#: The scripts with a `_oneshot` front end this card added or rewrote.
FRONT_END = ("rebuild_production", "setia_governor_model", "redo_faction_model")

#: The two whose front end this card adds.
NEW_FRONT_END = ("setia_governor_model", "redo_faction_model")

#: A write, after leading whitespace and comments, as the dry run must never reach one.
WRITE = re.compile(r"\s*(?:INSERT|UPDATE|DELETE)\b", re.I)

OWN = scratch_id(__name__)


def _script(name: str):
    return importlib.import_module(f"scripts.{name}")


@contextlib.contextmanager
def _no_writes(message: str):
    """Make every write raise inside the block, so a dry run that writes fails the test."""
    def boom(*args, **kwargs):
        raise AssertionError(message)

    def reads_only(real):
        async def checked(sql, *args, **kwargs):
            if WRITE.match(sql):
                raise AssertionError(message)
            return await real(sql, *args, **kwargs)

        return checked

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Database, "execute", boom)
        patch.setattr(Database, "transaction", boom)
        for name in ("fetch", "fetchrow", "fetchval"):
            patch.setattr(Database, name, reads_only(getattr(Database, name)))
        yield


def _freeze(monkeypatch, frozen_ids):
    monkeypatch.setattr("core.session.frozen", lambda: set(frozen_ids))
    monkeypatch.setattr("core.ooc._maintenance_active", lambda: False)


async def _territory(session_id: int, name: str, governor: str) -> int:
    return await Database.fetchval(
        "INSERT INTO maya_rp.territory (session_id, system_name, controlling_faction, governor_name,"
        " population, tax_rate, development_level, title_performance)"
        " VALUES ($1, $2, 'Setia Empire', $3, 1000000, 0.05, 1, 0) RETURNING id",
        session_id, name, governor)


async def _faction(session_id: int, name: str, treasury: int) -> int:
    return await Database.fetchval(
        "INSERT INTO maya_rp.factions (session_id, name, standing, treasury)"
        " VALUES ($1, $2, 'neutral', $3) RETURNING id", session_id, name, treasury)


async def _tax_row(session_id: int, source: str, amount: int) -> None:
    await Database.execute(
        "INSERT INTO maya_rp.resource_production"
        " (session_id, source, resource_type, amount_per_day) VALUES ($1, $2, 'credits', $3)",
        session_id, source, amount)


@pytest_asyncio.fixture
async def sid(scratch_session):
    """The file's scratch campaign, and a neighbour for the cross-campaign rows."""
    assert scratch_session == OWN, (scratch_session, OWN)
    await Database.init()
    await _clear_session_rows(OWN)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status, game_day)"
        " VALUES ($1, 'one-shot scope scratch', 'active', 40)", OWN)
    try:
        yield OWN
    finally:
        await _clear_session_rows(OWN)
        with contextlib.suppress(Exception):
            await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", OWN)
        await Database.close()


# ── the front end ───────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name", NEW_FRONT_END)
async def test_a_session_is_required(name):
    with pytest.raises(SystemExit) as raised:
        await _script(name).main([])
    assert raised.value.code == 2


@pytest.mark.parametrize("name", FRONT_END)
def test_no_source_names_a_default_session(name):
    source = (ROOT / "scripts" / f"{name}.py").read_text()
    assert "Config.SESSION_ID" not in source, name
    assert not re.search(r"^(?:SID|SESSION)\s*=\s*(?:\d|Config)", source, re.M), name


@pytest.mark.parametrize("name", NEW_FRONT_END)
async def test_a_dry_run_writes_nothing(name, sid):
    with _no_writes("a dry run wrote"):
        assert await _script(name).main(["--session", str(sid)]) == 0


@pytest.mark.parametrize("name", NEW_FRONT_END)
async def test_a_frozen_session_is_refused_before_the_first_write(name, sid, monkeypatch):
    from core.ooc import FrozenSession

    _freeze(monkeypatch, {sid})
    with _no_writes("a write landed before the guard"), pytest.raises(FrozenSession):
        await _script(name).main(["--session", str(sid), "--apply"])


# ── setia_governor_model ────────────────────────────────────────────────────────────────────────

async def test_the_governor_model_writes_one_campaign(sid, capsys):
    """The dry run reports and writes nothing; the apply writes this campaign's territory alone."""
    mod = _script("setia_governor_model")
    other = 900 + (sid - 900 + 50) % 100
    await _clear_session_rows(other)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status, game_day)"
        " VALUES ($1, 'one-shot scope neighbour', 'active', 40) ON CONFLICT (id) DO NOTHING", other)
    mine = await _territory(sid, "Binding Prime", "Binding Governor")
    foreign = await _territory(other, "Binding Elsewhere", "Foreign Governor")
    try:
        assert await mod.main(["--session", str(sid)]) == 0
        assert "DRY RUN" in capsys.readouterr().out
        assert await Database.fetchval(
            "SELECT title_performance FROM maya_rp.territory WHERE id = $1", mine) == 0

        assert await mod.main(["--session", str(sid), "--apply"]) == 0
        written = await Database.fetchval(
            "SELECT title_performance FROM maya_rp.territory WHERE id = $1", mine)
        assert written >= 10, written
        assert await Database.fetchval(
            "SELECT title_performance FROM maya_rp.territory WHERE id = $1", foreign) == 0, \
            "another campaign's governor was written"
    finally:
        await _clear_session_rows(other)
        with contextlib.suppress(Exception):
            await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", other)


# ── redo_faction_model ──────────────────────────────────────────────────────────────────────────

async def test_the_faction_model_writes_one_campaign(sid, capsys):
    """Treasury comes from this campaign's tax row, and the UPDATE names this campaign."""
    mod = _script("redo_faction_model")
    other = 900 + (sid - 900 + 50) % 100
    await _clear_session_rows(other)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status, game_day)"
        " VALUES ($1, 'one-shot scope neighbour', 'active', 40) ON CONFLICT (id) DO NOTHING", other)
    name = f"Binding Concord {sid}"
    # `factions.name` is globally unique, so the two campaigns cannot share a faction name. The tax
    # source keeps the caller's text in both campaigns, so a missing session filter would sum the
    # neighbour's row.
    source = f"{name} — Collective Tax"
    mine = await _faction(sid, name, 100000)
    foreign = await _faction(other, f"Binding Concord {other}", 111111)
    await _tax_row(sid, source, 100)
    await _tax_row(other, source, 999999)
    try:
        assert await mod.main(["--session", str(sid)]) == 0
        assert "DRY RUN" in capsys.readouterr().out
        assert await Database.fetchval(
            "SELECT treasury FROM maya_rp.factions WHERE id = $1", mine) == 100000

        assert await mod.main(["--session", str(sid), "--apply"]) == 0
        treasury = await Database.fetchval(
            "SELECT treasury FROM maya_rp.factions WHERE id = $1", mine)
        assert treasury == 3000, f"the tax read crossed campaigns: {treasury}"
        assert await Database.fetchval(
            "SELECT treasury FROM maya_rp.factions WHERE id = $1", foreign) == 111111, \
            "another campaign's faction was written"
    finally:
        await _clear_session_rows(other)
        with contextlib.suppress(Exception):
            await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", other)
