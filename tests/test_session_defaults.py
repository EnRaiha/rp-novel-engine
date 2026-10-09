"""The process default session, and the two ways it can point somewhere nobody chose.

`Config.SESSION_ID` is resolved once, at import. That is fine for a short-lived command and wrong for
a long-lived one: the bridge or the MCP server that started while the arc was session 3 keeps writing
to session 3 after the arc moves to 5, and session 3 is the frozen reference.

The other way is a silent fallback. When the resolver fails, the config falls back to the legacy TKG
campaign, which is exactly the frozen session. So the failure has to say so out loud.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class TestStaleProcessDefault:
    def test_a_stale_default_names_the_drift(self, monkeypatch):
        from core import session
        from core.session import stale_process_default

        # 3 is the legacy session the engine used before the arc moved. The frozen list is data the
        # owner edits, so the test pins it instead of reading the live file.
        monkeypatch.setattr(session, "frozen", lambda: [3])
        message = stale_process_default(3)
        assert message is not None, "a process stuck on the old session must be told"
        assert "session 3" in message and "frozen" in message

    def test_a_stale_default_that_is_not_frozen_omits_the_frozen_note(self, monkeypatch):
        from core import session
        from core.session import stale_process_default

        monkeypatch.setattr(session, "frozen", lambda: [])
        message = stale_process_default(3)
        assert message is not None and "session 3" in message and "frozen" not in message

    def test_a_matching_default_says_nothing(self):
        from core.config import Config
        from core.session import stale_process_default

        assert stale_process_default(int(Config.SESSION_ID)) is None

    def test_the_config_default_matches_the_resolver(self):
        """The two must not disagree today, or every count below is meaningless."""
        from core.config import Config
        from core.session import resolve_session

        assert int(Config.SESSION_ID) == int(resolve_session())


class TestFallbackAnnouncesItself:
    def test_the_fallback_warns_on_stderr(self, monkeypatch, capsys):
        import importlib

        import core.config as config

        monkeypatch.setattr(sys, "path", sys.path)
        # Make the resolver fail the way a missing arc file does, then rebuild the default.
        monkeypatch.setenv("RP_SESSION", "")
        monkeypatch.setattr("core.session.active_arc", lambda: None)
        monkeypatch.setattr("core.session._maintenance_active", lambda: False)
        monkeypatch.setattr(config, "SESSION_FALLBACK_USED", False)
        session = config._default_session()
        captured = capsys.readouterr()
        assert session == 3, "the fallback is the legacy campaign"
        assert "FROZEN" in captured.err, "a silent fallback is a write to a session nobody chose"
        assert config.SESSION_FALLBACK_USED is True
        # Undo the patches BEFORE the reload, and the order is the whole point. The
        # reload re-runs the class body, which computes Config.SESSION_ID again. With
        # `active_arc` still patched to None it computes the fallback, and that value
        # stays on the class for the rest of the process: monkeypatch.undo() restores
        # the patched function, never the attribute the reload just wrote. Every test
        # after this one then reads the frozen campaign through Config.SESSION_ID,
        # which is the hazard this file exists to describe.
        monkeypatch.undo()
        importlib.reload(config)


class TestCrossSessionReads:
    """A read that ignores the session reports another campaign's world.

    `gate_toll_income` summed `faction_trade_deals` without a filter, and that table carried no session
    marker, so the live arc, whose world is empty, reported 14,700,000 credits of treasury income from
    the frozen campaign's trade network. Migration 125 gives the table the marker it needed.
    """

    def test_the_trade_deals_table_carries_a_session_marker(self):
        import os
        import pathlib as _pathlib

        import psycopg2

        env = _pathlib.Path.home() / ".env"
        if env.is_file():
            for line in env.read_text(encoding="utf-8", errors="replace").splitlines():
                if "=" in line and not line.strip().startswith("#"):
                    key, _, value = line.partition("=")
                    key = key.removeprefix("export ").strip()
                    if key.startswith(("OC_PG_", "POSTGRES_")) and key not in os.environ:
                        os.environ[key] = value.strip().strip("'\"")
        if not os.environ.get("OC_PG_HOST"):
            import pytest

            pytest.skip("no OC_PG_* settings")
        conn = psycopg2.connect(host=os.environ["OC_PG_HOST"],
                                port=int(os.environ.get("OC_PG_PORT", 5432)),
                                user=os.environ["OC_PG_USER"], password=os.environ.get("OC_PG_PASS"),
                                dbname=os.environ.get("OC_PG_DB", "maya_memory"))
        try:
            cur = conn.cursor()
            cur.execute("""SELECT 1 FROM information_schema.columns
                           WHERE table_schema='maya_rp' AND table_name='faction_trade_deals'
                             AND column_name='session_id'""")
            assert cur.fetchone(), "a campaign-owned table needs a session marker"
        finally:
            conn.close()

    def test_the_income_query_filters_by_session(self):
        import inspect

        from modules import economy

        source = inspect.getsource(economy.gate_toll_income)
        assert "ftd.session_id = $1" in source, "unfiltered, every session reads session 3's trade"

    async def test_a_session_with_no_trade_reads_zero(self):
        from core.db import Database
        from modules.economy import gate_toll_income

        await Database.init()
        assert await gate_toll_income(5) == 0, "session 5 has no trade network"
        await Database.close()


class TestCrossSessionAggregates:
    """An aggregate over a two-campaign table without a session filter answers with both.

    `faction_ships` carries 8,223 session-3 hulls and none for session 5. Two queries summed or counted
    it without a filter. Measured: the unfiltered sum for session 5 is 846,639,437 against a filtered 0,
    so a battle in the live arc would have credited the enemy with the frozen campaign's entire fleet,
    and the pirate den regen counted session 3's hulls toward session 5's cap, so no den ever rebuilt.
    """

    def test_battle_filters_the_enemy_power_by_session(self):
        import inspect

        from modules import battle

        source = inspect.getsource(battle)
        marker = "SELECT COALESCE(SUM(power_rating),0) FROM maya_rp.faction_ships"
        assert marker in source, "the enemy power query moved"
        # Read a window around the statement: the same file has another faction_ships query, and
        # slicing to the first bracket picked that one instead.
        window = source[source.index(marker):source.index(marker) + 260]
        assert "session_id=$2" in window, "an unfiltered sum is both campaigns added together"

    def test_the_pirate_cap_counts_only_this_session(self):
        import inspect

        from modules import pirates

        source = inspect.getsource(pirates)
        marker = "SELECT COUNT(*) FROM maya_rp.faction_ships"
        assert marker in source, "the cap query moved"
        window = source[source.index(marker):source.index(marker) + 200]
        assert "session_id=$2" in window

    async def test_the_filtered_sum_differs_by_session(self):
        from core.db import Database

        await Database.init()
        total = await Database.fetchval(
            "SELECT COALESCE(SUM(power_rating),0) FROM maya_rp.faction_ships")
        live = await Database.fetchval(
            "SELECT COALESCE(SUM(power_rating),0) FROM maya_rp.faction_ships WHERE session_id=5")
        assert int(live or 0) < int(total or 0), "if they are equal there is nothing to filter"
        await Database.close()
