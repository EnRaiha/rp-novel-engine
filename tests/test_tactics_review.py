"""Tactics module review tests — one per defect found reading modules/tactics.py.

Defects covered:

1. `calculate_fleet_power` took `fleet_name` and never read it, so a caller asking for one fleet was
   answered with the whole campaign's order of battle. Session 3 holds 44,269 hulls and its largest
   named fleet 10,329; "Legion Silent Maw" holds 9.
2. The same function read a hull with `hull_current or hull`, so a hull at zero — a wreck — counted at
   its original hull value. Session 3 carries one: ship 1516, `TKG Phoenix Reborn`, hull 34250,
   hull_current 0, status destroyed.
3. `resolve_exchange` resolved an unknown weapon name as kinetic, so a typo fought at kinetic odds
   with nothing said. `BattleEngine._tactic_mult` refuses an unknown tactic; this now matches it.
4. `get_tactical_position` gave an unknown zone, terrain or formation a default multiplier in silence,
   the same answer for a typo as for a real value.

Pinned, not reconciled, and reported to the lead: the module holds two formation tables that do not
agree (`_FORMATIONS` for `formation_bonus`, which `battle.run_tick` applies, and the position
reader's own chain), and `MILITARY_OPS` has no caller anywhere in the repo. The pin test below states
the disagreement so the next reader sees it instead of rediscovering it; changing either side changes
numbers a campaign has already been shown, which is not a reviewer's call.

Everything here is read-only against the database: the fleet test reads session 3 and writes nothing.
"""
from __future__ import annotations

import pytest

from core.db import Database  # noqa: E402
import modules.tactics as tactics  # noqa: E402


class FakeDB:
    """One ships query and nothing else, so a hull's contribution can be isolated."""

    def __init__(self, ships):
        self.ships = ships

    async def fetch(self, sql, *args):
        return self.ships

    async def fetchrow(self, sql, *args):
        return None


DESTROYED_HULL = {"tier": 1, "hull": 34250, "hull_current": 0, "speed": 10}


class TestTheFleetPowerReader:
    async def test_a_wreck_counts_as_the_wreck_it_is(self, monkeypatch):
        """`hull_current or hull` read the real zero as missing and restored 34250 hulls."""
        monkeypatch.setattr(tactics, "Database", FakeDB([DESTROYED_HULL]))

        out = await tactics.calculate_fleet_power(3)

        assert out["ship_count"] == 1, out
        assert out["fleet_power"] == 10, out

    async def test_an_intact_hull_still_counts_at_its_hull(self, monkeypatch):
        monkeypatch.setattr(tactics, "Database",
                            FakeDB([{"tier": 1, "hull": 34250, "hull_current": 34250, "speed": 10}]))

        out = await tactics.calculate_fleet_power(3)

        assert out["fleet_power"] == 10 + 3425, out

    async def test_a_named_fleet_is_read_through_its_own_members(self):
        """Read-only: the named fleet is compared against the campaign it sits in."""
        await Database.init()
        try:
            expected = await Database.fetchval(
                "SELECT COUNT(*) FROM maya_rp.fleet_members fm"
                " JOIN maya_rp.ships s ON s.id=fm.ship_id"
                " WHERE fm.fleet_id=(SELECT id FROM maya_rp.fleets"
                "                    WHERE session_id=3 AND name='Legion Silent Maw')")
            named = await tactics.calculate_fleet_power(3, "Legion Silent Maw")
            whole = await tactics.calculate_fleet_power(3)
        finally:
            await Database.close()

        assert expected, "the fleet has no members to compare against"
        assert named["ship_count"] == expected, (named, expected)
        assert named["fleet_power"] < whole["fleet_power"], (named, whole)
        assert named["ship_count"] < whole["ship_count"], (named, whole)

    async def test_an_unknown_fleet_name_raises_rather_than_answering_with_everything(self):
        await Database.init()
        try:
            with pytest.raises(ValueError) as exc:
                await tactics.calculate_fleet_power(3, "No Such Fleet")
        finally:
            await Database.close()

        assert "No Such Fleet" in str(exc.value), exc.value


class TestTheExchange:
    async def test_a_typo_in_the_weapon_is_refused(self):
        with pytest.raises(ValueError) as exc:
            await tactics.resolve_exchange(200, 5, 20, 1, "banana", None)

        assert "banana" in str(exc.value), exc.value
        assert "kinetic" in str(exc.value), exc.value

    async def test_none_still_means_kinetic_because_the_cli_passes_none(self):
        out = await tactics.resolve_exchange(200, 5, 20, 1, None, None)

        assert out["weapon"] == "kinetic", out

    async def test_a_known_weapon_keeps_its_multiplier(self):
        kinetic = await tactics.resolve_exchange(200, 5, 20, 1, "kinetic", None)
        explosive = await tactics.resolve_exchange(200, 5, 20, 1, "explosive", None)

        assert explosive["damage"] == round(kinetic["damage"] * 1.3), (kinetic, explosive)

    async def test_an_unknown_targeting_system_is_refused(self):
        with pytest.raises(ValueError) as exc:
            await tactics.resolve_exchange(200, 5, 20, 1, "kinetic", "hull")

        assert "hull" in str(exc.value), exc.value

    async def test_a_known_targeting_system_is_echoed_back(self):
        out = await tactics.resolve_exchange(200, 5, 20, 1, "kinetic", "shields")

        assert out["targeting_system"] == "shields", out


class TestThePositionReader:
    async def test_an_unknown_zone_is_named_in_the_answer(self):
        out = await tactics.get_tactical_position(5, "flank", None, None)

        assert "warnings" in out, out
        assert "flank" in out["warnings"][0], out

    async def test_the_warning_does_not_move_the_number_it_reports(self):
        """The unrecognised zone keeps the multiplier it always had; only the silence is gone."""
        out = await tactics.get_tactical_position(5, "flank", None, None)

        assert out["effective_power"] == round(0.8 * 0.8 * 0.9, 2), out

    async def test_recognised_inputs_are_not_warned_about(self):
        out = await tactics.get_tactical_position(5, "aft", "asteroid_field", "wedge")

        assert "warnings" not in out, out
        assert out["effective_power"] == 1.0, out

    async def test_none_is_not_a_typo(self):
        """The CLI passes None for terrain and formation; that stays the module's default."""
        out = await tactics.get_tactical_position(5, "forward", None, None)

        assert "warnings" not in out, out


class TestTheFormationTablesArePinned:
    def test_two_formation_tables_disagree_and_stay_that_way_until_a_ruling(self):
        """`formation_bonus` is what battle applies; the position reader has its own chain.

        Wedge is 1.15 in one and 1.0 in the other, and spearhead — the position reader's default — is
        not in `_FORMATIONS` at all, while `FORMATIONS` advertises it. Reconciling them changes numbers
        the CLI has already shown a campaign, so this test states the disagreement rather than
        resolving it.
        """
        assert tactics.formation_bonus("wedge") == 1.15
        assert "spearhead" in tactics.FORMATIONS
        assert "spearhead" not in tactics._FORMATIONS
        assert tactics.formation_bonus("spearhead") == 1.0

    def test_the_battle_tick_still_gets_a_multiplier_and_a_terrain(self):
        """battle.run_tick imports both of these synchronously; neither may become a coroutine."""
        import inspect

        assert not inspect.iscoroutinefunction(tactics.formation_bonus)
        assert not inspect.iscoroutinefunction(tactics.roll_terrain)
        assert "player_mod" in tactics.roll_terrain()
