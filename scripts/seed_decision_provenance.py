#!/usr/bin/env python3
"""Seed decision-provenance chains (Semantica plan Fasa 1).

Backfills parent_id / game_day / event_ids / state_after for the three
canonical arcs of Day 2191-2194 (Big Fish Doctrine night + RS-2 sign-off
+ Magnetar saga). All decisions already exist as cabinet_decrees or
grand_plan items — this script links them into provable causal chains.

Each RS-2 decree is looked up by title in the session first and inserted only when absent.

  python3 scripts/seed_decision_provenance.py --session N            # report only
  python3 scripts/seed_decision_provenance.py --session N --apply    # write in one transaction
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from core.db import Database
from scripts._oneshot import parse, guard

ROOT_TITLE = "RS-2 P1+P3 SIGNED"
P2_TITLE = "RS-2 P2 + MINISTRY TRACKS SIGNED"
FIND_DECREE = ("SELECT id FROM maya_rp.cabinet_decrees WHERE session_id=$1 AND title=$2 "
               "ORDER BY id LIMIT 1")


async def main(argv=None) -> int:
    args = parse(__doc__, argv)
    guard(args)
    sid = args.session
    await Database.init()

    # ── Chain A: Big Fish Doctrine (Day 2191) ─────────────────────────
    links = [
        # (child, parent, game_day, state_after, event_ids)
        (19, 18, 2191, {"ships_released": 734, "mode": "downtime", "treasury": 582200000000},
         [18888, 18889]),
        (20, 19, 2191, {"magnetar": "destabilized", "status": "thread_closed"},
         [18890, 18893, 18894, 18895, 18896]),
    ]
    root = await Database.fetchval(FIND_DECREE, sid, ROOT_TITLE)
    p2 = await Database.fetchval(FIND_DECREE, sid, P2_TITLE)

    if not args.apply:
        for child, parent, day, _delta, _evs in links:
            found = await Database.fetchval(
                "SELECT id FROM maya_rp.cabinet_decrees WHERE id=$1 AND session_id=$2", child, sid)
            if found is None:
                print(f"WARN decree {child} not found in session {sid}")
            else:
                print(f"would link decree {child} to parent {parent} at day {day}")
        print(f"would {'keep' if root else 'insert'} '{ROOT_TITLE}'" + (f" (decree {root})" if root else ""))
        print(f"would {'keep' if p2 else 'insert'} '{P2_TITLE}'" + (f" (decree {p2})" if p2 else ""))
        print(f"would extend the evidence of decree {links[-1][0]}")
        print("DRY RUN — re-run with --apply to write.")
        await Database.close()
        return 0

    async with Database.transaction() as conn:
        for child, parent, day, delta, evs in links:
            tag = await conn.execute(
                "UPDATE maya_rp.cabinet_decrees SET parent_id=$1, game_day=$2, "
                "state_after=$3::jsonb, event_ids=$4::int[] WHERE id=$5 AND session_id=$6",
                parent, day, json.dumps(delta), evs, child, sid)
            if not tag.endswith("1"):
                print(f"WARN decree {child} not found in session {sid}")

        # ── Chain B: RS-2 sign-off (Day 2096 sign -> Day 2194 execute) ─────
        if root is None:
            root_desc = ("Golden Age plan funding - signed backing, executed Day 2194 (event 18912)")
            root = await conn.fetchval(
                "INSERT INTO maya_rp.cabinet_decrees "
                "(session_id, issued_by, decree_type, title, description, status, priority, "
                " secrecy_level, game_day, state_after, impact_deltas) "
                "VALUES ($1,'Izzat','economic',$2,$3,'completed','critical','public',"
                " 2096, $4::jsonb, $5::jsonb) RETURNING id",
                sid, ROOT_TITLE, root_desc,
                json.dumps({"plan_approved": 26, "treasury": 685000000000}),
                json.dumps({"P1": 200000000000, "P3": 115000000000}))
            print("RS-2 root decree:", root)
        else:
            print("RS-2 root decree exists:", root)

        if p2 is None:
            p2_desc = ("sign n go - Day 2194")
            p2 = await conn.fetchval(
                "INSERT INTO maya_rp.cabinet_decrees "
                "(session_id, issued_by, decree_type, title, description, status, priority, "
                " secrecy_level, parent_id, game_day, state_after, impact_deltas, event_ids) "
                "VALUES ($1,'Izzat','economic',$2,$3,"
                " 'completed','critical','public',$4,2194,"
                " $5::jsonb, $6::jsonb, ARRAY[18912]) RETURNING id",
                sid, P2_TITLE, p2_desc, root,
                json.dumps({"plan_approved": 57}), json.dumps({"P2": 21000000000, "ministry": 433000000000}))
            print("P2+ministry decree:", p2)
        else:
            print("P2+ministry decree exists:", p2)

        # ── Chain C: Magnetar saga — extend the evidence of the chain's last decree ─────
        await conn.execute(
            "UPDATE maya_rp.cabinet_decrees SET event_ids = "
            "ARRAY(SELECT DISTINCT unnest(event_ids || ARRAY[18897,18901])) "
            "WHERE id=$2 AND session_id=$1", sid, links[-1][0])

    # ── Verify ────────────────────────────────────────────────────────
    rows = await Database.fetch(
        "SELECT id, parent_id, game_day, title FROM maya_rp.cabinet_decrees "
        "WHERE session_id=$1 AND id IN (18,19,20,21,$2,$3) ORDER BY id",
        sid, root, p2)
    for r in rows:
        print(f"  #{r['id']} parent={r['parent_id']} D{r['game_day']} {r['title'][:55]}")
    await Database.close()
    print("SEED DONE")
    return 0


if __name__ == "__main__":
    import asyncio
    raise SystemExit(asyncio.run(main()))
