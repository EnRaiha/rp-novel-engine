import os
#!/usr/bin/env python3
"""FLEET EXPANSION WORKFLOW — automated executor.

Trigger: user says "expand" / "expand 2 legion" / "expand Legion X to standard".

Implements the SOP (Bumi-Hijau/main/reference/fleet-expansion-workflow.md):
  Phase 0 PLAN → Phase 1 ANALYSIS (recommend) → Phase 2 QUEUE (engineering)
  → Phase 3 CREW REQUIREMENT → Phase 4 CREW ASSIGN → Phase 5 OFFICER+COMMANDER
  → Phase 6 DOCKYARD ROUTING → Phase 7 REPORT+CHECKPOINT.

Usage:
  python3 scripts/fleet_expansion.py                       # analyze + recommend only (dry)
  python3 scripts/fleet_expansion.py --commit              # execute full workflow
  python3 scripts/fleet_expansion.py --legion "Legion X"   # expand specific legion to 100±20%
  python3 scripts/fleet_expansion.py --count 2             # build 2 new legions

Standard: 1 legion = 100 ships ±20% (80-120). Cost/crew models in legion_build_program.
"""
import asyncio, sys, argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.config import Config
from core.db import Database

SID = Config.SESSION_ID
STD_MIN, STD_MAX, STD_TARGET = 80, 120, 100
WAR_TARGET = 100   # warships per legion — the hard standard (100 ±20%)
SUP_TARGET = 20    # support ships: AUTO-FILL appropriate number per legion (commander can request more)

COST = {  # type -> (credit, alloy, days)
    "battle_cruiser":  (25_000_000, 12_000, 8),
    "medium_cruiser":  (8_000_000, 4_000, 5),
    "frigate":         (3_000_000, 1_500, 3),
    "interceptor":     (1_500_000, 800, 2),
    "patrol_boat":     (1_200_000, 600, 2),
    "spy_plane":       (2_000_000, 900, 3),
    "bomber":          (2_500_000, 1_200, 3),
    "science_small":   (2_500_000, 1_000, 4),
    "supply_courier":  (1_000_000, 500, 2),
    "fuel_tanker":     (1_200_000, 600, 2),
    "repair_tender":   (1_500_000, 700, 3),
    "ammo_ship":       (1_200_000, 600, 3),
}
CREW = {"battle_cruiser": 402, "medium_cruiser": 103, "frigate": 24, "interceptor": 10,
        "patrol_boat": 11, "spy_plane": 6, "bomber": 11, "science_small": 50,
        "supply_courier": 11, "fuel_tanker": 24, "repair_tender": 57, "ammo_ship": 22}
# Warship template (100 per legion — the hard standard)
WAR_TEMPLATE = [("battle_cruiser", 2), ("medium_cruiser", 12), ("frigate", 20),
                ("interceptor", 40), ("patrol_boat", 12), ("spy_plane", 8), ("bomber", 6)]
# Support package (20 per legion — appropriate support)
SUP_TEMPLATE = [("supply_courier", 8), ("fuel_tanker", 4), ("science_small", 4),
                ("repair_tender", 2), ("ammo_ship", 2)]
WAR_TYPES = {t for t, _ in WAR_TEMPLATE}
SUP_TYPES = {t for t, _ in SUP_TEMPLATE}


def composition(gap_war: int, gap_sup: int) -> list[tuple]:
    """Scale warship + support templates to fill the gaps."""
    comp = []
    for t, c in WAR_TEMPLATE:
        n = round(c * gap_war / WAR_TARGET)
        if n > 0:
            comp.append((t, n))
    for t, c in SUP_TEMPLATE:
        n = round(c * gap_sup / SUP_TARGET) if SUP_TARGET > 0 else 0
        if n > 0:
            comp.append((t, n))
    return comp


async def fleet_counts(db) -> dict[str, dict]:
    """Per-legion: total, warship, support counts."""
    rows = await db.fetch(
        """SELECT f.name, COUNT(fm.ship_id) AS n,
                  COUNT(fm.ship_id) FILTER (WHERE s.ship_type = ANY($2::text[])) AS wars,
                  COUNT(fm.ship_id) FILTER (WHERE s.ship_type = ANY($3::text[])) AS sup
           FROM maya_rp.fleets f
           LEFT JOIN maya_rp.fleet_members fm ON fm.fleet_id=f.id
           LEFT JOIN maya_rp.ships s ON s.id=fm.ship_id
           WHERE f.session_id=$1 AND f.name LIKE 'Legion %'
           GROUP BY f.id, f.name ORDER BY f.name""",
        SID, list(WAR_TYPES), list(SUP_TYPES))
    return {r["name"]: {"total": r["n"], "wars": r["wars"], "sup": r["sup"]} for r in rows}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true", help="execute (default: dry analysis)")
    ap.add_argument("--fill", action="store_true", help="greedy: queue everything affordable in priority order")
    ap.add_argument("--legion", type=str, default=None, help="expand specific legion to standard")
    ap.add_argument("--count", type=int, default=0, help="build N new legions")
    ap.add_argument("--support", type=int, default=0, help="additional support ships per legion (requested, unlimited)")
    args = ap.parse_args()

    # support ships auto-fill appropriate number (SUP_TARGET); commander requests MORE via --support N
    sup_target = SUP_TARGET if args.support == 0 else args.support

    await Database.init()

    # ── PHASE 0-1: PLAN + ANALYSIS ──
    print("═" * 60)
    print("PHASE 0-1: PLAN + ANALYSIS (fleet composition vs 100±20% standard)")
    print("═" * 60)
    counts = await fleet_counts(Database)
    plan = []

    targets = {}
    if args.legion:
        targets[args.legion] = STD_TARGET
    elif args.count > 0:
        targets = {f"Legion New-{i+1}": STD_TARGET for i in range(args.count)}
    else:
        # auto: fill EVERY legion to 100 warships + 20 support (Izzat's standard)
        targets = {k: STD_TARGET for k in counts}

    if not targets:
        print("No legions found.")
        await Database.close()
        return

    for name, target in targets.items():
        cur = counts.get(name, {"total": 0, "wars": 0, "sup": 0})
        gap_war = max(0, WAR_TARGET - cur["wars"])
        gap_sup = max(0, sup_target - cur["sup"])
        if gap_war == 0 and gap_sup == 0:
            print(f"\n{name}: already at standard ({cur['wars']} wars + {cur['sup']} support)")
            continue
        comp = composition(gap_war, gap_sup)
        cr = sum(COST[t][0] * c for t, c in comp)
        al = sum(COST[t][1] * c for t, c in comp)
        crew = sum(CREW[t] * c for t, c in comp)
        plan.append({"legion": name, "cur_war": cur["wars"], "cur_sup": cur["sup"],
                     "gap_war": gap_war, "gap_sup": gap_sup,
                     "comp": comp, "cr": cr, "al": al, "crew": crew})
        print(f"\n{name}: {cur['wars']} warships + {cur['sup']} support -> target {WAR_TARGET}W+{sup_target}S "
              f"(gaps {gap_war}W + {gap_sup}S)")
        print(f"  Recommend: " + ", ".join(f"{c}x {t}" for t, c in comp))
        print(f"  Cost: {cr/1e6:.1f}M C + {al/1e3:.0f}K A · Crew: {crew:,} · Lead: {max(COST[t][2] for t,_ in comp)}d")

    tot_cr = sum(p["cr"] for p in plan); tot_al = sum(p["al"] for p in plan); tot_crew = sum(p["crew"] for p in plan)
    print(f"\nTOTAL: {sum(p['gap_war'] for p in plan)} warships + {sum(p['gap_sup'] for p in plan)} support · "
          f"{tot_cr/1e6:.1f}M C · {tot_al/1e3:.0f}K A · {tot_crew:,} crew")

    if not args.commit:
        print("\nDRY RUN — re-run with --commit to execute (queue builds, reserve crew, assign).")
        await Database.close()
        return

    # ── PHASE 2: AFFORDABILITY + QUEUE (greedy --fill in priority order) ──
    print("\n" + "═" * 60)
    print("PHASE 2: CONSTRUCTION QUEUE (engineering team)")
    print("═" * 60)
    res = await Database.fetchrow(
        "SELECT credits, alloys, crew_pool FROM maya_rp.resources WHERE session_id=$1", SID)
    res = dict(res)  # mutable running budget for greedy fill

    # Priority order for --fill: empty new legions first, then Silent Maw, then cheap top-ups
    def priority(p: dict) -> tuple:
        is_empty = p["cur_war"] == 0 and p["cur_sup"] == 0
        is_maw = p["legion"] == "Legion Silent Maw"
        return (0 if is_empty else (1 if is_maw else 2), p["cr"])

    order = sorted(plan, key=priority) if args.fill else plan
    queued = []
    for p in order:
        if p["gap_war"] <= 0 and p["gap_sup"] <= 0:
            continue
        if args.fill:
            # greedy: check affordability per item, stop when broke
            if res["credits"] < p["cr"] or res["alloys"] < p["al"] or res["crew_pool"] < p["crew"]:
                print(f"SKIP {p['legion']} (insufficient: need {p['cr']/1e6:.1f}M C/{p['al']/1e3:.0f}K A/{p['crew']:,} crew, "
                      f"have {res['credits']/1e6:.1f}M C/{res['alloys']/1e3:.0f}K A/{res['crew_pool']:,})")
                continue
        elif res["credits"] < p["cr"] or res["alloys"] < p["al"]:
            print(f"NOT AFFORDABLE total: need {tot_cr:,}C/{tot_al:,}A, have {res['credits']:,}C/{res['alloys']:,}A — abort, no writes.")
            await Database.close()
            return
        if res["crew_pool"] < p["crew"]:
            print(f"CREW SHORT for {p['legion']}: need {p['crew']:,}, pool {res['crew_pool']:,} — abort, no writes.")
            await Database.close()
            return

        await Database.execute(
            "UPDATE maya_rp.resources SET credits=credits-$1, alloys=alloys-$2, crew_pool=crew_pool-$3 WHERE session_id=$4",
            p["cr"], p["al"], p["crew"], SID)
        res["credits"] -= p["cr"]; res["alloys"] -= p["al"]; res["crew_pool"] -= p["crew"]

        desc = ", ".join(f"{c}x {t}" for t, c in p["comp"])
        n_ships = p["gap_war"] + p["gap_sup"]
        await Database.execute(
            "INSERT INTO maya_rp.build_queue (session_id, project_name, project_type, status, "
            "alloy_cost, fuel_cost, credit_cost, build_time_days, created_at) "
            "VALUES ($1,$2,'legion_build','queued',$3,0,$4,$5,NOW())",
            SID, f"BUILD {p['legion']} — {n_ships} ships: {desc} | crew {p['crew']}",
            p["al"], p["cr"], max(COST[t][2] for t, _ in p["comp"]))
        queued.append(p["legion"])
        print(f"QUEUED {p['legion']}: {p['gap_war']}W+{p['gap_sup']}S ({p['cr']/1e6:.1f}M C, crew {p['crew']:,})")

    if not queued:
        print("Nothing queued — all legions already at standard or unaffordable.")
        await Database.close()
        return

    # ── PHASE 3-5: CREW + OFFICER + COMMANDER (reserved; completion-time steps) ──
    print("\n" + "═" * 60)
    print("PHASE 3-5: CREW RESERVED · OFFICER/COMMANDER QUEUE")
    print("═" * 60)
    for p in order:
        if p["legion"] not in queued:
            continue
        cmdr = await Database.fetchrow(
            "SELECT id, name FROM maya_rp.crew_roster WHERE session_id=$1 AND ship_id IS NULL "
            "AND clearance_level>=4 AND loyalty_flag='loyal' AND status='active' "
            "ORDER BY level DESC, id LIMIT 1", SID)
        if cmdr:
            print(f"{p['legion']}: commander candidate = {cmdr['name']} (crew#{cmdr['id']}, C4+ loyal)")
        else:
            print(f"{p['legion']}: WARN no free C4+ loyal commander — promote from pool at completion")

    # ── PHASE 6: DOCKYARD ROUTING ──
    print("\n" + "═" * 60)
    print("PHASE 6: DOCKYARD ROUTING")
    print("═" * 60)
    yards = await Database.fetch(
        "SELECT id, name, ship_type FROM maya_rp.ships WHERE session_id=$1 AND status='active' "
        "AND ship_type IN ('heavy_shipyard','light_dockyard') ORDER BY name", SID)
    print(f"Available dockyards: {len(yards)} (heavy_shipyard + light_dockyard @ Stasiun TKG)")

    # ── PHASE 7: EVENT + CHECKPOINT ──
    n_w = sum(p["gap_war"] for p in order if p["legion"] in queued)
    n_s = sum(p["gap_sup"] for p in order if p["legion"] in queued)
    tot_q = sum((p["cr"], p["al"], p["crew"])[0] for p in order if p["legion"] in queued)
    legion_names = ", ".join(queued)
    desc = (f"FLEET EXPANSION WORKFLOW Day 178: {n_w} warships + {n_s} support queued "
            f"({legion_names}). Standard 100W±20% + {sup_target} support auto-fill. "
            f"Cost {tot_q/1e6:.1f}M C, crew reserved. Composition per SOP template.")
    await Database.execute(
        "INSERT INTO maya_rp.events (session_id,event_type,title,description,importance) "
        "VALUES ($1,'military','FLEET EXPANSION WORKFLOW executed',$2,3)", SID, desc)
    after = await Database.fetchrow("SELECT credits, alloys, crew_pool FROM maya_rp.resources WHERE session_id=$1", SID)
    print(f"\nTREASURY AFTER: {after['credits']:,}C / {after['alloys']:,}A / pool {after['crew_pool']:,}")
    print("\nRun: python3 scripts/cli.py save \"fleet expansion\" — then roll100 to advance builds.")
    await Database.close()


if __name__ == "__main__":
    asyncio.run(main())
