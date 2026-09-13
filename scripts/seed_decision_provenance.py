#!/usr/bin/env python3
"""Seed decision-provenance chains (Semantica plan Fasa 1).

Backfills parent_id / game_day / event_ids / state_after for the three
canonical arcs of Day 2191-2194 (Big Fish Doctrine night + RS-2 sign-off
+ Magnetar saga). All decisions already exist as cabinet_decrees or
grand_plan items — this script links them into provable causal chains.
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from core.db import Database
from core.config import Config

SID = Config.SESSION_ID

async def main():
    await Database.init()

    # ── Chain A: Big Fish Doctrine (Day 2191) ─────────────────────────
    links = [
        # (child, parent, game_day, state_after, event_ids)
        (19, 18, 2191, {"ships_released": 734, "mode": "downtime", "treasury": 582200000000},
         [18888, 18889]),
        (20, 19, 2191, {"magnetar": "destabilized", "status": "thread_closed"},
         [18890, 18893, 18894, 18895, 18896]),
    ]
    for child, parent, day, delta, evs in links:
        await Database.execute(
            "UPDATE maya_rp.cabinet_decrees SET parent_id=$1, game_day=$2, "
            "state_after=$3::jsonb, event_ids=$4::int[] WHERE id=$5 AND session_id=$6",
            parent, day, json.dumps(delta), evs, child, SID)

    # ── Chain B: RS-2 sign-off (Day 2096 sign -> Day 2194 execute) ─────
    root_desc = ("Golden Age plan funding - signed backing, executed Day 2194 (event 18912)")
    root = await Database.fetchval(
        "INSERT INTO maya_rp.cabinet_decrees "
        "(session_id, issued_by, decree_type, title, description, status, priority, "
        " secrecy_level, game_day, state_after, impact_deltas) "
        "VALUES ($1,'Izzat','economic','RS-2 P1+P3 SIGNED',$2,'completed','critical','public',"
        " 2096, $3::jsonb, $4::jsonb) RETURNING id",
        SID, root_desc,
        json.dumps({"plan_approved": 26, "treasury": 685000000000}),
        json.dumps({"P1": 200000000000, "P3": 115000000000}))
    print("RS-2 root decree:", root)

    p2_desc = ("sign n go - Day 2194")
    p2 = await Database.fetchval(
        "INSERT INTO maya_rp.cabinet_decrees "
        "(session_id, issued_by, decree_type, title, description, status, priority, "
        " secrecy_level, parent_id, game_day, state_after, impact_deltas, event_ids) "
        "VALUES ($1,'Izzat','economic','RS-2 P2 + MINISTRY TRACKS SIGNED',$2,"
        " 'completed','critical','public',$3,2194,"
        " $4::jsonb, $5::jsonb, ARRAY[18912]) RETURNING id",
        SID, p2_desc, root,
        json.dumps({"plan_approved": 57}), json.dumps({"P2": 21000000000, "ministry": 433000000000}))
    print("P2+ministry decree:", p2)

    # ── Chain C: Magnetar saga — extend decree 20 evidence ─────────────
    await Database.execute(
        "UPDATE maya_rp.cabinet_decrees SET event_ids = "
        "ARRAY(SELECT DISTINCT unnest(event_ids || ARRAY[18897,18901])) "
        "WHERE id=20 AND session_id=$1", SID)

    # ── Verify ────────────────────────────────────────────────────────
    rows = await Database.fetch(
        "SELECT id, parent_id, game_day, title FROM maya_rp.cabinet_decrees "
        "WHERE session_id=$1 AND id IN (18,19,20,21,$2,$3) ORDER BY id",
        SID, root, p2)
    for r in rows:
        print(f"  #{r['id']} parent={r['parent_id']} D{r['game_day']} {r['title'][:55]}")
    await Database.close()
    print("SEED DONE")

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
