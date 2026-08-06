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
        return await produce_crew(sid)
    if action == "backfill":
        return await backfill_history(sid, params.get("start_day", 26), params.get("end_day"))
    if action == "consume":
        return await consume_crew(sid, params["ship_id"], params.get("required", params.get("crew", 10)))
    return {"error": f"Unknown action '{action}' (report/produce/backfill/consume)"}


async def run_tick(session_id: int | None = None) -> dict:
    if session_id is None:
        session_id = Config.SESSION_ID
    try:
        r = await produce_crew(session_id)
        return {"produced": r["produced"]}
    except Exception as e:
        info("crew_system", f"Tick error: {e}")
        return {"error": str(e)}
