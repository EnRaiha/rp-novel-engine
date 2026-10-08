"""Slave System — acquisition, assignment, training, revolts, breeding, market."""
import random, json
from datetime import datetime, timezone
from decimal import Decimal
from core.db import Database
from core.events import EventBus
from core.log import error, info
from core.session import require_session


class _Refuse(Exception):
    """Carries an error answer out of a transaction so every write in it rolls back."""

    def __init__(self, out: dict):
        super().__init__(out.get("error", ""))
        self.out = out


def _tag_count(tag) -> int:
    """Row count of an asyncpg command tag such as `UPDATE 1`; 0 when unreadable."""
    try:
        return int(str(tag).split()[-1])
    except (ValueError, IndexError):
        return 0


def _stoch(delta: float) -> int:
    """Round a per-tick delta to an int without losing its expected value.

    `health`, `loyalty` and `progress` are integer columns and asyncpg rejects a float bind, which
    aborted the whole tick. Plain `round()` is not the fix: health loses at most 0.25 a tick, which
    rounds to 0 every time and stops the decay. The fraction becomes the chance of one extra point.

    @param delta - signed amount.
    @returns the int amount, with the fractional part applied at random.
    """
    whole = int(delta // 1)
    return whole + (1 if random.random() < delta - whole else 0)

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

async def run_tick(session_id: int = None):
    """Slave system tick — training, health, loyalty, revolts, market.

    Every read below is scoped to the tick's campaign. `slave_training` and
    `slave_births` carry no session_id, so their scope comes through the join to
    `slaves`. The default used to be the frozen reference campaign.
    """
    session_id = require_session(session_id)
    from core.ooc import _refuse_frozen
    _refuse_frozen(session_id)
    try:
        gd = 0.5  # simplified game days
        # Advance training
        for r in await Database.fetch(
            "SELECT st.*, s.loyalty FROM slave_training st JOIN slaves s ON s.id=st.slave_id "
            "WHERE st.progress<100 AND s.session_id=$1", session_id):
            p = min(100, (r["progress"] or 0) + _stoch(2 * gd * (1 + (r["loyalty"] or 50) / 100)))
            await Database.execute("UPDATE slave_training SET progress=$1 WHERE id=$2", p, r["id"])
            if p >= 100:
                await Database.execute("UPDATE slave_training SET completed_at=NOW() WHERE id=$1", r["id"])
                await Database.execute("UPDATE slaves SET role=$1 WHERE id=$2", r["training_type"], r["slave_id"])
        # Update health/loyalty
        for s in await Database.fetch(
                "SELECT id, health, loyalty, assigned_to, assigned_id FROM slaves "
                "WHERE status='active' AND session_id=$1", session_id):
            h = max(0, (s["health"] or 0) - _stoch(random.uniform(0, 0.5) * gd))
            l = s["loyalty"] if s["loyalty"] is not None else 50
            if s["assigned_to"] == "territory":
                t = await Database.fetchrow(
                    "SELECT morale FROM territory WHERE id=$1 AND session_id=$2",
                    s["assigned_id"], session_id)
                if t: l += _stoch((-0.5 if t["morale"] < 40 else 0.3 if t["morale"] > 70 else 0) * gd)
            await Database.execute("UPDATE slaves SET health=$1, loyalty=$2 WHERE id=$3", h, max(0, min(100, l)), s["id"])
        # Revolt checks
        for t in await Database.fetch("SELECT id, slave_population FROM territory WHERE slave_population>0 AND session_id=$1", session_id):
            risk = await _revolt_risk(t["id"], session_id)
            if risk > 70 and random.random() < 0.1 * gd:
                await _trigger_revolt(session_id, t["id"])
        # Market refresh
        if random.random() < 0.2 * gd:
            t = await Database.fetchrow("SELECT id FROM territory WHERE session_id=$1 AND controlling_faction='Setia Empire' ORDER BY random() LIMIT 1", session_id)
            if t: await _generate_market(session_id, t["id"], random.randint(1, 3))
    except Exception as e:
        # A bare print() left the orchestrator scoring a crash as success.
        error("slaves", f"Tick error: {e}")
        return {"error": str(e)}
    return {"training_advanced": True, "session_id": session_id}

async def _revolt_risk(tid: int, session_id: int | None = None) -> int:
    """Compute a territory's revolt risk and store it.

    `slave_revolt_risk` is an integer column. The risk was a float, and `AVG(loyalty)` arrives as
    Decimal, so `float + Decimal` raised TypeError before the bind could.

    @param tid - territory id.
    @param session_id - restricts the read and the write to this campaign; None means unscoped.
    @returns the risk as an int from 0 to 100.
    """
    t = await Database.fetchrow(
        "SELECT slave_population, population, slave_revolt_risk FROM territory "
        "WHERE id=$1 AND ($2::int IS NULL OR session_id=$2)", tid, session_id)
    if not t or not t["slave_population"]: return 0
    sr = t["slave_population"] / max(1, t["population"] or 0) * 30
    al = await Database.fetchrow(
        "SELECT AVG(loyalty) AS a FROM slaves WHERE assigned_to='territory' AND assigned_id=$1 "
        "AND status='active' AND ($2::int IS NULL OR session_id=$2)", tid, session_id)
    if al and al["a"] is not None: sr += max(0, (50 - float(al["a"])) / 2)
    risk = int(round(min(100, sr)))
    await Database.execute(
        "UPDATE territory SET slave_revolt_risk=$1 WHERE id=$2 AND ($3::int IS NULL OR session_id=$3)",
        risk, tid, session_id)
    return risk

async def _trigger_revolt(sid: int, tid: int) -> bool:
    """Start a revolt in a territory unless one is already ongoing there.

    The tick rolled every pass, so a territory above the risk line collected a new 'ongoing' row per
    hit and halved its population again each time. The territory row is locked while the check and the
    writes run, so two ticks cannot both pass the check.

    @param sid - session id.
    @param tid - territory id.
    @returns True when a revolt started; False when the territory is missing or already in revolt.
    """
    risk = await _revolt_risk(tid, sid)
    async with Database.transaction() as conn:
        t = await conn.fetchrow(
            "SELECT system_name, slave_population FROM territory WHERE id=$1 AND session_id=$2 FOR UPDATE",
            tid, sid)
        if not t: return False
        if await conn.fetchval(
                "SELECT 1 FROM slave_revolts WHERE session_id=$1 AND territory_id=$2 AND outcome='ongoing'",
                sid, tid):
            return False
        sz = int(t["slave_population"] * random.uniform(0.2, 0.8))
        sev = min(10, int(risk / 10) + 1)
        await conn.execute("INSERT INTO slave_revolts (session_id,territory_id,size,severity,outcome,narrative) VALUES ($1,$2,$3,$4,'ongoing',$5)", sid, tid, sz, sev, f"Revolt in {t['system_name']}: {sz} slaves risen.")
        await conn.execute(
            "UPDATE territory SET slave_population=GREATEST(0,slave_population-$1) "
            "WHERE id=$2 AND session_id=$3", sz, tid, sid)
        # PostgreSQL has no UPDATE … ORDER BY … LIMIT — use a subquery to pick the
        # exact rows (this statement used to abort the whole revolt phase).
        await conn.execute(
            "UPDATE slaves SET status='rebellious' WHERE id IN ("
            "  SELECT id FROM slaves WHERE session_id=$1 AND assigned_to='territory' "
            "  AND assigned_id=$2 AND status='active' ORDER BY loyalty ASC LIMIT $3)",
            sid, tid, sz)
        await _log(sid, "crisis", f"Slave Revolt in {t['system_name']}", f"{sz} slaves risen, severity {sev}/10", 4, conn)
    return True

async def _generate_market(sid: int, tid: int, count: int = 5, pool: str = None):
    """Novel adaptation: market dengan price tiers + category pools (gacha pulls).
    EXPANSION 083: functional men & women — Setia territory sahaja (tetap via territory filter)."""
    async with Database.transaction() as conn:
        await conn.execute("DELETE FROM slave_market WHERE session_id=$1 AND territory_id=$2", sid, tid)
        for _ in range(count):
            s, i = random.randint(1, 10), random.randint(1, 10)
            # Gacha pool: 70% common, 20% half-beast, 8% succubus, 2% ex-commander. The roll is local to
            # each slot: the first roll used to overwrite `pool`, so every later slot repeated it and an
            # ex-commander roll filled the whole market.
            slot_pool = pool
            if slot_pool is None:
                r = random.random()
                slot_pool = "common" if r < 0.70 else "half_beast" if r < 0.90 else "succubus" if r < 0.98 else "ex_commander"
            pconf = CREW_POOLS[slot_pool]
            species = random.choice(pconf["species"])
            base_price = 500 + (s + i) * 500 + random.randint(0, 5000)
            price = int(base_price * pconf["price_mult"])
            talent = random.choice(HIDDEN_TALENTS) if slot_pool in ("ex_commander", "succubus") else None
            # Functional role — lelaki & perempuan bekerja (bukan hamba semata)
            functional_role = random.choice(["deckhand", "engineer", "gunner", "medic", "pilot", "logistics",
                                             "sensor_op", "cook", "helmsman", "welder"])
            # Clearance: ex-commander = 5 (screened), succubus = 3, lain = 1 (C1-C4)
            clr = 5 if slot_pool == "ex_commander" else 3 if slot_pool == "succubus" else 1
            await conn.execute(
                "INSERT INTO slave_market (session_id,territory_id,slave_name,species,gender,age,strength,intelligence,"
                "price,price_tier,category,hidden_talent,functional_role,clearance_level) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)",
                sid, tid, random.choice(NAMES), species, random.choice(["M", "F"]), random.randint(18, 45), s, i,
                price, slot_pool, pconf["desc"], talent, functional_role, clr)

def _name(): return f"{random.choice(NAMES)} {random.choice(NAMES)}"

async def _log(sid: int, cat: str, title: str, content: str, imp: int = 1, conn=None):
    await (conn or Database).execute("INSERT INTO events (session_id,event_type,title,description,importance,tags) VALUES ($1,$2,$3,$4,$5,$6)", sid, cat, title, content, imp, json.dumps([cat]))

_WRITE_ACTIONS = {"assign", "train", "market", "market_shop", "buy", "revolt_risk", "suppress", "breed"}


async def cmd(sid: int | None, action: str, params: dict) -> dict:
    """Run one slave-system action for a campaign.

    @param sid - session key; the active session when None.
    @param action - list, assign, train, market, market_shop, buy, revolt_risk, suppress, breed or stats.
    @param params - action arguments.
    @returns the action's answer, or {"error": ...}.
    @raises FrozenSession for every action except list and stats when the campaign is frozen.
    """
    sid = require_session(sid)
    if action in _WRITE_ACTIONS:
        from core.ooc import _refuse_frozen
        _refuse_frozen(sid)
    if action == "list":
        # slave_overview has no session_id of its own, so the scope comes through
        # the base table. The view used to list every campaign's slaves.
        return {"slaves": [dict(r) for r in await Database.fetch(
            "SELECT so.* FROM slave_overview so JOIN slaves s ON s.id = so.id "
            "WHERE s.session_id = $1", sid)]}
    if action == "assign":
        s = params["slave_id"]; tt = params["target_type"]; ti = params["target_id"]; role = params.get("role", "laborer")
        try:
            async with Database.transaction() as conn:
                sl = await conn.fetchrow("SELECT * FROM slaves WHERE id=$1 AND session_id=$2 FOR UPDATE", s, sid)
                if not sl: raise _Refuse({"error": "Not found"})
                if tt == "territory" and not await conn.fetchrow(
                        "SELECT id FROM territory WHERE id=$1 AND session_id=$2", ti, sid):
                    raise _Refuse({"error": "Territory not found"})
                # Counters follow the slave. A reassignment used to add to the new territory and leave the
                # old one counting a slave who had gone, so slave_population only ever grew.
                bonus = Decimal((sl["strength"] or 0) + (sl["intelligence"] or 0)) / Decimal(20)
                was_there = sl["assigned_to"] == "territory" and sl["assigned_id"] is not None
                same = was_there and tt == "territory" and sl["assigned_id"] == ti
                await conn.execute("UPDATE slaves SET assigned_to=$1, assigned_id=$2, role=$3 WHERE id=$4", tt, ti, role, s)
                if was_there and not same:
                    await conn.execute(
                        "UPDATE territory SET slave_productivity_mult=GREATEST(1.0, slave_productivity_mult-$1), "
                        "slave_population=GREATEST(0, slave_population-1) WHERE id=$2 AND session_id=$3",
                        bonus, sl["assigned_id"], sid)
                if tt == "territory" and not same:
                    await conn.execute(
                        "UPDATE territory SET slave_productivity_mult=slave_productivity_mult+$1, "
                        "slave_population=slave_population+1 WHERE id=$2 AND session_id=$3", bonus, ti, sid)
        except _Refuse as refused:
            return refused.out
        return {"success": True}
    if action == "train":
        # slave_training has no session_id: the slave has to be yours first.
        if not await Database.fetchrow(
                "SELECT id FROM slaves WHERE id=$1 AND session_id=$2", params["slave_id"], sid):
            return {"error": "Slave not found"}
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
        # Claim, charge and the three inserts commit together. The charge used to land before the
        # inserts, so a failing insert kept the credits, and the market row was released last, so two
        # buyers could both pass the availability read.
        try:
            async with Database.transaction() as conn:
                m = await conn.fetchrow(
                    "UPDATE slave_market SET availability=false "
                    "WHERE id=$1 AND availability=true AND session_id=$2 RETURNING *",
                    params["market_id"], sid)
                if not m: raise _Refuse({"error": "Not available"})
                charged = await conn.execute(
                    "UPDATE resources SET credits=credits-$1 WHERE session_id=$2 AND credits>=$1",
                    m["price"], sid)
                if _tag_count(charged) == 0: raise _Refuse({"error": "Insufficient credits"})
                sl_id = (await conn.fetchrow("INSERT INTO slaves (session_id,name,species,gender,age,strength,intelligence,loyalty,health,cost) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,80,$9) RETURNING id",
                    sid, m["slave_name"], m["species"], m["gender"], m["age"], m["strength"], m["intelligence"], 50, m["price"]))["id"]
                # EXPANSION 083: functional crew — masukkan ke crew_roster dengan clearance + role
                clr = m.get("clearance_level") or 1
                role = m.get("functional_role") or "deckhand"
                crew_id = await conn.fetchval(
                    """INSERT INTO maya_rp.crew_roster (session_id, name, role, status, loyalty_flag, clearance_level, screened)
                       VALUES ($1, $2, $3, 'active', 'neutral', $4, $5) RETURNING id""",
                    sid, m["slave_name"], role, clr, clr >= 5)
                if m.get("hidden_talent"):
                    # crew_skills.crew_id is a crew_roster id. It was given the slaves.id, so the talent
                    # landed on another crew member, or on none.
                    await conn.execute(
                        "INSERT INTO crew_skills (crew_id, session_id, skill_name, proficiency) VALUES ($1,$2,$3,2) "
                        "ON CONFLICT (crew_id, skill_name) DO UPDATE SET proficiency=crew_skills.proficiency+1",
                        crew_id, sid, m["hidden_talent"])
                talent_msg = f" | Hidden talent: {m['hidden_talent']}" if m.get("hidden_talent") else ""
                clr_msg = f" | Clearance: C{clr}" if clr >= 5 else ""
                await _log(sid, "slave", f"Crew Recruited: {m['slave_name']}", f"Cost: {m['price']}C ({m.get('price_tier','common')}){talent_msg}{clr_msg}", 2, conn)
        except _Refuse as refused:
            return refused.out
        return {"slave_id": sl_id, "price": m["price"], "tier": m.get("price_tier"), "talent": m.get("hidden_talent"),
                "clearance": clr, "role": role}
    if action == "revolt_risk":
        return {"risk": await _revolt_risk(params["territory_id"], sid)}
    if action == "suppress":
        r = await Database.fetchrow(
            "SELECT * FROM slave_revolts WHERE id=$1 AND outcome='ongoing' AND session_id=$2",
            params["revolt_id"], sid)
        if not r: return {"error": "Not found"}
        force = params.get("force", True)
        success = random.random() < (0.7 if force else 0.4)
        cas = int(r["size"] * random.uniform(0.1, 0.5)) if success else 0
        if success:
            await Database.execute("UPDATE slave_revolts SET end_time=NOW(), outcome='suppressed', casualties=$1 WHERE id=$2", cas, r["id"])
            await Database.execute(
                "UPDATE slaves SET status='active', loyalty=GREATEST(0,loyalty+10) "
                "WHERE status='rebellious' AND assigned_id=$1 AND session_id=$2",
                r["territory_id"], sid)
            await _log(sid, "crisis", f"Revolt Suppressed", f"Casualties: {cas}", 3)
        else:
            sv = min(10, r["severity"] + 1)
            await Database.execute("UPDATE slave_revolts SET severity=$1 WHERE id=$2", sv, r["id"])
            esc = int(r["size"] * random.uniform(0.1, 0.3))
            await Database.execute(
                "UPDATE slaves SET status='escaped' WHERE id IN ("
                "  SELECT id FROM slaves WHERE session_id=$1 AND status='rebellious' "
                "  ORDER BY random() LIMIT $2)", sid, esc)
            await _log(sid, "crisis", f"Revolt Escalates!", f"Severity now {sv}/10, {esc} escaped", 4)
            return {"success": False, "severity": sv, "escaped": esc}
        return {"success": success, "casualties": cas}
    if action == "breed":
        a = await Database.fetchrow("SELECT * FROM slaves WHERE id=$1 AND session_id=$2", params["parent_a"], sid)
        b = await Database.fetchrow("SELECT * FROM slaves WHERE id=$1 AND session_id=$2", params["parent_b"], sid)
        if not a or not b: return {"error": "Parent not found"}
        s = max(1, min(10, int((a["strength"] + b["strength"]) / 2) + random.randint(-2, 2)))
        i = max(1, min(10, int((a["intelligence"] + b["intelligence"]) / 2) + random.randint(-2, 2)))
        # One child, one name. Two birth rows used to name two children that were
        # never created, and neither name matched the child in `slaves`.
        child_name = _name()
        cid = (await Database.fetchrow("INSERT INTO slaves (session_id,name,species,gender,strength,intelligence,loyalty,health) VALUES ($1,$2,$3,$4,$5,$6,50,90) RETURNING id",
            sid, child_name, random.choice([a["species"], b["species"]]), random.choice(["M","F"]), s, i))["id"]
        for parent in (a, b):
            await Database.execute(
                "INSERT INTO slave_births (parent_slave_id,child_name) VALUES ($1,$2)",
                parent["id"], child_name)
        await _log(sid, "slave", "New Slave Born", f"From {a['name']} and {b['name']}: {child_name}", 1)
        return {"child_id": cid, "child_name": child_name}
    if action == "stats":
        total = (await Database.fetchrow("SELECT COUNT(*) AS c FROM slaves WHERE session_id=$1 AND status='active'", sid))["c"]
        by_role = await Database.fetch("SELECT role, COUNT(*) AS c FROM slaves WHERE session_id=$1 AND status='active' GROUP BY role", sid)
        avg_l = (await Database.fetchrow("SELECT AVG(loyalty) AS a FROM slaves WHERE session_id=$1", sid))["a"]
        return {"total": total, "by_role": [dict(r) for r in by_role], "avg_loyalty": avg_l}
    return {"error": f"Unknown: {action}"}
