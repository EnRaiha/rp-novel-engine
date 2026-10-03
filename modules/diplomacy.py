"""Async diplomacy module — treaties, envoys, AI actions.

`treaties` and `envoys` carry no session of their own: they reach it through
`factions`, which does. Every query here that touches either table joins or
subqueries that session, because an unfiltered pass expired the other
campaign's treaties, processed its envoys, and decayed every faction's
reputation in the database.
"""
import random, json
from datetime import datetime, timezone, timedelta
from core.db import Database
from core.config import Config
from core.utils import calc_game_days

#: The session's faction ids, as a subquery over the session's own rows.
_SESSION_FACTIONS = "SELECT id FROM factions WHERE session_id=$1"


async def run_tick(session_id: int = None):
    """Treaty expiry, envoy resolution, AI diplomacy, reputation drift.

    Defaults to the engine's session, not the literal 3: that id is the frozen
    reference campaign.
    """
    if session_id is None:
        session_id = Config.SESSION_ID
    row = await Database.fetchrow("SELECT last_tick_at FROM resources WHERE session_id=$1", session_id)
    if not row or not row.get("last_tick_at"): return
    gd = calc_game_days(row["last_tick_at"])
    if gd < 0.01: return

    # Expire treaties — only the ones this campaign is a party to. The rows are
    # reachable from either side, so both columns are checked.
    await Database.execute(
        f"UPDATE treaties SET active=false WHERE expires_at<NOW() AND active=true "
        f"AND (faction_a_id IN ({_SESSION_FACTIONS}) OR faction_b_id IN ({_SESSION_FACTIONS}))",
        session_id)

    # Process envoys — the sending faction decides the campaign.
    envoys = await Database.fetch(
        "SELECT e.*, f.name AS fn, f2.name AS tn FROM envoys e "
        "JOIN factions f ON f.id=e.faction_id JOIN factions f2 ON f2.id=e.target_faction_id "
        "WHERE e.status='active' AND f.session_id=$1",
        session_id)
    for e in envoys:
        elapsed = (datetime.now(timezone.utc) - e["started_at"]).total_seconds() / 3600 / 6
        if elapsed < e["duration_days"]: continue
        standing = e.get("standing", "neutral")
        sm = {"allied": 40, "friendly": 20, "neutral": 0, "hostile": -20, "enemy": -40}.get(standing, 0)
        success = random.random() * 100 < 50 + sm
        await Database.execute("UPDATE envoys SET status=$1, result=$2 WHERE id=$3",
                               "completed" if success else "failed",
                               json.dumps({"success": success}), e["id"])
        if success:
            ns = {"hostile": "neutral", "neutral": "friendly", "friendly": "allied"}.get(standing, standing)
            await Database.execute(
                "UPDATE factions SET standing=$1, reputation=reputation+5 WHERE id=$2 AND session_id=$3",
                ns, e["target_faction_id"], session_id)

    # AI actions
    ais = await Database.fetch("SELECT id, name, reputation FROM factions WHERE session_id=$1 AND name NOT IN ('Setia Empire')", session_id)
    for f in ais:
        if random.random() > 0.1 * gd: continue
        # The target must be in this campaign: an unfiltered list let a live-arc
        # faction sign a treaty with the frozen campaign's neighbour.
        targets = await Database.fetch(
            "SELECT id, name, standing FROM factions WHERE id!=$1 AND session_id=$2",
            f["id"], session_id)
        if not targets: continue
        t = random.choice(targets)
        rep = f.get("reputation", 0) or 0
        if rep < -20 and random.random() < 0.3:
            war = await Database.fetchrow(
                "SELECT id FROM treaties WHERE ((faction_a_id=$1 AND faction_b_id=$2) OR (faction_a_id=$2 AND faction_b_id=$1)) AND treaty_type='war' AND active=true",
                f["id"], t["id"])
            if not war:
                await Database.execute("INSERT INTO treaties (name, treaty_type, faction_a_id, faction_b_id, signed_at, expires_at, active, created_by) VALUES ($1,'war',$2,$3,NOW(),NOW()+interval '9999 days',true,'ai')",
                                       f"War: {f['name']} vs {t['name']}", f["id"], t["id"])
        elif rep > 20 and random.random() < 0.4:
            tt = random.choice(["defense_pact", "trade_pact", "research_pact"])
            existing = await Database.fetchrow(
                "SELECT id FROM treaties WHERE ((faction_a_id=$1 AND faction_b_id=$2) OR (faction_a_id=$2 AND faction_b_id=$1)) AND treaty_type=$3 AND active=true",
                f["id"], t["id"], tt)
            if not existing:
                await Database.execute("INSERT INTO treaties (name, treaty_type, faction_a_id, faction_b_id, signed_at, expires_at, active, created_by) VALUES ($1,$2,$3,$4,NOW(),NOW()+interval '365 days',true,'ai')",
                                       f"{f['name']}-{t['name']} {tt}", tt, f["id"], t["id"])

    # Reputation drifts toward zero — for THIS campaign's factions only. The
    # unfiltered form decayed the other campaign's reputation every tick.
    await Database.execute(
        "UPDATE factions SET reputation = reputation - sign(reputation)*1 WHERE reputation!=0 AND session_id=$1",
        session_id)
    print(f"  Diplomacy: {len(ais)} AI factions")


# ─── Action Parser: resolve_intent ───────────────────────────────────────

STANDING_MAP = {"ally": "allied", "friend": "friendly", "neutral": "neutral",
                "hostile": "hostile", "enemy": "enemy"}
#: An action the parser may name. `declare_war` is the docstring's "declare war"
#: with the space normalised away.
#: Narration-only intents: the engine has no threat model, so these reach the
#: faction and change no standing. They are accepted because the docstring names
#: them, and their result says exactly that.
NARRATION_ACTIONS = ("talk", "threaten")
ACTION_ALIASES = {"declare_war": "war", "declarewar": "war", "war": "war"}
KNOWN_ACTIONS = tuple(STANDING_MAP) + tuple(STANDING_MAP.values()) + ("war",) + NARRATION_ACTIONS


async def resolve_intent(session_id: int, action: str, target: str) -> dict:
    """
    Resolve a diplomatic intent — talk/threaten/ally/declare war.
    Returns {success, standing_change, reaction} for Deepseek narration.

    An action outside KNOWN_ACTIONS used to fall through to the "contact made"
    branch and report `success: True` with nothing changed. It is refused by
    name now, so a misunderstanding reads as one.
    """
    act = str(action or "").strip().lower().replace(" ", "_").replace("-", "_")
    act = ACTION_ALIASES.get(act, act)
    if act not in KNOWN_ACTIONS:
        return {
            "domain": "diplomacy",
            "success": False,
            "narrative_hook": f"Unknown diplomatic action '{action}'. Supported: "
                              f"{', '.join(sorted(KNOWN_ACTIONS))}.",
        }

    faction = await Database.fetchrow(
        "SELECT id, name, standing, reputation FROM maya_rp.factions "
        "WHERE session_id=$1 AND LOWER(name) LIKE LOWER($2) ORDER BY id LIMIT 1",
        session_id, f"%{target}%")

    if not faction:
        return {
            "domain": "diplomacy",
            "success": False,
            "narrative_hook": f"No faction found matching '{target}'.",
        }

    target_standing = STANDING_MAP.get(act, act)

    if target_standing == "war":
        # Declare war
        await Database.execute(
            "UPDATE maya_rp.factions SET standing='enemy' WHERE id=$1 AND session_id=$2",
            faction["id"], session_id)
        return {
            "domain": "diplomacy",
            "success": True,
            "standing_change": "enemy",
            "narrative_hook": f"War declared against {faction['name']}. The galaxy takes notice.",
            "reaction": f"{faction['name']} responds with immediate mobilization.",
        }

    elif target_standing in ("allied", "friendly") and faction["standing"] != target_standing:
        # Improve relations
        await Database.execute(
            "UPDATE maya_rp.factions SET standing=$1, reputation=LEAST(100, reputation+10) "
            "WHERE id=$2 AND session_id=$3",
            target_standing, faction["id"], session_id)
        return {
            "domain": "diplomacy",
            "success": True,
            "standing_change": target_standing,
            "narrative_hook": f"Relations with {faction['name']} improved to {target_standing}.",
            "reaction": f"{faction['name']} receives the envoy with {'warmth' if target_standing == 'allied' else 'cautious optimism'}.",
        }

    else:
        return {
            "domain": "diplomacy",
            "success": True,
            "standing_change": faction["standing"],
            "narrative_hook": f"Contact made with {faction['name']}. Current standing: {faction['standing']}.",
            "reaction": f"{faction['name']} listens to what you have to say.",
        }
