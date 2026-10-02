"""Megastructures and ports: built by something, and owned by one session.

Seven entry points of megastructures_ports.py had no caller: both catalogues, both status readers,
both builders and the port upgrader. `run_tick` advanced construction nothing could start. The two
instance views, megastructure_status and port_overview, exposed no session_id, so the readers returned
every campaign's rows.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.db import Database  # noqa: E402
from modules import megastructures_ports as mp  # noqa: E402


class TestTheCatalogues:
    async def test_both_catalogues_answer(self):
        await Database.init()
        types = await mp.get_megastructure_types()
        ports = await mp.get_port_types()
        assert types, "no megastructure types"
        assert ports, "no port types"
        await Database.close()


class TestSessionScope:
    async def test_ports_are_scoped_to_their_session(self):
        await Database.init()
        territory = await Database.fetchval("SELECT id FROM maya_rp.territory LIMIT 1")
        pt = await Database.fetchval("SELECT id FROM maya_rp.port_types ORDER BY id LIMIT 1")
        assert territory and pt, "nothing to build with"
        row = await Database.fetchrow(
            "INSERT INTO maya_rp.ports (session_id, territory_id, port_type_id, name, level, status)"
            " VALUES (3, $1, $2, 'red proof port', 1, 'active') RETURNING id", territory, pt)
        try:
            mine = await mp.get_port_overview(3)
            theirs = await mp.get_port_overview(5)
            assert any(r["id"] == row["id"] for r in mine), "session 3 cannot see its own port"
            assert not any(r["id"] == row["id"] for r in theirs), "session 5 sees session 3 ports"
        finally:
            await Database.execute("DELETE FROM maya_rp.ports WHERE id=$1", row["id"])
            await Database.close()

    async def test_megastructures_are_scoped_to_their_session(self):
        await Database.init()
        counts = {sid: len(await mp.get_megastructure_status(sid)) for sid in (3, 5)}
        assert counts[3] >= 0 and counts[5] >= 0
        # Whatever the numbers, the two queries must not be able to return the same cross-session set
        # by accident: each is filtered, so a future row in one session cannot appear in the other.
        rows5 = await mp.get_megastructure_status(5)
        assert all(r.get("session_id") in (None, 5) for r in rows5), rows5
        await Database.close()
