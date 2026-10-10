"""Construction intent: the bridge and the player reach a build through one resolver.

The intent answers with the module's own result on success and refuses a name that matches nothing,
a name that matches several types, an action the resolver does not support, and a frozen campaign.
The campaign is a scratch session (900-999); sessions 3 and 5 are never written.
"""
from __future__ import annotations

import contextvars
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from core import ooc  # noqa: E402
from core.db import Database  # noqa: E402
from modules import megastructures_ports as mp  # noqa: E402
from scripts import kilo_bridge  # noqa: E402

WORLDFORGE = 3
RESOURCES = ("credits", "alloys", "fuel", "dream_essence", "rare_earth", "starsteel",
             "void_crystal", "aetherium")

#: The connection `Database.transaction()` yields, for a stand-in that is not the real class.
_tx_conn = contextvars.ContextVar("mega_intent_tx_conn", default=None)


async def _seed(session_id, **cols):
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1, 'mega intent test', 'active')"
        " ON CONFLICT (id) DO NOTHING", session_id)
    await Database.execute("DELETE FROM maya_rp.resources WHERE session_id = $1", session_id)
    marks = ", ".join(f"${n}" for n in range(2, len(RESOURCES) + 2))
    await Database.execute(
        f"INSERT INTO maya_rp.resources (session_id, {', '.join(RESOURCES)}) VALUES ($1, {marks})",
        session_id, *(cols.get(name, 0) for name in RESOURCES))


async def _wipe(session_id):
    await Database.execute(
        "DELETE FROM maya_rp.megastructure_construction WHERE session_id = $1", session_id)
    await Database.execute("DELETE FROM maya_rp.story_log WHERE session_id = $1", session_id)
    await Database.execute("DELETE FROM maya_rp.resources WHERE session_id = $1", session_id)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", session_id)


async def _sites(session_id):
    return await Database.fetchval(
        "SELECT count(*) FROM maya_rp.megastructure_construction WHERE session_id = $1",
        session_id)


class _GateOpen:
    """Open gate, and a transaction bound to its own stand-in connection.

    The `_tx_conn` ContextVar is read by the connection methods, so the same stand-in serves both
    call shapes: `Database.transaction()` is set up before the connection's first await, and the
    `task = asyncio.ensure_future(...)` inside asyncpg copies the context at that point.
    """

    @staticmethod
    def _connection():
        return _tx_conn.get() or _GateOpen

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
        return _Tx()


class _Tx:
    """`Database.transaction()` as the module uses it: the same answers on the connection."""

    async def __aenter__(self):
        _tx_conn.set(_GateOpen)
        return _GateOpen

    async def __aexit__(self, *exc):
        _tx_conn.set(None)
        return False


@pytest.fixture
async def campaign(scratch_campaign, monkeypatch):
    monkeypatch.setattr(mp, "Database", _GateOpen)
    await Database.init()
    await _seed(scratch_campaign, credits=1_000_000, alloys=200_000, fuel=100_000)
    try:
        yield scratch_campaign
    finally:
        await _wipe(scratch_campaign)
        await Database.close()


class TestTheAction:
    async def test_start_builds_and_carries_the_module_result(self, campaign):
        out = await mp.resolve_intent(campaign, "start", "Worldforge")

        assert out["domain"] == "construction" and out["success"] is True, out
        assert out["charged"] == {"fuel": 20000, "alloys": 80000}, out
        assert await _sites(campaign) == 1
        assert out["estimated_completion"][:10] in out["narrative_hook"], out

    @pytest.mark.parametrize("alias", ["build", "begin", "construct"])
    async def test_every_alias_is_a_start(self, campaign, alias):
        out = await mp.resolve_intent(campaign, alias, "Worldforge")

        assert out["success"] is True, out

    async def test_status_reads_without_building(self, campaign):
        await mp.start_construction(campaign, WORLDFORGE)

        out = await mp.resolve_intent(campaign, "status", "Worldforge")

        assert out["success"] is True and out["target"] == "Worldforge", out
        assert len(out["sites"]) == 1, out
        assert await _sites(campaign) == 1, "status built a second site"

    async def test_a_percent_target_matches_no_type(self, campaign):
        """`%` was a LIKE wildcard: it resolved to the first type by id and built it."""
        out = await mp.resolve_intent(campaign, "start", "%")

        assert out["success"] is False, out
        assert "0 type(s)" in out["narrative_hook"], out
        assert await _sites(campaign) == 0

    async def test_two_matching_names_are_both_named(self, campaign):
        """Fragments resolve to one type or refuse: guessing between two builds the wrong one."""
        out = await mp.resolve_intent(campaign, "start", "S")

        assert out["success"] is False, out
        assert "Dyson Sphere" in out["narrative_hook"], out
        assert "Stellar Forge" in out["narrative_hook"], out
        assert "Aether Nexus" in out["narrative_hook"], out
        assert await _sites(campaign) == 0

    async def test_an_unknown_action_lists_the_supported_ones(self, campaign):
        out = await mp.resolve_intent(campaign, "advance", "Worldforge")

        assert out["success"] is False, out
        assert "start" in out["narrative_hook"] and "status" in out["narrative_hook"], out
        assert await _sites(campaign) == 0

    async def test_a_territory_that_is_not_an_id_is_refused(self, campaign):
        out = await mp.resolve_intent(campaign, "start", "Worldforge", territory="the keep")

        assert out["success"] is False and "not an id" in out["narrative_hook"], out
        assert await _sites(campaign) == 0

    async def test_a_locked_gate_names_the_research(self, campaign, monkeypatch):
        class _Locked(_GateOpen):
            @staticmethod
            async def fetchrow(sql, *args):
                if "research_projects" in sql:
                    return {"unlocked": False}
                return await Database.fetchrow(sql, *args)

        monkeypatch.setattr(mp, "Database", _Locked)

        # The refusal names the catalogue value, which migration 140 rewrites from a slug to the
        # project name. Read it here so the assertion survives that apply.
        gate = await Database.fetchval(
            "SELECT research_required FROM maya_rp.megastructure_types WHERE name = 'Worldforge'")
        out = await mp.resolve_intent(campaign, "start", "Worldforge")

        assert out["success"] is False, out
        assert f'Research "{gate}" is locked.' in out["narrative_hook"], out
        assert await _sites(campaign) == 0

    async def test_a_frozen_campaign_raises_and_writes_nothing(self, campaign, monkeypatch):
        monkeypatch.setattr("core.session.is_frozen", lambda sid: True)
        monkeypatch.setattr("core.ooc._maintenance_active", lambda: False)

        with pytest.raises(ooc.FrozenSession):
            await mp.resolve_intent(campaign, "start", "Worldforge")

        assert await _sites(campaign) == 0


class TestTheBridge:
    async def test_the_bridge_routes_construction_to_the_module(self, campaign):
        out = await kilo_bridge.handle("action_intent", {
            "domain": "construction", "action": "build", "target": "Worldforge",
            "session": campaign})

        assert out["status"] == "ok", out
        data = out["data"]
        assert data["domain"] == "construction" and data["success"] is True, data
        assert data["charged"] == {"fuel": 20000, "alloys": 80000}, data
        assert await _sites(campaign) == 1

    async def test_an_unknown_domain_lists_construction(self):
        out = await kilo_bridge.handle("action_intent", {
            "domain": "nonsense", "action": "start", "target": "Worldforge"})

        assert "construction" in out["data"]["available_domains"], out
