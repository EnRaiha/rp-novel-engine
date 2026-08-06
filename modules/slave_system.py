"""Slave System — acquisition, assignment, training, revolts, breeding, market."""
import random, json
from datetime import datetime, timezone
from core.db import Database
from core.events import EventBus

NAMES = ['Kael','Mira','Theron','Seph','Elara','Dorian','Lysander','Valia','Rourke','Jax',
         'Mara','Vex','Grieves','Sam','Razor','Shadow','Crimson','Raven','Wolf','Storm']
SPECIES = ['Human','Alien','Cyborg','Hybrid']

# Novel adaptation — crew market pools (bab 8-9, 52): price tiers + hidden talents
CREW_POOLS = {
    "common": {"species": ["Human", "Alien"], "price_mult": 1.0, "desc": "Crew biasa"},
    "half_beast": {"species": ["Half-Beast", "Half-Beast", "Half-Beast"], "price_mult": 3.0,
                   "desc": "Half-beast crew — setia, kuat (novel bab 8)"},
    "succubus": {"species": ["Succubus"], "price_mult": 12.0,
                 "desc": "Succubus — charismatic, morale boost (novel bab 52)"},
    "ex_commander": {"species": ["Human", "Alien"], "price_mult": 40.0,
                     "desc": "Ex-fleet commander — leadership, command skills (novel bab 9)"},
}
HIDDEN_TALENTS = ["gunnery", "tactics", "navigation", "engineering", "charisma", "logistics",
                  "espionage", "morale", "boarding", "research"]

async def run_tick(session_id: int = 3):
    """Slave system tick — training, health, loyalty, revolts, market."""
    try:
        gd = 0.5  # simplified game days
        # Advance training
        for r in await Database.fetch(
            "SELECT st.*, s.loyalty FROM slave_training st JOIN slaves s ON s.id=st.slave_id WHERE st.progress<100"):
            p = min(100, r["progress"] + 2 * gd * (1 + (r["loyalty"] or 50) / 100))
            await Database.execute("UPDATE slave_training SET progress=$1 WHERE id=$2", p, r["id"])
            if p >= 100:
                await Database.execute("UPDATE slave_training SET completed_at=NOW() WHERE id=$1", r["id"])
                await Database.execute("UPDATE slaves SET role=$1 WHERE id=$2", r["training_type"], r["slave_id"])
        # Update health/loyalty
        for s in await Database.fetch("SELECT id, health, loyalty, assigned_to, assigned_id FROM slaves WHERE status='active'"):
            h = max(0, s["health"] - random.uniform(0, 0.5) * gd)
            l = s["loyalty"]
            if s["assigned_to"] == "territory":
                t = await Database.fetchrow("SELECT morale FROM territory WHERE id=$1", s["assigned_id"])
                if t: l += (-0.5 if t["morale"] < 40 else 0.3 if t["morale"] > 70 else 0) * gd
            await Database.execute("UPDATE slaves SET health=$1, loyalty=$2 WHERE id=$3", h, max(0, min(100, l)), s["id"])
        # Revolt checks
        for t in await Database.fetch("SELECT id, slave_population FROM territory WHERE slave_population>0 AND session_id=$1", session_id):
            risk = await _revolt_risk(t["id"])
            if risk > 70 and random.random() < 0.1 * gd:
                await _trigger_revolt(session_id, t["id"])
        # Market refresh
        if random.random() < 0.2 * gd:
            t = await Database.fetchrow("SELECT id FROM territory WHERE session_id=$1 AND controlling_faction='Setia Empire' ORDER BY random() LIMIT 1", session_id)
            if t: await _generate_market(session_id, t["id"], random.randint(1, 3))
    except Exception as e:
        print(f"  Slaves: {e}")

async def _revolt_risk(tid: int) -> int:
    t = await Database.fetchrow("SELECT slave_population, population, slave_revolt_risk FROM territory WHERE id=$1", tid)
    if not t or not t["slave_population"]: return 0
    sr = t["slave_population"] / max(1, t["population"]) * 30
    al = await Database.fetchrow("SELECT AVG(loyalty) AS a FROM slaves WHERE assigned_to='territory' AND assigned_id=$1 AND status='active'", tid)
    if al and al["a"]: sr += max(0, (50 - al["a"]) / 2)
    sr = min(100, sr)
    await Database.execute("UPDATE territory SET slave_revolt_risk=$1 WHERE id=$2", sr, tid)
    return sr

async def _trigger_revolt(sid: int, tid: int):
    t = await Database.fetchrow("SELECT system_name, slave_population FROM territory WHERE id=$1", tid)
    sz = int(t["slave_population"] * random.uniform(0.2, 0.8))
    sev = min(10, int(await _revolt_risk(tid) / 10) + 1)
    await Database.execute("INSERT INTO slave_revolts (session_id,territory_id,size,severity,outcome,narrative) VALUES ($1,$2,$3,$4,'ongoing',$5)", sid, tid, sz, sev, f"Revolt in {t['system_name']}: {sz} slaves risen.")
    await Database.execute("UPDATE territory SET slave_population=GREATEST(0,slave_population-$1) WHERE id=$2", sz, tid)
    await Database.execute("UPDATE slaves SET status='rebellious' WHERE assigned_to='territory' AND assigned_id=$1 AND status='active' ORDER BY loyalty ASC LIMIT $2", tid, sz)
    await _log(sid, "crisis", f"Slave Revolt in {t['system_name']}", f"{sz} slaves risen, severity {sev}/10", 4)

async def _generate_market(sid: int, tid: int, count: int = 5, pool: str = None):
    """Novel adaptation: market dengan price tiers + category pools (gacha pulls).
    EXPANSION 083: functional men & women — Setia territory sahaja (tetap via territory filter)."""
    await Database.execute("DELETE FROM slave_market WHERE session_id=$1 AND territory_id=$2", sid, tid)
    for _ in range(count):
        s, i = random.randint(1, 10), random.randint(1, 10)
        # Gacha pool: 70% common, 20% half-beast, 8% succubus, 2% ex-commander
        if pool is None:
            r = random.random()
            pool = "common" if r < 0.70 else "half_beast" if r < 0.90 else "succubus" if r < 0.98 else "ex_commander"
        pconf = CREW_POOLS[pool]
        species = random.choice(pconf["species"])
        base_price = 500 + (s + i) * 500 + random.randint(0, 5000)
        price = int(base_price * pconf["price_mult"])
        talent = random.choice(HIDDEN_TALENTS) if pool in ("ex_commander", "succubus") else None
        # Functional role — lelaki & perempuan bekerja (bukan hamba semata)
        functional_role = random.choice(["deckhand", "engineer", "gunner", "medic", "pilot", "logistics",
                                         "sensor_op", "cook", "helmsman", "welder"])
        # Clearance: ex-commander = 5 (screened), succubus = 3, lain = 1 (C1-C4)
        clr = 5 if pool == "ex_commander" else 3 if pool == "succubus" else 1
        await Database.execute(
            "INSERT INTO slave_market (session_id,territory_id,slave_name,species,gender,age,strength,intelligence,"
            "price,price_tier,category,hidden_talent,functional_role,clearance_level) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)",
            sid, tid, random.choice(NAMES), species, random.choice(["M", "F"]), random.randint(18, 45), s, i,
            price, pool, pconf["desc"], talent, functional_role, clr)

def _name(): return f"{random.choice(NAMES)} {random.choice(NAMES)}"

async def _log(sid: int, cat: str, title: str, content: str, imp: int = 1):
    await Database.execute("INSERT INTO events (session_id,event_type,title,description,importance,tags) VALUES ($1,$2,$3,$4,$5,$6)", sid, cat, title, content, imp, json.dumps([cat]))

async def cmd(sid: int, action: str, params: dict) -> dict:
    if action == "list":
        return {"slaves": [dict(r) for r in await Database.fetch("SELECT * FROM slave_overview")]}
    if action == "assign":
        s = params["slave_id"]; tt = params["target_type"]; ti = params["target_id"]; role = params.get("role", "laborer")
        sl = await Database.fetchrow("SELECT * FROM slaves WHERE id=$1", s)
        if not sl: return {"error": "Not found"}
        if tt == "territory" and not await Database.fetchrow("SELECT id FROM territory WHERE id=$1", ti): return {"error": "Territory not found"}
        await Database.execute("UPDATE slaves SET assigned_to=$1, assigned_id=$2, role=$3 WHERE id=$4", tt, ti, role, s)
        if tt == "territory":
            bonus = (sl["strength"] + sl["intelligence"]) / 20
            await Database.execute("UPDATE territory SET slave_productivity_mult=slave_productivity_mult+$1, slave_population=slave_population+1 WHERE id=$2", bonus, ti)
        return {"success": True}
    if action == "train":
        e = await Database.fetchrow("SELECT id FROM slave_training WHERE slave_id=$1 AND progress<100", params["slave_id"])
        if e: return {"error": "Already training"}
        await Database.execute("INSERT INTO slave_training (slave_id,training_type) VALUES ($1,$2)", params["slave_id"], params.get("training_type", "laborer"))
        return {"success": True}
    if action == "market":
        await _generate_market(sid, params["territory_id"], params.get("count", 5), params.get("pool"))
        return {"market": [dict(r) for r in await Database.fetch("SELECT * FROM slave_market WHERE session_id=$1 AND territory_id=$2 AND availability=true", sid, params["territory_id"])]}
    if action == "market_shop":
        """Novel crew market (gacha): list pools + current market."""
        t = await Database.fetchrow("SELECT id FROM territory WHERE session_id=$1 AND controlling_faction='Setia Empire' ORDER BY random() LIMIT 1", sid)
        if not t:
            return {"error": "No territory available"}
        await _generate_market(sid, t["id"], params.get("count", 5), params.get("pool"))
        market = await Database.fetch(
            "SELECT id, slave_name, species, gender, price, price_tier, category, hidden_talent, "
            "functional_role, clearance_level "
            "FROM slave_market WHERE session_id=$1 AND territory_id=$2 AND availability=true ORDER BY price DESC",
            sid, t["id"])
        return {"pools": list(CREW_POOLS.keys()), "territory_id": t["id"],
                "market": [dict(r) for r in market]}
    if action == "buy":
        m = await Database.fetchrow("SELECT * FROM slave_market WHERE id=$1 AND availability=true", params["market_id"])
        if not m: return {"error": "Not available"}
        cr = await Database.fetchrow("SELECT credits FROM resources WHERE session_id=$1", sid)
        if not cr or cr["credits"] < m["price"]: return {"error": "Insufficient credits"}
        await Database.execute("UPDATE resources SET credits=credits-$1 WHERE session_id=$2", m["price"], sid)
        sl_id = (await Database.fetchrow("INSERT INTO slaves (session_id,name,species,gender,age,strength,intelligence,loyalty,health,cost) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,80,$9) RETURNING id",
            sid, m["slave_name"], m["species"], m["gender"], m["age"], m["strength"], m["intelligence"], 50, m["price"]))["id"]
        # EXPANSION 083: functional crew — masukkan ke crew_roster dengan clearance + role
        clr = m.get("clearance_level") or 1
        role = m.get("functional_role") or "deckhand"
        await Database.execute(
            """INSERT INTO maya_rp.crew_roster (session_id, name, role, status, loyalty_flag, clearance_level, screened)
               VALUES ($1, $2, $3, 'active', 'neutral', $4, $5)""",
            sid, m["slave_name"], role, clr, clr >= 5)
        if m.get("hidden_talent"):
            await Database.execute(
                "INSERT INTO crew_skills (crew_id, session_id, skill_name, proficiency) "
                "SELECT $1, $2, $3, 2 WHERE EXISTS (SELECT 1 FROM crew_roster WHERE id=$1) "
                "ON CONFLICT (crew_id, skill_name) DO UPDATE SET proficiency=crew_skills.proficiency+1",
                sl_id, sid, m["hidden_talent"])
        await Database.execute("UPDATE slave_market SET availability=false WHERE id=$1", params["market_id"])
        talent_msg = f" | Hidden talent: {m['hidden_talent']}" if m.get("hidden_talent") else ""
        clr_msg = f" | Clearance: C{clr}" if clr >= 5 else ""
        await _log(sid, "slave", f"Crew Recruited: {m['slave_name']}", f"Cost: {m['price']}C ({m.get('price_tier','common')}){talent_msg}{clr_msg}", 2)
        return {"slave_id": sl_id, "price": m["price"], "tier": m.get("price_tier"), "talent": m.get("hidden_talent"),
                "clearance": clr, "role": role}
    if action == "revolt_risk":
        return {"risk": await _revolt_risk(params["territory_id"])}
    if action == "suppress":
        r = await Database.fetchrow("SELECT * FROM slave_revolts WHERE id=$1 AND outcome='ongoing'", params["revolt_id"])
        if not r: return {"error": "Not found"}
        force = params.get("force", True)
        success = random.random() < (0.7 if force else 0.4)
        cas = int(r["size"] * random.uniform(0.1, 0.5)) if success else 0
        if success:
            await Database.execute("UPDATE slave_revolts SET end_time=NOW(), outcome='suppressed', casualties=$1 WHERE id=$2", cas, r["id"])
            await Database.execute("UPDATE slaves SET status='active', loyalty=GREATEST(0,loyalty+10) WHERE status='rebellious' AND assigned_id=$1", r["territory_id"])
            await _log(sid, "crisis", f"Revolt Suppressed", f"Casualties: {cas}", 3)
        else:
            sv = min(10, r["severity"] + 1)
            await Database.execute("UPDATE slave_revolts SET severity=$1 WHERE id=$2", sv, r["id"])
            esc = int(r["size"] * random.uniform(0.1, 0.3))
            await Database.execute("UPDATE slaves SET status='escaped' WHERE status='rebellious' ORDER BY random() LIMIT $1", esc)
            await _log(sid, "crisis", f"Revolt Escalates!", f"Severity now {sv}/10, {esc} escaped", 4)
            return {"success": False, "severity": sv, "escaped": esc}
        return {"success": success, "casualties": cas}
    if action == "breed":
        a = await Database.fetchrow("SELECT * FROM slaves WHERE id=$1", params["parent_a"])
        b = await Database.fetchrow("SELECT * FROM slaves WHERE id=$1", params["parent_b"])
        if not a or not b: return {"error": "Parent not found"}
        s = max(1, min(10, int((a["strength"] + b["strength"]) / 2) + random.randint(-2, 2)))
        i = max(1, min(10, int((a["intelligence"] + b["intelligence"]) / 2) + random.randint(-2, 2)))
        cid = (await Database.fetchrow("INSERT INTO slaves (session_id,name,species,gender,strength,intelligence,loyalty,health) VALUES ($1,$2,$3,$4,$5,$6,50,90) RETURNING id",
            sid, _name(), random.choice([a["species"], b["species"]]), random.choice(["M","F"]), s, i))["id"]
        await Database.execute("INSERT INTO slave_births (parent_slave_id,child_name) VALUES ($1,$2)", a["id"], _name())
        await Database.execute("INSERT INTO slave_births (parent_slave_id,child_name) VALUES ($1,$2)", b["id"], _name())
        await _log(sid, "slave", "New Slave Born", f"From {a['name']} and {b['name']}", 1)
        return {"child_id": cid}
    if action == "stats":
        total = (await Database.fetchrow("SELECT COUNT(*) AS c FROM slaves WHERE session_id=$1 AND status='active'", sid))["c"]
        by_role = await Database.fetch("SELECT role, COUNT(*) AS c FROM slaves WHERE session_id=$1 AND status='active' GROUP BY role", sid)
        avg_l = (await Database.fetchrow("SELECT AVG(loyalty) AS a FROM slaves WHERE session_id=$1", sid))["a"]
        return {"total": total, "by_role": [dict(r) for r in by_role], "avg_loyalty": avg_l}
    return {"error": f"Unknown: {action}"}
