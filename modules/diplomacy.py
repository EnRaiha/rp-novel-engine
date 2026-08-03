"""Async diplomacy module — treaties, envoys, AI actions."""
import random, json
from datetime import datetime, timezone, timedelta
from core.db import Database
from core.utils import calc_game_days

async def run_tick(session_id: int = 3):
    row = await Database.fetchrow("SELECT last_tick_at FROM resources WHERE session_id=$1", session_id)
    if not row or not row.get("last_tick_at"): return
    gd = calc_game_days(row["last_tick_at"])
    if gd < 0.01: return

    # Expire treaties
    await Database.execute("UPDATE treaties SET active=false WHERE expires_at<NOW() AND active=true")

    # Process envoys
    envoys = await Database.fetch(
        "SELECT e.*, f.name AS fn, f2.name AS tn FROM envoys e "
        "JOIN factions f ON f.id=e.faction_id JOIN factions f2 ON f2.id=e.target_faction_id "
        "WHERE e.status='active'")
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
            await Database.execute("UPDATE factions SET standing=$1, reputation=reputation+5 WHERE id=$2", ns, e["target_faction_id"])

    # AI actions
    ais = await Database.fetch("SELECT id, name, reputation FROM factions WHERE session_id=$1 AND name NOT IN ('Setia Empire')", session_id)
    for f in ais:
        if random.random() > 0.1 * gd: continue
        targets = await Database.fetch("SELECT id, name, standing FROM factions WHERE id!=$1", f["id"])
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

    await Database.execute("UPDATE factions SET reputation = reputation - sign(reputation)*1 WHERE reputation!=0")
    print(f"  Diplomacy: {len(ais)} AI factions")


# ─── Action Parser: resolve_intent ───────────────────────────────────────

async def resolve_intent(session_id: int, action: str, target: str) -> dict:
    """
    Resolve a diplomatic intent — talk/threaten/ally/declare war.
    Returns {success, standing_change, reaction} for Deepseek narration.
    """
    faction = await Database.fetchrow(
        "SELECT id, name, standing, reputation FROM maya_rp.factions "
        "WHERE session_id=$1 AND LOWER(name) LIKE LOWER($2) LIMIT 1",
        session_id, f"%{target}%")

    if not faction:
        return {
            "domain": "diplomacy",
            "success": False,
            "narrative_hook": f"No faction found matching '{target}'.",
        }

    standing_map = {"ally": "allied", "friend": "friendly", "neutral": "neutral",
                    "hostile": "hostile", "enemy": "enemy"}
    target_standing = standing_map.get(action, action)

    if target_standing == "war":
        # Declare war
        await Database.execute(
            "UPDATE maya_rp.factions SET standing='enemy' WHERE id=$1", faction["id"])
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
            "UPDATE maya_rp.factions SET standing=$1, reputation=LEAST(100, reputation+10) WHERE id=$2",
            target_standing, faction["id"])
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
