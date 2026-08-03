#!/usr/bin/env python3
"""TKG Calendar — 12 months x 30 days. Game time, holidays, seasons."""
from __future__ import annotations
import json
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info

MONTHS = ["Harapan","Lautan","Bintang","Api","Daun","Hujan",
          "Tanah","Padi","Angin","Bulan","Senja","Malam"]
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
    year = (game_day - 1) // 360 + 1
    doy = (game_day - 1) % 360 + 1
    m_idx = (doy - 1) // 30
    dom = (doy - 1) % 30 + 1
    month = MONTHS[m_idx]
    season = SEASONS.get(month, "transition")

    holiday = None
    key = (m_idx + 1, dom)
    if key in HOLIDAYS:
        holiday = HOLIDAYS[key]
        holiday["days_until"] = 0

    return {
        "raw_day": game_day,
        "year": year,
        "month": month,
        "month_num": m_idx + 1,
        "day": dom,
        "doy": doy,
        "season": season,
        "holiday": holiday,
        "formatted": f"{dom} {month}, Year {year}",
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

async def get_upcoming(session_id: int, lookahead: int = 30) -> list[dict]:
    """Holidays in the next N game days."""
    date = await get_game_date(session_id)
    if not date:
        return []
    events = []
    for i in range(lookahead):
        check_day = date.get("raw_day", 1) + i
        check_doy = (check_day - 1) % 360 + 1
        m_idx = (check_doy - 1) // 30
        dom = (check_doy - 1) % 30 + 1
        key = (m_idx + 1, dom)
        if key in HOLIDAYS:
            h = dict(HOLIDAYS[key])
            h["days_until"] = i
            h["date"] = f"{dom} {MONTHS[m_idx]}"
            events.append(h)
    return events[:10]

async def run_tick(session_id: int = None) -> dict:
    """Calendar tick: advance day, apply holiday, check upcoming."""
    if session_id is None:
        session_id = Config.SESSION_ID
    try:
        date = await advance_day(session_id)
        if not date or "error" in date:
            return {"error": str(date)}
        await apply_holiday(date, session_id)
        upcoming = await get_upcoming(session_id, 7)
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
