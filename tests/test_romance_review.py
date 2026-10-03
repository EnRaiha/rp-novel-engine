"""Romance module review: what reading `modules/romance.py` in full turned up.

Seven fixes. Each test fails against the module as it stood before. Nothing here writes to session 3,
nothing touches the private scene machinery beyond the rows it cleans up, and every row this file
creates in session 5 is removed in a `finally`.
"""
from __future__ import annotations

import inspect
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from core.db import Database  # noqa: E402
from modules import romance  # noqa: E402

SESSION = 5
MARK = "review romance"


async def _character(bond=6, traits="[\"stoic\"]"):
    return await Database.fetchval(
        "INSERT INTO maya_rp.characters (id, session_id, name, bond, traits) "
        "VALUES ((SELECT COALESCE(MAX(id), 0) + 1 FROM maya_rp.characters), $1, $2, $3, $4::jsonb) "
        "RETURNING id",
        SESSION, f"{MARK} character", bond, traits)


async def _arc(character_id, saturation=60, arc_stage="attraction", intimacy_level=2):
    return await Database.fetchval(
        "INSERT INTO maya_rp.romance_arcs "
        "(id, session_id, character_id, saturation_pct, arc_stage, intimacy_level) "
        "VALUES ((SELECT COALESCE(MAX(id), 0) + 1 FROM maya_rp.romance_arcs), $1, $2, $3, $4, $5) "
        "RETURNING id",
        SESSION, character_id, saturation, arc_stage, intimacy_level)


async def _drop(character_id):
    await Database.execute(
        "DELETE FROM maya_rp.romance_arcs WHERE session_id = $1 AND character_id = $2",
        SESSION, character_id)
    await Database.execute(
        "DELETE FROM maya_rp.intimacy_events WHERE session_id = $1 AND character_id = $2",
        SESSION, character_id)
    await Database.execute(
        "DELETE FROM maya_rp.jealousy_states WHERE session_id = $1 AND character_id = $2",
        SESSION, character_id)
    await Database.execute("DELETE FROM maya_rp.characters WHERE id = $1", character_id)


class TestTheLocationTableIsOneTable:
    def test_the_table_is_defined_once(self):
        """Two definitions of LOCATION_MOODS meant an edit to the first changed nothing."""
        source = inspect.getsource(romance)
        assert source.count("\nLOCATION_MOODS = {") == 1, source.count("\nLOCATION_MOODS = {")
        assert "heaven_pool" in romance.LOCATION_MOODS
        assert all("sound_anchor" in v for v in romance.LOCATION_MOODS.values())


class TestTheThresholdsComeFromTheTiers:
    def test_the_crossings_are_the_tier_requirements(self):
        assert romance.get_crossed_thresholds(4, 10) == [5, 7, 9]

    def test_moving_a_tier_moves_its_crossing(self, monkeypatch):
        monkeypatch.setitem(romance.TIERS["flame"], "bond_threshold", 8)
        assert romance.get_crossed_thresholds(4, 10) == [5, 8, 9]

    def test_the_milestones_are_the_crossings(self):
        assert romance.get_milestones(4, 10) == ["flirt_unlocked", "kiss_unlocked",
                                                 "intimacy_unlocked"]
        assert romance.get_milestones(6, 7) == ["kiss_unlocked"]


class TestOneBandingRule:
    async def test_healing_progress_agrees_with_its_state(self):
        """`progress` used a local 20/50 ladder while `state` used SATURATION_THRESHOLDS."""
        await Database.init()
        cid = await _character()
        await _arc(cid, saturation=60)
        try:
            out = await romance.process_healing(cid, "talk", SESSION)
            assert out["saturation_after"] == 50, out
            assert out["state"] == "balanced", out
            assert out["progress"] == "Stage: balanced", out
        finally:
            await _drop(cid)
            await Database.close()

    async def test_every_saturation_value_lands_in_a_band(self):
        for value in range(0, 101):
            state = romance.calculate_saturation_state(value)["state"]
            assert state in romance.SATURATION_THRESHOLDS, (value, state)


class TestTheUnknownIsNamed:
    def test_a_companion_with_no_voice_is_refused(self):
        out = romance.get_voice_profile("Ghost")
        assert "Ghost" in out.get("error", ""), out
        assert out["available"] == ["Melano", "Nethara", "Valia"]

    def test_a_scene_for_an_unknown_companion_is_refused(self):
        """The unknown name used to come back as Nethara's profile, cadence and all."""
        out = romance.generate_scene({}, "ember", "Ghost", "kiss")
        assert "Ghost" in out.get("error", ""), out

    async def test_an_unknown_position_is_refused_before_the_lookups(self):
        await Database.init()
        try:
            out = await romance.execute_rolling_scene(999999, 999998, "backflip", session_id=SESSION)
            assert "unknown position" in out.get("error", ""), out
            assert "pile_driver" not in out["available"]
            assert out["available"] == sorted(romance.POSITIONS)
        finally:
            await Database.close()

    async def test_release_without_an_arc_is_refused(self):
        """The update touched no row and the answer still said the release was done."""
        await Database.init()
        cid = await _character(bond=4)
        try:
            out = await romance.release_and_heal(cid, SESSION)
            assert "no romance arc" in out.get("error", ""), out
        finally:
            await _drop(cid)
            await Database.close()

    async def test_release_with_an_arc_still_works(self):
        await Database.init()
        cid = await _character(bond=4)
        await _arc(cid, saturation=20, arc_stage="deepening", intimacy_level=5)
        try:
            out = await romance.release_and_heal(cid, SESSION)
            assert out["released"] is True, out
            stored = await Database.fetchval(
                "SELECT saturation_pct FROM maya_rp.romance_arcs WHERE character_id = $1", cid)
            assert stored == 90
        finally:
            await _drop(cid)
            await Database.close()


class TestTheDeclaredContract:
    def test_the_unused_action_parameter_is_declared(self):
        doc = inspect.getdoc(romance.calculate_bond_shift) or ""
        assert "`action` is accepted and read by nothing" in doc, doc

    def test_the_shift_still_follows_the_quality_word(self):
        assert romance.calculate_bond_shift("kiss", "perfect")["delta"] == 2
        assert romance.calculate_bond_shift("kiss", "pushy")["delta"] == -1
