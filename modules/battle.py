"""Battle Engine — terrain, tactics, formations, phases, commanders, aftermath."""
import random, json, asyncio
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from core.db import Database
from core.events import EventBus
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

class BattleEngine:
    @classmethod
    async def init(cls, session_id: int, player_ships: List[int],
                   enemy_faction: str, terrain_id: int = None) -> BattleState:
        """Initialize a new battle."""
        pf = await cls._make_fleet(player_ships, "Setia Empire")
        ef = await cls._make_fleet([], enemy_faction)
        terrain = await Database.fetchrow("SELECT * FROM battle_terrain WHERE id=$1" if terrain_id
            else "SELECT * FROM battle_terrain ORDER BY random() LIMIT 1", terrain_id or 1) or {}
        bid = await Database.fetchrow(
            "INSERT INTO combat_results (session_id, player_power, enemy_power, status) "
            "VALUES ($1,$2,$3,'active') RETURNING id",
            session_id, sum(s.combat_rating for s in pf.ships), sum(s.combat_rating for s in ef.ships))
        state = BattleState(battle_id=bid["id"], player=pf, enemy=ef, terrain=terrain)
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
        ships = []
        for row in await Database.fetch(
            "SELECT s.*, sr.base_stats FROM ships s LEFT JOIN ship_roles sr ON sr.name=s.role WHERE s.id = ANY($1)", ship_ids) if ship_ids else []:
            bs = (row.get("base_stats") or {}); r = row["combat_rating"]
            ships.append(BattleShip(id=row["id"], name=row["name"], ship_type=row.get("ship_type",""),
                hull=int(row.get("hull",100)*bs.get("hull_mult",1)),
                shield=int(row.get("hull_current",50)*bs.get("shield_mult",1)),
                speed=int(row.get("speed",10)*bs.get("speed_mult",1)),
                evasion=float(row.get("evasion",0.1)), combat_rating=float(r)))
        return BattleFleet(faction=faction, ships=ships)

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
            "UPDATE combat_results SET outcome=$1, ended_at=NOW(), status='completed' WHERE id=$2",
            outcome, state.battle_id)
        loot = random.randint(1000, 50000) if outcome == "player_victory" else 0
        rep = 10 if outcome == "player_victory" else -10
        await Database.execute("INSERT INTO battle_aftermath (battle_id, loot_credits, reputation_change, narrative) VALUES ($1,$2,$3,$4)",
            state.battle_id, loot, rep, f"Battle resolved: {outcome}")
        # Novel adaptation — Ship Legacy (bab 7, 35): kapal veteran dapat battle_honors + legacy_score
        if outcome == "player_victory" and state.player.ships:
            await Database.execute(
                "UPDATE maya_rp.ships SET battle_honors=battle_honors+1, veteran_kills=veteran_kills+1, "
                "legacy_score=legacy_score+GREATEST(1, LEAST(10, power_rating/50000)) "
                "WHERE session_id=$1 AND id = ANY($2::int[])",
                state.session_id, state.player.ships)
            # NOVEL ULTIMATE #5 — Rank naik + procedural scars untuk near-death survivor
            for ship_id in state.player.ships:
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
        r = await Database.fetchrow("SELECT bonus FROM fleet_formations WHERE name=$1", formation)
        if r: await Database.execute("UPDATE combat_results SET player_formation=$1 WHERE id=$2", formation, battle_id)

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
            "UPDATE combat_results SET retreat_attempted=true, retreat_successful=$1, pursuit_damage=$2, status='completed' WHERE id=$3",
            success, dmg if success else 0, battle_id)
        await EventBus.emit("battle_retreated", {"battle_id": battle_id, "success": success})
        return {"success": success, "damage": dmg if not success else 0}

    @classmethod
    def _narr(cls, state: BattleState, wins: bool) -> str:
        pn = PHASE_NAMES[min(state.phase - 1, 4)]; state.phase += 1
        return f"{pn}: {'Player presses attack.' if wins else 'Enemy counterattacks.'} Using {state.player_tactic}."

    @classmethod
    async def _save(cls, state: BattleState, entry: Dict):
        await Database.execute(
            "INSERT INTO battle_log_entries (battle_id, turn_number, actor, action, result, damage) VALUES ($1,$2,$3,$4,$5,$6)",
            state.battle_id, entry["turn"], "player" if entry["won"] else "enemy",
            entry["tactic"], entry["narrative"], entry["damage_dealt"])
        if state.turn % 3 == 0 and state.phase < 5:
            await Database.execute(
                "INSERT INTO battle_phases (battle_id, phase_number, phase_name, player_tactic, enemy_tactic, damage_dealt, damage_taken) VALUES ($1,$2,$3,$4,$5,$6,$7)",
                state.battle_id, state.phase, PHASE_NAMES[state.phase-1], entry["tactic"],
                entry["enemy_tactic"], entry["damage_dealt"], entry["damage_taken"])

    @classmethod
    async def _load_state(cls, battle_id: int) -> Optional[BattleState]:
        row = await Database.fetchrow("SELECT * FROM combat_results WHERE id=$1", battle_id)
        if not row: return None
        return BattleState(battle_id=battle_id, player=BattleFleet("player"),
                           enemy=BattleFleet("ai"), terrain={}, phase=row.get("phase",1))

async def run_tick(session_id: int = None):
    """Battle module tick — currently no active battles to process."""
    from core.log import info
    if session_id is None: session_id = Config.SESSION_ID
    info("battle", "Tick: no active battles")
    return {"active_battles": 0}


# ─── Action Parser: resolve_intent ───────────────────────────────────────

async def resolve_intent(session_id: int, action: str, target: str, fleet_name: str = "") -> dict:
    """
    Resolve a combat intent from the Action Parser.
    Returns {winner, ships_lost, damage_taken, narrative_hook} for Deepseek narration.
    Called by kilo_bridge.py action_intent domain=combat.
    """
    # Simple combat resolution: TKG forces vs target
    player_power = await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.ships WHERE session_id=$1 AND status='active'", session_id) or 0
    enemy_power = random.randint(player_power // 2, player_power * 2)

    # Basic outcome
    if player_power >= enemy_power:
        winner = "TKG"
        ships_lost = random.randint(0, max(1, player_power // 10))
        damage_taken = random.randint(100, 500)
        narrative = f"TKG forces engaged {target}. Victory achieved with {ships_lost} ship{'s' if ships_lost != 1 else ''} lost."
    else:
        winner = target
        ships_lost = random.randint(max(1, player_power // 5), player_power // 3)
        damage_taken = random.randint(500, 2000)
        narrative = f"TKG forces engaged {target}. Defeat sustained — {ships_lost} ship{'s' if ships_lost != 1 else ''} lost. Fleet retreating."

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
    }
