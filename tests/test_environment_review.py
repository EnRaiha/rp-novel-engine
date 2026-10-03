"""Environment module review tests — one per defect found reading modules/environment.py.

Defects covered:

1. `generate_details` read the crew average with `... or 50`. The COALESCE already handled a session
   with no crew rows, so the `or` only ever fired on a real zero: a crew at zero morale was described
   with a fifty-morale tell ("Routine. The ship runs like clockwork.") on the one ship where the
   mutiny tells were written for it.
2. `TELLS["death"]` was unreachable. The combat tell asked how many fights had ended in the last 72
   hours and nothing asked what those fights cost, so the memorial and the empty seat could not be
   shown for a fight that killed anyone. Session 3's two fights carry 163 and 66 crew casualties.

Not fixed, reported to the lead: `TELLS["prosperity"]` is still unreachable. Nothing in the live arc
measures material comfort — session 5 has no `resources` row, no colonies and no stockpiles — so
wiring it would mean inventing a threshold, which is a decision rather than a fix.

Every test drives a fake Database: nothing here writes to a campaign.
"""
from __future__ import annotations

import pytest

import modules.environment as environment  # noqa: E402


class FakeDB:
    """Answers the two reads `generate_details` makes, and nothing else."""

    def __init__(self, morale=None, fights=0, casualties=0):
        self.morale = morale
        self.fights = fights
        self.casualties = casualties
        self.calls = []

    async def fetchval(self, sql, *args):
        self.calls.append(("fetchval", " ".join(sql.split()), args))
        return self.morale

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", " ".join(sql.split()), args))
        if "combat_results" in sql:
            return {"fights": self.fights, "casualties": self.casualties}
        return None

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", " ".join(sql.split()), args))
        return []


MUTINY_TELLS = environment.TELLS["morale"][3][2]      # the 0..25 band
ROUTINE_TELLS = environment.TELLS["morale"][1][2]     # the 50..80 band
DEATH_TELLS = environment.TELLS["death"][0][2]
COMBAT_TELLS = environment.TELLS["combat"][0][2]


@pytest.fixture
def no_combat(monkeypatch):
    """A crew and no recent fight, so a detail list is the morale tell alone."""
    def make(morale):
        db = FakeDB(morale=morale)
        monkeypatch.setattr(environment, "Database", db)
        return db
    return make


class TestZeroMoraleIsNotFifty:
    async def test_a_crew_at_zero_reads_as_mutinous(self, no_combat):
        """`0.0 or 50` is 50, so the one band the mutiny tells were written for never matched."""
        no_combat(0)

        details = await environment.generate_details("rope_deck", 5)

        assert details, "no detail for a crew at zero morale"
        assert details[0] in MUTINY_TELLS, details
        assert details[0] not in ROUTINE_TELLS, details

    async def test_a_crew_at_zero_and_a_half_is_still_the_top_of_the_low_band(self, no_combat):
        no_combat(0.5)

        details = await environment.generate_details("rope_deck", 5)

        assert details[0] in MUTINY_TELLS, details

    async def test_a_missing_crew_average_is_still_fifty(self, no_combat):
        """The contract the COALESCE holds: a session with no crew is not a mutiny."""
        no_combat(None)

        details = await environment.generate_details("rope_deck", 5)

        assert details[0] in ROUTINE_TELLS, details

    async def test_a_healthy_crew_keeps_its_own_band(self, no_combat):
        no_combat(90)

        details = await environment.generate_details("rope_deck", 5)

        assert details[0] in environment.TELLS["morale"][0][2], details


class TestTheCostOfAFightIsShown:
    async def test_casualties_bring_the_death_tell(self, monkeypatch):
        monkeypatch.setattr(environment, "Database", FakeDB(morale=70, fights=1, casualties=66))

        details = await environment.generate_details("rope_deck", 3)

        assert any(d in DEATH_TELLS for d in details), details

    async def test_a_fight_that_cost_nothing_keeps_the_death_tell_away(self, monkeypatch):
        monkeypatch.setattr(environment, "Database", FakeDB(morale=70, fights=1, casualties=0))

        details = await environment.generate_details("rope_deck", 3)

        assert any(d in COMBAT_TELLS for d in details), details
        assert not any(d in DEATH_TELLS for d in details), details

    async def test_no_recent_fight_shows_neither_tell(self, monkeypatch):
        monkeypatch.setattr(environment, "Database", FakeDB(morale=70, fights=0, casualties=0))

        details = await environment.generate_details("rope_deck", 3)

        assert not any(d in COMBAT_TELLS for d in details), details
        assert not any(d in DEATH_TELLS for d in details), details


class TestTheTellsContract:
    async def test_a_known_location_still_contributes_its_own_line(self, monkeypatch):
        monkeypatch.setattr(environment, "Database", FakeDB(morale=70))

        details = await environment.generate_details("bridge", 3)

        assert any(d in environment.LOCATION_TELLS["bridge"] for d in details), details
        assert len(details) <= 4, details

    def test_weather_is_the_same_for_one_game_day_whatever_the_session(self):
        """The module's stated contract: weather is a function of the day, not of the campaign."""
        assert environment.current_weather(5, 3) == environment.current_weather(3, 3)
        assert environment.current_weather(5, 3)["weather"] == environment.WEATHER[3 % len(environment.WEATHER)]

    def test_every_morale_band_is_reachable_and_only_one_matches(self):
        """The four bands must cover 0..100 with no gap and no overlap, or a tell is unreachable."""
        for morale in list(range(0, 101)):
            hits = [i for i, (lo, hi, _) in enumerate(environment.TELLS["morale"]) if lo <= morale < hi]
            assert len(hits) == 1, (morale, hits)
