"""Social module review: what reading `modules/social.py` in full turned up.

Seven fixes. Each test fails against the module as it stood before. Every row this file creates lives in a scratch
session and is removed in teardown. Sessions 3 and 5 are frozen and never touched.
"""
from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

from core.db import Database  # noqa: E402
from modules import social  # noqa: E402

#: A scratch session (900-999). The writers refuse the frozen sessions 3 and 5.
SESSION = 900 + os.getpid() % 100

#: Children first: foreign keys run from these tables to `characters` and `sessions`.
_TABLES = ("character_relationships", "characters", "crew_roster", "morale_history", "social_events")
CREW_MARK = "review crew"


async def _wipe() -> None:
    for table in _TABLES:
        await Database.execute(f"DELETE FROM maya_rp.{table} WHERE session_id = $1", SESSION)
    await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", SESSION)


@pytest_asyncio.fixture
async def scratch():
    """The scratch session exists for the test; every row of it is removed after, in foreign-key order."""
    await Database.init()
    await _wipe()
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status) VALUES ($1, 'scratch', 'active')"
        " ON CONFLICT (id) DO NOTHING", SESSION)
    try:
        yield
    finally:
        await _wipe()
        await Database.close()


async def _characters() -> tuple[int, int]:
    """Two characters of the scratch session. `character_relationships` has foreign keys on both."""
    ids = [await Database.fetchval(
        "INSERT INTO maya_rp.characters (session_id, name) VALUES ($1, $2) RETURNING id",
        SESSION, f"review char {n}") for n in "ab"]
    return ids[0], ids[1]


async def _relationship(char_a, char_b, score=10):
    await Database.execute(
        "INSERT INTO maya_rp.character_relationships "
        "(id, session_id, char_a_id, char_b_id, score, relationship_type, last_interaction) "
        "VALUES ((SELECT COALESCE(MAX(id), 0) + 1 FROM maya_rp.character_relationships), "
        "$1, $2, $3, $4, 'neutral', NOW())",
        SESSION, char_a, char_b, score,
    )


async def _crew(count):
    await Database.execute(
        "INSERT INTO maya_rp.crew_roster (id, session_id, name, morale) "
        "SELECT (SELECT COALESCE(MAX(id), 0) FROM maya_rp.crew_roster) + g, $1, $2 || ' ' || g, 50 "
        "FROM generate_series(1, $3) g",
        SESSION, CREW_MARK, count,
    )


async def _drop_crew():
    await Database.execute(
        "DELETE FROM maya_rp.crew_roster WHERE session_id = $1 AND name LIKE $2",
        SESSION, CREW_MARK + " %")


async def _drop_events(event_type=None):
    if event_type is None:
        await Database.execute("DELETE FROM maya_rp.social_events WHERE session_id = $1", SESSION)
    else:
        await Database.execute(
            "DELETE FROM maya_rp.social_events WHERE session_id = $1 AND event_type = $2",
            SESSION, event_type)


class TestTheEventModifiersReachTheFormula:
    """`test_crew_loyalty` feeds rows straight out of `social_events`, whose column is `event_type`."""

    def test_a_social_event_row_moves_the_score(self):
        score = social.calculate_loyalty({"loyalty_flag": "neutral", "name": "x"}, 50,
                                         [{"event_type": "injustice"}])
        assert score == 0.4, score

    def test_a_js_shaped_event_still_moves_the_score(self):
        score = social.calculate_loyalty({"loyalty_flag": "neutral", "name": "x"}, 50,
                                         [{"type": "betrayal_revealed"}])
        assert score == 0.35, score

    def test_a_recognised_hero_gains(self):
        score = social.calculate_loyalty({"loyalty_flag": "neutral", "name": "Rika"}, 50,
                                         [{"event_type": "hero_recognized", "target": "Rika"}])
        assert score == 0.65, score


class TestTheClassifierAndItsTable:
    def test_the_four_flags_come_from_the_table(self):
        """The thresholds existed twice: in LOYALTY_FLAG_LEVELS and again inside the classifier."""
        bands = {flag: cfg["threshold"] for flag, cfg in social.LOYALTY_FLAG_LEVELS.items()}
        assert social.classify_loyalty(0.95) == "loyal"
        assert social.classify_loyalty(bands["loyal"]) == "loyal"
        assert social.classify_loyalty(bands["loyal"] - 0.01) == "neutral"
        assert social.classify_loyalty(bands["neutral"] - 0.01) == "wavering"
        assert social.classify_loyalty(bands["wavering"] - 0.01) == "disloyal"

    def test_the_classifier_follows_the_table_when_the_table_moves(self, monkeypatch):
        """A copied threshold agrees with the table until the table changes."""
        monkeypatch.setitem(social.LOYALTY_FLAG_LEVELS, "loyal", {"threshold": 0.9, "desc": "x"})
        assert social.classify_loyalty(0.8) == "neutral"
        assert social.classify_loyalty(0.95) == "loyal"


class TestTheRingleaderDivision:
    async def test_an_empty_relationship_table_does_not_divide_by_zero(self, scratch):
        """`max(..., default=1)` still returned 0 when every member had no network at all."""
        out = await social.get_ringleaders(SESSION, [
            {"id": 999001, "loyalty_flag": "disloyal"},
            {"id": 999002, "loyalty_flag": "wavering"},
        ])
        assert out == [], out

    async def test_an_influential_malcontent_is_returned(self, scratch):
        char_a, char_b = await _characters()
        await _relationship(char_a, char_b)
        out = await social.get_ringleaders(SESSION, [
            {"id": char_a, "loyalty_flag": "disloyal"},
            {"id": char_b, "loyalty_flag": "neutral"},
        ])
        assert [r["crew_id"] for r in out] == [char_a], out
        assert out[0]["risk"] == 100, out


class TestTheMoraleFloor:
    async def test_a_crew_member_at_zero_is_not_read_as_fifty(self, monkeypatch):
        async def fake_fetch(query, *args):
            return [{"morale": 0}, {"morale": 100}]

        monkeypatch.setattr(social.Database, "fetch", fake_fetch)
        assert await social._get_fleet_morale(SESSION) == 50

    async def test_update_morale_does_not_rescue_a_zero(self, scratch):
        """A member at morale 0 gets the delta added to 0, never to the 50 that stands in for NULL."""
        await Database.execute(
            "INSERT INTO maya_rp.crew_roster (id, session_id, name, morale) VALUES "
            "((SELECT COALESCE(MAX(id), 0) + 1 FROM maya_rp.crew_roster), $1, 'zero hero', 0)", SESSION)
        fleet = await social.update_morale(SESSION, 5)
        morale = await Database.fetchval(
            "SELECT morale FROM maya_rp.crew_roster WHERE session_id = $1 AND name = 'zero hero'", SESSION)
        assert morale == 5, f"a zero was read as fifty: {morale}"
        assert fleet == 5, fleet


class TestTheUnknownIsNamed:
    def test_an_unknown_event_config_is_refused(self):
        out = social.get_social_event_config("feast")
        assert "feast" in out.get("error", ""), out
        assert out["available"] == sorted(social.SOCIAL_EVENT_TYPES)

    def test_a_known_event_config_is_returned(self):
        assert social.get_social_event_config("trial") == social.SOCIAL_EVENT_TYPES["trial"]

    async def test_generate_social_event_refuses_an_unknown_type(self, scratch):
        try:
            out = await social.generate_social_event(SESSION, "feast")
            assert "feast" in out.get("error", ""), out
        finally:
            await _drop_events("feast")

    def test_an_unknown_morale_event_is_named_not_silent(self):
        out = social.apply_morale_event(50, "great_speech")
        assert out["applied"] is False, out
        assert "great_speech" in out["error"], out
        assert out["delta"] == 0
        assert out["new_morale"] == 50

    def test_a_known_morale_event_still_moves_morale(self):
        out = social.apply_morale_event(50, "good_speech")
        assert out["delta"] == 15
        assert out["new_morale"] == 65
        assert "applied" not in out


class TestTheMinimumAttendance:
    async def test_a_rally_gathers_its_minimum(self, scratch):
        """`config["min"]` was read into `needed` and dropped, so a rally of thirty gathered ten."""
        await _crew(35)
        try:
            out = await social.generate_social_event(SESSION, "rally")
            assert "error" not in out, out
            assert len(out["participants"]) >= social.SOCIAL_EVENT_TYPES["rally"]["min"], out["participants"]
        finally:
            await _drop_events("rally")
            await _drop_crew()

    async def test_a_banquet_still_keeps_its_own_shape(self, scratch):
        await _crew(12)
        try:
            out = await social.generate_social_event(SESSION, "banquet", ["Nethara"])
            assert out["participants"][0]["name"] == "Nethara"
            assert out["beats"][0]["type"] == "opening"
            assert out["beats"][-1]["type"] == "player_moment"
        finally:
            await _drop_events("banquet")
            await _drop_crew()
