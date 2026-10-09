#!/usr/bin/env python3
"""
Roll N game days — world sim + transparent resource override + flexible build completions.

Safety: a .sav checkpoint (core.savegame.export_sav) is written BEFORE any mutation, and the roll
refuses to start when it cannot be written. --dry-run shows what would happen.
The session resolves per call (--session, RP_SESSION, active arc). A roll refuses while GM MAYA
maintenance is armed and on a frozen session.
Flags:
  --dry-run          show projections, write nothing
  --session ID       session to roll (default: RP_SESSION, then the active arc)
  --no-builds        skip build-queue completion
  --no-collapse      skip collapse check
  --no-sarang        skip Sarang carrier insertion
  --no-preg          skip pregnancy progression (births OFF — default ON)
  --rates A,B,C      override daily credits, alloys, fuel (e.g. --rates 12000000,700000,110000)

Transactions: the world sim and the module steps (pregnancy, voyage, sentiment, ministry, collapse)
commit on their own connections. The resource override, build completion, roll_state and Sarang
carriers share ONE transaction: a failure rolls all four back. The sim has already advanced the
clock by then, so a failed roll must be repaired from the checkpoint, never rerun.

Resource override: the sim moves credits, alloys and fuel (and clamps alloys and fuel to a cap).
The override replaces that move with rate * days, as a relative change applied to the row under
lock. A change made by another writer outside the sim survives it.

Build logic (flexible, game-day based): each in_build row accumulates progress equal to the
number of game days rolled. A build completes when accumulated progress >= build_time_days.
Progress is tracked in maya_rp.roll_state (build_progress JSONB map: build_id -> days done).

Pregnancy logic: after game_day advances, every tracked pregnancy is progressed against the
new day — trimesters advance, due_soon flags set, and any pregnancy past due_game_day fires
a birth. This keeps babies on the SAME clock as ships, so narration skips reconcile BOTH.

Sarang carriers: spawned only from completed Sarang build-queue rows (not hardcoded).
"""
import os
import asyncio, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.db import Database
from core.log import info
from modules.chrono_engine import execute_time_skip

# Default transparent line items (narrative-anchored, not magic)
DEFAULT_CREDITS_PER_DAY = 10_000_000
DEFAULT_ALLOYS_PER_DAY = 80_000 + 150_000 + 400_000   # chrono + economy + Jaw 400K/d
DEFAULT_FUEL_PER_DAY = 100_000


_KNOWN_FLAGS = {"--dry-run", "--no-builds", "--no-collapse", "--no-sarang",
                "--no-preg", "--rates", "--session", "-h", "--help"}

USAGE = """roll100.py [DAYS] [options]

  DAYS            days to roll (default 100)
  --dry-run       preview only — NO writes (use this unless you mean it)
  --session ID    session to roll (default: RP_SESSION, then the active arc)
  --no-builds     skip build-queue processing
  --no-collapse   skip collapse checks
  --no-sarang     skip Sarang AI progression
  --no-preg       skip pregnancy tracking
  --rates C,A,F   override credits/alloys/fuel per day

Without --dry-run this ADVANCES THE GAME CLOCK and writes state.
Refuses while GM MAYA maintenance is armed and on a frozen session.
"""


def parse_flags(argv: list[str]) -> dict:
    # `--help` used to fall through to a LIVE 100-day roll (no arg validation,
    # substring matching only) — one call cost a full restore from backup.
    if any(a in ("-h", "--help") for a in argv):
        print(USAGE)
        raise SystemExit(0)
    unknown = [a for a in argv
               if a.startswith("-") and a not in _KNOWN_FLAGS and not a.startswith("--session=")]
    if unknown:
        print("roll100: unknown option(s): " + " ".join(unknown), file=sys.stderr)
        print(USAGE, file=sys.stderr)
        raise SystemExit(2)

    flags = {
        "dry": "--dry-run" in argv,
        "no_builds": "--no-builds" in argv,
        "no_collapse": "--no-collapse" in argv,
        "no_sarang": "--no-sarang" in argv,
        "no_preg": "--no-preg" in argv,
    }
    # The token after --session is its value, never the day count.
    session = None
    value_slots: set[int] = set()
    for i, a in enumerate(argv):
        if a.startswith("--session="):
            session = a.split("=", 1)[1]
        elif a == "--session":
            if i + 1 >= len(argv):
                print("roll100: --session needs a session id", file=sys.stderr)
                raise SystemExit(2)
            session = argv[i + 1]
            value_slots.add(i + 1)
    days = 100
    for i, a in enumerate(argv):
        if i not in value_slots and a.isdigit():
            days = int(a)
            break
    rates = None
    for i, a in enumerate(argv):
        if a == "--rates" and i + 1 < len(argv):
            try:
                c, al, f = (int(x) for x in argv[i + 1].split(","))
                rates = (c, al, f)
            except ValueError:
                info("roll100", f"Bad --rates value: {argv[i+1]}")
    flags["days"] = days
    flags["rates"] = rates
    flags["session"] = session
    return flags


def resolve_target(explicit) -> tuple[int | None, str | None]:
    """Resolve the session for this roll and apply the brakes. Reads no database.

    Maintenance is asked first, as `run_full_tick` does: it resolves no session of its own.

    @param explicit - session id from `--session`; None follows RP_SESSION, then the active arc.
    @returns (session_id, None) to proceed, or (None, reason) when the roll must not start.
    """
    from core import maintenance
    from core.session import FrozenListUnreadable, is_frozen, require_session

    if maintenance.active():
        return None, "GM MAYA maintenance is armed"
    try:
        session_id = require_session(explicit)
    except (RuntimeError, ValueError) as e:
        return None, str(e)
    try:
        if is_frozen(session_id):
            return None, f"session {session_id} is frozen for reference"
    except FrozenListUnreadable as e:
        return None, str(e)
    return session_id, None


def override_deltas(before, after_sim, sim: dict, rates: tuple[int, int, int], days: int) -> tuple[int, int, int]:
    """Relative change that replaces the sim's economy with the transparent line items.

    The change is `rate * days - sim_move`, applied to whatever the row holds, so a write by
    another process outside the sim survives. Credits take the sim's own before/after, read under
    its row lock. Alloys and fuel take the move between the row read before the sim and the row
    read after it, which includes the sim's cap clamp.

    @param before - credits, alloys, fuel read just before the sim.
    @param after_sim - credits, alloys, fuel read after the sim, under lock.
    @param sim - `execute_time_skip` result.
    @param rates - credits, alloys, fuel per day.
    @param days - days rolled.
    @returns (credits, alloys, fuel) change to add to the row.
    """
    credits_pd, alloys_pd, fuel_pd = rates
    if sim.get("credits_before") is not None and sim.get("credits_after") is not None:
        sim_credits = sim["credits_after"] - sim["credits_before"]
    else:
        sim_credits = after_sim["credits"] - before["credits"]
    return (credits_pd * days - sim_credits,
            alloys_pd * days - (after_sim["alloys"] - before["alloys"]),
            fuel_pd * days - (after_sim["fuel"] - before["fuel"]))


async def checkpoint(session_id: int) -> str:
    """Write a restorable .sav of the session. `import_sav` restores it.

    `export_sav` is the pre-roll save: it dumps every session table and raises when one cannot be
    read. `StateManager.save_checkpoint` writes a Markdown story summary that cannot restore rows.

    @param session_id - session about to be rolled.
    @returns path of the .sav.
    @raises Exception from `export_sav`; the caller aborts before any write.
    """
    from core.savegame import export_sav

    return await export_sav(session_id)


async def main(argv: list[str] | None = None) -> int:
    """Run the roll. @returns the process exit code: 0 done, 1 refused or rolled back, 2 bad usage."""
    flags = parse_flags(sys.argv[1:] if argv is None else argv)

    session_id, refusal = resolve_target(flags["session"])
    if session_id is None:
        print(f"roll100: refused — {refusal}", file=sys.stderr)
        return 1

    await Database.init()
    try:
        return await _roll(session_id, flags)
    finally:
        await Database.close()


async def _roll(sid: int, flags: dict) -> int:
    days = flags["days"]
    dry = flags["dry"]

    if not dry:
        print("⚠ LIVE ROLL — this advances the game clock and writes state. "
              "Use --dry-run to preview.", file=sys.stderr)
    info("roll100", f"Rolling {days} days on session {sid} — {'DRY RUN (no writes)' if dry else 'LIVE'}")

    rates = flags["rates"] or (DEFAULT_CREDITS_PER_DAY, DEFAULT_ALLOYS_PER_DAY, DEFAULT_FUEL_PER_DAY)
    credits_pd, alloys_pd, fuel_pd = rates

    before = await Database.fetchrow(
        "SELECT credits, alloys, fuel FROM maya_rp.resources WHERE session_id=$1", sid)
    if before is None:
        print(f"roll100: refused — session {sid} has no resources row", file=sys.stderr)
        return 1
    print(f"BEFORE: {before['credits']:,}C / {before['alloys']:,}A / {before['fuel']:,}F")
    print(f"LINES:  +{credits_pd*days:,}C  +{alloys_pd*days:,}A  +{fuel_pd*days:,}F"
          f"   (credits {credits_pd:,}/d · alloys {alloys_pd:,}/d · fuel {fuel_pd:,}/d)")

    if dry:
        print(f"AFTER (projected): {before['credits'] + credits_pd*days:,}C / "
              f"{before['alloys'] + alloys_pd*days:,}A / {before['fuel'] + fuel_pd*days:,}F")
        return 0

    # 0. Checkpoint before any write. No checkpoint, no roll.
    try:
        sav = await checkpoint(sid)
    except Exception as e:
        print(f"❌ CHECKPOINT FAILED: {type(e).__name__}: {e} — aborting roll (nothing written)")
        return 1
    print(f"CHECKPOINT: {sav}")

    # The checkpoint takes seconds. Read the row again so the sim's move is measured from here.
    before = await Database.fetchrow(
        "SELECT credits, alloys, fuel FROM maya_rp.resources WHERE session_id=$1", sid)
    if before is None:
        print(f"roll100: refused — session {sid} lost its resources row", file=sys.stderr)
        return 1

    # 1. World simulation — economy focus (research, morale, geopolitics)
    r = await execute_time_skip(days, focus="economy", session_id=sid)
    if "error" in r:
        print(f"❌ CHRONO ERROR: {r['error']} — aborting roll (day unchanged)")
        return 1
    print(f"SIM EVENTS: {len(r.get('events', []))}  SIM ECONOMY: {r.get('economy')}")

    # 2-4. One transaction: resource override, build completion, roll_state, Sarang carriers.
    report: list[str] = []
    try:
        async with Database.transaction() as conn:
            await _apply_roll_writes(conn, sid, flags, before, r, rates, report)
    except Exception as e:
        print(f"❌ ROLL WRITES ROLLED BACK: {type(e).__name__}: {e}")
        print(f"   The sim already advanced the clock {days} days. Do NOT rerun. "
              f"Repair from the checkpoint: {sav}")
        return 1
    for line in report:
        print(line)

    # 4b. Pregnancy progression — babies on the SAME clock as ships.
    #    Narration skips must reconcile pregnancies too (no more silent siap for wombs).
    if flags["no_preg"]:
        print("PREGNANCY: skipped (--no-preg)")
    else:
        from modules.pregnancy import advance as pregnancy_advance
        preg = await pregnancy_advance(sid)
        births = preg.get("births", [])
        checked = preg.get("checked", 0)
        updated = preg.get("updated", 0)
        print(f"PREGNANCY: checked {checked} · updated {updated} · births {len(births)}")
        for b in births:
            print(f"   👶 BIRTH: {b.get('mother')} → {b.get('name')} ({b.get('gender')}), day {b.get('game_day')}")

    # 4c. Voyage transit — fleets land on schedule during skips (same clock as ships/babies)
    from modules.voyage import advance as voyage_advance
    voy = await voyage_advance(sid)
    if voy.get("arrivals", 0) > 0:
        print(f"VOYAGES: {voy['arrivals']} arrived — {', '.join(voy['arrived'])}")
    else:
        print("VOYAGES: none due")

    # 4d. Population sentiment — refresh across the skip (people feel time pass)
    from modules.population_sentiment import run_tick as sentiment_tick
    sent = await sentiment_tick(sid)
    print(f"SENTIMENT: {sent.get('updated', 0)} rows refreshed · news bias {sent.get('news_bias_applied', 0)}")

    # 4e. Ministry AI — ministries act/prompt depending on King presence
    from modules.ministry_ai import run_tick as ministry_tick
    mini = await ministry_tick(sid)
    print(f"MINISTRY: king_present={mini.get('king_present')} · autonomous {mini.get('taken_autonomous')} · prompts {mini.get('prompted')}")

    # 5. Collapse check (optional)
    if flags["no_collapse"]:
        print("COLLAPSE: skipped (--no-collapse)")
    else:
        from modules.collapse import check_for_collapse
        collapse = await check_for_collapse(sid)
        if collapse:
            print(f"⚠️ COLLAPSE: {collapse['title']} ({collapse['new_arc']})")
            print(f"   Recovery: {collapse['recovery']}")
        else:
            print("COLLAPSE: stable")

    after = await Database.fetchrow(
        "SELECT credits, alloys, fuel FROM maya_rp.resources WHERE session_id=$1", sid)
    active_ships = await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.ships WHERE session_id=$1 AND status='active'", sid)
    queue_completed = await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.build_queue WHERE session_id=$1 AND status='completed'", sid)
    print(f"AFTER:  {after['credits']:,}C / {after['alloys']:,}A / {after['fuel']:,}F")
    print(f"ACTIVE SHIPS: {active_ships}")
    print(f"QUEUE COMPLETED: {queue_completed}")
    print(f"\nDONE. Checkpoint taken before the roll: {sav}")
    return 0


async def _apply_roll_writes(conn, sid: int, flags: dict, before, sim: dict,
                             rates: tuple[int, int, int], report: list[str]) -> None:
    """The roll's own writes, every statement on `conn` so the caller's transaction covers all.

    @param conn - connection of the open transaction.
    @param sid - session rolled.
    @param flags - parsed flags.
    @param before - credits, alloys, fuel read just before the sim.
    @param sim - `execute_time_skip` result.
    @param rates - credits, alloys, fuel per day.
    @param report - output lines, printed by the caller only after the commit.
    """
    days = flags["days"]

    # 2. Transparent resource override, relative to the row as it stands under lock.
    now = await conn.fetchrow(
        "SELECT credits, alloys, fuel FROM maya_rp.resources WHERE session_id=$1 FOR UPDATE", sid)
    if now is None:
        raise RuntimeError(f"resources row of session {sid} disappeared during the roll")
    d_credits, d_alloys, d_fuel = override_deltas(before, now, sim, rates, days)
    await conn.execute(
        "UPDATE maya_rp.resources SET credits = credits + $1, alloys = alloys + $2, fuel = fuel + $3 "
        "WHERE session_id=$4", d_credits, d_alloys, d_fuel, sid)

    # 3. Flexible build completion — game-day progress accumulation
    new_day = await conn.fetchval("SELECT game_day FROM maya_rp.sessions WHERE id=$1", sid)
    if flags["no_builds"]:
        report.append("BUILDS: skipped (--no-builds)")
    else:
        # load roll state
        state = await conn.fetchrow(
            "SELECT build_progress FROM maya_rp.roll_state WHERE session_id=$1", sid)
        raw_progress = state["build_progress"] if state and state["build_progress"] else "{}"
        progress = json.loads(raw_progress) if isinstance(raw_progress, str) else dict(raw_progress or {})

        due_rows = await conn.fetch(
            """SELECT id, project_name, build_time_days
               FROM maya_rp.build_queue
               WHERE session_id=$1 AND status='in_build' AND build_time_days IS NOT NULL""", sid)

        reached = []
        still = []
        for b in due_rows:
            pid = str(b["id"])
            done = int(progress.get(pid, 0)) + days
            if done >= (b["build_time_days"] or 0):
                reached.append(b["id"])
            else:
                progress[pid] = done
                still.append(b["id"])

        # Claim first: only a row still in_build completes, so a concurrent tick cannot be doubled.
        completed_ids = []
        if reached:
            claimed = await conn.fetch(
                "UPDATE maya_rp.build_queue SET status='completed', completed_at=NOW() "
                "WHERE session_id=$1 AND id=ANY($2::int[]) AND status='in_build' RETURNING id",
                sid, reached)
            completed_ids = [row["id"] for row in claimed]
        # persist progress (drop fully completed entries)
        for pid in [str(i) for i in completed_ids]:
            progress.pop(pid, None)
        await conn.execute(
            "INSERT INTO maya_rp.roll_state (session_id, last_rolled_game_day, build_progress) "
            "VALUES ($1, $2, $3) "
            "ON CONFLICT (session_id) DO UPDATE SET last_rolled_game_day=$2, build_progress=$3",
            sid, new_day, json.dumps(progress))

        report.append(f"BUILDS COMPLETED: {len(completed_ids)} · in progress: {len(still)}")
        for b in due_rows:
            mark = "COMPLETED" if b["id"] in completed_ids else f"{progress.get(str(b['id']), days)}/{b['build_time_days']}d"
            report.append(f"   {b['project_name']}: {mark}")

    # 4. Sarang AI carriers — spawn ONLY from completed Sarang build rows
    if flags["no_sarang"]:
        report.append("SARANG: skipped (--no-sarang)")
    else:
        done_sarang = await conn.fetch(
            """SELECT id FROM maya_rp.build_queue
               WHERE session_id=$1 AND status='completed' AND project_name LIKE '%Sarang%'""", sid)
        existing = await conn.fetchval(
            "SELECT COUNT(*) FROM maya_rp.ships WHERE session_id=$1 AND name LIKE 'Sarang-%'", sid)
        spawned = 0
        for idx, b in enumerate(done_sarang, start=1):
            if existing + spawned >= 3:
                break
            await conn.execute(
                """INSERT INTO maya_rp.ships
                   (session_id, name, ship_type, mass, length_m, hull, speed, crew, location, status,
                    tier, power_rating, sub_class, role)
                   VALUES ($1, $2, 'carrier', 2000000, 900, 60000, 40, 1200,
                           'Legion Aerie - Fleet Carrier', 'active', 6, 150000,
                           'Fleet Carrier (40% Heaven AI)', 'carrier')""",
                sid, f"Sarang-{idx}")
            spawned += 1
        if spawned:
            report.append(f"SARANG CARRIERS: {spawned} spawned from completed builds")
        else:
            report.append(f"SARANG CARRIERS: none ({existing} already present or builds not complete)")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
