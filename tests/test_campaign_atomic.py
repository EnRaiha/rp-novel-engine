"""Campaign atomicity and lookup defects: spend, restore_snapshot, ending conditions, find_character, speakers.

C1 `spend` applied its effect before the RPP debit and read the balance in a separate statement. Two
concurrent `skip_beat` calls both read 25, both completed a beat, and the second debit then broke
`roleplay_points >= 0`: one payment, two completions.

C2 `restore_snapshot` wrote four phases through the pool with no transaction. A bad second suspicion
row (or an FK failure on rule_id) raised after state, milestones and exemptions were already written.

C3 `condition_met` read an unknown stat as 0, so a `<` ending naming a misspelled stat fired at once and
`triggered_endings` stamped it permanently.

C4 `find_character('')` fell through to `%%` and matched every character; `QUEUE_ORDERS["bond"]` ordered by
`bond_level`, the marriage bond, which is 0 for everyone until the marriages happen.

C5 `SPOKE` captured a sentence-initial word as part of the name ("Lalu Wulan berkata"), and `check`
compared against a NULL scene location, flagging every speaker with a recorded location.

Every row is written in a scratch session (900-999) and removed in the fixture's finally.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core import campaign, omniscience, portraits  # noqa: E402
from core.db import Database  # noqa: E402

CLEANUP = (
    "DELETE FROM maya_rp.ooc_directives WHERE session_id=$1",
    "DELETE FROM maya_rp.ooc_suspicion WHERE session_id=$1",
    "DELETE FROM maya_rp.ooc_exemptions WHERE session_id=$1",
    "DELETE FROM maya_rp.ooc_milestones WHERE session_id=$1",
    "DELETE FROM maya_rp.ooc_endings WHERE session_id=$1",
    "DELETE FROM maya_rp.ooc_system_state WHERE session_id=$1",
    "DELETE FROM maya_rp.characters WHERE session_id=$1",
)


async def _clear(sid: int) -> None:
    for statement in CLEANUP:
        await Database.execute(statement, sid)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", sid)


@pytest.fixture()
async def arena(scratch_session):
    """A scratch session with state (25 rpp), two open beats and one character named Alpha."""
    sid = scratch_session
    await Database.init()
    await _clear(sid)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1,'Campaign atomic','active')", sid)
    await Database.execute(
        "INSERT INTO maya_rp.ooc_system_state (session_id, roleplay_points) VALUES ($1, 25)", sid)
    for beat in ("beat-a", "beat-b"):
        await Database.execute(
            "INSERT INTO maya_rp.ooc_milestones (session_id, name, stage) VALUES ($1,$2,'selective')",
            sid, beat)
    char = await Database.fetchval(
        "INSERT INTO maya_rp.characters (session_id, name, status, bond) VALUES ($1,'Alpha','active',0)"
        " RETURNING id", sid)
    try:
        yield {"sid": sid, "char": char}
    finally:
        await _clear(sid)
        await Database.close()


async def _rpp(sid: int) -> int:
    return await Database.fetchval(
        "SELECT roleplay_points FROM maya_rp.ooc_system_state WHERE session_id=$1", sid)


class TestSpendDebitsBeforeItApplies:
    async def test_two_concurrent_skip_beats_complete_exactly_one(self, arena):
        """Both calls read balance 25 and both completed a beat; the second debit then broke the CHECK."""
        sid = arena["sid"]
        results = await asyncio.gather(
            campaign.spend(sid, "skip_beat", "beat-a"),
            campaign.spend(sid, "skip_beat", "beat-b"),
            return_exceptions=True,
        )
        done = await Database.fetchval(
            "SELECT count(*) FROM maya_rp.ooc_milestones WHERE session_id=$1 AND completed_at IS NOT NULL", sid)
        wins = [r for r in results if isinstance(r, dict)]
        refused = [r for r in results if isinstance(r, ValueError)]
        assert done == 1, f"one payment of 25 rpp buys one beat, {done} completed"
        assert len(wins) == 1 and len(refused) == 1, f"one win and one refusal expected, got {results!r}"
        assert await _rpp(sid) == 0, "the winner paid 25 and the balance never went negative"

    async def test_the_debit_is_already_taken_when_the_effect_runs(self, arena, monkeypatch):
        """The effect ran first and the debit after, so the effect saw the undebited balance."""
        sid = arena["sid"]
        seen = {}

        async def effect(session_id, note):
            seen["balance"] = await _rpp(sid)

        monkeypatch.setattr(campaign, "add_directive", effect)
        await campaign.spend(sid, "reveal_intel", "who")
        assert seen["balance"] == 15, "price 10 is debited before the effect applies"

    async def test_a_failing_effect_refunds_the_price(self, arena, monkeypatch):
        sid = arena["sid"]

        async def boom(session_id, note):
            raise RuntimeError("directive write failed")

        monkeypatch.setattr(campaign, "add_directive", boom)
        with pytest.raises(RuntimeError, match="directive write failed"):
            await campaign.spend(sid, "reveal_intel", "who")
        assert await _rpp(sid) == 25, "a spend whose effect failed costs nothing"

    async def test_an_unaffordable_spend_is_refused_with_the_price(self, arena):
        sid = arena["sid"]
        await Database.execute("UPDATE maya_rp.ooc_system_state SET roleplay_points=5 WHERE session_id=$1", sid)
        with pytest.raises(ValueError, match="costs 25 rpp; the crown holds 5"):
            await campaign.spend(sid, "skip_beat", "beat-a")
        assert await _rpp(sid) == 5


class TestRestoreSnapshotIsAllOrNothing:
    async def _seed(self, arena):
        sid = arena["sid"]
        rule = await Database.fetchval("SELECT id FROM maya_rp.ooc_rules WHERE enabled ORDER BY id LIMIT 1")
        await Database.execute(
            "UPDATE maya_rp.ooc_system_state SET arc_stage='lockdown', deviation=1, roleplay_points=25"
            " WHERE session_id=$1", sid)
        await Database.execute(
            "INSERT INTO maya_rp.ooc_exemptions (session_id, rule_id, action_key, cost_rpp, permanent)"
            " VALUES ($1,$2,'old_action',5,false)", sid, rule)
        return rule

    async def _picture(self, sid: int):
        return (
            dict(await Database.fetchrow(
                "SELECT arc_stage, deviation, roleplay_points FROM maya_rp.ooc_system_state WHERE session_id=$1", sid)),
            [dict(r) for r in await Database.fetch(
                "SELECT name, completed_at FROM maya_rp.ooc_milestones WHERE session_id=$1 ORDER BY name", sid)],
            [dict(r) for r in await Database.fetch(
                "SELECT rule_id, action_key, cost_rpp FROM maya_rp.ooc_exemptions WHERE session_id=$1 ORDER BY 2", sid)],
            await Database.fetchval("SELECT count(*) FROM maya_rp.ooc_suspicion WHERE session_id=$1", sid),
        )

    async def test_a_bad_second_suspicion_row_leaves_everything_as_before(self, arena):
        """State, milestones, exemptions and the first suspicion row were written, then the second raised."""
        sid = arena["sid"]
        rule = await self._seed(arena)
        before = await self._picture(sid)
        bad = {
            "session_id": sid,
            "state": {"arc_stage": "confrontation", "deviation": 90, "roleplay_points": 99},
            "milestones": [{"name": "beat-a", "completed_at": "2026-01-02T03:04:05+00:00"}],
            "exemptions": [{"rule_id": rule, "action_key": "new_action", "cost_rpp": 7, "permanent": True}],
            "suspicion": [{"observer_id": arena["char"], "suspicion": 50}, {"suspicion": 7}],
        }
        with pytest.raises(ValueError, match="no observer_id"):
            await campaign.restore_snapshot(bad)
        assert await self._picture(sid) == before, "a refused snapshot changes nothing"

    async def test_a_foreign_key_failure_mid_restore_rolls_back_the_earlier_writes(self, arena):
        """An unknown rule_id raised from the database after state and milestones were already committed."""
        sid = arena["sid"]
        await self._seed(arena)
        before = await self._picture(sid)
        bad = {
            "session_id": sid,
            "state": {"arc_stage": "confrontation", "deviation": 90, "roleplay_points": 99},
            "milestones": [{"name": "beat-a", "completed_at": "2026-01-02T03:04:05+00:00"}],
            "exemptions": [{"rule_id": -987654, "action_key": "ghost", "cost_rpp": 1, "permanent": False}],
        }
        with pytest.raises(Exception):
            await campaign.restore_snapshot(bad)
        assert await self._picture(sid) == before, "the rollback covers the statements that ran before the failure"


class TestAnUnknownStatDoesNotFireAnEnding:
    def test_a_less_than_condition_on_a_misspelled_stat_is_not_met(self):
        """`deviaton < 10` read the stat as 0 and fired immediately."""
        cond = {"stat": "deviaton", "op": "<", "value": 10}
        assert campaign.condition_met(cond, {"deviation": 50}) is False, "a missing stat is no evidence"

    def test_a_known_stat_still_evaluates(self):
        assert campaign.condition_met({"stat": "deviation", "op": "<", "value": 10}, {"deviation": 5}) is True

    def test_near_endings_gives_no_hint_for_a_less_than_condition(self):
        entry = {"name": "Calm", "met": False, "condition": {"stat": "deviation", "op": "<", "value": 10}}
        assert campaign.near_endings([entry], {"deviation": 9}) == [], "9/10 is not 'near' for a ceiling"

    def test_near_endings_still_hints_for_a_floor(self):
        entry = {"name": "Doom", "met": False, "condition": {"stat": "deviation", "op": ">=", "value": 100}}
        assert campaign.near_endings([entry], {"deviation": 90}) == ["- endings near: Doom (90/100)"]

    async def test_triggered_endings_does_not_stamp_an_unknown_stat(self, arena):
        sid = arena["sid"]
        await Database.execute(
            "INSERT INTO maya_rp.ooc_endings (session_id, name, kind, condition) VALUES ($1,'Typo','neutral',$2)",
            sid, json.dumps({"stat": "deviaton", "op": "<", "value": 10}))
        assert await campaign.triggered_endings(sid) == []
        assert await Database.fetchval(
            "SELECT triggered_at FROM maya_rp.ooc_endings WHERE session_id=$1", sid) is None, \
            "an unreachable ending must not be stamped as fired"


class TestFindCharacterAndQueueOrder:
    async def test_an_empty_name_matches_nobody(self, arena):
        """`%%` matched every character and returned the most important one."""
        sid = arena["sid"]
        assert await portraits.find_character(sid, "") is None
        assert await portraits.find_character(sid, "   ") is None

    async def test_a_percent_in_the_name_is_literal(self, arena):
        """`a%` was a prefix pattern that matched Alpha."""
        sid = arena["sid"]
        assert await portraits.find_character(sid, "a%") is None
        assert await portraits.find_character(sid, "A_pha") is None, "`_` is literal, not one-character"
        found = await portraits.find_character(sid, "alp")
        assert found is not None and found["name"] == "Alpha", "ordinary prefix lookup still works"

    def test_the_bond_order_uses_the_relationship_column(self):
        """`bond_level` is the marriage bond, 0 for everyone, so the order collapsed to queue id."""
        sql = portraits.QUEUE_ORDERS["bond"]
        assert sql.startswith("c.bond DESC"), sql
        assert "bond_level" not in sql, "bond_level is 0 until the marriages happen"


class TestSpeakerResolution:
    ROSTER = ["Wulan", "Doyo Kwarta", "Ersya Ardani"]

    def test_a_sentence_initial_word_does_not_hide_the_speaker(self):
        """"Lalu Wulan berkata" was captured whole and reported not_in_roster."""
        said = omniscience.speakers("Lalu Wulan berkata dengan lantang")
        assert said == ["Lalu Wulan"]
        assert omniscience.resolve_speaker(said[0], self.ROSTER) == "Wulan"

    def test_a_leading_name_with_a_trailing_word_resolves_by_the_first_word(self):
        assert omniscience.resolve_speaker("Wulan Kemudian", self.ROSTER) == "Wulan"

    def test_a_two_word_name_that_resolves_whole_is_kept(self):
        assert omniscience.resolve_speaker("Doyo Kwarta", self.ROSTER) == "Doyo Kwarta"

    def test_a_name_nobody_answers_to_still_resolves_to_nothing(self):
        assert omniscience.resolve_speaker("Lalu Krosh", self.ROSTER) is None

    @pytest.mark.parametrize("scene,at", [(None, "rumah_agung"), ("rumah_agung", None), (None, None)])
    async def test_a_null_location_side_is_not_a_speaks_elsewhere_finding(self, arena, scene, at):
        """`player_context.location` is NULL for every session, so every located speaker was flagged."""
        sid = arena["sid"]
        await Database.execute("UPDATE maya_rp.characters SET scene_location=$2 WHERE id=$1", arena["char"], at)
        await Database.execute(
            "INSERT INTO maya_rp.player_context (session_id, location) VALUES ($1,$2)"
            " ON CONFLICT (session_id) DO UPDATE SET location=EXCLUDED.location", sid, scene)
        try:
            result = await omniscience.check(sid, "Lalu Alpha berkata pelan")
        finally:
            await Database.execute("DELETE FROM maya_rp.player_context WHERE session_id=$1", sid)
        assert result["findings"] == [], f"scene={scene!r} recorded={at!r} is no evidence of omniscience"
