#!/usr/bin/env python3
"""Population sentiment — how the PEOPLE feel, per system × per faction.

Model (Izzat, Day 1383): population is resource-driven and faction-INDEPENDENT.
Sentiment tracks what people think OF factions, never ownership of the people.

Drivers (tick + on-demand):
  - morale            → base sentiment pull (territory.morale)
  - tax_rate          → approval drop when taxes high
  - crisis_level      → fear up, approval down
  - slave_revolt_risk → fear up
  - food/resource     → food modifiers low = approval down (resource→people rule)
  - news bias         → news_articles.faction_bias shifts bias + sentiment
  - governor          → governor presence +title_performance → trust
"""
from __future__ import annotations
from typing import Any
from core.db import Database
from core.config import Config
from core.log import info

SID = Config.SESSION_ID

# Weighted drivers (all clamped -100..100 / 0..100)
W_MORALE  = 0.30
W_TAX     = 0.20
W_CRISIS  = 0.15
W_FEAR    = 0.15
W_RES     = 0.10
W_GOV     = 0.10


def _clamp(v: float, lo: int = -100, hi: int = 100) -> int:
    return int(max(lo, min(hi, round(v))))


async def init_for_territory(session_id: int | None = None) -> int:
    """Ensure every territory has baseline rows (governor faction + Setia Empire)."""
    if session_id is None:
        session_id = SID
    n = 0
    for t in await Database.fetch(
            "SELECT id, controlling_faction FROM maya_rp.territory WHERE session_id=$1", session_id):
        facs = [t["controlling_faction"]] if t["controlling_faction"] else []
        facs.append("Setia Empire (Kingdom)")
        for f in facs:
            r = await Database.execute(
                """INSERT INTO maya_rp.population_sentiment
                   (session_id, territory_id, faction_name, sentiment, approval, fear, trust, bias, last_shift_reason)
                   VALUES ($1,$2,$3,5,55,10,45,0,'seed: governance baseline')
                   ON CONFLICT (session_id, territory_id, faction_name) DO NOTHING""",
                session_id, t["id"], f)
            n += r  # type: ignore
    return n


async def refresh(session_id: int | None = None, territory_id: int | None = None) -> dict:
    """Recompute sentiment for all rows (or one territory). Returns updated count."""
    if session_id is None:
        session_id = SID
    rows = await Database.fetch(
        """SELECT ps.id, ps.territory_id, ps.faction_name,
                  t.morale, t.tax_rate, t.crisis_level, t.slave_revolt_risk,
                  t.title_performance, t.governor_name, t.id AS tid
           FROM maya_rp.population_sentiment ps
           JOIN maya_rp.territory t ON t.id = ps.territory_id
           WHERE ps.session_id=$1 AND ($2::int IS NULL OR ps.territory_id=$2::int)""",
        session_id, territory_id)
    updated = 0
    for r in rows:
        morale   = float(r["morale"] if r["morale"] is not None else 50)
        tax      = float(r["tax_rate"] if r["tax_rate"] is not None else 0.05)
        crisis   = float(r["crisis_level"] if r["crisis_level"] is not None else 0)
        revolt   = float(r["slave_revolt_risk"] if r["slave_revolt_risk"] is not None else 0)
        gov_perf = float(r["title_performance"] if r["title_performance"] is not None else 50)
        has_gov  = 1 if (r["governor_name"] and r["governor_name"] != "") else 0

        # approval: base 55 + morale pull + gov - tax penalty - crisis
        approval = 55 + (morale - 50) * 0.4 + has_gov * 8 - (tax - 0.05) * 120 - crisis * 6
        # fear: base 10 + crisis + revolt - trust in governor
        fear = 10 + crisis * 8 + revolt * 10 - has_gov * 4
        # trust: base 45 + gov perf pull - crisis
        trust = 45 + (gov_perf - 50) * 0.3 - crisis * 3
        # sentiment: net = approval - fear, weighted
        sentiment = approval * 0.55 - fear * 0.45

        approval = _clamp(approval, 0, 100)
        fear     = _clamp(fear, 0, 100)
        trust    = _clamp(trust, 0, 100)
        new_sent = _clamp(sentiment)

        old = r["faction_name"]  # for reason logging we just note driver set
        reason = f"drivers: morale {morale} tax {round(tax*100)}% crisis {crisis} revolt {round(revolt*100)}% gov {'y' if has_gov else 'n'}"
        await Database.execute(
            """UPDATE maya_rp.population_sentiment
               SET sentiment=$2, approval=$3, fear=$4, trust=$5,
                   last_shift = $2 - (SELECT sentiment FROM maya_rp.population_sentiment WHERE id=$1),
                   last_shift_reason=$6, updated_at=NOW()
               WHERE id=$1""",
            r["id"], new_sent, approval, fear, trust, reason)
        updated += 1
    return {"updated": updated}


async def shift(session_id: int | None, territory_id: int, faction_name: str,
                delta: int, reason: str) -> dict:
    """Manual/narrative shift (news, events, decrees). Clamped."""
    if session_id is None:
        session_id = SID
    row = await Database.fetchrow(
        """SELECT id, sentiment FROM maya_rp.population_sentiment
           WHERE session_id=$1::int AND territory_id=$2::int AND faction_name=$3::text""",
        session_id, territory_id, faction_name)
    if not row:
        return {"error": f"no sentiment row for {faction_name} @ {territory_id}"}
    new = _clamp(row["sentiment"] + delta)
    await Database.execute(
        """UPDATE maya_rp.population_sentiment
           SET sentiment=$2, last_shift=$3, last_shift_reason=$4, updated_at=NOW()
           WHERE id=$1""",
        row["id"], new, new - row["sentiment"], reason)
    return {"territory_id": territory_id, "faction": faction_name, "sentiment": new, "delta": delta, "reason": reason}


async def apply_news_bias(session_id: int | None = None, limit: int = 50) -> int:
    """Pull recent news faction_bias into sentiment shifts."""
    if session_id is None:
        session_id = SID
    news = await Database.fetch(
        """SELECT id, headline, faction_bias, game_day FROM maya_rp.news_articles
           WHERE session_id=$1 ORDER BY id DESC LIMIT $2""",
        session_id, limit)
    applied = 0
    for n in news:
        fb = n["faction_bias"] or ""
        if not fb:
            continue
        # bias column: news about faction X -> nudge all systems' sentiment toward X
        # simple driver: bias value 0..1 (or text) — treat nonzero as +3 nudge
        try:
            delta = 3 if float(fb) > 0.5 else -3 if float(fb) < -0.5 else 0
        except (TypeError, ValueError):
            delta = 0
        if delta:
            await Database.execute(
                """UPDATE maya_rp.population_sentiment
                   SET sentiment = GREATEST(-100, LEAST(100, sentiment + $3)),
                       bias = GREATEST(0, LEAST(100, bias + $4)),
                       last_shift_reason = COALESCE(last_shift_reason, '') || '; news#' || $5,
                       updated_at = NOW()
                   WHERE session_id=$1 AND territory_id IN
                     (SELECT id FROM maya_rp.territory WHERE session_id=$1)
                     AND faction_name ILIKE '%' || $6 || '%'""",
                session_id, n["id"], delta, 2, n["id"], fb)
            applied += 1
    return applied


async def run_tick(session_id: int | None = None) -> dict:
    """Tick hook: refresh all + apply news bias."""
    if session_id is None:
        session_id = SID
    init_for_territory(session_id)  # ensure rows
    ref = await refresh(session_id)
    nb = await apply_news_bias(session_id)
    info("sentiment", f"refreshed {ref['updated']} rows, news bias {nb} articles")
    return {**ref, "news_bias_applied": nb}


async def status(session_id: int | None = None, territory_id: int | None = None,
                 faction_name: str | None = None) -> list[dict]:
    if session_id is None:
        session_id = SID
    q = """SELECT ps.territory_id, t.system_name, ps.faction_name, ps.sentiment,
                  ps.approval, ps.fear, ps.trust, ps.bias, ps.last_shift_reason, ps.updated_at
           FROM maya_rp.population_sentiment ps
           JOIN maya_rp.territory t ON t.id = ps.territory_id
           WHERE ps.session_id=$1"""
    args: list[Any] = [session_id]
    if territory_id is not None:
        q += " AND ps.territory_id=$2"
        args.append(territory_id)
    if faction_name:
        q += " AND ps.faction_name ILIKE $3" if territory_id is None else " AND ps.faction_name ILIKE $3"
        args.append(f"%{faction_name}%")
    q += " ORDER BY ps.sentiment DESC"
    return await Database.fetch(q, *args)