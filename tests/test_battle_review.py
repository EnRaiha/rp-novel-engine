"""Battle module review tests — one per defect found reading modules/battle.py.

Defects covered:

1. `_make_enemy_fleet` read `faction_ships` with no session filter. That table
   carries both campaigns (8,223 hulls for session 3, 246 for session 5), so a
   live-arc battle was handed the frozen campaign's order of battle.
2. `_make_fleet` matched `ships.id` alone. Ids are unique across campaigns, so
   a stale id let a frozen-campaign hull fight in the live arc, and ids that
   matched nothing shrank the fleet without a word.
3. `_tactic_mult` returned 1.0 for any unknown tactic, so a typo silently
   fought at "Direct Assault" odds.
4. `set_formation` wrote nothing and returned None for a name outside
   fleet_formations, leaving the battle at its old formation in silence.
5. `attempt_retreat` persisted `pursuit_damage` as `dmg if success`, the
   inverse of the damage it returned to the caller.
6. `_resolve` read and updated `maya_rp.ships` by id with no session filter.
7. All three `EventBus.emit` payloads omitted session_id; EventBus falls back
   to session 3, so live-arc battle events were filed in the frozen campaign.
8. `resolve_intent` reported `player_remaining_ships` with a floor of 1, so a
   one-ship fleet that lost its ship was told it still had one.

Every test drives a fake Database or a pure helper: nothing writes to the
live campaign.
"""
import json

import pytest

from modules.battle import (BattleEngine, BattleFleet, BattleShip, BattleState,
                            _encounter_size, resolve_intent)


class FakeDB:
    def __init__(self, fetch=None, fetchrow=None, fetchval=None):
        self.fetch_rows = fetch if fetch is not None else []
        self.fetchrow_rows = fetchrow if fetchrow is not None else {}
        self.fetchval_value = fetchval
        self.calls = []

    async def fetch(self, sql, *args):
        self.calls.append(("fetch", " ".join(sql.split()), args))
        return self.fetch_rows

    async def fetchrow(self, sql, *args):
        self.calls.append(("fetchrow", " ".join(sql.split()), args))
        for key, value in self.fetchrow_rows.items():
            if key in sql:
                return value
        return None

    async def fetchval(self, sql, *args):
        self.calls.append(("fetchval", " ".join(sql.split()), args))
        return self.fetchval_value

    async def execute(self, sql, *args):
        self.calls.append(("execute", " ".join(sql.split()), args))
        return "UPDATE 1"

    def sql(self, kind=None):
        return [c[1] for c in self.calls if kind is None or c[0] == kind]

    def args_for(self, needle, kind=None):
        return [c[2] for c in self.calls
                if needle in c[1] and (kind is None or c[0] == kind)]


def _install(monkeypatch, fake):
    for name in ("fetch", "fetchrow", "fetchval", "execute"):
        monkeypatch.setattr("modules.battle.Database." + name, getattr(fake, name))
    return fake


def _ship(sid=1, hull=100, shield=50, speed=10, evasion=0.1, rating=100.0):
    return BattleShip(id=sid, name=f"Hull {sid}", ship_type="frigate", hull=hull,
                      shield=shield, speed=speed, evasion=evasion,
                      combat_rating=rating, role="line")


def _state(player_ships=None, enemy_ships=None, session_id=5, battle_id=11):
    return BattleState(battle_id=battle_id,
                       player=BattleFleet(faction="Setia Empire",
                                          ships=list([_ship()] if player_ships is None else player_ships)),
                       enemy=BattleFleet(faction="Corsairs",
                                         ships=list([_ship(2)] if enemy_ships is None else enemy_ships)),
                       terrain={}, session_id=session_id)


# ── 1 + 2. Session scope on both fleet builders ──────────────────────────

async def test_enemy_fleet_is_session_scoped(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[]))
    await BattleEngine._make_enemy_fleet("Corsairs", session_id=5)

    sql = [s for s in fake.sql("fetch") if "faction_ships" in s]
    assert len(sql) == 1
    assert "session_id=$2" in sql[0], sql[0]
    assert fake.args_for("faction_ships")[0][1] == 5


async def test_player_fleet_is_session_scoped(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetch=[]))
    await BattleEngine._make_fleet([1, 2], "Setia Empire", 5)

    sql = [s for s in fake.sql("fetch") if "FROM ships" in s]
    assert len(sql) == 1
    assert "s.session_id=$2" in sql[0], sql[0]
    assert fake.args_for("FROM ships")[0] == ([1, 2], 5)


async def test_player_fleet_names_the_ids_that_matched_nothing(monkeypatch):
    rows = [{"id": 1, "name": "Found", "ship_type": "frigate", "hull": 100,
             "hull_current": 100, "speed": 10, "power_rating": 10, "role": "line",
             "base_stats": None}]
    _install(monkeypatch, FakeDB(fetch=rows))
    seen = []
    monkeypatch.setattr("modules.battle.info", lambda mod, msg: seen.append(msg))

    fleet = await BattleEngine._make_fleet([1, 99], "Setia Empire", 5)

    assert [s.id for s in fleet.ships] == [1]
    assert any("99" in m for m in seen), seen


# ── 3. An unknown tactic is refused ──────────────────────────────────────

async def test_unknown_tactic_raises(monkeypatch):
    _install(monkeypatch, FakeDB(fetchrow={}))
    with pytest.raises(ValueError, match="Unknown tactic"):
        await BattleEngine._tactic_mult("Broadsides")


async def test_known_tactic_returns_catalogue_multiplier(monkeypatch):
    row = {"effect_multiplier": 0.5}
    _install(monkeypatch, FakeDB(fetchrow={"tactics_catalog": row}))
    assert await BattleEngine._tactic_mult("Disengage") == 0.5


# ── 4. set_formation reports what it did ─────────────────────────────────

async def test_unknown_formation_raises(monkeypatch):
    _install(monkeypatch, FakeDB(fetchrow={}))
    with pytest.raises(ValueError, match="Unknown formation"):
        await BattleEngine.set_formation(11, "Blob Formation")


async def test_formation_persists_catalogue_spelling(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchrow={"fleet_formations": {"name": "Wedge"}}))

    stored = await BattleEngine.set_formation(11, "wedge")

    assert stored == "Wedge"
    updates = fake.args_for("UPDATE combat_results SET player_formation", "execute")
    assert updates and updates[0] == ("Wedge", 11)


# ── 5. Pursuit damage lands on a FAILED retreat ──────────────────────────

@pytest.mark.parametrize("roll,expected_success", [(0.0, True), (1.0, False)])
async def test_retreat_persists_the_damage_it_reports(monkeypatch, roll, expected_success):
    fake = _install(monkeypatch, FakeDB())
    monkeypatch.setattr(BattleEngine, "_load_state",
                        classmethod(lambda cls, bid: _await(_state())))
    monkeypatch.setattr("modules.battle.random.random", lambda: roll)
    monkeypatch.setattr("modules.battle.random.randint", lambda a, b: 20)

    res = await BattleEngine.attempt_retreat(11)

    assert res["success"] is expected_success
    persisted = fake.args_for("retreat_successful", "execute")[0]
    assert persisted[0] is expected_success
    assert persisted[1] == res["damage"]
    if expected_success:
        assert res["damage"] == 0        # escape costs nothing in pursuit
    else:
        assert res["damage"] > 0         # the failure is what the pursuit charges


async def _await(value):
    return value


# ── 6 + 7. _resolve: session-scoped hull writes, session-tagged events ───

async def test_resolve_scopes_every_ship_write_by_session(monkeypatch):
    # Near-death survivor row: hull_current 5/100 trips the scar branch too, so
    # all three ship statements run and each one has to carry the session.
    survivor = {"name": "Hull 7", "veteran_kills": 0, "hull": 100, "hull_current": 5,
                "scars_jsonb": [], "ship_rank": "Standard"}
    fake = _install(monkeypatch, FakeDB(fetchrow={"maya_rp.ships": survivor}))
    state = _state(player_ships=[_ship(7)], enemy_ships=[], session_id=5)

    await BattleEngine._resolve(state)

    ship_sql = [s for s in fake.sql() if "maya_rp.ships" in s]
    assert len(ship_sql) == 3, ship_sql      # honors, survivor lookup, scar
    for sql in ship_sql:
        assert "session_id" in sql, sql
    assert fake.args_for("battle_honors", "execute")[0] == (5, [7])
    assert fake.args_for("scars_jsonb", "execute")[0][2] == 5


class RecordingBus:
    def __init__(self):
        self.events = []

    async def __call__(self, name, payload):
        self.events.append((name, payload))


async def test_resolve_emits_the_session_with_the_event(monkeypatch):
    _install(monkeypatch, FakeDB(fetchrow={"maya_rp.ships": None}))
    bus = RecordingBus()
    monkeypatch.setattr("modules.battle.EventBus.emit", bus)

    await BattleEngine._resolve(_state(enemy_ships=[], session_id=5))

    assert bus.events, "battle_completed was not emitted"
    name, payload = bus.events[0]
    assert name == "battle_completed"
    assert payload["session_id"] == 5


# ── 8. remaining ships is a count, not a floor ───────────────────────────

async def test_single_ship_fleet_reports_zero_remaining(monkeypatch):
    fake = _install(monkeypatch, FakeDB(fetchval=1))

    async def debuffs(session_id):
        return {"battle_penalty": 0, "debuff": None, "note": ""}

    monkeypatch.setattr("core.campaign.debuff_effects", debuffs)
    rolls = iter([0, 1, 300])                      # enemy 0 · lost 1 · damage
    monkeypatch.setattr("modules.battle.random.randint", lambda a, b: next(rolls))

    out = await resolve_intent(5, "attack", "the raider")

    assert out["ships_lost"] == 1
    assert out["player_remaining_ships"] == 0, "one ship lost of one is none remaining"
    lost = fake.args_for("SET status='lost'", "execute")
    assert lost and lost[0] == (5, 1)


# ── Module contract ──────────────────────────────────────────────────────

async def test_contract_shield_absorbs_sixty_percent_before_hull():
    ship = _ship(hull=100, shield=60)
    state = _state(player_ships=[ship], enemy_ships=[_ship(2)])

    await BattleEngine._apply_damage(state, 0, 100)

    assert ship.shield == 0 and ship.hull == 60   # 60 to shield, 40 to hull
    assert [s.id for s in state.player.ships] == [1]


async def test_contract_dead_hull_leaves_the_fleet():
    state = _state(player_ships=[_ship(hull=10, shield=0)], enemy_ships=[_ship(2)])
    await BattleEngine._apply_damage(state, 0, 999)
    assert state.player.ships == []


@pytest.mark.parametrize("player,enemy,expected", [
    (True, False, "player_victory"),
    (False, True, "player_defeat"),
    (False, False, "stalemate"),
])
async def test_contract_outcome_names_follow_the_surviving_fleets(monkeypatch, player, enemy, expected):
    fake = _install(monkeypatch, FakeDB(fetchrow={"maya_rp.ships": None}))
    state = _state(player_ships=[_ship()] if player else [],
                   enemy_ships=[_ship(2)] if enemy else [])

    await BattleEngine._resolve(state)

    written = fake.args_for("SET outcome=$1", "execute")
    assert written and written[0][0] == expected


@pytest.mark.parametrize("power,expected", [
    (0, "skirmish"), (9_999, "skirmish"), (10_000, "engagement"),
    (99_999, "engagement"), (100_000, "battle"), (999_999, "battle"),
    (1_000_000, "fleet_action"), (9_999_999, "fleet_action"), (10_000_000, "armada"),
])
def test_contract_encounter_size_boundaries(power, expected):
    assert _encounter_size(power) == expected


def test_contract_snapshot_round_trips_a_fleet_field_for_field():
    state = _state(player_ships=[_ship(3, hull=42, shield=7)])
    snap = json.loads(json.dumps(BattleEngine._snapshot(state)))
    restored = BattleShip(**snap["player"]["ships"][0])
    assert restored == state.player.ships[0]
