"""Async narrative module — story generation, hooks, ambient events."""
import random, json
from datetime import datetime, timezone
from core.db import Database
from core.utils import calc_game_days
from core.events import EventBus

CATEGORIES = ["economy", "social", "military", "diplomatic", "science", "mystery"]

async def _story_entry(session_id: int, cat: str, title: str, content: str, imp: int = 1):
    await Database.execute(
        "INSERT INTO story_log (session_id, category, title, content, importance) VALUES ($1,$2,$3,$4,$5)",
        session_id, cat, title, content, imp)
    await Database.execute(
        "INSERT INTO events (session_id, event_type, title, description, importance, tags) VALUES ($1,'narrative',$2,$3,$4,$5)",
        session_id, title, content, imp, json.dumps(["narrative", cat]))

async def run_tick(session_id: int = 3):
    row = await Database.fetchrow("SELECT last_tick_at FROM resources WHERE session_id=$1", session_id)
    if not row or not row.get("last_tick_at"):
        return
    gd = calc_game_days(row["last_tick_at"])
    if gd < 0.01:
        return

    # Get state
    res = await Database.fetchrow("SELECT credits FROM resources WHERE session_id=$1", session_id)
    crisis = await Database.fetchrow(
        "SELECT COALESCE(SUM(crisis_level),0) AS ct FROM territory WHERE session_id=$1 AND controlling_faction='Setia Empire'",
        session_id)
    factions = await Database.fetch(
        "SELECT name, standing FROM factions WHERE session_id=$1 AND name NOT IN ('Setia Empire')", session_id)

    # Ambient event (20%)
    if random.random() < 0.2 * gd:
        cat = random.choice(CATEGORIES)
        t = None; c = None
        credits = (res or {}).get("credits", 0) or 0
        ct = (crisis or {}).get("ct", 0) or 0
        if cat == "economy":
            t = "Trade Winds Shift" if credits > 5_000_000 else "Coins Run Low"
            c = "Markets fluctuate. Merchant guilds adjust their strategies." if credits > 5_000_000 else "Treasury reports a modest shortfall. Spending reviewed."
        elif cat == "social":
            t = "Festival Season" if ct < 5 else "Unrest Simmers"
            c = "Celebrations across the empire." if ct < 5 else "Colonies report growing discontent."
        elif cat == "military":
            t = "Fleet Drills"
            c = "Squadrons run tactical exercises. Readiness confirmed."
        elif cat == "diplomatic" and factions:
            f = random.choice(factions)
            t = f"Word from {f['name']}"
            c = f"Envoy reports: {f['name']} remains {f['standing']}."
        elif cat == "science":
            t = "Discovery in the Forge"
            c = "Heaven station reports a new stellar phenomenon."
        elif cat == "mystery":
            t = "Unknown Signal"
            c = "Deep space sensors detect rhythmic pulses from an uncharted nebula."
        if t and c:
            await _story_entry(session_id, cat, t, c, 1)

    # Narrative hooks
    hooks = await Database.fetch(
        "SELECT COUNT(*) AS c FROM narrative_hooks WHERE session_id=$1 AND status='active'", session_id)
    active = hooks[0]["c"] if hooks else 0
    if active < 3 and random.random() < 0.1 * gd:
        ht = random.choice(["mystery", "opportunity", "intrigue"])
        descs = {
            "mystery": "An ancient structure pulses with unknown energy on a distant moon.",
            "opportunity": "A neutral faction offers exclusive trade rights in exchange for military escorts.",
            "intrigue": "A coded message intercepted — someone is plotting within the council.",
        }
        desc = descs.get(ht, "Something stirs in the deep.")
        await Database.execute(
            "INSERT INTO narrative_hooks (session_id, hook_type, description) VALUES ($1,$2,$3)",
            session_id, ht, desc)
        await _story_entry(session_id, "narrative", f"Hook: {ht.title()}", desc, 2)

    print(f"  Narrative: ambient events + hooks")
