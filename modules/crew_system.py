#!/usr/bin/env python3
"""Crew System — crew pool (numeric), production dari university/academy, consumption oleh kapal.

Novel: "Oops! We are short of talent" — bottleneck bukan kapal, tapi CREW.
- crew_pool: crew terlatih yang sedia untuk assign (numeric)
- Production: university campuses (research-based) + academy campuses (student slots)
- Consumption: kapal baru consume crew ikut ships.crew
- Shortage → undercrewed penalty (Stakes Integrity)
"""
from __future__ import annotations
import random
from core.db import Database
from core.config import Config
from core.log import info

# Kadar produksi: academy campus produce crew per tick ikut slots & prestige
def _academy_output(slots_used: int, max_students: int, prestige: int) -> int:
    """Pelajar grad → crew. Kadar: 8% slots + prestige bonus per tick (bulk crew)."""
    return max(2, int((max_students or 100) * 0.08 * (1 + int(prestige or 50) / 100)))


def _university_output(research_rate: float, level: int, prestige: int) -> int:
    """University produce specialist crew — research-driven. Kadar kecil tapi pakar."""
    return max(1, int(float(research_rate or 1.0) * int(level or 1) * (1 + int(prestige or 0) / 100)))


async def produce_crew(session_id: int | None = None) -> dict:
    """Tick production: academy + university → crew_pool."""
    if session_id is None:
        session_id = Config.SESSION_ID
    gd = await Database.fetchval("SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id) or 1
    total = 0
    sources = []

    # Academy campuses (Karunia, Pelabuhan, Stasiun TKG, Heaven AI)
    for a in await Database.fetch("SELECT name, student_slots_used, max_students, prestige FROM maya_rp.academy_campuses"):
        out = _academy_output(a["student_slots_used"] or 0, a["max_students"] or 100, a["prestige"] or 50)
        total += out
        sources.append((f"academy:{a['name']}", out))

    # University campuses (Chen, Bisik, Vein, Ghost Signal)
    for u in await Database.fetch("SELECT name, research_rate, level, prestige FROM maya_rp.university_campuses"):
        out = _university_output(u["research_rate"] or 1.0, u["level"] or 1, u["prestige"] or 50)
        total += out
        sources.append((f"university:{u['name']}", out))

    if total > 0:
        await Database.execute(
            "UPDATE maya_rp.resources SET crew_pool=crew_pool+$1, crew_trained_total=crew_trained_total+$1 "
            "WHERE session_id=$2", total, session_id)
        pool = await Database.fetchval("SELECT crew_pool FROM maya_rp.resources WHERE session_id=$1", session_id)
        for src, amt in sources:
            await Database.execute(
                "INSERT INTO maya_rp.crew_production_log (session_id, game_day, source, amount, pool_after) "
                "VALUES ($1,$2,$3,$4,$5)", session_id, gd, src, amt, pool)
    return {"produced": total, "sources": sources}


async def consume_crew(session_id: int | None, ship_id: int, required: int) -> dict:
    """Ship launch consume crew dari pool. Kurang → undercrewed (penalty, bukan block)."""
    if session_id is None:
        session_id = Config.SESSION_ID
    gd = await Database.fetchval("SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id) or 1
    pool = await Database.fetchval("SELECT crew_pool FROM maya_rp.resources WHERE session_id=$1", session_id) or 0
    name = await Database.fetchval("SELECT name FROM maya_rp.ships WHERE id=$1", ship_id) or "?"

    if pool >= required:
        new_pool = pool - required
        await Database.execute(
            "UPDATE maya_rp.resources SET crew_pool=$1, crew_consumed_total=crew_consumed_total+$2 WHERE session_id=$3",
            new_pool, required, session_id)
        await Database.execute(
            "UPDATE maya_rp.ships SET crew_current=$1, undercrewed_penalty=0, status='active' WHERE id=$2",
            required, ship_id)
        await Database.execute(
            "INSERT INTO maya_rp.crew_consumption_log (session_id, game_day, ship_id, ship_name, amount, pool_after) "
            "VALUES ($1,$2,$3,$4,$5,$6)", session_id, gd, ship_id, name, required, new_pool)
        return {"consumed": required, "pool_after": new_pool, "status": "active"}

    # Shortage — undercrewed (Stakes Integrity: kapal jadi liability, bukan block)
    deficit = required - pool
    penalty = round(deficit / max(1, required), 3)
    await Database.execute(
        "UPDATE maya_rp.ships SET crew_current=$1, crew_required=$2, undercrewed_penalty=$3, status='undercrewed' "
        "WHERE id=$4", pool, required, penalty, ship_id)
    await Database.execute(
        "INSERT INTO maya_rp.crew_consumption_log (session_id, game_day, ship_id, ship_name, amount, pool_after) "
        "VALUES ($1,$2,$3,$4,$5,$6)", session_id, gd, ship_id, name, pool, 0)
    return {"consumed": pool, "deficit": deficit, "penalty": penalty, "status": "undercrewed"}


async def backfill_history(session_id: int | None = None, start_day: int = 26, end_day: int | None = None,
                           initial_consumption: int = 20000) -> dict:
    """Kira semula crew dari era old council (Day 26) sampai sekarang.
    Anggap academy/university beroperasi sejak Day 26 dengan kadar semasa.
    initial_consumption = anggaran crew yang dah dipakai era lama (narrative GM)."""
    if session_id is None:
        session_id = Config.SESSION_ID
    if end_day is None:
        end_day = await Database.fetchval("SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id) or 171

    # Kadar harian semasa
    acad = await Database.fetch("SELECT max_students, prestige FROM maya_rp.academy_campuses")
    univ = await Database.fetch("SELECT research_rate, level, prestige FROM maya_rp.university_campuses")
    daily = sum(_academy_output(0, a["max_students"] or 100, a["prestige"] or 50) for a in acad)
    daily += sum(_university_output(u["research_rate"] or 1.0, u["level"] or 1, u["prestige"] or 50) for u in univ)

    days = max(1, end_day - start_day)
    total_produced = daily * days

    # Consumption: kapal aktif sekarang (binaan era ini) — tapi hadkan ikut produced
    required = await Database.fetchval(
        "SELECT COALESCE(SUM(crew),0) FROM maya_rp.ships WHERE session_id=$1 AND status IN ('active','undercrewed')",
        session_id) or 0

    # Pool = produced - initial_consumption (clamp ≥ 0) — narrative: era lama dah guna sebahagian
    pool = max(0, total_produced - initial_consumption)
    consumed = total_produced - pool

    await Database.execute(
        "UPDATE maya_rp.resources SET crew_pool=$1, crew_trained_total=$2, crew_consumed_total=$3 WHERE session_id=$4",
        pool, total_produced, consumed, session_id)

    # Log ringkasan
    await Database.execute(
        "INSERT INTO maya_rp.crew_production_log (session_id, game_day, source, amount, pool_after) "
        "VALUES ($1,$2,'backfill_history',$3,$4)",
        session_id, end_day, total_produced, pool)

    return {"days": days, "daily_rate": daily, "total_produced": total_produced,
            "initial_consumption": initial_consumption, "pool": pool,
            "required_now": required, "shortage": max(0, required - pool)}


async def crew_report(session_id: int | None = None) -> dict:
    """Full crew report — dashboard untuk briefing."""
    if session_id is None:
        session_id = Config.SESSION_ID
    r = await Database.fetchrow(
        "SELECT crew_pool, crew_trained_total, crew_consumed_total FROM maya_rp.resources WHERE session_id=$1",
        session_id)
    required = await Database.fetchval(
        "SELECT COALESCE(SUM(crew),0) FROM maya_rp.ships WHERE session_id=$1 AND status IN ('active','undercrewed')",
        session_id) or 0
    ships = await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.ships WHERE session_id=$1 AND status IN ('active','undercrewed')",
        session_id) or 0
    undercrewed = await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.ships WHERE session_id=$1 AND status='undercrewed'", session_id) or 0
    named_crew = await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.crew_roster WHERE session_id=$1 AND status='active'", session_id) or 0

    pool = r["crew_pool"] if r else 0
    trained = r["crew_trained_total"] if r else 0
    consumed = r["crew_consumed_total"] if r else 0

    return {
        "crew_pool": pool,
        "crew_trained_total": trained,
        "crew_consumed_total": consumed,
        "crew_required_active": required,
        "ships_active": ships,
        "ships_undercrewed": undercrewed,
        "named_officers": named_crew,
        "shortage": max(0, required - pool),
        "coverage_pct": round(min(100, pool / max(1, required) * 100), 1),
    }


async def cmd(sid: int, action: str, params: dict) -> dict:
    if action == "report":
        return await crew_report(sid)
    if action == "produce":
        return await graduation_cycle(sid)   # sekarang = graduation cycle, bukan harian
    if action == "backfill":
        return await backfill_history(sid, params.get("start_day", 26), params.get("end_day"))
    if action == "consume":
        return await consume_crew(sid, params["ship_id"], params.get("required", params.get("crew", 10)))
    if action == "allocate":
        return await ai_allocate_crew(sid)   # Heaven AI allocation
    if action == "screen":
        return await screen_crew(sid, params["crew_id"], params.get("clearance", 5))
    if action == "set_clearance":
        return await set_min_clearance(sid, params["ship_id"], params.get("clearance", 5))
    return {"error": f"Unknown action '{action}' (report/produce/backfill/consume/allocate/screen/set_clearance)"}


async def run_tick(session_id: int | None = None) -> dict:
    if session_id is None:
        session_id = Config.SESSION_ID
    try:
        # 1. Graduation cycle (30 hari cohort — bukan harian)
        g = await graduation_cycle(session_id)
        # 2. Heaven AI allocation — auto-assign crew ke kapal
        a = await ai_allocate_crew(session_id)
        return {"graduated": g["graduated"], "ai_allocated": a["allocated"], "pool_after": a["pool_after"]}
    except Exception as e:
        info("crew_system", f"Tick error: {e}")
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════
# EXPANSION 083 — University per sistem + Graduation Cycle + AI Control
# 1. University expand ke setiap sistem (37 campuses)
# 2. Graduation cycle: cohort graduat setiap 30 hari (bukan harian — realistik)
# 3. AI allocation: Heaven AI urus crew dari Heaven core — 2 sistem kawalan
# 4. Clearance: C1-C4 market crew OK; C5+ kena loyalty tinggi / screened
# ═══════════════════════════════════════════════════════════════

async def graduation_cycle(session_id: int | None = None) -> dict:
    """Cohort graduat: setiap campus graduat pada cycle 30 hari.
    Bukan harian — realistik macam universiti sebenar."""
    if session_id is None:
        session_id = Config.SESSION_ID
    gd = await Database.fetchval("SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id) or 1
    campuses = await Database.fetch(
        "SELECT id, name, research_rate, level, prestige, graduation_cycle_days, last_graduation_day "
        "FROM maya_rp.university_campuses")
    total = 0
    graduated = []
    for c in campuses:
        cycle = c["graduation_cycle_days"] or 30
        last = c["last_graduation_day"] or 0
        # Graduat bila gd - last >= cycle (dan dah lulus sekurang-kurangnya satu cycle)
        if gd - last >= cycle:
            # Cohort size: prestasi campus (level + prestige + research) — setiap cycle
            cohort = max(5, int(float(c["research_rate"] or 1.0) * (c["level"] or 1)
                                * (1 + (c["prestige"] or 0) / 150)))
            total += cohort
            graduated.append((c["name"], cohort))
            await Database.execute(
                "UPDATE maya_rp.university_campuses SET last_graduation_day=$1 WHERE id=$2",
                gd, c["id"])
    if total > 0:
        await Database.execute(
            "UPDATE maya_rp.resources SET crew_pool=crew_pool+$1, crew_trained_total=crew_trained_total+$1 "
            "WHERE session_id=$2", total, session_id)
        pool = await Database.fetchval("SELECT crew_pool FROM maya_rp.resources WHERE session_id=$1", session_id)
        for name, amt in graduated:
            await Database.execute(
                "INSERT INTO maya_rp.crew_production_log (session_id, game_day, source, amount, pool_after) "
                "VALUES ($1,$2,$3,$4,$5)", session_id, gd, f"graduation:{name}", amt, pool)
    return {"day": gd, "graduated": total, "campuses": len(graduated)}


async def ai_allocate_crew(session_id: int | None = None) -> dict:
    """HEAVEN AI CONTROL — urus alokasi crew dari Heaven core.
    Prioriti: C5+ (tier>=5) crew clearance/loyalty/screened dulu, lepas tu C1-C4 (tier<5).
    Pool numeric → crew_roster rows diwujudkan (functional crew) semasa allocate."""
    if session_id is None:
        session_id = Config.SESSION_ID
    gd = await Database.fetchval("SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id) or 1
    pool = await Database.fetchval("SELECT crew_pool FROM maya_rp.resources WHERE session_id=$1", session_id) or 0
    if pool <= 0:
        return {"allocated": 0, "pool": 0, "note": "Pool kosong — tunggu graduation/recruitment"}

    # Semua kapal yang perlukan crew (undercrewed / crew_current < crew), prioriti tier tinggi dulu
    ships = await Database.fetch(
        """SELECT id, name, tier, crew, crew_current, min_clearance
           FROM maya_rp.ships
           WHERE session_id=$1 AND status IN ('active','undercrewed')
             AND (crew_current IS NULL OR crew_current < crew)
           ORDER BY tier DESC, crew DESC""", session_id)

    allocated = 0
    details = []
    # Nama generik untuk functional crew — gunakan name_gen (unique, first+family, no canon collision)
    from core.name_gen import NameGenerator
    _name_gen = NameGenerator(Database.pool if hasattr(Database, "pool") else None)
    for s in ships:
        if pool <= 0:
            break
        need = (s["crew"] or 0) - (s["crew_current"] or 0)
        if need <= 0:
            continue
        min_clr = s["min_clearance"] or (5 if (s["tier"] or 0) >= 5 else 1)
        # C5+ (tier>=5): kena crew clearance >=5 (screened)
        if min_clr >= 5:
            avail = await Database.fetchval(
                """SELECT COUNT(*) FROM maya_rp.crew_roster
                   WHERE session_id=$1 AND ship_id IS NULL AND status='active'
                     AND clearance_level >= 5 AND screened=true""", session_id) or 0
            take = min(need, avail, pool)
        else:
            # C1-C4: mana-mana crew functional — cipta dari pool kalau crew_roster tak cukup
            avail = await Database.fetchval(
                """SELECT COUNT(*) FROM maya_rp.crew_roster
                   WHERE session_id=$1 AND ship_id IS NULL AND status='active'""", session_id) or 0
            take = min(need, avail, pool)
        if take <= 0:
            continue
        # Jika crew_roster tak cukup (pool numeric > rows), cipta crew rows dari pool
        rows_needed = take
        while rows_needed > 0:
            existing_free = await Database.fetchval(
                """SELECT COUNT(*) FROM maya_rp.crew_roster WHERE session_id=$1 AND ship_id IS NULL AND status='active'""",
                session_id) or 0
            if existing_free <= 0:
                # Cipta functional crew dari pool — unique first+family name
                clr = min_clr
                crew_name = await _name_gen.unique_crew_name()
                await Database.execute(
                    """INSERT INTO maya_rp.crew_roster (session_id, name, role, status, loyalty_flag, clearance_level, screened)
                       VALUES ($1, $2, $3, 'active', 'neutral', $4, $5)""",
                    session_id, crew_name,
                    "crew", clr, clr >= 5)
            rows_needed -= 1
        # Assign crew (screened dulu untuk C5+)
        if min_clr >= 5:
            await Database.execute(
                """UPDATE maya_rp.crew_roster SET ship_id=$1 WHERE id IN
                   (SELECT id FROM maya_rp.crew_roster WHERE session_id=$2 AND ship_id IS NULL
                    AND status='active' AND clearance_level>=5 AND screened=true LIMIT $3)""",
                s["id"], session_id, take)
        else:
            await Database.execute(
                """UPDATE maya_rp.crew_roster SET ship_id=$1 WHERE id IN
                   (SELECT id FROM maya_rp.crew_roster WHERE session_id=$2 AND ship_id IS NULL
                    AND status='active' LIMIT $3)""",
                s["id"], session_id, take)
        new_crew = (s["crew_current"] or 0) + take
        status = "active" if new_crew >= (s["crew"] or 0) else "undercrewed"
        penalty = 0 if status == "active" else round(((s["crew"] or 1) - new_crew) / (s["crew"] or 1), 3)
        await Database.execute(
            "UPDATE maya_rp.ships SET crew_current=$1, status=$2, undercrewed_penalty=$3 WHERE id=$4",
            new_crew, status, penalty, s["id"])
        pool -= take
        allocated += take
        details.append({"ship": s["name"], "assigned": take, "status": status})
        await Database.execute(
            "INSERT INTO maya_rp.crew_allocation_log (session_id, game_day, ship_id, ship_name, crew_assigned, source) "
            "VALUES ($1,$2,$3,$4,$5,'ai_heaven')", session_id, gd, s["id"], s["name"], take)

    await Database.execute(
        "UPDATE maya_rp.resources SET crew_pool=$1 WHERE session_id=$2", pool, session_id)
    return {"allocated": allocated, "pool_after": pool, "ships": details}


async def screen_crew(session_id: int | None, crew_id: int, clearance: int = 5) -> dict:
    """Screen crew untuk C5+ clearance — Kira/Heaven AI vetting."""
    if session_id is None:
        session_id = Config.SESSION_ID
    cr = await Database.fetchrow(
        "SELECT id, name, loyalty FROM maya_rp.crew_roster WHERE id=$1 AND session_id=$2", crew_id, session_id)
    if not cr:
        return {"error": "Crew not found"}
    await Database.execute(
        "UPDATE maya_rp.crew_roster SET clearance_level=$1, screened=true WHERE id=$2",
        clearance, crew_id)
    return {"screened": cr["name"], "clearance": clearance, "loyalty": cr["loyalty"]}


async def set_min_clearance(session_id: int | None, ship_id: int, clearance: int) -> dict:
    """Tetapkan min clearance untuk kapal (C5+ = 5)."""
    if session_id is None:
        session_id = Config.SESSION_ID
    await Database.execute(
        "UPDATE maya_rp.ships SET min_clearance=$1 WHERE id=$2 AND session_id=$3",
        clearance, ship_id, session_id)
    return {"ship_id": ship_id, "min_clearance": clearance}
