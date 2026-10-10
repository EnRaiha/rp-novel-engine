"""`relive_session.py` binds the source session to the novel it replays, not only the target.

`--novel` named the target alone. `--from 3 --to 905 --novel tkg-the-sunrise` cloned session 3's Setia
cast into a Sunrise campaign, because only the target's novel was compared. The script now reads the
source session's `novel_id` too and refuses a crossing, unless the operator passes `--allow-cross-novel`.

Both campaigns are scratch sessions (900-999): the source plays `tkg-setia-kingdom` or `tkg-the-sunrise`
as a label on its own row, and the target plays `tkg-the-sunrise`. Sessions 3 and 5 are never read or
written, and the script runs against the live database only through these two scratch rows.
"""
from __future__ import annotations

import contextlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest_asyncio  # noqa: E402

from core.db import Database  # noqa: E402
from scripts import relive_session  # noqa: E402
from tests.conftest import _clear_session_rows, scratch_id  # noqa: E402

SETIA = "tkg-setia-kingdom"
SUNRISE = "tkg-the-sunrise"

TARGET = scratch_id(__name__)
SOURCE = 900 + (TARGET - 900 + 50) % 100
CAST = ("Zz Relive Queen", "Zz Relive Captain")


async def _session(session_id: int, novel_id: str) -> None:
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status, game_day, novel_id)"
        " VALUES ($1, 'relive source scratch', 'active', 40, $2)"
        " ON CONFLICT (id) DO UPDATE SET novel_id = EXCLUDED.novel_id", session_id, novel_id)


async def _run(monkeypatch, *flags: str) -> int:
    """Run `relive_session.main` from SOURCE to TARGET, then reopen the pool the script closed."""
    monkeypatch.setattr(sys, "argv", ["relive_session.py", "--from", str(SOURCE), "--to", str(TARGET),
                                      *flags])
    try:
        return await relive_session.main()
    finally:
        await Database.init()


async def _cast(session_id: int) -> int:
    return await Database.fetchval(
        "SELECT count(*) FROM maya_rp.characters WHERE session_id=$1", session_id)


@pytest_asyncio.fixture
async def campaigns(scratch_session):
    """A source that plays Setia with two characters, and a target that plays Sunrise."""
    assert scratch_session == TARGET, (scratch_session, TARGET)
    await Database.init()
    for session_id in (SOURCE, TARGET):
        await _clear_session_rows(session_id)
    await _session(SOURCE, SETIA)
    await _session(TARGET, SUNRISE)
    for name in CAST:
        await Database.execute(
            "INSERT INTO maya_rp.characters (session_id, name) VALUES ($1, $2)", SOURCE, name)
    try:
        yield
    finally:
        for session_id in (SOURCE, TARGET):
            await _clear_session_rows(session_id)
            with contextlib.suppress(Exception):
                await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", session_id)
        await Database.close()


async def test_a_source_from_another_novel_is_refused_and_names_both(campaigns, monkeypatch, capsys):
    code = await _run(monkeypatch, "--novel", SUNRISE)

    err = capsys.readouterr().err
    assert code == 2
    assert SETIA in err and SUNRISE in err, f"the refusal must name both novels: {err!r}"
    assert "--allow-cross-novel" in err, f"the refusal must name the override: {err!r}"
    assert await _cast(TARGET) == 0, "a refused crossing cloned the cast"


async def test_a_refused_source_does_not_create_the_target(campaigns, monkeypatch):
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", TARGET)

    code = await _run(monkeypatch, "--novel", SUNRISE)

    assert code == 2
    assert await Database.fetchval("SELECT count(*) FROM maya_rp.sessions WHERE id=$1", TARGET) == 0, \
        "a refused crossing still created the target session"


async def test_a_source_with_no_session_row_is_refused(campaigns, monkeypatch, capsys):
    await _clear_session_rows(SOURCE)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", SOURCE)

    code = await _run(monkeypatch, "--novel", SUNRISE)

    assert code == 2
    assert f"session {SOURCE}" in capsys.readouterr().err
    assert await _cast(TARGET) == 0


async def test_a_source_from_the_same_novel_is_cloned(campaigns, monkeypatch, capsys):
    await _session(SOURCE, SUNRISE)

    code = await _run(monkeypatch, "--novel", SUNRISE)

    assert code == 0, capsys.readouterr().err
    assert await _cast(TARGET) == len(CAST)
    names = {row["name"] for row in await Database.fetch(
        "SELECT name FROM maya_rp.characters WHERE session_id=$1", TARGET)}
    assert names == set(CAST)


async def test_a_dry_run_from_the_same_novel_writes_no_character(campaigns, monkeypatch, capsys):
    await _session(SOURCE, SUNRISE)

    code = await _run(monkeypatch, "--novel", SUNRISE, "--dry-run")

    assert code == 0, capsys.readouterr().err
    assert await _cast(TARGET) == 0


async def test_the_override_clones_across_novels_and_warns(campaigns, monkeypatch, capsys):
    code = await _run(monkeypatch, "--novel", SUNRISE, "--allow-cross-novel")

    err = capsys.readouterr().err
    assert code == 0, err
    assert SETIA in err and SUNRISE in err, f"the override must still name both novels: {err!r}"
    assert await _cast(TARGET) == len(CAST)

