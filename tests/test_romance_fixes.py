"""Live-database tests for the `modules/romance.py` defects found in the wave 3 review.

Each test fails against the module as it stood before the fix.

Defects covered:

1. R1  a scene whose score is 0 or less raised `CheckViolation` on `intimacy_events.intensity >= 1`,
       after the bond and saturation writes had committed.
2. R2  Trial by Fire paid +2 bond on every heal of a character already at saturation 20 or below.
3. R3  `advance_bond` raised `intimacy_level` by `abs(delta)`, so a penalty deepened intimacy.
4. R4  `advance_bond` read the bond, added in Python and wrote it back, so concurrent advances were lost.
5. R5  no writer refused a frozen campaign, and an omitted session read `Config.SESSION_ID`.
6. R6  the jealousy tick looked for a rival at bond >= 7 while the logic picked the highest bond, so a
       rival at bond 5-6 never got a `jealousy_states` row.
7. R7  `check_threshold` took the first tier that matched instead of the highest.
8. R8  `generate_scene` matched `bond_lines` on exact keys 5, 7 and 9, so bonds 6, 8 and 10 read the
       bond-5 line.

Scratch session: 900 + pid % 100, the slot `scratch_session` hands out. Sessions 3 and 5 are never
written. The freeze in R5 is simulated by patching `core.session.is_frozen`; the real
`~/.config/rp-engine/frozen_sessions` is never touched. Every row this file creates is removed in `finally`.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from core import ooc  # noqa: E402
from core.db import Database  # noqa: E402
from modules import romance  # noqa: E402


async def _open(session_id: int) -> None:
    await Database.init()
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1,'Romance fixes scratch','active')"
        " ON CONFLICT (id) DO NOTHING",
        session_id,
    )


async def _clear(session_id: int) -> None:
    """Remove every row this file creates, children first."""
    for table in ("jealousy_states", "intimacy_events", "romance_arcs", "characters"):
        await Database.execute(f"DELETE FROM maya_rp.{table} WHERE session_id=$1", session_id)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id=$1", session_id)


async def _character(session_id: int, name: str, bond: int = 5, traits: list[str] | None = None) -> int:
    return int(await Database.fetchval(
        "INSERT INTO maya_rp.characters (session_id, name, status, bond, traits)"
        " VALUES ($1,$2,'active',$3,$4::jsonb) RETURNING id",
        session_id, name, bond, json.dumps(traits or [])))


async def _arc(session_id: int, character_id: int, saturation: int = 50,
               arc_stage: str = "attraction", intimacy_level: int = 2) -> None:
    await Database.execute(
        "INSERT INTO maya_rp.romance_arcs"
        " (session_id, character_id, arc_stage, intimacy_level, saturation_pct)"
        " VALUES ($1,$2,$3,$4,$5)",
        session_id, character_id, arc_stage, intimacy_level, saturation)


async def _bond(character_id: int) -> int:
    return int(await Database.fetchval("SELECT bond FROM maya_rp.characters WHERE id=$1", character_id))


async def _arc_row(character_id: int) -> dict:
    return dict(await Database.fetchrow(
        "SELECT arc_stage, intimacy_level, saturation_pct, nights_shared,"
        " initiatives_by_player, initiatives_by_companion"
        " FROM maya_rp.romance_arcs WHERE character_id=$1", character_id))


async def _count(table: str, session_id: int) -> int:
    return int(await Database.fetchval(
        f"SELECT count(*) FROM maya_rp.{table} WHERE session_id=$1", session_id))


class TestSceneScoreBelowOne:
    async def test_a_scene_scoring_zero_or_less_logs_intensity_one_and_does_not_raise(
            self, scratch_session, monkeypatch):
        """Pre-fix: roll 1 + doggy 10 - Watcher's Curse 40 = -29 hit CHECK (intensity >= 1) and raised."""
        sid = scratch_session
        await _open(sid)
        try:
            target = await _character(sid, "Fix Target", bond=0, traits=["scientist"])
            initiator = await _character(sid, "Fix Initiator", bond=0)
            monkeypatch.setattr(romance.random, "randint", lambda a, b: 1)

            out = await romance.execute_rolling_scene(initiator, target, "doggy", session_id=sid)

            assert out["success"] is True, out
            assert out["final_score"] < 1, f"setup must score below 1, got {out['final_score']}"
            intensity = await Database.fetchval(
                "SELECT intensity FROM maya_rp.intimacy_events"
                " WHERE session_id=$1 AND character_id=$2 AND event_type='scene_roll'", sid, target)
            assert intensity is not None and intensity >= 1, f"logged intensity {intensity}"
        finally:
            await _clear(sid)
            await Database.close()


class TestTrialByFireFiresOnTheCrossing:
    async def test_a_character_already_at_or_below_20_gets_no_bonus(self, scratch_session):
        """Pre-fix: healing a character at 15 reached 5 and still paid +2 bond and the trait."""
        sid = scratch_session
        await _open(sid)
        try:
            cid = await _character(sid, "Fix Healed", bond=3)
            await _arc(sid, cid, saturation=15)

            out = await romance.process_healing(cid, "talk", sid)

            assert out["saturation_after"] == 5, out
            assert "trait" not in out, f"trait granted without a crossing: {out}"
            assert await _bond(cid) == 3, "bond moved without a crossing"
        finally:
            await _clear(sid)
            await Database.close()

    async def test_the_heal_that_crosses_to_20_still_pays_the_bonus(self, scratch_session):
        """Control: 25 -> 15 is the crossing, so the bonus stays."""
        sid = scratch_session
        await _open(sid)
        try:
            cid = await _character(sid, "Fix Crosser", bond=3)
            await _arc(sid, cid, saturation=25)

            out = await romance.process_healing(cid, "talk", sid)

            assert out.get("trait") == "Trial by Fire", out
            assert await _bond(cid) == 5, "the crossing must pay +2 bond"
        finally:
            await _clear(sid)
            await Database.close()


class TestNegativeDeltaNeverRaisesIntimacy:
    async def test_a_penalty_lowers_bond_and_leaves_intimacy_alone(self, scratch_session):
        """Pre-fix: delta -1 added abs(-1) to intimacy_level, so the penalty deepened it."""
        sid = scratch_session
        await _open(sid)
        try:
            cid = await _character(sid, "Fix Penalised", bond=5)
            await _arc(sid, cid, intimacy_level=4)

            out = await romance.advance_bond(cid, -1, sid)

            assert out["bond_new"] == 4, out
            assert (await _arc_row(cid))["intimacy_level"] == 4, "a negative delta raised intimacy"
        finally:
            await _clear(sid)
            await Database.close()


class TestConcurrentAdvancesAreNotLost:
    async def test_four_concurrent_advances_add_four(self, scratch_session):
        """Pre-fix: each call read the same bond and wrote bond+1, so concurrent calls collapsed to one.

        Four calls instead of two, so the interleaving that loses an update is near certain.
        """
        sid = scratch_session
        await _open(sid)
        try:
            cid = await _character(sid, "Fix Racer", bond=0)
            await _arc(sid, cid, arc_stage="strangers", intimacy_level=0)

            await asyncio.gather(*(romance.advance_bond(cid, 1, sid) for _ in range(4)))

            assert await _bond(cid) == 4, "concurrent advances were lost"
        finally:
            await _clear(sid)
            await Database.close()

    async def test_concurrent_indulgences_each_count_a_night(self, scratch_session):
        """Pre-fix: nights_shared and the initiative counters were read, incremented and written back."""
        sid = scratch_session
        await _open(sid)
        try:
            cid = await _character(sid, "Fix Nights", bond=6)
            await _arc(sid, cid, saturation=0)

            await asyncio.gather(*(romance.process_indulgence(cid, "ember", True, sid) for _ in range(4)))

            row = await _arc_row(cid)
            assert row["nights_shared"] == 4, row
            assert row["initiatives_by_player"] == 4, row
            assert row["saturation_pct"] == 20, row
        finally:
            await _clear(sid)
            await Database.close()


class TestEveryWriterRefusesAFrozenCampaign:
    @pytest.fixture()
    def frozen(self, monkeypatch):
        import core.session as session_mod

        monkeypatch.setattr(session_mod, "is_frozen", lambda sid: True)
        monkeypatch.setattr(ooc, "_maintenance_active", lambda: False)
        return True

    WRITERS = {
        "advance_bond": lambda cid, sid: romance.advance_bond(cid, 1, sid),
        "check_jealousy": lambda cid, sid: romance.check_jealousy(sid),
        "process_healing": lambda cid, sid: romance.process_healing(cid, "talk", sid),
        "release_and_heal": lambda cid, sid: romance.release_and_heal(cid, sid),
        "process_indulgence": lambda cid, sid: romance.process_indulgence(cid, "flame", True, sid),
        "decay_saturation": lambda cid, sid: romance.decay_saturation(sid),
        "run_tick": lambda cid, sid: romance.run_tick(sid),
        "execute_rolling_scene": lambda cid, sid: romance.execute_rolling_scene(cid, cid, "peck", session_id=sid),
        "process_aftercare": lambda cid, sid: romance.process_aftercare(cid, cid, sid),
    }

    @pytest.mark.parametrize("writer", sorted(WRITERS))
    async def test_the_writer_is_refused_and_writes_nothing(self, scratch_session, frozen, writer):
        """Pre-fix: each writer wrote into the frozen campaign with no check."""
        sid = scratch_session
        await _open(sid)
        try:
            cid = await _character(sid, "Fix Frozen", bond=5)
            await _arc(sid, cid, saturation=50, intimacy_level=2)
            before = (await _bond(cid), await _arc_row(cid),
                      await _count("intimacy_events", sid), await _count("jealousy_states", sid))

            with pytest.raises(ooc.FrozenSession):
                await self.WRITERS[writer](cid, sid)

            after = (await _bond(cid), await _arc_row(cid),
                     await _count("intimacy_events", sid), await _count("jealousy_states", sid))
            assert after == before, f"{writer} wrote before it refused: {before} -> {after}"
        finally:
            await _clear(sid)
            await Database.close()

    async def test_an_omitted_session_resolves_per_call_not_from_config(self, scratch_session, monkeypatch):
        """Pre-fix: `get_romance_arcs(None)` read `Config.SESSION_ID`, fixed at import."""
        sid = scratch_session
        await _open(sid)
        try:
            cid = await _character(sid, "Fix Resolved", bond=5)
            await _arc(sid, cid)
            monkeypatch.setenv("RP_SESSION", str(sid))

            arcs = await romance.get_romance_arcs()

            assert [a["character_name"] for a in arcs] == ["Fix Resolved"], arcs
        finally:
            await _clear(sid)
            await Database.close()


class TestJealousyNamesTheRivalTheLogicPicked:
    async def test_a_rival_at_bond_five_gets_a_state_row_and_repeats_raise_its_level(self, scratch_session):
        """Pre-fix: the tick searched for a rival at bond >= 7, found none for a bond-5 rival, wrote no row."""
        sid = scratch_session
        await _open(sid)
        try:
            active = await _character(sid, "Fix Alpha", bond=7)
            rival = await _character(sid, "Fix Beta", bond=5)
            await _arc(sid, active, arc_stage="deepening", intimacy_level=0)   # derived bond 7
            await _arc(sid, rival, arc_stage="attraction", intimacy_level=0)   # derived bond 5

            first = await romance.check_jealousy(sid)
            levels = [await Database.fetchval(
                "SELECT jealousy_level FROM maya_rp.jealousy_states WHERE character_id=$1 AND rival_id=$2",
                active, rival)]
            await romance.check_jealousy(sid)
            levels.append(await Database.fetchval(
                "SELECT jealousy_level FROM maya_rp.jealousy_states WHERE character_id=$1 AND rival_id=$2",
                active, rival))

            assert [e["character"] for e in first] == ["Fix Alpha"], first
            assert levels == [1, 2], f"expected one row raised by the second tick, got {levels}"
            assert await _count("jealousy_states", sid) == 1, "the upsert made a second row"
        finally:
            await _clear(sid)
            await Database.close()

    def test_the_logic_names_its_rival(self):
        out = romance.check_jealousy_logic("Nethara", 9, [{"name": "Melano", "bond": 7}])
        assert out["rival"] == "Melano", out


class TestThresholdTakesTheHighestTier:
    def test_a_request_naming_two_tiers_needs_the_higher_bond(self):
        """Pre-fix: 'tease' matched ember first, so a kiss request passed at bond 5."""
        out = romance.check_threshold(5, "tease her and then kiss her")
        assert out["required"] == 7, out
        assert out["allowed"] is False, out

    def test_keywords_without_action_matches_also_take_the_highest_tier(self):
        """Pre-fix: the keyword fallback took ember ('playful') before flame ('lips')."""
        out = romance.check_threshold(5, "playful lips")
        assert out["required"] == 7, out

    def test_a_single_tier_request_is_unchanged(self):
        assert romance.check_threshold(7, "kiss")["allowed"] is True


class TestBondLineFollowsTheHighestThresholdReached:
    @pytest.mark.parametrize("bond,threshold", [(5, 5), (6, 5), (7, 7), (8, 7), (9, 9), (10, 9)])
    def test_the_line_is_the_highest_threshold_at_or_below_the_bond(self, bond, threshold):
        """Pre-fix: `.get(bond)` hit only 5, 7 and 9, so bonds 8 and 10 read the bond-5 line."""
        scene = romance.generate_scene({"bond": bond}, "flame", "Nethara", "kiss")
        assert scene["bond_line"] == romance.VOICE_PROFILES["Nethara"]["bond_lines"][threshold], scene["bond_line"]

    def test_a_bond_below_every_threshold_keeps_the_lowest_line(self):
        scene = romance.generate_scene({"bond": 2}, "ember", "Valia", "gaze")
        assert scene["bond_line"] == romance.VOICE_PROFILES["Valia"]["bond_lines"][5]
