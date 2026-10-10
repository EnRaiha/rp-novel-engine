"""Pirate War Machine + Loot — aggressive spawning, attacks, salvage, artifacts.

Every pirate faction, base and bounty belongs to one campaign: `factions`
carries `session_id`, and `pirate_bases` / `pirate_bounties` reach it through
`faction_id`. A read or write that skips that column reaches the frozen
reference campaign from a live tick, and this module's money movement makes
that expensive: a raid would seize a session-3 hoard into the session-5 coffer.
"""
import random, json
from datetime import datetime, timezone
from core.config import Config
from core.db import Database
from core.events import EventBus
from core.log import error, info
from core.utils import calc_game_days
from core.session import require_session

# ── WAR MACHINE ──

async def run_tick(session_id: int = None) -> dict:
    """Main pirate tick — spawn, move, attack, alert, hoard income, den regen.

    A missing session resolves per call through `require_session`, never to the legacy TKG id 3,
    which is the frozen reference campaign. The orchestrator treats an `error` dict as a failed
    module, so a tick error is returned and not only logged.
    """
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    try:
        await _spawn(session_id)
        await _attack(session_id)
        await _alerts(session_id)
        await _hoard_tick(session_id)
        await _den_feeding(session_id)
        await _den_regen(session_id)
        return {"session_id": session_id}
    except Exception as e:
        error("pirates", f"Tick error (session {session_id}): {e}")
        return {"error": str(e)}


async def _den_regen(session_id: int):
    """Den regeneration (2026-08-14): dens with a LIVING Pirate Queen or King
    rebuild their fleet each tick up to fleet_cap. Both leaders dead → regen
    stops — kill the crown, kill the swarm.

    The den belongs to the campaign that owns its faction: an unfiltered read
    rebuilt the frozen campaign's dens and filed their new hulls under THIS
    session, ships no faction of this campaign owns.
    """
    bases = await Database.fetch(
        "SELECT pb.id, pb.faction_id, pb.regen_per_tick, pb.fleet_cap, pb.name "
        "FROM maya_rp.pirate_bases pb JOIN maya_rp.factions f ON f.id = pb.faction_id "
        "WHERE pb.status='active' AND f.session_id=$1 AND COALESCE(pb.regen_per_tick,0) > 0",
        session_id)
    regen = 0
    for b in bases:
        try:
            leader = await Database.fetchval(
                "SELECT COUNT(*) FROM maya_rp.characters WHERE faction_id=$1 AND status='active' "
                "AND session_id=$2 "
                "AND (role ILIKE '%pirate queen%' OR role ILIKE '%pirate king%')",
                b["faction_id"], session_id)
            if not leader:
                continue
            fname = await Database.fetchval(
                "SELECT name FROM maya_rp.factions WHERE id=$1", b["faction_id"])
            current = await Database.fetchval(
                # Same reason as battle.py: only this campaign's hulls count toward the cap.
                "SELECT COUNT(*) FROM maya_rp.faction_ships WHERE faction_name=$1 AND session_id=$2",
                fname, session_id) or 0
            cap = b["fleet_cap"] or 300
            add = min(int(b["regen_per_tick"] or 0), max(0, cap - current))
            for i in range(add):
                await Database.execute(
                    "INSERT INTO maya_rp.faction_ships "
                    "(session_id, faction_name, ship_name, class_name, tier, power_rating, status) "
                    "VALUES ($1,$2,$3,'Raider',5,$4,'active')",
                    session_id, fname, f"{b['name'][:14]} #{current + i + 1}",
                    120000 + random.randint(0, 60000))
            regen += add
        except Exception as e:
            info("pirates", f"den regen error {b['name']}: {e}")
    if regen:
        info("pirates", f"Den regen: {regen} T5 ships rebuilt")

# HARTA KARUN: the Den's treasure floor. No upper limit — the longer a
# hoard lives, the fatter it gets. Every faction strong enough can feed.
HOARD_FLOOR = 40_000_000

async def _hoard_tick(session_id: int):
    """Den treasure engine — grow, floor, rebuild.

    Every step names the campaign. The floor used to be applied to both
    campaigns' pirate treasuries by a tick that only belongs to one.
    """
    # 1. Faction-level floor: the Den itself always holds >= 40M.
    await Database.execute(
        "UPDATE maya_rp.factions SET treasury = GREATEST(treasury, $1) "
        "WHERE is_pirate=true AND session_id=$2 AND (status='active' OR status IS NULL)",
        HOARD_FLOOR, session_id)

    # 2. Base growth (1% per tick, min 5K) + base floor.
    bases = await Database.fetch(
        "SELECT pb.id, pb.treasury FROM maya_rp.pirate_bases pb "
        "JOIN maya_rp.factions f ON f.id = pb.faction_id "
        "WHERE pb.status='active' AND f.session_id=$1", session_id)
    for b in bases:
        growth = max(5000, int((b["treasury"] or 0) * 0.01))
        await Database.execute(
            "UPDATE maya_rp.pirate_bases SET treasury = GREATEST($1, treasury+$2) WHERE id=$3",
            HOARD_FLOOR, growth, b["id"])

    # 3. Rebuild: destroyed bases return — the Den always crawls back,
    #    and the new base starts consolidated at the 40M floor. faction_id=6
    #    is the Den of the reference campaign; the join keeps a live tick from
    #    resurrecting it, and leaves a campaign without a Den at zero.
    destroyed = await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.pirate_bases pb "
        "JOIN maya_rp.factions f ON f.id = pb.faction_id "
        "WHERE pb.faction_id=6 AND pb.status='destroyed' AND f.session_id=$1",
        session_id) or 0
    if destroyed > 0 and random.random() < 0.15:
        zone = await Database.fetchrow(
            "SELECT system_id FROM pirate_zones WHERE active=true AND protected=false"
            " AND session_id=$1 ORDER BY random() LIMIT 1", session_id)
        if zone:
            await Database.execute(
                "UPDATE maya_rp.pirate_bases SET status='active', treasury=$1, hidden=TRUE, defenses=50 "
                "WHERE id=(SELECT pb.id FROM maya_rp.pirate_bases pb "
                "JOIN maya_rp.factions f ON f.id = pb.faction_id "
                "WHERE pb.faction_id=6 AND pb.status='destroyed' AND f.session_id=$2 "
                "ORDER BY pb.id LIMIT 1)",
                HOARD_FLOOR, session_id)
            await Database.execute(
                "INSERT INTO pirate_alerts (session_id, message, severity) VALUES ($1,$2,2)",
                session_id, "DEN REBUILT: a razed base is active again — hoard restored to 40M.")

async def _den_feeding(session_id: int):
    """The sector eats the Den — every faction strong enough feeds on the hoard.
    Only the excess above the 40M floor is takeable; the floor always holds.

    Both sides of the transfer are in one campaign. Unfiltered, a session-3
    hoard could be poured into a session-5 faction's treasury.
    """
    den = await Database.fetchrow(
        "SELECT id FROM maya_rp.factions WHERE is_pirate=true AND status='active' "
        "AND session_id=$1 ORDER BY id LIMIT 1", session_id)
    if not den:
        return
    bases = await Database.fetch(
        "SELECT id, treasury FROM maya_rp.pirate_bases WHERE faction_id=$1 AND status='active'",
        den["id"])
    if not bases:
        return
    feeders = await Database.fetch(
        "SELECT id, name, economic_strength FROM maya_rp.factions "
        "WHERE is_pirate=false AND status='active' AND session_id=$1 AND name != 'Setia Empire'",
        session_id)
    for f in feeders:
        if random.random() >= 0.03 + float(f["economic_strength"] or 0) * 0.03:
            continue
        bite = random.randint(2_000_000, 8_000_000)
        target = random.choice(bases)
        # Only the excess above the floor is takeable.
        actual = min(bite, (target["treasury"] or 0) - HOARD_FLOOR)
        if actual <= 0:
            continue
        # The bite was sized on a snapshot: the debit re-checks the floor and the
        # status against the row, so a feeder that lost the race takes nothing.
        tag = await Database.execute(
            "UPDATE maya_rp.pirate_bases SET treasury=treasury-$1 WHERE id=$2 AND status='active' "
            "AND treasury-$1 >= " + str(HOARD_FLOOR),
            actual, target["id"])
        if tag.split()[-1:] == ["0"]:
            continue
        await Database.execute(
            "UPDATE maya_rp.factions SET treasury=treasury+$1 WHERE id=$2",
            actual, f["id"])
        await Database.execute(
            "INSERT INTO pirate_alerts (session_id, message, severity) VALUES ($1,$2,2)",
            session_id, f"{f['name']} raided a Den hoard — {actual:,}C taken.")

async def _spawn(session_id: int):
    # King's rule: pirates pop up ANYWHERE — but never near the capital.
    # Protected zones (capital vicinity) never spawn pirate fleets, and migration 138 binds a zone to
    # one campaign: a live tick spawns in its own zones, never in the frozen reference's.
    zones = await Database.fetch(
        "SELECT * FROM pirate_zones WHERE active=true AND protected=false AND session_id=$1",
        session_id)
    for z in zones:
        if random.random() < z["danger_level"] * 0.03:  # 3-15% per tick
            tl = "patrol" if z["danger_level"] <= 2 else "raiding" if z["danger_level"] <= 3 else "invasion"
            t = await Database.fetchrow(
                "SELECT * FROM pirate_fleet_templates WHERE threat_level=$1 ORDER BY random() LIMIT 1", tl)
            if t: await _spawn_fleet(session_id, z["system_id"], t["name"])

async def _spawn_fleet(session_id: int, system_id: int, template: str):
    t = await Database.fetchrow("SELECT * FROM pirate_fleet_templates WHERE name=$1", template)
    if not t:
        info("pirates", f"no fleet template named {template!r} — nothing spawned")
        return
    ship_ids = []
    comp = json.loads(t["composition"]) if isinstance(t["composition"], str) else (t["composition"] or {})
    for cls, cnt in comp.items():
        for _ in range(cnt):
            sc = await Database.fetchrow("SELECT * FROM pirate_ship_classes WHERE name=$1", cls)
            if not sc:
                info("pirates", f"no ship class named {cls!r} in template {template!r}")
                continue
            sid = await Database.fetchval(
                "INSERT INTO ships (session_id, name, ship_type, hull, hull_current, speed, tier, location, status) "
                "VALUES ($1,$2,$3,$4,$4,$5,5,$6,'hostile') RETURNING id",
                session_id,
                f"Pirate {cls} #{random.randint(1000,9999)}", cls, sc["hull"], sc["speed"], f"System {system_id}")
            ship_ids.append(sid)
    # Store in faction treasury as "fleet" — this campaign's pirate faction,
    # or the power lands on the other campaign's Den.
    pf = await Database.fetchrow(
        "SELECT id FROM factions WHERE is_pirate=true AND session_id=$1 ORDER BY random() LIMIT 1",
        session_id)
    if not pf:
        info("pirates", f"session {session_id} has no pirate faction — {len(ship_ids)} spawned "
                        f"hull(s) carry no faction power, no alert filed")
        return
    await Database.execute("UPDATE factions SET pirate_fleet_power=pirate_fleet_power+$1 WHERE id=$2", t["total_power"], pf["id"])
    await Database.execute(
        "INSERT INTO pirate_alerts (session_id, message, severity) VALUES ($1,$2,$3)",
        session_id, f"Pirate {t['name']} detected (system {system_id})!", 2)

async def _take_credits(session_id: int, amount: int) -> int | None:
    """Take up to `amount`, never below zero. None: the session has no resources row."""
    async with Database.transaction() as conn:
        held = await conn.fetchval(
            "SELECT credits FROM maya_rp.resources WHERE session_id=$1 FOR UPDATE", session_id)
        if held is None:
            return None
        taken = min(int(amount), max(0, int(held)))
        if taken:
            await conn.execute(
                "UPDATE maya_rp.resources SET credits=credits-$1 WHERE session_id=$2", taken, session_id)
        return taken


async def _attack(session_id: int):
    # Simple attack: pick a target, roll, generate loot.
    # King's rule: the capital (TKG Mastika) is never a raid target.
    targets = await Database.fetch(
        "SELECT id, system_name, population FROM territory WHERE session_id=$1 AND controlling_faction='Setia Empire' "
        "AND system_name != 'TKG Mastika'",
        session_id)
    if not targets: return
    t = random.choice(targets)
    # The raider is this campaign's pirate: an unfiltered pick let the frozen
    # campaign's strongest Den raid the live arc and bank the loot.
    pf = await Database.fetchrow(
        "SELECT id, pirate_fleet_power FROM factions WHERE is_pirate=true AND session_id=$1 "
        "ORDER BY pirate_fleet_power DESC NULLS LAST LIMIT 1", session_id)
    if not pf or (pf["pirate_fleet_power"] or 0) < 50: return
    # Defense capped at 5000+50 — canon-scale worlds (hundreds of millions)
    # can't become raid-proof; the Den can still strike, just never the capital.
    defense = min(int(t["population"] / 1000), 5000) + 50
    # ── ML decision hook (2026-08-14): pirate group → doctrine → raid policy
    group = "free"
    policy = "check_first"
    try:
        from core.decision_models import (detect_pirate_group, predict_pirate_policy,
                                          predict_pirate_survival, log_decision)
        group = await detect_pirate_group(pf["id"], session_id)
        cond = "boarding" if t["population"] < 100000 else "den_resists"
        policy = predict_pirate_policy(group, "ai_policy", "STANDARD UNIFORMITY",
                                       cond, "check_first")["class"]
        await log_decision(pf["id"], "pirate_policy",
                           {"src": "ai_policy", "policy": "STANDARD UNIFORMITY",
                            "cond": cond, "act": "check_first"},
                           policy, None, group, session_id)
    except Exception as e:  # noqa: BLE001 - reported below
        error("pirates", f"_attack: {e}")
    # doctrine modifiers: aggression trades loot for risk
    _AGGRO = {"bullet": 1.0, "clear_all": 1.0, "bullet_or_ransom": 0.9,
              "check_first": 0.97, "confirm_first": 0.95, "debt_bound": 0.9,
              "convert": 0.9, "level": 0.85}
    if policy not in _AGGRO:
        info("pirates", f"unknown raid policy {policy!r} from the decision model — "
                        f"using the 0.95 default")
    aggro = _AGGRO.get(policy, 0.95)
    success = random.random() < aggro * pf["pirate_fleet_power"] / (pf["pirate_fleet_power"] + defense)
    loot = await _generate_loot("raiding", 0)
    loot_c = loot.get("credits", random.randint(25000, 100000)) if success else 0
    # sponsored wolf packs take a cut for their patron; hired crews run clean
    if success and group in ("sponsor", "hired"):
        loot_c = int(loot_c * (1.05 if group == "sponsor" else 0.9))
    if success and loot_c:
        # The raid only takes what the treasury actually holds: a session with
        # no resources row must not be recorded (or banked) as robbed. Charged
        # before the raid row, so the row states what moved.
        taken = await _take_credits(session_id, loot_c)
        if taken is None:
            info("pirates", f"session {session_id} has no resources row — "
                            f"{loot_c:,}C raid loss NOT deducted")
            loot_c = 0
        else:
            loot_c = taken
    await Database.execute(
        "INSERT INTO pirate_raids (pirate_faction_id, target_territory_id, raid_type, loot_credits, outcome, description) "
        "VALUES ($1,$2,'colony',$3,$4,$5)",
        pf["id"], t["id"], loot_c, "success" if success else "failure",
        f"Raid on {t['system_name']} [{group}:{policy}]: {'+' if success else '-'}{loot_c}C")
    if success:
        # HARTA KARUN: 40% goes to Den faction treasury, 60% into their
        # active base hoards — so every raid on us grows the treasure
        # we can take back by smashing their bases.
        den_share = int(loot_c * 0.4)
        hoard_share = loot_c - den_share
        if loot_c:
            await Database.execute("UPDATE factions SET treasury=treasury+$1 WHERE id=$2", den_share, pf["id"])
            base = await Database.fetchrow(
                "SELECT id FROM maya_rp.pirate_bases WHERE faction_id=$1 AND status='active' "
                "ORDER BY random() LIMIT 1", pf["id"])
            if base and hoard_share:
                await Database.execute(
                    "UPDATE maya_rp.pirate_bases SET treasury=treasury+$1 WHERE id=$2",
                    hoard_share, base["id"])
        # Loot items too. `_apply_loot` CREDITS the treasury, so the credits are
        # stripped first: passing the raid's own loot dict paid the victim back
        # the money the raid had just taken.
        if loot.get("items") or loot.get("artifacts"):
            await _apply_loot(session_id, dict(loot, credits=0))
    else:
        loss = int(pf["pirate_fleet_power"] * 0.1)
        await Database.execute("UPDATE factions SET pirate_fleet_power=GREATEST(0,pirate_fleet_power-$1) WHERE id=$2", loss, pf["id"])
        # ML survival hook: on intercepted raid, predict the crew's fate
        try:
            from core.decision_models import predict_pirate_survival, log_decision
            live = 0.5 if (pf["pirate_fleet_power"] or 0) > defense else 0.25
            fate = predict_pirate_survival(group, 0, live, "queen_offers_alliance")
            await log_decision(pf["id"], "pirate_survival",
                               {"virgin": 0, "live_chance": live,
                                "action": "queen_offers_alliance"},
                               fate["class"], fate.get("probs"), group, session_id)
            await Database.execute(
                "INSERT INTO maya_rp.pirate_raids (pirate_faction_id, target_territory_id, raid_type, loot_credits, outcome, description) "
                "VALUES ($1,$2,'intercept',0,'fate', $3)",
                pf["id"], t["id"], f"Intercepted raid crew fate [{group}]: {fate['class']} ({fate['source']})")
        except Exception as e:  # noqa: BLE001 - reported below
            error("pirates", f"_attack: {e}")

async def _alerts(session_id: int):
    total = await Database.fetchrow(
        "SELECT COALESCE(SUM(pirate_fleet_power),0) AS t FROM factions "
        "WHERE is_pirate=true AND session_id=$1", session_id)
    if total and total["t"] > 5000:
        await Database.execute("INSERT INTO pirate_alerts (session_id, message, severity) VALUES ($1,$2,4)",
            session_id, "CRISIS: Pirate armada detected! Over 5000 power.")

# ── LOOT ──

LOOT_TABLES = {
    "patrol": {"credits": (5000,25000), "resources": {"Alloys":(50,200),"Fuel":(30,150)}, "chance": 0.6},
    "raiding": {"credits": (25000,100000), "resources": {"Alloys":(200,800),"Fuel":(100,400),"Rare Earth Elements":(5,20)}, "chance": 0.8},
    "invasion": {"credits": (100000,500000), "resources": {"Alloys":(500,2000),"Fuel":(300,1000),"Aetherium":(2,10),"Orichalcum":(1,5)}, "chance": 0.9},
    "armada": {"credits": (500000,2000000), "resources": {"Alloys":(2000,8000),"Fuel":(1000,4000),"Starsteel":(1,5),"Dream Essence":(1,3),"Void Crystal":(1,2)}, "chance": 1.0},
}

async def _generate_loot(threat: str, fleet_id: int = 0) -> dict:
    """Roll a loot table for a threat level.

    An unknown threat raises. Falling back to the patrol table silently
    under-paid an "armada" (500K-2M) as a "patrol" (5K-25K) with no word that
    the name never matched. `fleet_id` is unused: loot does not vary by fleet.
    """
    if threat not in LOOT_TABLES:
        raise ValueError(f"Unknown threat {threat!r} — one of {tuple(LOOT_TABLES)}")
    lt = LOOT_TABLES[threat]
    loot = {"credits": 0, "resources": {}, "items": [], "artifacts": []}
    if random.random() < lt["chance"]:
        loot["credits"] = random.randint(*lt["credits"])
        for rn, (mn, mx) in lt.get("resources", {}).items():
            loot["resources"][rn] = random.randint(mn, mx)
    # Artifacts
    art_chance = {"invasion": 0.2, "armada": 0.5}.get(threat, 0)
    if random.random() < art_chance:
        art = await Database.fetchrow("SELECT * FROM pirate_artifacts ORDER BY random() LIMIT 1")
        if art: loot["artifacts"].append(dict(art))
    return loot

async def _apply_loot(session_id: int, loot: dict):
    if loot.get("credits", 0) > 0:
        await Database.execute("UPDATE resources SET credits=credits+$1 WHERE session_id=$2", loot["credits"], session_id)
    for rn, amt in loot.get("resources", {}).items():
        await Database.execute(
            "INSERT INTO resource_inventory (resource_id, quantity) SELECT id, $1 FROM strategic_resources WHERE name=$2 "
            "ON CONFLICT (resource_id) DO UPDATE SET quantity=resource_inventory.quantity+EXCLUDED.quantity",
            amt, rn)
    for art in loot.get("artifacts", []):
        await Database.execute("INSERT INTO events (session_id, event_type, title, description, importance, tags) "
            "VALUES ($1,'loot',$2,$3,4,$4)",
            session_id, f"Artifact: {art['name']}", f"{art['rarity']}: {art['description']}", json.dumps(["artifact", art["rarity"]]))

async def salvage_ship(ship_class: str) -> dict:
    """Salvage a destroyed pirate ship.

    An unknown class returns the empty result AND says so in the log: the
    zeros are indistinguishable from "the wreck yielded nothing", which is a
    different answer. Raises nothing — callers treat this as a best-effort
    lookup on a class name they may only know from lore.

    Computes the yield only: it does not destroy or consume the wreck.
    """
    t = await Database.fetchrow("SELECT salvage_pool, capture_chance FROM pirate_salvage_templates WHERE ship_class=$1", ship_class)
    if not t:
        info("pirates", f"no salvage template for class {ship_class!r} — nothing yielded")
        return {"credits": 0, "resources": {}, "components": [], "captured": False}
    sp = json.loads(t["salvage_pool"]) if isinstance(t["salvage_pool"], str) else (t["salvage_pool"] or {})
    if random.random() < float(t["capture_chance"]):
        return {"credits": random.randint(10000,100000), "resources": {}, "components": [f"{ship_class}_intact"], "captured": True}
    return {
        "credits": random.randint(*sp.get("credits", (0,0))) if "credits" in sp else 0,
        "resources": {rn: random.randint(*rv) for rn, rv in sp.get("resources", {}).items()} if random.random() < 0.7 else {},
        "components": [c for c in sp.get("components", []) if random.random() < 0.7],
        "captured": False,
    }

class _NoCoffer(Exception):
    """The session has no resources row, so a credit has nowhere to land."""


async def _pay_bounty(session_id: int, pirate_faction_id: int, claimant_id: int) -> int | None:
    """Mark one open bounty claimed and credit its amount in one transaction.

    The status-guarded UPDATE claims first: a second caller finds no open row and
    pays nothing. Raises `_NoCoffer` before the commit when the credit has no row,
    so the bounty stays open. None: no open bounty.
    """
    async with Database.transaction() as conn:
        amount = await conn.fetchval(
            "UPDATE maya_rp.pirate_bounties SET claimed_by=$2, last_updated=NOW() WHERE id=("
            "SELECT id FROM maya_rp.pirate_bounties WHERE pirate_faction_id=$1 AND claimed_by IS NULL"
            " ORDER BY id LIMIT 1) AND claimed_by IS NULL RETURNING COALESCE(bounty_amount, 0)",
            pirate_faction_id, claimant_id)
        if amount is None:
            return None
        tag = await conn.execute(
            "UPDATE maya_rp.resources SET credits=credits+$1 WHERE session_id=$2", amount, session_id)
        if tag.split()[-1:] == ["0"]:
            raise _NoCoffer(session_id)
        return amount


async def claim_bounty(session_id: int, pirate_faction_id: int) -> dict:
    """Pay one open bounty on a defeated pirate faction of this session.

    The bounty row carries no session of its own, so the faction lookup scopes it:
    a faction that is not a pirate of `session_id` pays nothing. The claimant is
    the session's first faction named `Setia Empire%`; without one nothing pays.
    Each call claims one bounty and credits it in one transaction.
    """
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    f = await Database.fetchrow(
        "SELECT status FROM factions WHERE id=$1 AND is_pirate=true AND session_id=$2",
        pirate_faction_id, session_id)
    if not f:
        return {"success": False, "error": "Not a pirate faction of this session."}
    if f["status"] != "defeated":
        return {"success": False, "error": "Pirates still active."}
    claimant = await Database.fetchval(
        "SELECT id FROM maya_rp.factions WHERE session_id=$1 AND name ILIKE 'Setia Empire%' "
        "ORDER BY id LIMIT 1", session_id)
    if claimant is None:
        info("pirates", f"session {session_id} has no Setia faction — bounty on "
                        f"faction {pirate_faction_id} NOT claimed")
        return {"success": False,
                "error": f"No Setia faction in session {session_id}: bounty not claimed."}
    try:
        amount = await _pay_bounty(session_id, pirate_faction_id, claimant)
    except _NoCoffer:
        info("pirates", f"session {session_id} has no resources row — bounty on "
                        f"faction {pirate_faction_id} NOT paid, not claimed")
        return {"success": False, "error": "No treasury row for this session."}
    if amount is None:
        return {"success": False, "error": "No bounty available."}
    return {"success": True, "credits": amount}


async def _seize_hoard(session_id: int, base) -> int | None:
    """Destroy an active base and credit its hoard in one transaction.

    The status-guarded UPDATE claims first: a second raider finds no active row
    and seizes nothing. Raises `_NoCoffer` before the commit when the credit has
    no row, so the base stays standing. None: the base is no longer active.
    """
    async with Database.transaction() as conn:
        hoard = await conn.fetchval(
            "WITH old AS (SELECT treasury FROM maya_rp.pirate_bases WHERE id=$1 AND status='active' FOR UPDATE)"
            " UPDATE maya_rp.pirate_bases pb SET status='destroyed', treasury=0 FROM old"
            " WHERE pb.id=$1 AND pb.status='active' RETURNING COALESCE(old.treasury, 0)", base["id"])
        if hoard is None:
            return None
        tag = await conn.execute(
            "UPDATE maya_rp.resources SET credits=credits+$1 WHERE session_id=$2", hoard, session_id)
        if tag.split()[-1:] == ["0"]:
            raise _NoCoffer(session_id)
        await conn.execute(
            "UPDATE maya_rp.factions SET pirate_fleet_power=GREATEST(0,pirate_fleet_power-$1) WHERE id=$2",
            int((base["pirate_fleet_power"] or 0) * 0.15), base["faction_id"])
        await conn.execute(
            "INSERT INTO maya_rp.pirate_alerts (session_id, message, severity) VALUES ($1,$2,3)",
            session_id, f"DEN BASE SMASHED: {base['name']} — {hoard:,}C seized!")
        return hoard


async def raid_pirate_base(session_id: int, base_id: int, attack_power: int = 50000) -> dict:
    """Strike a Den base and seize its hoard. attack_power = fleet power sent.

    Success → treasury seized into the realm coffer, base destroyed,
    Den fleet power takes a hit. Failure → base goes to ground. A raid cannot
    seize one campaign's hoard into another's coffer.

    `_seize_hoard` claims the active base, credits the coffer and logs the alert
    in one transaction: two raiders seize a hoard once, and a missing coffer
    leaves the base standing.
    """
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    base = await Database.fetchrow(
        "SELECT pb.*, f.pirate_fleet_power FROM maya_rp.pirate_bases pb "
        "JOIN maya_rp.factions f ON f.id = pb.faction_id "
        "WHERE pb.id=$1 AND pb.status='active' AND f.session_id=$2", base_id, session_id)
    if not base:
        return {"success": False, "error": "Base not found or already destroyed."}

    attack_power = max(1000, attack_power)
    defense_power = (base["defenses"] or 0) * 500 + (base["pirate_fleet_power"] or 0) * 0.3
    odds = attack_power / (attack_power + defense_power)
    success = random.random() < odds

    if success:
        try:
            hoard = await _seize_hoard(session_id, base)
        except _NoCoffer:
            info("pirates", f"session {session_id} has no resources row — hoard "
                            f"{(base['treasury'] or 0):,}C NOT seized, base left standing")
            return {"success": False, "base": base["name"], "odds": round(odds, 2),
                    "error": "No treasury row for this session.",
                    "message": f"Raid on {base['name']} found no coffer to receive the hoard."}
        if hoard is None:
            return {"success": False, "error": "Base not found or already destroyed."}
        return {"success": True, "base": base["name"], "hoard_seized": hoard,
                "odds": round(odds, 2), "message": f"{base['name']} destroyed. {hoard:,}C to the coffer."}
    else:
        await Database.execute(
            "UPDATE maya_rp.pirate_bases SET hidden=TRUE WHERE id=$1", base_id)
        await Database.execute(
            "INSERT INTO maya_rp.pirate_alerts (session_id, message, severity) VALUES ($1,$2,2)",
            session_id, f"DEN BASE RAID REPULSED: {base['name']} went to ground.")
        return {"success": False, "base": base["name"], "odds": round(odds, 2),
                "message": f"Raid on {base['name']} repulsed. Base went dark."}
