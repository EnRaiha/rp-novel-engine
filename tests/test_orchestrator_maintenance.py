"""The tick must honour GM MAYA maintenance, because four modules did and the driver did not.

Measured on 2026-10-03: `gm_maint status` reported the mode, `core/session.py` derived it, four modules
(council, environment, secrets, voyage) read it, and `run_full_tick` never asked. With maintenance armed
the tick kept running and opened a `fuel_zero` collapse arc against the live session (`Dead in the Water`,
story_arcs 117, event 27912 at 12:00), because the resources row this engine left behind carries fuel 0
and population 0 against a story with 29,600 people in three settlements.

A guard the callers honour and the driver ignores is not a guard. These two tests hold both directions:
armed means no module runs, disarmed means the tick still ticks.

Module-review tests for `scripts/orchestrator.py`. No database is touched: `Database.init` and the
per-module runner are both stubbed, and the assertion is about which of them was called, not about a row.
"""

from __future__ import annotations

import sys
import pathlib

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from scripts import orchestrator as orch  # noqa: E402


@pytest.fixture
def recorded(monkeypatch):
    """Record every module the tick tries to run, and stop it touching the database."""
    seen: list[str] = []

    async def fake_tick(name, mod, session_id):
        seen.append(name)
        return True

    async def fake_init(*_a, **_k):
        return None

    monkeypatch.setattr(orch, "tick", fake_tick)
    monkeypatch.setattr(orch.Database, "init", fake_init)
    return seen


async def test_the_tick_is_skipped_while_maintenance_is_armed(recorded, monkeypatch, capsys):
    monkeypatch.setattr("core.maintenance.active", lambda: True)

    await orch.run_full_tick(session_id=5, verbose=True)

    assert recorded == [], (
        f"the tick ran {len(recorded)} module(s) while maintenance was armed: {recorded[:4]}. "
        "That is the state that opened the Dead in the Water collapse.")
    assert "SKIPPED" in capsys.readouterr().out, "the skip was silent"


async def test_the_tick_still_ticks_when_maintenance_is_disarmed(recorded, monkeypatch):
    """The other direction. A guard that never lets the tick run is an outage, not a guard."""
    monkeypatch.setattr("core.maintenance.active", lambda: False)

    try:
        await orch.run_full_tick(session_id=5, verbose=False)
    except Exception:
        # Later phases touch modules whose real work is out of scope here; what this test asserts is that
        # the guard let the tick reach them at all.
        pass

    assert recorded, "the tick ran no module while maintenance was disarmed"


async def test_a_statistics_read_that_fails_does_not_stop_the_tick(recorded, monkeypatch):
    """The write-tracking snapshot runs before the phases, and it must not be able to hold them up.

    This test exists because the first version did: `snapshot()` called the database before any
    module ran, the fixture here stubs `Database.init` and not the pool, and the raise travelled up
    through `run_full_tick` so no module ran at all. A measurement that can stop the thing it
    measures is worse than no measurement, because the outage looks like a tick that did nothing.
    """
    monkeypatch.setattr("core.maintenance.active", lambda: False)

    async def explode(*_a, **_k):
        raise RuntimeError("pg_stat_user_tables is not readable by this role")

    from core import tick_writes
    monkeypatch.setattr(tick_writes, "snapshot", explode)

    try:
        await orch.run_full_tick(session_id=5, verbose=False)
    except Exception:
        pass

    assert recorded, "an unreadable statistics view stopped the tick before any module ran"
