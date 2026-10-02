#!/usr/bin/env python3
"""TKG Calendar — 12 months x 30 days plus 5 leftover days. Game time, holidays, seasons.

Canon (`CURRENCY-CALENDAR-2026-10-02.md`, decision D5): twelve months of thirty days, then
five leftover days that belong to no month, for 365 in a year. The five days were previously
rolled into a 360-day cycle, which contradicted the ruling, so the cycle was corrected here.

The correction moves the printed date of any day after day 360. `game_day` itself is
unchanged, and every stored number stays as it was; only the label the calendar puts on it
shifts. Session 3 is frozen, so its historical dates print under the new rule and that shift
is recorded in the canon doc rather than hidden.
"""
from __future__ import annotations
import json
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info

MONTHS = ["Harapan","Lautan","Bintang","Api","Daun","Hujan",
          "Tanah","Padi","Angin","Bulan","Senja","Malam"]
DAYS_PER_MONTH = 30
MONTH_DAYS = DAYS_PER_MONTH * len(MONTHS)   # 360
LEFTOVER_DAYS = 5                           # the leftover days, canon D5
LEFTOVER_NAME = "Hari Sisa"                 # proposed name; canon does not fix one yet
YEAR_DAYS = MONTH_DAYS + LEFTOVER_DAYS      # 365
SEASONS = {"Harapan":"new_year","Lautan":"monsoon","Bintang":"dry","Api":"dry",
           "Daun":"transition","Hujan":"monsoon","Tanah":"harvest","Padi":"harvest",
           "Angin":"transition","Bulan":"cool","Senja":"cool","Malam":"winter"}
HOLIDAYS = {
    (1,1):   {"name":"Hari Harapan","type":"festival","bonus":5,"desc":"New Year — fresh start"},
    (4,15):  {"name":"Hari Api Menggila","type":"ceremony","bonus":2,"desc":"Fire festival — boldness celebrated"},
    (7,1):   {"name":"Malam Panen","type":"festival","bonus":5,"desc":"Harvest festival — abundance"},
    (10,10): {"name":"Malam Bulan Penuh","type":"romantic","bonus":3,"desc":"Full moon — romance peaks"},
    (12,30): {"name":"Malam Hitam","type":"somber","bonus":-2,"desc":"Stillness before renewal"},
}

async def advance_day(session_id: int) -> dict:
    """Advance game day by 1 and return the new date."""
    row = await Database.fetchrow("SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id)
    if not row:
        return {"error": "No session found"}
    new_day = (row["game_day"] or 1) + 1
    await Database.execute("UPDATE maya_rp.sessions SET game_day=$1 WHERE id=$2", new_day, session_id)
    date = await get_game_date(session_id, new_day)
    if not date:
        return {"error": "Failed to get date"}
    info("calendar", f"Day {new_day}: {date.get('formatted', '?')}")
    return date

async def get_game_date(session_id: int, game_day: int = None) -> dict:
    """Convert game_day to date."""
    if game_day is None:
        row = await Database.fetchrow("SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id)
        game_day = (row["game_day"] or 1) if row else 1
    year = (game_day - 1) // YEAR_DAYS + 1
    doy = (game_day - 1) % YEAR_DAYS + 1
    leftover = doy > MONTH_DAYS
    if leftover:
        m_idx, dom = None, doy - MONTH_DAYS
        month = LEFTOVER_NAME
    else:
        m_idx = (doy - 1) // DAYS_PER_MONTH
        dom = (doy - 1) % DAYS_PER_MONTH + 1
        month = MONTHS[m_idx]
    season = "leftover" if leftover else SEASONS.get(month, "transition")

    holiday = None
    key = None if leftover else (m_idx + 1, dom)
    if key and key in HOLIDAYS:
        holiday = HOLIDAYS[key]
        holiday["days_until"] = 0

    return {
        "raw_day": game_day,
        "year": year,
        "month": month,
        "month_num": m_idx + 1 if m_idx is not None else None,
        "leftover": leftover,
        "day": dom,
        "doy": doy,
        "season": season,
        "holiday": holiday,
        "formatted": (f"Hari Sisa {dom}, Year {year}" if leftover
                      else f"{dom} {month}, Year {year}"),
    }

async def apply_holiday(date: dict, session_id: int):
    """Apply holiday effects."""
    if not date or not date.get("holiday"):
        return
    h = date["holiday"]
    await Database.execute(
        "INSERT INTO maya_rp.events (session_id, happened_at, event_type, title, description, tags, importance) "
        "VALUES ($1, NOW(), 'holiday', $2, $3, $4, 3)",
        session_id,
        f"Holiday: {h['name']}",
        f"The fleet observes {h['name']}. {h.get('desc','')}",
        json.dumps(["calendar", "holiday", h["type"]]))
    # economy/morale hook (2026-08-14): festivals boost crew morale; the
    # Crown covers festival costs — somber days slow spending instead.
    bonus = h.get("bonus", 0)
    if bonus != 0:
        await Database.execute(
            "UPDATE maya_rp.crew_roster SET morale=LEAST(100, morale+$1) WHERE session_id=$2",
            bonus, session_id)
        spend = max(0, bonus) * 2000
        if spend:
            await Database.execute(
                "UPDATE maya_rp.resources SET credits=GREATEST(0, credits-$1) WHERE session_id=$2",
                spend, session_id)

async def get_upcoming(session_id: int, lookahead: int = 30) -> list[dict]:
    """Holidays in the next N game days."""
    date = await get_game_date(session_id)
    if not date:
        return []
    events = []
    for i in range(lookahead):
        check_day = date.get("raw_day", 1) + i
        check_doy = (check_day - 1) % YEAR_DAYS + 1
        if check_doy > MONTH_DAYS:
            continue  # the leftover days carry no holiday
        m_idx = (check_doy - 1) // DAYS_PER_MONTH
        dom = (check_doy - 1) % DAYS_PER_MONTH + 1
        key = (m_idx + 1, dom)
        if key in HOLIDAYS:
            h = dict(HOLIDAYS[key])
            h["days_until"] = i
            h["date"] = f"{dom} {MONTHS[m_idx]}"
            events.append(h)
    return events[:10]

async def run_tick(session_id: int = None) -> dict:
    """Calendar tick: advance day, apply holiday, check upcoming, quarterly tasks."""
    if session_id is None:
        session_id = Config.SESSION_ID
    try:
        date = await advance_day(session_id)
        if not date or "error" in date:
            return {"error": str(date)}
        await apply_holiday(date, session_id)
        upcoming = await get_upcoming(session_id, 7)
        # NOVEL ULTIMATE #2 — Quarterly tasks: setiap 90 hari jana 4 misi baru
        qt = {}
        try:
            gd = await Database.fetchval("SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id)
            if gd and gd % 90 == 0:
                from modules.objectives import generate_quarterly_tasks
                qt = await generate_quarterly_tasks(session_id)
        except Exception as e:
            info("calendar", f"Quarterly tasks check error: {e}")
        info("calendar", f"{date.get('formatted','?')} | Season: {date.get('season','?')} | Upcoming: {len(upcoming)}")
        return {
            "date": date["formatted"],
            "season": date["season"],
            "holiday": (date.get("holiday") or {}).get("name"),
            "upcoming": upcoming,
        }
    except Exception as e:
        info("calendar", f"Error: {e}")
        return {"error": str(e)}
