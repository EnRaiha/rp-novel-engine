"""Battle Engine — terrain, tactics, formations, phases, commanders, aftermath.

Schema contract (migration 105): combat_results keeps the live battle row
(status/outcome/ended_at/player_formation/ship_states); battle_log_entries,
battle_phases and battle_aftermath hang off combat_results.id. `ships` carries
no combat_rating/evasion column — power_rating is the rated combat value and
evasion/multipliers come from ship_roles.base_stats.
"""
import random, json, asyncio
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from core.db import Database
from core.events import EventBus
from core.log import info
from core.utils import calc_game_days
from core.config import Config

PHASE_NAMES = ["Opening", "Complication", "Companion Moment", "Turning Point", "Finisher"]

@dataclass
class BattleShip:
    id: int; name: str; ship_type: str; hull: int; shield: int
    speed: int; evasion: float; combat_rating: float; role: str = "line"

@dataclass
class BattleFleet:
    faction: str; ships: List[BattleShip] = field(default_factory=list)
    commander: Optional[Dict] = None; formation: str = "Line"

@dataclass
class BattleState:
    battle_id: int; player: BattleFleet; enemy: BattleFleet
    terrain: Dict; phase: int = 1; turn: int = 0
    player_tactic: str = "Direct Assault"; enemy_tactic: str = "Direct Assault"
    log: list = field(default_factory=list)
    session_id: int = 0

class BattleEngine:
    @classmethod
    async def init(cls, session_id: int, player_ships: List[int],
                   enemy_faction: str, terrain_id: int = None) -> BattleState:
        """Initialize a new battle."""
        pf = await cls._make_fleet(player_ships, "Setia Empire")
        ef = await cls._make_enemy_fleet(enemy_faction)
        # One argument list per query: passing terrain_id into the "random()"
        # variant raised InterfaceError (server expects 0 arguments) every time
        # init() was called without an explicit terrain.
        if terrain_id:
            terrain = await Database.fetchrow("SELECT * FROM battle_terrain WHERE id=$1", terrain_id) or {}
        else:
            terrain = await Database.fetchrow("SELECT * FROM battle_terrain ORDER BY random() LIMIT 1") or {}
        terrain = dict(terrain)
        bid = await Database.fetchrow(
            "INSERT INTO combat_results (session_id, player_power, enemy_power, status) "
            "VALUES ($1,$2,$3,'active') RETURNING id",
            session_id, sum(s.combat_rating for s in pf.ships), sum(s.combat_rating for s in ef.ships))
        state = BattleState(battle_id=bid["id"], player=pf, enemy=ef, terrain=terrain,
                            session_id=session_id)
        await cls._save(state, None)
        await EventBus.emit("battle_started", {"battle_id": state.battle_id})
        return state

    @classmethod
    async def resolve_turn(cls, state: BattleState, tactic: str) -> BattleState:
        state.turn += 1; state.player_tactic = tactic
        state.enemy_tactic = await cls._ai_tactic(state)
        pm = await cls._tactic_mult(tactic); em = await cls._tactic_mult(state.enemy_tactic)
        pp = sum(s.combat_rating for s in state.player.ships) * pm
        ep = sum(s.combat_rating for s in state.enemy.ships) * em
        te = state.terrain.get("effects", {}) or {}
        if isinstance(te, str):   # asyncpg hands jsonb back as text
            te = json.loads(te)
        if "damage_bonus" in te: pp *= 1 + te["damage_bonus"]; ep *= 1 + te["damage_bonus"]
        ratio = pp / max(1, ep); wins = random.random() < ratio / (1 + ratio)
        dd = int((pp + ep) / 10 * random.uniform(0.7, 1.3))
        dt = int((pp + ep) / 10 * random.uniform(0.7, 1.3))
        dd, dt = (int(dd*1.5), int(dt*0.5)) if wins else (int(dd*0.5), int(dt*1.5))
        state = await cls._apply_damage(state, dd, dt)
        entry = {"turn": state.turn, "tactic": tactic, "enemy_tactic": state.enemy_tactic,
                 "won": wins, "damage_dealt": dd, "damage_taken": dt, "narrative": cls._narr(state, wins)}
        state.log.append(entry)
        await cls._save(state, entry)
        if not state.player.ships or not state.enemy.ships or state.turn >= 10:
            state = await cls._resolve(state)
        return state

    @classmethod
    async def _make_fleet(cls, ship_ids: List[int], faction: str) -> BattleFleet:
        if not ship_ids:
            return BattleFleet(faction=faction)
        rows = await Database.fetch(
            "SELECT s.*, sr.base_stats FROM ships s "
            "LEFT JOIN ship_roles sr ON LOWER(sr.name)=LOWER(s.role) "
            "WHERE s.id = ANY($1::int[])", ship_ids)
        return BattleFleet(faction=faction, ships=[cls._to_ship(r) for r in rows])

    @classmethod
    async def _make_enemy_fleet(cls, faction: str, limit: int = 60) -> BattleFleet:
        """Enemy order of battle comes from `faction_ships` — `ships` only holds
        Setia hulls, so an enemy built from it was always an empty fleet."""
        rows = await Database.fetch(
            "SELECT id, ship_name, ship_type, hull, speed, power_rating FROM maya_rp.faction_ships "
            "WHERE faction_name=$1 AND status='active' ORDER BY power_rating DESC LIMIT $2",
            faction, limit)
        if not rows:
            info("battle", f"Faction '{faction}' has no active hulls — empty order of battle")
        return BattleFleet(faction=faction, ships=[cls._to_ship(r) for r in rows])

    @staticmethod
    def _to_ship(row) -> BattleShip:
        """Map a `ships`/`faction_ships` row onto BattleShip."""
        bs = row.get("base_stats") or {}
        if isinstance(bs, str):
            bs = json.loads(bs)
        hull = int(row.get("hull") or 100)
        return BattleShip(
            id=row["id"], name=row.get("name") or row.get("ship_name") or "",
            ship_type=row.get("ship_type") or "",
            hull=int(hull * bs.get("hull_mult", 1)),
            shield=int((row.get("hull_current") or hull) * bs.get("shield_mult", 1)),
            speed=int((row.get("speed") or 10) * bs.get("speed_mult", 1)),
            evasion=float(bs.get("evasion", 0.1)),
            combat_rating=float(row.get("power_rating") or 0),
            role=row.get("role") or row.get("ship_type") or "line")

    @classmethod
    async def _tactic_mult(cls, tactic: str) -> float:
        r = await Database.fetchrow("SELECT effect_multiplier FROM tactics_catalog WHERE name=$1", tactic)
        return float(r["effect_multiplier"]) if r else 1.0

    @classmethod
    async def _ai_tactic(cls, state: BattleState) -> str:
        pp = sum(s.combat_rating for s in state.player.ships)
        ep = sum(s.combat_rating for s in state.enemy.ships)
        ratio = ep / max(1, pp)
        if ratio < 0.8: return random.choice(["Screen","Disengage","Feint","Hit-and-Run"])
        if ratio > 1.5: return random.choice(["Ambush","Flanking","Direct Assault","Pincer"])
        return random.choice(["Intercept","Pursuit","Blockade","Lay Trap"])

    @classmethod
    async def _apply_damage(cls, state: BattleState, dd: int, dt: int) -> BattleState:
        for fleet, dmg in [(state.enemy, dd), (state.player, dt)]:
            r = dmg
            for s in fleet.ships:
                if r <= 0: break
                hd = min(s.shield, int(r * 0.6)); s.shield -= hd; r -= hd
                if r > 0: hd = min(s.hull, r); s.hull -= hd; r -= hd
            fleet.ships = [s for s in fleet.ships if s.hull > 0]
        return state

    @classmethod
    async def _resolve(cls, state: BattleState) -> BattleState:
        pa, ea = bool(state.player.ships), bool(state.enemy.ships)
        outcome = "player_victory" if pa and not ea else "player_defeat" if not pa and ea else "stalemate"
        await Database.execute(
            "UPDATE combat_results SET outcome=$1, ended_at=NOW(), status='completed', "
            "player_power=$2, enemy_power=$3 WHERE id=$4",
            outcome, sum(s.combat_rating for s in state.player.ships),
            sum(s.combat_rating for s in state.enemy.ships), state.battle_id)
        loot = random.randint(1000, 50000) if outcome == "player_victory" else 0
        rep = 10 if outcome == "player_victory" else -10
        await Database.execute("INSERT INTO battle_aftermath (battle_id, loot_credits, reputation_change, narrative) VALUES ($1,$2,$3,$4)",
            state.battle_id, loot, rep, f"Battle resolved: {outcome}")
        # Novel adaptation — Ship Legacy (bab 7, 35): kapal veteran dapat battle_honors + legacy_score
        if outcome == "player_victory" and state.player.ships:
            ship_ids = [s.id for s in state.player.ships]
            await Database.execute(
                "UPDATE maya_rp.ships SET battle_honors=battle_honors+1, veteran_kills=veteran_kills+1, "
                "legacy_score=legacy_score+GREATEST(1, LEAST(10, power_rating/50000)) "
                "WHERE session_id=$1 AND id = ANY($2::int[])",
                state.session_id, ship_ids)
            # NOVEL ULTIMATE #5 — Rank naik + procedural scars untuk near-death survivor
            for ship_id in ship_ids:
                row = await Database.fetchrow(
                    "SELECT name, veteran_kills, hull, hull_current, scars_jsonb, ship_rank FROM maya_rp.ships WHERE id=$1",
                    ship_id)
                if not row:
                    continue
                kills = row["veteran_kills"] or 0
                rank = row["ship_rank"] or "Standard"
                new_rank = rank
                if kills >= 50:
                    new_rank = "Legendary"
                elif kills >= 10:
                    new_rank = "Veteran"
                if new_rank != rank:
                    await Database.execute(
                        "UPDATE maya_rp.ships SET ship_rank=$1 WHERE id=$2", new_rank, ship_id)
                    await Database.execute(
                        "INSERT INTO maya_rp.events (session_id, event_type, title, description, importance) "
                        "VALUES ($1, 'honor', $2, $3, 4)",
                        state.session_id, f"SHIP PROMOTED: {row['name']} → {new_rank}",
                        f"{row['name']} mencapai {kills} kills. Kini berpangkat {new_rank}.")
                # Procedural scar: survive dengan <15% hull = near-death experience
                hc = row["hull_current"] or row["hull"]
                hull = row["hull"] or 1
                if 0 < hc <= hull * 0.15:
                    scar = {"scar": "Critical Survivor",
                            "effect": "evasion +5%, max_hull -5%",
                            "story": f"Survived with {hc}/{hull} hull ({(hc/hull)*100:.0f}%)"}
                    await Database.execute(
                        "UPDATE maya_rp.ships SET scars_jsonb = scars_jsonb || $1::jsonb, "
                        "hull = GREATEST(1, hull * 0.95) WHERE id=$2",
                        json.dumps(scar), ship_id)
        await EventBus.emit("battle_completed", {"battle_id": state.battle_id, "outcome": outcome})
        return state

    @classmethod
    async def set_formation(cls, battle_id: int, formation: str):
        # fleet_formations is capitalised ('Wedge', 'Defensive Circle'); the
        # campaign tick hands out lowercase names, so match case-insensitively
        # and persist the catalogue's own spelling.
        r = await Database.fetchrow(
            "SELECT name FROM maya_rp.fleet_formations WHERE LOWER(name)=LOWER($1)", formation)
        if r:
            await Database.execute("UPDATE combat_results SET player_formation=$1 WHERE id=$2", r["name"], battle_id)

    @classmethod
    async def attempt_retreat(cls, battle_id: int) -> Dict:
        state = await cls._load_state(battle_id)
        if not state: return {"success": False, "error": "Not found"}
        spd = sum(s.speed for s in state.player.ships) / max(1, len(state.player.ships))
        eva = sum(s.evasion for s in state.player.ships) / max(1, len(state.player.ships))
        chance = max(0.1, min(0.95, 0.5 + (spd - 5) * 0.05 + eva * 0.5))
        success = random.random() < chance
        dmg = int(random.randint(0, 20) * (1 - chance))
        await Database.execute(
            "UPDATE combat_results SET retreat_attempted=true, retreat_successful=$1, "
            "pursuit_damage=$2, status='completed', ended_at=NOW(), "
            "outcome=COALESCE(outcome,'player_retreat') WHERE id=$3",
            success, dmg if success else 0, battle_id)
        await EventBus.emit("battle_retreated", {"battle_id": battle_id, "success": success})
        return {"success": success, "damage": dmg if not success else 0}

    @classmethod
    def _narr(cls, state: BattleState, wins: bool) -> str:
        pn = PHASE_NAMES[min(state.phase - 1, 4)]; state.phase += 1
        return f"{pn}: {'Player presses attack.' if wins else 'Enemy counterattacks.'} Using {state.player_tactic}."

    @classmethod
    async def _save(cls, state: BattleState, entry: Optional[Dict]):
        # Live hull/shield snapshot so a mid-battle reload (retreat, resume) can
        # rebuild the fleets instead of fighting with empty ones.
        await Database.execute(
            "UPDATE combat_results SET ship_states=$1 WHERE id=$2",
            json.dumps(cls._snapshot(state)), state.battle_id)
        if entry is None:
            return
        await Database.execute(
            "INSERT INTO battle_log_entries (battle_id, turn_number, actor, action, result, damage) VALUES ($1,$2,$3,$4,$5,$6)",
            state.battle_id, entry["turn"], "player" if entry["won"] else "enemy",
            entry["tactic"], entry["narrative"], entry["damage_dealt"])
        if state.turn % 3 == 0 and state.phase < 5:
            await Database.execute(
                "INSERT INTO battle_phases (battle_id, phase_number, phase_name, player_tactic, enemy_tactic, damage_dealt, damage_taken) VALUES ($1,$2,$3,$4,$5,$6,$7)",
                state.battle_id, state.phase, PHASE_NAMES[state.phase-1], entry["tactic"],
                entry["enemy_tactic"], entry["damage_dealt"], entry["damage_taken"])

    @staticmethod
    def _snapshot(state: BattleState) -> Dict:
        def ser(f: BattleFleet) -> Dict:
            return {"faction": f.faction, "formation": f.formation, "ships": [
                {"id": s.id, "name": s.name, "ship_type": s.ship_type, "hull": s.hull,
                 "shield": s.shield, "speed": s.speed, "evasion": s.evasion,
                 "combat_rating": s.combat_rating, "role": s.role} for s in f.ships]}
        return {"player": ser(state.player), "enemy": ser(state.enemy),
                "phase": state.phase, "turn": state.turn,
                "player_tactic": state.player_tactic, "enemy_tactic": state.enemy_tactic}

    @classmethod
    async def _load_state(cls, battle_id: int) -> Optional[BattleState]:
        row = await Database.fetchrow("SELECT * FROM combat_results WHERE id=$1", battle_id)
        if not row: return None
        snap = row.get("ship_states") or {}
        if isinstance(snap, str): snap = json.loads(snap)

        def fleet(key: str, default_faction: str) -> BattleFleet:
            d = snap.get(key) or {}
            f = BattleFleet(faction=d.get("faction") or default_faction,
                            ships=[BattleShip(**s) for s in (d.get("ships") or [])])
            f.formation = d.get("formation") or "Line"
            return f

        return BattleState(battle_id=battle_id, player=fleet("player", "player"),
                           enemy=fleet("enemy", "ai"), terrain={},
                           phase=snap.get("phase", 1), turn=snap.get("turn", 0),
                           session_id=row["session_id"])

async def run_tick(session_id: int = None):
    """Autonomous campaign engagement tick (added 2026-08-14).

    Previously a stub ("no active battles"). Now: wars in hot phases
    (clash/attrition/turning_point) generate engagements with
    formation/terrain bonuses, casualties flow to wars + combat_results,
    and named commanders can take injuries (character_injuries).
    Conservative: cold phases (escalation/mobilization) never fight here —
    war.advance() owns phase progression.
    """
    from core.log import info, error
    if session_id is None: session_id = Config.SESSION_ID
    try:
        from modules.tactics import formation_bonus, roll_terrain
        import random as _r
        wars = await Database.fetch(
            "SELECT id, opponent_faction, phase FROM maya_rp.wars "
            "WHERE session_id=$1 AND status='active'", session_id)
        hot = {"clash": 0.35, "attrition": 0.50, "turning_point": 0.40}
        engagements = 0
        for w in wars:
            chance = hot.get(w["phase"], 0)
            if not chance or _r.random() > chance:
                continue
            player_power = await Database.fetchval(
                "SELECT COALESCE(SUM(power_rating),0) FROM maya_rp.ships "
                "WHERE session_id=$1 AND status IN ('active','standby_alert')", session_id) or 0
            enemy_power = await Database.fetchval(
                "SELECT COALESCE(SUM(power_rating),0) FROM maya_rp.faction_ships "
                "WHERE faction_name=$1 AND status='active'", w["opponent_faction"]) or 0
            if player_power < 1000 or enemy_power < 1000:
                continue  # don't burn paper fleets
            formation = _r.choice(["wedge", "wall", "screen", "pincer"])
            terrain = roll_terrain()   # sync helper — NOT a coroutine
            p_mult = formation_bonus(formation) + terrain.get("player_mod", 0)
            ratio = (player_power * max(0.5, p_mult)) / max(1, enemy_power)
            # loss caps protect the smaller side
            small_side = min(player_power, enemy_power)
            p_loss = max(0, _r.randint(0, int(small_side * 0.02)))
            e_loss = max(0, _r.randint(0, int(small_side * 0.025)))
            if ratio >= 1.2:
                e_loss = int(e_loss * 1.6)
            elif ratio <= 0.8:
                p_loss = int(p_loss * 1.6)
            await Database.execute(
                "INSERT INTO maya_rp.combat_results "
                "(session_id, difficulty, encounter_size, player_power, enemy_power, "
                "ships_lost, ships_damaged, enemy_ships_destroyed, enemy_ships_routed, crew_casualties) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)",
                session_id, "hard", _encounter_size(small_side), player_power, enemy_power,
                json.dumps({"hulls": p_loss}), json.dumps({"hulls": max(0, _r.randint(0, int(p_loss * 0.5)))}),
                e_loss, max(0, e_loss // 2), _r.randint(0, 200))
            await Database.execute(
                "UPDATE maya_rp.wars SET attacker_casualties=attacker_casualties+$1, "
                "defender_casualties=defender_casualties+$2 WHERE id=$3",
                p_loss, e_loss, w["id"])
            # injury hook: named commander risk
            if _r.random() < 0.05:
                await _maybe_injure_commander(session_id)
            await Database.execute(
                "INSERT INTO maya_rp.events (session_id, happened_at, event_type, title, description, tags, importance) "
                "VALUES ($1, NOW(), 'battle', $2, $3, $4, 6)",
                session_id, f"Engagement: {w['opponent_faction']}",
                f"{formation}/{terrain['name']} — ratio {ratio:.2f}; losses {p_loss}/{e_loss}",
                json.dumps(["war", w["opponent_faction"], "battle"]))
            engagements += 1
        info("battle", f"Tick: {engagements} engagements resolved")
        return {"engagements": engagements}
    except Exception as e:
        error("battle", f"Tick error: {e}")
        return {"error": str(e)}


def _encounter_size(power: int) -> str:
    """Map a fleet-power total to the combat_results.encounter_size enum."""
    if power >= 10_000_000:
        return "armada"
    if power >= 1_000_000:
        return "fleet_action"
    if power >= 100_000:
        return "battle"
    if power >= 10_000:
        return "engagement"
    return "skirmish"


async def _maybe_injure_commander(session_id: int):
    """5% hook → injure a random named commander (spouse first)."""
    import random as _r
    import json as _j
    gd = await Database.fetchval(
        "SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id) or 0
    char = await Database.fetchrow(
        "SELECT id, name FROM maya_rp.characters WHERE session_id=$1 AND "
        "status IN ('active','married') ORDER BY is_spouse DESC, random() LIMIT 1",
        session_id)
    if not char:
        return
    body = _r.choice(["left arm", "right leg", "ribs", "shoulder", "side"])
    sev = _r.choice(["minor", "minor", "serious"])
    heal_days = 5 if sev == "minor" else 20
    await Database.execute(
        "INSERT INTO maya_rp.character_injuries "
        "(session_id, character_id, description, severity, body_part, cause, "
        "received_game_day, heal_by_game_day, became_scar, status) "
        "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,false,'active')",
        session_id, char["id"], f"{sev} wound to {body}",
        sev, body, "campaign engagement", gd, gd + heal_days)


# ─── Action Parser: resolve_intent ───────────────────────────────────────

async def resolve_intent(session_id: int, action: str, target: str, fleet_name: str = "") -> dict:
    """
    Resolve a combat intent from the Action Parser.
    Returns {winner, ships_lost, damage_taken, narrative_hook} for Deepseek narration.
    Called by kilo_bridge.py action_intent domain=combat.
    """
    # Simple combat resolution: TKG forces vs target
    from core import campaign

    effects = await campaign.debuff_effects(session_id)
    player_power = await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.ships WHERE session_id=$1 AND status='active'", session_id) or 0
    # M6: the penalty ladder degrades command, not the hulls — effective power
    # drops, and the narrative says why.
    effective_power = max(1, player_power - int(effects["battle_penalty"]))
    enemy_power = random.randint(effective_power // 2, effective_power * 2)

    # Basic outcome
    if effective_power >= enemy_power:
        winner = "TKG"
        ships_lost = random.randint(0, max(1, player_power // 10))
        damage_taken = random.randint(100, 500)
        narrative = f"TKG forces engaged {target}. Victory achieved with {ships_lost} ship{'s' if ships_lost != 1 else ''} lost."
    else:
        winner = target
        loss_low = max(1, player_power // 5)
        loss_high = max(loss_low, player_power // 3)  # a one-ship fleet still rolls
        ships_lost = random.randint(loss_low, loss_high)
        damage_taken = random.randint(500, 2000)
        narrative = f"TKG forces engaged {target}. Defeat sustained — {ships_lost} ship{'s' if ships_lost != 1 else ''} lost. Fleet retreating."

    if effects["battle_penalty"]:
        narrative += f" [{effects['debuff']}: {effects['note']}; command penalty -{effects['battle_penalty']}]"

    # Reduce ship count from DB
    remaining = max(1, player_power - ships_lost)
    await Database.execute(
        "UPDATE maya_rp.ships SET status='lost' WHERE session_id=$1 AND status='active' "
        "AND ctid IN (SELECT ctid FROM maya_rp.ships WHERE session_id=$1 AND status='active' LIMIT $2)",
        session_id, ships_lost)

    return {
        "domain": "combat",
        "winner": winner,
        "ships_lost": ships_lost,
        "damage_taken": damage_taken,
        "narrative_hook": narrative,
        "player_remaining_ships": remaining,
        "player_power_effective": effective_power,
        "debuff_battle_penalty": int(effects["battle_penalty"]),
    }
