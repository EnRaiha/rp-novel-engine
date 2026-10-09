"""ministry_ai fix 2: prompt dedup, the applicant status, and call-time session resolution.

Every write lands in a scratch session (900-999). Sessions 3 and 5 are read by nothing here.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

from core import session as core_session  # noqa: E402
from core.db import Database  # noqa: E402
from modules import ministry_ai as mia  # noqa: E402

#: The four ministries that prompt every tick while the King is present.
PRESENT_MINISTRIES = {"Lord of War", "Lord Diplomat", "Lord of the Deep", "Lord Governor"}


#: Children of `sessions` this file writes, removed before the session row (territory has a foreign key to it).
_TABLES = ("governor_applicants", "adjutant_prompts", "events", "territory")


async def _wipe(session_id):
    for table in _TABLES:
        await Database.execute(f"DELETE FROM maya_rp.{table} WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", session_id)


@pytest_asyncio.fixture
async def sid(scratch_session):
    """A scratch session row with the King present."""
    await Database.init()
    await _wipe(scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status, game_day, king_present, dark_mode) "
        "VALUES ($1, 'ministry fix2 scratch', 'active', 1, true, false)", scratch_session)
    try:
        yield scratch_session
    finally:
        await _wipe(scratch_session)
        await Database.close()


async def _pending(session_id, ministry=None):
    if ministry is None:
        return await Database.fetchval(
            "SELECT COUNT(*) FROM maya_rp.adjutant_prompts WHERE session_id=$1 AND status='pending'",
            session_id)
    return await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.adjutant_prompts "
        "WHERE session_id=$1 AND status='pending' AND ministry=$2", session_id, ministry)


class TestPromptsAreIdempotent:
    async def test_a_second_tick_queues_nothing_while_the_first_prompts_are_pending(self, sid):
        first = await mia.run_tick(sid)
        assert first["prompted"] == 4, first
        assert await _pending(sid) == 4
        second = await mia.run_tick(sid)
        third = await mia.run_tick(sid)
        assert second["prompted"] == 0 and third["prompted"] == 0, (second, third)
        assert await _pending(sid) == 4
        rows = await Database.fetch(
            "SELECT DISTINCT ministry FROM maya_rp.adjutant_prompts WHERE session_id=$1", sid)
        assert {r["ministry"] for r in rows} == PRESENT_MINISTRIES

    async def test_a_resolved_prompt_can_be_raised_again(self, sid):
        await mia.run_tick(sid)
        war = await Database.fetchval(
            "SELECT id FROM maya_rp.adjutant_prompts WHERE session_id=$1 AND ministry='Lord of War'", sid)
        assert (await mia.resolve(sid, war, "accepted"))["decision"] == "accepted"
        out = await mia.run_tick(sid)
        assert out["prompted"] == 1, out
        assert await _pending(sid, "Lord of War") == 1
        assert await _pending(sid) == 4

    async def test_concurrent_prompts_for_one_key_insert_one_row(self, sid):
        results = await asyncio.gather(*[
            mia._prompt(sid, "Cabinet", "Holder", "Mastika crisis response", "t", "impact", "critical")
            for _ in range(8)])
        assert sorted(results) == [False] * 7 + [True], results
        assert await _pending(sid, "Cabinet") == 1

    async def test_the_same_ministry_with_another_action_is_its_own_prompt(self, sid):
        assert await mia._prompt(sid, "Cabinet", "H", "Action one", "t", "i") is True
        assert await mia._prompt(sid, "Cabinet", "H", "Action two", "t", "i") is True
        assert await mia._prompt(sid, "Cabinet", "H", "Action two", "t", "changed impact text") is False
        assert await _pending(sid, "Cabinet") == 2

    async def test_another_session_does_not_share_the_dedup_key(self, sid):
        other = 900 + (sid - 900 + 37) % 100
        try:
            assert await mia._prompt(sid, "Cabinet", "H", "Same action", "t", "i") is True
            assert await mia._prompt(other, "Cabinet", "H", "Same action", "t", "i") is True
            assert await mia._prompt(other, "Cabinet", "H", "Same action", "t", "i") is False
            assert await _pending(sid) == 1 and await _pending(other) == 1
        finally:
            await Database.execute("DELETE FROM maya_rp.adjutant_prompts WHERE session_id=$1", other)

    async def test_an_away_king_queues_nothing(self, sid):
        await mia.set_king(sid, False)
        out = await mia.run_tick(sid)
        assert out["prompted"] == 0 and await _pending(sid) == 0, out

    async def test_existing_rows_are_never_removed(self, sid):
        await Database.execute(
            "INSERT INTO maya_rp.adjutant_prompts "
            "(session_id, ministry, holder, action, target, impact, urgency, status, routed_via) "
            "SELECT $1, 'Lord of War', 'h', 'Respond to Iron Concord activity', 't', 'i', 'high', "
            "'pending', 'Maya' FROM generate_series(1, 3)", sid)
        out = await mia.run_tick(sid)
        assert out["prompted"] == 3, out
        assert await _pending(sid, "Lord of War") == 3


async def _territory(sid, name):
    return await Database.fetchval(
        "INSERT INTO maya_rp.territory (id, session_id, system_name, controlling_faction, crisis_level) "
        "VALUES ((SELECT COALESCE(MAX(id), 0) + 1 FROM maya_rp.territory), $1, $2, 'Setia Empire', 0) "
        "RETURNING id", sid, name)


async def _applicant(sid, name, status, score):
    return await Database.fetchval(
        "INSERT INTO maya_rp.governor_applicants (session_id, name, status, total_score) "
        "VALUES ($1, $2, $3, $4) RETURNING id", sid, name, status, score)


async def _status(applicant_id):
    return await Database.fetchval(
        "SELECT status FROM maya_rp.governor_applicants WHERE id=$1", applicant_id)


class TestTheGovernorPipelineReadsTheLiveStatus:
    async def test_the_best_vetted_applicant_is_appointed(self, sid):
        await mia.set_king(sid, False)
        tid = await _territory(sid, "fix2-alpha")
        low = await _applicant(sid, "Vetted Low", "vetted", 50)
        best = await _applicant(sid, "Vetted Best", "vetted", 80)
        skipped = await _applicant(sid, "Skipped Loyalty", "skipped_loyalty", 99)
        done = await _applicant(sid, "Already Appointed", "appointed", 99)
        legacy = await _applicant(sid, "Legacy Pending", "pending", 99)
        out = await mia.run_tick(sid)
        assert out["governors_assigned"] == 1, out
        assert await Database.fetchval(
            "SELECT governor_name FROM maya_rp.territory WHERE id=$1", tid) == "Vetted Best"
        assert await _status(best) == "appointed"
        assert [await _status(a) for a in (low, skipped, done, legacy)] == [
            "vetted", "skipped_loyalty", "appointed", "pending"]
        event = await Database.fetchrow(
            "SELECT title, tags FROM maya_rp.events WHERE session_id=$1 AND event_type='appointment'", sid)
        assert event["title"] == "Governor: Vetted Best"
        assert json.loads(event["tags"]) == ["governor", "fix2-alpha"]

    async def test_an_applicant_is_never_given_two_territories(self, sid):
        await mia.set_king(sid, False)
        await _territory(sid, "fix2-one")
        await _territory(sid, "fix2-two")
        only = await _applicant(sid, "Only Vetted", "vetted", 70)
        out = await mia.run_tick(sid)
        assert out["governors_assigned"] == 2, out
        names = sorted(r["governor_name"] for r in await Database.fetch(
            "SELECT governor_name FROM maya_rp.territory WHERE session_id=$1", sid))
        assert names == ["Acting Governor (Crown caretaker)", "Only Vetted"], names
        assert await _status(only) == "appointed"

    async def test_no_vetted_applicant_leaves_a_crown_caretaker(self, sid):
        await mia.set_king(sid, False)
        tid = await _territory(sid, "fix2-solo")
        await _applicant(sid, "Pending Only", "pending", 90)
        await mia.run_tick(sid)
        assert await Database.fetchval(
            "SELECT governor_name FROM maya_rp.territory WHERE id=$1", tid
        ) == "Acting Governor (Crown caretaker)"

    async def test_a_governed_territory_is_not_touched_again(self, sid):
        await mia.set_king(sid, False)
        await _territory(sid, "fix2-gov")
        await _applicant(sid, "First", "vetted", 70)
        await _applicant(sid, "Second", "vetted", 60)
        await mia.run_tick(sid)
        again = await mia.run_tick(sid)
        assert again["governors_assigned"] == 0, again
        assert await Database.fetchval(
            "SELECT COUNT(*) FROM maya_rp.governor_applicants WHERE session_id=$1 AND status='appointed'",
            sid) == 1


class TestTheDefaultSessionIsResolvedPerCall:
    def test_an_explicit_id_wins(self, monkeypatch):
        monkeypatch.setenv("RP_SESSION", "905")
        assert mia._sid(7) == 7

    def test_no_id_follows_rp_session_and_never_config(self, monkeypatch):
        monkeypatch.setenv("RP_SESSION", "905")
        monkeypatch.setattr("core.config.Config.SESSION_ID", 3, raising=False)
        assert mia._sid(None) == 905
        monkeypatch.setenv("RP_SESSION", "906")
        assert mia._sid(None) == 906

    def test_no_id_follows_the_active_arc_file(self, monkeypatch, tmp_path):
        arc = tmp_path / "active_arc"
        arc.write_text("907\n")
        monkeypatch.delenv("RP_SESSION", raising=False)
        monkeypatch.setattr(core_session, "ACTIVE_ARC", arc)
        assert mia._sid(None) == 907
        arc.write_text("908\n")
        assert mia._sid(None) == 908

    def test_nothing_to_resolve_refuses_instead_of_guessing(self, monkeypatch, tmp_path):
        monkeypatch.delenv("RP_SESSION", raising=False)
        monkeypatch.setattr(core_session, "ACTIVE_ARC", tmp_path / "missing")
        monkeypatch.setattr(core_session, "_maintenance_active", lambda: False)
        with pytest.raises(RuntimeError):
            mia._sid(None)

    async def test_the_default_paths_use_the_resolved_session(self, sid, monkeypatch):
        monkeypatch.setenv("RP_SESSION", str(sid))
        assert await mia.king_status() is True
        # The flag writers are captured, never run: a default that resolved wrongly would write
        # another campaign's row.
        written = []

        async def capture(query, *args):
            written.append(args[0])
            return "UPDATE 1"

        with monkeypatch.context() as patch:
            patch.setattr(mia.Database, "execute", capture)
            await mia.set_king(None, False)
            await mia.set_dark(None, True)
        assert written == [sid, sid], written
        await mia._prompt(sid, "Cabinet", "H", "Default read", "t", "i")
        assert [r["action"] for r in await mia.pending()] == ["Default read"]
