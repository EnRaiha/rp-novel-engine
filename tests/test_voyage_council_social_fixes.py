"""Voyage, council and social fixes: one test per defect, each red against the previous modules.

Every test runs in a scratch session (900-999, see `conftest.scratch_session`). Sessions 3 and 5 are
never read or written. The `sid` fixture creates the `sessions` row and removes every row the test
made, in a `finally`, so a red test leaves nothing behind.

Defects covered:

* F1  every writer wrote into a frozen session, and fell back to the import-time `Config.SESSION_ID`.
* F2  `issue_decree` refused every decree: `laid_back` ministers, and decree types matched by substring.
* F3  `voyage.advance` marked all due voyages arrived, then resolved them in autocommit; one raise
      stranded the rest as `arrived` with no effects.
* F4  `voyage.register` charged the gate toll before an INSERT that a duplicate then failed.
* F5  `thwart_plot` re-activated a thwarted plot on a failed roll.
* F6  `update_morale` wrote absolute values from a stale read, so concurrent deltas were lost.
* F7  `calculate_loyalty` raised TypeError on a NULL morale.
* F8  `advance` dropped `loss_ships` for a slip or a bribe, and booked `reward_credits` it never paid.
* F9  `compute_travel` booked an arbitrary lane when the destination did not resolve.
* F11 `scan_for_plots` detected less at quality 1 than at quality 0.
* F12 unescaped `ILIKE` (`%` matched every row) and `stability or 0.5` reading a real 0 as missing.
* Small: `shift_bond` stored an unclamped first bond, and the companion beat carried the wrong speaker.
"""
from __future__ import annotations

import asyncio
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

from core import ooc  # noqa: E402
from core.db import Database  # noqa: E402
from modules import council, social, voyage  # noqa: E402

#: Children first: foreign keys run from these tables to `sectors`, `characters`, `cabinet_hierarchy`.
_TABLES = (
    "cabinet_decrees", "cabinet_hierarchy", "character_relationships", "characters", "conspiracies",
    "crew_roster", "events", "intel_network", "morale_history", "resources", "social_events",
    "territory", "voyages", "wormholes", "black_holes", "sector_connections", "sectors",
)

GATE = {"name": "Fix Gate", "distance": 10.0, "travel_time_hours": 24.0, "hidden": False,
        "lane_type": "gate", "toll_credits": 25000, "pirate_density": 0.05}


async def _wipe(session_id: int) -> None:
    for table in _TABLES:
        try:
            await Database.execute(f"DELETE FROM maya_rp.{table} WHERE session_id = $1", session_id)
        except Exception as e:  # noqa: BLE001 - report, never mask the test's own failure
            print(f"could not clear {table}: {e!r}")
    try:
        await Database.execute("DELETE FROM maya_rp.sessions WHERE id = $1", session_id)
    except Exception as e:  # noqa: BLE001
        print(f"could not remove session {session_id}: {e!r}")


@pytest_asyncio.fixture
async def sid(scratch_session):
    """A scratch session with a `sessions` row at game day 10; every row of it is removed after."""
    assert 900 <= scratch_session <= 999, scratch_session
    await Database.init()
    await _wipe(scratch_session)
    await Database.execute(
        "INSERT INTO maya_rp.sessions (id, name, status, game_day)"
        " VALUES ($1, 'voyage council social fixes', 'active', 10)", scratch_session)
    try:
        yield scratch_session
    finally:
        await _wipe(scratch_session)
        await Database.close()


@pytest.fixture
def frozen(monkeypatch):
    """Make `core.ooc._refuse_frozen` refuse, with maintenance off, for any session."""
    monkeypatch.setattr("core.session.is_frozen", lambda _sid: True)
    monkeypatch.setattr(ooc, "_maintenance_active", lambda: False)


async def _insert(table: str, **cols) -> int:
    keys = ", ".join(cols)
    marks = ", ".join(f"${i + 1}" for i in range(len(cols)))
    return await Database.fetchval(
        f"INSERT INTO maya_rp.{table} ({keys}) VALUES ({marks}) RETURNING id", *cols.values())


async def _voyage(sid: int, name: str, **over) -> int:
    cols = {"session_id": sid, "voyage_name": name, "origin": "A", "destination": "B",
            "depart_day": 1, "arrive_day": 5, "status": "in_transit", "ship_count": 10,
            "lane_type": "gate"}
    cols.update(over)
    return await _insert("voyages", **cols)


async def _sector(sid: int, name: str, x: int = 0, y: int = 0) -> int:
    return await _insert("sectors", session_id=sid, name=name, x_coord=x, y_coord=y)


async def _credits(sid: int):
    return await Database.fetchval("SELECT credits FROM maya_rp.resources WHERE session_id=$1", sid)


async def _cabinet(sid: int) -> dict[str, int]:
    """A Consul plus one `laid_back` minister per portfolio a decree type routes to."""
    seats = [("Grand Consul", 0, "sovereign", "executing"),
             ("Military Minister", 2, "defense", "laid_back"),
             ("Diplomacy Minister", 2, "diplomacy", "laid_back"),
             ("Finance Minister", 2, "economy", "laid_back"),
             ("Intel Lead", 2, "intel", "laid_back"),
             ("Education Minister", 2, "education", "laid_back")]
    return {title: await _insert(
        "cabinet_hierarchy", session_id=sid, tier=tier, title=title, portfolio=portfolio,
        holder=f"Holder of {title}", is_wife=tier > 0, wife_mode=mode)
        for title, tier, portfolio, mode in seats}


async def _footprint(sid: int) -> dict[str, tuple]:
    """Row count and content digest of every table a writer here can touch."""
    out = {}
    for table in _TABLES:
        out[table] = tuple(await Database.fetchrow(
            f"SELECT count(*), md5(coalesce(string_agg(t::text, '|' ORDER BY t::text), ''))"
            f" FROM maya_rp.{table} t WHERE session_id = $1", sid))
    return out


async def _seed_everything(sid: int) -> None:
    """Rows every writer below would change if the frozen guard let it through."""
    await Database.execute("INSERT INTO maya_rp.resources (session_id, credits) VALUES ($1, 100000)", sid)
    entry, exit_ = await _sector(sid, "Seed Entry"), await _sector(sid, "Seed Exit", 5, 5)
    await _insert("wormholes", session_id=sid, name="Seed Hole", entry_sector_id=entry,
                  exit_sector_id=exit_, stability=0.5, status="decaying")
    await _voyage(sid, "Seed Due")
    for i in range(3):
        await _insert("crew_roster", session_id=sid, name=f"seed hand {i}", morale=60,
                      loyalty_flag="neutral")
    await _insert("conspiracies", session_id=sid, plot_type="sabotage", target="seed",
                  current_phase="0", difficulty=5, status="active")
    await Database.execute(
        "INSERT INTO maya_rp.territory (id, session_id, system_name, controlling_faction,"
        " governor_name, revocation_risk, title_performance, crisis_level, development_level)"
        " VALUES ((SELECT COALESCE(MAX(id), 0) + 1 FROM maya_rp.territory), $1, 'Seed System',"
        " 'Federation', 'Seed Governor', 0, 0, 0, 1)", sid)
    await _cabinet(sid)


# ── F1: frozen sessions ────────────────────────────────────────────────

_FROZEN_CALLS = {
    "voyage.register": lambda s: voyage.register("Frozen Run", distance_units=48, depart_day=10,
                                                 session_id=s),
    "voyage.advance": lambda s: voyage.advance(s),
    "voyage.wormhole_decay": lambda s: voyage.wormhole_decay(s),
    "voyage.run_tick": lambda s: voyage.run_tick(s),
    "council.issue_decree": lambda s: council.issue_decree(s, "military"),
    "council.thwart_plot": lambda s: council.thwart_plot(1, "arrest_asset", s),
    "council.assign_agent": lambda s: council.assign_agent(s, 1, "watcher"),
    "council.check_title_revocation": lambda s: council.check_title_revocation(s),
    "council.revoke_title": lambda s: council.revoke_title(s, "Seed System", "frozen"),
    "council.run_tick": lambda s: council.run_tick(s),
    "social.shift_bond": lambda s: social.shift_bond(s, 1, 2, 5),
    "social.update_morale": lambda s: social.update_morale(s, -10, "frozen"),
    "social.test_crew_loyalty": lambda s: social.test_crew_loyalty(s),
    "social.calculate_mutiny_risk": lambda s: social.calculate_mutiny_risk(s),
    "social.generate_social_event": lambda s: social.generate_social_event(s, "banquet"),
    "social.run_tick": lambda s: social.run_tick(s),
}


class TestFrozenSessionsRefuseWrites:
    @pytest.mark.parametrize("name", sorted(_FROZEN_CALLS))
    async def test_a_writer_refuses_a_frozen_session_and_writes_nothing(self, name, sid, frozen):
        """Before the fix each writer ran against a frozen session: tolls, losses, decrees, bonds and
        morale landed in reference data. The guard is `core.ooc._refuse_frozen` on the resolved id."""
        await _seed_everything(sid)
        before = await _footprint(sid)
        with pytest.raises(ooc.FrozenSession):
            await _FROZEN_CALLS[name](sid)
        assert await _footprint(sid) == before, f"{name} wrote into a frozen session"


class TestNoImportTimeSession:
    def test_the_three_modules_no_longer_read_config_session_id(self):
        """`Config.SESSION_ID` is fixed at import, so a long-lived tick wrote to a stale session."""
        for module in (voyage, council, social):
            source = pathlib.Path(module.__file__).read_text()
            assert "Config.SESSION_ID" not in source.replace("`Config.SESSION_ID`", ""), (
                f"{module.__name__} still falls back to Config.SESSION_ID")


# ── F2: consul decrees ─────────────────────────────────────────────────

_DECREES = [("military", "defense"), ("diplomatic", "diplomacy"), ("economic", "economy"),
            ("covert", "intel"), ("social", "education"), ("education", "education"),
            ("emergency", "defense"), ("directive", "intel")]


class TestConsulDecrees:
    @pytest.mark.parametrize("decree_type,portfolio", _DECREES)
    async def test_a_consul_decree_reaches_a_laid_back_minister(self, decree_type, portfolio, sid):
        """`can_do(minister, decree_type)` ran without `consumer_decree`, so every `laid_back` minister
        (the column default) refused, and `military`, `economic`, `social`, `education`, `emergency`
        and `directive` matched no action word of their portfolio."""
        await _cabinet(sid)
        out = await council.issue_decree(sid, decree_type)
        assert out.get("issued") is True, out
        minister = await Database.fetchval(
            "SELECT h.portfolio FROM maya_rp.cabinet_decrees d"
            " JOIN maya_rp.cabinet_hierarchy h ON h.id = d.delegated_to"
            " WHERE d.session_id = $1 AND d.decree_type = $2", sid, decree_type)
        assert minister == portfolio, f"{decree_type} went to {minister}, not {portfolio}"

    async def test_an_unknown_decree_type_is_refused_by_name(self, sid):
        """The table CHECK lists eight types; `tax` used to fall through to a generic refusal."""
        await _cabinet(sid)
        out = await council.issue_decree(sid, "tax")
        assert out.get("issued") is False, out
        assert "tax" in out.get("reason", ""), out
        assert out.get("available") == sorted(council.DECREE_TO_PORTFOLIO), out

    async def test_the_portfolio_rules_still_gate_a_non_consul_action(self):
        """Guard, green before and after: only a Consul decree skips the laid-back and portfolio gate."""
        minister = {"active": True, "tier": 2, "portfolio": "defense", "holder": "M",
                    "wife_mode": "laid_back", "max_fleet_power": 0}
        assert council.can_do(minister, "deploy")["allowed"] is False
        minister = dict(minister, wife_mode="executing")
        assert council.can_do(minister, "scout")["allowed"] is False
        assert council.can_do(minister, "deploy")["allowed"] is True


# ── F3 + F8: advance ───────────────────────────────────────────────────

class TestAdvanceIsolatesFailures:
    async def test_a_raising_voyage_stays_in_transit_and_the_others_resolve(self, sid):
        """`advance` marked all due voyages `arrived` in one statement, then resolved each in
        autocommit. A slingshot to a missing black hole raised on voyage 2 and left it, and every
        voyage after it, `arrived` with no event."""
        good_a = await _voyage(sid, "Good Alpha")
        bad = await _voyage(sid, "Bad Slingshot", transit_kind="slingshot", transit_name="No Such Maw")
        good_c = await _voyage(sid, "Good Gamma")

        out = await voyage.advance(sid)

        status = {r["id"]: r["status"] for r in await Database.fetch(
            "SELECT id, status FROM maya_rp.voyages WHERE session_id = $1", sid)}
        assert status[bad] == "in_transit", f"the raising voyage is {status[bad]}"
        assert status[good_a] == "arrived" and status[good_c] == "arrived", status
        assert sorted(out["arrived"]) == ["Good Alpha", "Good Gamma"], out
        assert [f["voyage"] for f in out["failed"]] == ["Bad Slingshot"], out
        events = await Database.fetchval(
            "SELECT count(*) FROM maya_rp.events WHERE session_id = $1 AND event_type = 'arrival'", sid)
        assert events == 2, f"{events} arrival events for two resolved voyages"


class TestLossAndRewardAreBooked:
    async def test_a_slip_that_costs_ships_persists_the_loss(self, sid, monkeypatch):
        """The event narrated `lost` hulls for a slipped run, but `loss_ships` was written only when
        the run was chased, so the row said nothing was lost."""
        vid = await _voyage(sid, "Slipping Run", via_hidden=True, lane_type="hidden_thread", act="sneak",
                            guide="g", prep_level=2, equip_level=2, knowledge_level=2, danger_pct=90,
                            ship_count=100)
        monkeypatch.setattr(voyage.random, "randint", lambda a, b: 10)       # 10 <= 90: detected
        monkeypatch.setattr(voyage.random, "uniform", lambda a, b: 0.05)     # escape band top: 5 of 100

        await voyage.advance(sid)

        row = await Database.fetchrow(
            "SELECT loss_ships, interdicted FROM maya_rp.voyages WHERE id = $1", vid)
        assert row["loss_ships"] == 5, f"loss_ships is {row['loss_ships']} after a 5-hull slip"
        assert row["interdicted"] is False, "a slipped run is not interdicted"

    async def test_reward_credits_stay_zero_when_the_treasury_row_is_missing(self, sid, monkeypatch):
        """The profit was written to `reward_credits` even when no resources row took the credit."""
        vid = await _voyage(sid, "Unpaid Run", via_hidden=True, lane_type="hidden_thread",
                            act="sneak", cargo_value=1000, danger_pct=50)
        monkeypatch.setattr(voyage.random, "randint", lambda a, b: 99)       # 99 > 50: clean
        monkeypatch.setattr(voyage.random, "uniform", lambda a, b: 0.30)     # margin 0.40

        out = await voyage.advance(sid)

        assert out["unbooked_credits"] == 400, out
        reward = await Database.fetchval("SELECT reward_credits FROM maya_rp.voyages WHERE id = $1", vid)
        assert reward == 0, f"reward_credits {reward} was booked but never credited"


# ── F4: register ───────────────────────────────────────────────────────

class TestRegisterToll:
    async def _gate(self, z1, z2, session_id=None):
        return dict(GATE)

    async def test_a_duplicate_registration_does_not_charge_the_toll(self, sid, monkeypatch):
        """The toll was debited first and the INSERT second. The second identical voyage hit the
        unique index after the debit, and the credits were gone with no voyage."""
        monkeypatch.setattr(voyage, "gate_crossing", self._gate)
        await Database.execute("INSERT INTO maya_rp.resources (session_id, credits) VALUES ($1, 100000)", sid)
        first = await voyage.register("Dup Run", "20,250,3", "25,12,2", ship_count=2,
                                      depart_day=10, session_id=sid)
        assert first["toll_paid"] == 5000 and await _credits(sid) == 95000

        with pytest.raises(ValueError, match="already registered"):
            await voyage.register("Dup Run", "20,250,3", "25,12,2", ship_count=2,
                                  depart_day=10, session_id=sid)

        assert await _credits(sid) == 95000, "the duplicate was charged"

    async def test_a_toll_above_the_treasury_is_refused_and_credits_stay_non_negative(self, sid, monkeypatch):
        """The debit had no `credits >= toll` guard, so a poor treasury went negative."""
        monkeypatch.setattr(voyage, "gate_crossing", self._gate)
        await Database.execute("INSERT INTO maya_rp.resources (session_id, credits) VALUES ($1, 100)", sid)
        with pytest.raises(ValueError, match="fewer than"):
            await voyage.register("Poor Run", "20,250,3", "25,12,2", ship_count=2,
                                  depart_day=10, session_id=sid)
        assert await _credits(sid) == 100
        assert await Database.fetchval(
            "SELECT count(*) FROM maya_rp.voyages WHERE session_id = $1", sid) == 0


# ── F5: thwart ─────────────────────────────────────────────────────────

class TestThwartedStaysThwarted:
    async def test_a_failed_roll_does_not_reactivate_a_thwarted_plot(self, sid, monkeypatch):
        """The update wrote `status = 'active'` on a failed roll with no status guard, so a second
        attempt on a thwarted plot put it back in play."""
        cid = await _insert("conspiracies", session_id=sid, plot_type="sabotage", target="t",
                            current_phase="0", difficulty=5, status="thwarted")
        monkeypatch.setattr(council.random, "random", lambda: 0.99)           # fails every method

        out = await council.thwart_plot(cid, "arrest_asset", session_id=sid)

        status = await Database.fetchval("SELECT status FROM maya_rp.conspiracies WHERE id = $1", cid)
        assert status == "thwarted", f"the plot is {status} after a failed re-thwart"
        assert out["success"] is False and "not active" in out["error"], out


# ── F6 + F7: morale ────────────────────────────────────────────────────

class TestMorale:
    async def test_concurrent_morale_deltas_both_land(self, sid):
        """`update_morale` read each morale, computed an absolute value and wrote it back. Three
        concurrent +5 calls each read 50 and wrote 55, so two deltas vanished."""
        for i in range(10):
            await _insert("crew_roster", session_id=sid, name=f"race hand {i}", morale=50)

        await asyncio.gather(*(social.update_morale(sid, 5, f"race {i}") for i in range(3)))

        values = {r["morale"] for r in await Database.fetch(
            "SELECT morale FROM maya_rp.crew_roster WHERE session_id = $1", sid)}
        assert values == {65}, f"morale after three +5 deltas: {values}"
        history = await Database.fetchval(
            "SELECT count(*) FROM maya_rp.morale_history WHERE session_id = $1", sid)
        assert history == 3, f"{history} history rows for three updates"

    async def test_a_null_morale_does_not_abort_the_loyalty_test(self, sid):
        """`crew_roster.morale` is nullable; `None - 50` raised TypeError and killed the tick."""
        await _insert("crew_roster", session_id=sid, name="null morale hand", morale=None,
                      loyalty_flag="neutral")
        assert 0.0 <= social.calculate_loyalty({"morale": None, "loyalty_flag": "neutral"}) <= 1.0

        results = await social.test_crew_loyalty(sid)

        assert [r["name"] for r in results] == ["null morale hand"], results


# ── F9: travel ─────────────────────────────────────────────────────────

class TestUnresolvedDestination:
    async def test_a_destination_that_matches_no_sector_raises(self, sid):
        """With the origin resolved and the destination not, `compute_travel` returned the first lane
        touching the origin, so a typo booked an unrelated travel time."""
        origin, other = await _sector(sid, "Fix Origin"), await _sector(sid, "Fix Neighbour", 3, 4)
        await _insert("sector_connections", session_id=sid, from_sector_id=origin,
                      to_sector_id=other, distance=5.0, travel_time_hours=120.0)

        with pytest.raises(ValueError, match="Fix Nowhere"):
            await voyage.compute_travel("Fix Origin", "Fix Nowhere", session_id=sid)

        linked = await voyage.compute_travel("Fix Origin", "Fix Neighbour", session_id=sid)
        assert linked["mode"] == "link" and linked["travel_hours"] == 120.0, linked


# ── F11: detection ─────────────────────────────────────────────────────

class TestDetectionGrowsWithQuality:
    async def test_a_better_network_never_detects_fewer_plots(self, sid):
        """Quality 0 detected 10% of plots and quality 1 detected 0.3%, because the formula had a
        floor only for 0 and the roll digest moved with the quality."""
        await Database.execute(
            "INSERT INTO maya_rp.conspiracies (session_id, plot_type, target, current_phase, difficulty, status)"
            " SELECT $1, 'sabotage', 'scan ' || g, '0', 5, 'active' FROM generate_series(1, 80) g", sid)

        counts = [len(await council.scan_for_plots(sid, q)) for q in (0, 1, 5, 20, 60, 100)]

        assert counts == sorted(counts), f"detections by quality 0,1,5,20,60,100: {counts}"
        assert counts[-1] > counts[0], f"quality 100 detects no more than quality 0: {counts}"


# ── F12: LIKE escaping, zero stability ─────────────────────────────────

class TestWildcardsAreLiteral:
    async def _hole(self, sid, name, **over):
        entry, exit_ = await _sector(sid, f"{name} In"), await _sector(sid, f"{name} Out", 4, 3)
        return await _insert("wormholes", session_id=sid, name=name, entry_sector_id=entry,
                             exit_sector_id=exit_, **over)

    async def test_a_percent_or_underscore_name_does_not_match_every_wormhole(self, sid):
        """`ILIKE '%' || name || '%'` with name `%` matched the lowest-id hole in the session."""
        await self._hole(sid, "Ghost Gate")
        with pytest.raises(ValueError, match="No wormhole named"):
            await voyage.wormhole_jump("%", session_id=sid)
        with pytest.raises(ValueError, match="No wormhole named"):
            await voyage.wormhole_jump("G_ost", session_id=sid)
        assert (await voyage.wormhole_jump("ghost", session_id=sid))["name"] == "Ghost Gate"

    async def test_a_hole_at_stability_zero_collapses_instead_of_resetting(self, sid):
        """`float(stability or 0.5)` read a real 0 as missing: the hole climbed to 0.49 and never
        collapsed."""
        await self._hole(sid, "Dead Hole", stability=0, status="decaying")

        out = await voyage.wormhole_decay(sid)

        assert out["collapsed"] == ["Dead Hole"], out


# ── Small fixes ────────────────────────────────────────────────────────

class TestSocialSmallFixes:
    async def test_the_first_bond_is_clamped_to_the_range(self, sid):
        """The conflict branch clamped to -50..50, but the first insert stored the delta as given."""
        a = await _insert("characters", session_id=sid, name="bond a")
        b = await _insert("characters", session_id=sid, name="bond b")

        out = await social.shift_bond(sid, a, b, 80, "first shift")

        assert out is not None and out["bond"] == 50, out
        stored = await Database.fetchval(
            "SELECT score FROM maya_rp.character_relationships WHERE session_id = $1", sid)
        assert stored == 50, f"stored bond {stored}"

    async def test_the_companion_beat_carries_the_speaker_of_its_line(self, sid):
        """The loop left `c_name` on the last companion: with Nethara then Kai, Nethara's line was
        printed under Kai's name."""
        out = await social.generate_social_event(sid, "banquet", ["Nethara", "Kai"])

        beat = next(b for b in out["beats"] if b["type"] == "companion_weigh_in")
        assert beat["speaker"] == "Nethara", beat
        assert beat["line"] == "!This crew needs to see strength. Or compassion. Decide which.", beat
