#!/usr/bin/env python3
"""Async tick orchestrator — runs all modules in dependency order with concurrency guard."""
import asyncio, json, sys, os, time
from datetime import datetime, timezone
sys.path.insert(0, str(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.db import Database
from core.config import Config
from core.events import EventBus
from core.log import info, error, warn
from core.session import stale_process_default

from modules import economy, narrative, diplomacy, research, victory, market
from modules import pirates, slave_system, space_wonders
from modules import megastructures_ports, infrastructure, space_horror, battle
from modules import prison, romance, social, council
from modules import pregnancy as pregnancy_mod
from modules import celestial, mystery, tactics, fleet_economy, encounters
from modules import ship_generation, ship_building, fleet, refit
from modules import espionage, darkops, stealth, defense, siege, disasters, weapon_design
from modules import tech_tree, manufacturing, exoscience, academy, university, alchemy
from modules import archaeology, artifacts, adventures, narrator, news, quest, epilogue
from modules import image_gen, guardrails, faction_ai, event_catalog
from modules import characters, locations, calendar_tkg, memories, war, narrative_seeds
from modules import objectives as objectives_mod, environment as environment_mod
from modules import npc_autonomy, secrets as secrets_mod, themes as themes_mod
from modules import conversation_log, physical_state, chekhov, world_react
from modules import logistics, geopolitics, crew_career, ideology
from modules import auto_queue, corporations
from modules import collapse as collapse_mod
from modules import wreck_assembly, duel, crew_system
from modules import voyage as voyage_mod
from modules import population_sentiment as population_sentiment_mod
from modules import ministry_ai as ministry_ai_mod
from core import consequences as consequences_mod
from core.pacing import PacingDirector

_tick_lock = asyncio.Lock()
_shutdown = False


def report_session_drift() -> str | None:
    """Say out loud when this process's default session is no longer the engine's.

    `Config.SESSION_ID` is resolved once, at import, and the whole tick hands it to
    every module that does not name a session. `core.session.stale_process_default`
    has detected that drift since the session work and nothing ran it, which is the
    same shape as the caller-less functions this review has been wiring all day: a
    detector that reports to nobody reports nothing.

    At process start the two values agree by construction, so a one-shot tick stays
    silent. The line this prints is for a process that has been alive across an arc
    change, which is the orchestrator when it is imported and driven in-process.

    @returns the warning line, or None when the two agree.
    """
    message = stale_process_default()
    if message:
        warn("orchestrator", message)
    return message

def _handle_signal(sig, frame):
    global _shutdown
    _shutdown = True
    print("\n⚠ Shutdown requested. Finishing current module...")

import signal
signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)

async def run_module(name: str, mod, session_id: int):
    """Run a module tick with timing, flag check, and error handling."""
    if not Config.is_module_active(name):
        info("orchestrator", f"{name}: SKIPPED (disabled)")
        return None
    if _shutdown:
        info("orchestrator", f"{name}: SKIPPED (shutting down)")
        return None
    t0 = time.monotonic()
    try:
        result = await mod.run_tick(session_id)
        elapsed = time.monotonic() - t0
        if isinstance(result, dict) and "error" in result:
            error("orchestrator", f"{name}: FAILED ({elapsed:.2f}s) — {result['error']}")
            return {"error": result["error"]}
        info("orchestrator", f"{name}: OK ({elapsed:.2f}s)")
        return {"ok": True}
    except Exception as e:
        elapsed = time.monotonic() - t0
        error("orchestrator", f"{name}: CRASHED ({elapsed:.2f}s) — {e}")
        return {"error": str(e)}

async def tick(name: str, mod, session_id: int) -> bool:
    """Run a module; skipped (disabled/shutdown) is NOT a failure.
    Crash/error dicts ARE failures."""
    result = await run_module(name, mod, session_id)
    if result is None:
        return True  # skipped — don't count as failure
    if isinstance(result, dict) and "error" in result:
        return False  # crashed or failed
    return bool(result)

async def tick_header(msg: str):
    """Log tick phase header."""
    info("orchestrator", msg)

async def run_full_tick(session_id: int = None, verbose: bool = True):
    # GM MAYA maintenance stops the tick. Measured on 2026-10-03: `gm_maint status` reported the mode and
    # four modules read it, but this entry point never asked, so the tick kept writing to the live session
    # while the brake the operator reached for was armed. It opened a `fuel_zero` collapse arc (Dead in the
    # Water, 12:00) against a session whose resources row this engine had zeroed. A guard that four callers
    # honour and the one that drives them ignores is not a guard.
    from core import maintenance

    if maintenance.active():
        if verbose:
            print("  RP ENGINE TICK SKIPPED — GM MAYA maintenance is armed")
        return

    # Resolved per tick, after the maintenance brake: a process that outlives an arc change must
    # not keep ticking the session it started on, and maintenance resolves no session at all.
    from core.session import require_session

    session_id = require_session(session_id)

    # A frozen session is reference data: every module writer refuses it, so ticking it only
    # produced one FrozenSession error per module and no state change. Say so once and stop.
    from core.session import is_frozen

    if is_frozen(session_id):
        if verbose:
            print(f"  RP ENGINE TICK SKIPPED — session {session_id} is frozen for reference")
        return

    if _tick_lock.locked():
        print("Tick already in progress. Aborting.")
        return
    async with _tick_lock:
        tick_start = time.monotonic()
        await Database.init()
        modules_ok, modules_failed = 0, 0
        # What the tick writes, measured rather than reported. `modules_ok` counts ticks that
        # returned without raising, and a successful tick returns `{"ok": True}` whether it moved
        # the campaign or read two tables and changed nothing. Postgres already records per-table
        # writes, so two snapshots around the phases give the difference without instrumenting a
        # single module.
        from core import tick_writes
        # A measurement must not be able to stop the thing it measures. If the statistics view is
        # unreadable the tick still runs, and the report says it could not look rather than
        # reporting zero writes, because those two look identical in a number.
        try:
            writes_before = await tick_writes.snapshot()
        except Exception as e:  # noqa: BLE001 - reported, never fatal
            writes_before = {}
            warn("orchestrator", f"tick write-tracking unavailable: {e}")
        print(f"\n{'='*60}")
        print(f"  RP ENGINE TICK — Session {session_id}  ({datetime.now():%H:%M:%S})")
        print(f"{'='*60}")

        # Phase 1: Economy & Resources
        await tick_header("Phase 1/31: Economy")
        if await tick("economy", economy, session_id): modules_ok += 1
        if await tick("market", market, session_id): modules_ok += 1
        else: modules_failed += 1
        # Crew production (novel: crew bottleneck)
        if await tick("crew_system", crew_system, session_id): modules_ok += 1
        else: modules_failed += 1

        # Phase 2: Prison
        await tick_header("Phase 2/31: Prison & Security")
        if await tick("prison", prison, session_id): modules_ok += 1
        else: modules_failed += 1

        # Phase 3: Social
        await tick_header("Phase 3/31: Social & Morale")
        if await tick("social", social, session_id): modules_ok += 1
        else: modules_failed += 1

        # Phase 4: Romance
        await tick_header("Phase 4/31: Romance & Bonds")
        if await tick("romance", romance, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("pregnancy", pregnancy_mod, session_id): modules_ok += 1
        else: modules_failed += 1
        # Voyages — fleets arrive on schedule (transit days booked)
        if await tick("voyage", voyage_mod, session_id): modules_ok += 1
        # Population sentiment — how the people feel (resource-driven, faction-independent)
        if await tick("population_sentiment", population_sentiment_mod, session_id): modules_ok += 1
        # Ministry AI — ministries do their jobs; prompt King via adjutant when present
        if await tick("ministry_ai", ministry_ai_mod, session_id): modules_ok += 1
        else: modules_failed += 1

        # Phase 5: Council
        await tick_header("Phase 5/31: Council & Governance")
        if await tick("council", council, session_id): modules_ok += 1
        else: modules_failed += 1

        # Phase 6: Research
        await tick_header("Phase 6/31: Research")
        if await tick("research", research, session_id): modules_ok += 1
        else: modules_failed += 1

        # Phase 7: Diplomacy
        await tick_header("Phase 7/31: Diplomacy & AI")
        if await tick("diplomacy", diplomacy, session_id): modules_ok += 1
        else: modules_failed += 1

        # Phase 8: Narrative & Events
        await tick_header("Phase 8/31: Narrative & Encounters")
        if await tick("narrative", narrative, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("events", encounters, session_id): modules_ok += 1
        else: modules_failed += 1

        # Phase 9: Celestial & Mystery
        await tick_header("Phase 9/31: Galaxy & Investigations")
        if await tick("celestial", celestial, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("mystery", mystery, session_id): modules_ok += 1
        else: modules_failed += 1

        # Phase 10: Tactics & Fleet Economy
        await tick_header("Phase 10/31: Combat Readiness")
        if await tick("tactics", tactics, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("fleet_economy", fleet_economy, session_id): modules_ok += 1
        else: modules_failed += 1

        # Phase 11: Pirates & Intel
        await tick_header("Phase 11/31: Pirates & Intel")
        if await tick("pirates", pirates, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("espionage", espionage, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("darkops", darkops, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("stealth", stealth, session_id): modules_ok += 1
        else: modules_failed += 1

        # Phase 12: Military Operations
        await tick_header("Phase 12/31: Military Operations")
        if await tick("defense", defense, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("siege", siege, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("disasters", disasters, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("battle", battle, session_id): modules_ok += 1
        else: modules_failed += 1

        # Phase 13: Slave System
        await tick_header("Phase 13/31: Population")
        if await tick("slave_system", slave_system, session_id): modules_ok += 1
        else: modules_failed += 1

        # Phase 14: Science & Tech
        await tick_header("Phase 14/31: Science & Technology")
        if await tick("tech_tree", tech_tree, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("manufacturing", manufacturing, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("auto_queue", auto_queue, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("exoscience", exoscience, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("academy", academy, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("university", university, session_id): modules_ok += 1
        else: modules_failed += 1

        # Phase 15: Magic & Discovery
        await tick_header("Phase 15/31: Magic & Discovery")
        if await tick("alchemy", alchemy, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("archaeology", archaeology, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("artifacts", artifacts, session_id): modules_ok += 1
        else: modules_failed += 1

        # Phase 16: Faction AI
        await tick_header("Phase 16/31: Faction Behavior")
        if await tick("faction_ai", faction_ai, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("event_catalog", event_catalog, session_id): modules_ok += 1
        else: modules_failed += 1

        # Phase 17: Narrative & Media
        await tick_header("Phase 17/31: Narrative & Media")
        if await tick("narrator", narrator, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("news", news, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("quest", quest, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("epilogue", epilogue, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("image_gen", image_gen, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("adventures", adventures, session_id): modules_ok += 1
        else: modules_failed += 1

        # Phase 18: Integration & Safety
        await tick_header("Phase 18/31: Integration & Safety")
        if await tick("guardrails", guardrails, session_id): modules_ok += 1
        else: modules_failed += 1

        # Phase 19: Characters
        await tick_header("Phase 19/31: Character Events")
        if await tick("characters", characters, session_id): modules_ok += 1
        else: modules_failed += 1

        # Phase 20-24: Infrastructure & Space
        await tick_header("Phase 20/31: Victory")
        if await tick("victory", victory, session_id): modules_ok += 1
        else: modules_failed += 1

        await tick_header("Phase 21/31: Space Wonders")
        if await tick("space_wonders", space_wonders, session_id): modules_ok += 1
        else: modules_failed += 1

        await tick_header("Phase 22/31: Megastructures & Infrastructure")
        if await tick("megastructures_ports", megastructures_ports, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("infrastructure", infrastructure, session_id): modules_ok += 1
        else: modules_failed += 1

        await tick_header("Phase 23/31: Space Horror")
        if await tick("space_horror", space_horror, session_id): modules_ok += 1
        else: modules_failed += 1

        # Phase 24: Calendar & Consequences
        await tick_header("Phase 24/31: Calendar & Consequences")
        if await tick("calendar", calendar_tkg, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("consequences", consequences_mod, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("narrative_seeds", narrative_seeds, session_id): modules_ok += 1
        else: modules_failed += 1

        # Phase 25: War & Memories
        await tick_header("Phase 25/31: War & Memories")
        if await tick("war", war, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("memories", memories, session_id): modules_ok += 1
        else: modules_failed += 1

        # Phase 26: Locations
        await tick_header("Phase 26/31: Locations & Scenes")
        if await tick("locations", locations, session_id): modules_ok += 1
        else: modules_failed += 1

        # Phase 27: Geopolitics & Logistics
        await tick_header("Phase 27/31: Geopolitics & Logistics")
        if await tick("geopolitics", geopolitics, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("logistics", logistics, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("crew_career", crew_career, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("corporations", corporations, session_id): modules_ok += 1
        else: modules_failed += 1

        # Phase 28: Living Universe — GM Brain + off-screen life
        await tick_header("Phase 28/31: Living Universe")
        if await tick("pacing", PacingDirector, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("objectives", objectives_mod, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("npc_autonomy", npc_autonomy, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("secrets", secrets_mod, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("world_react", world_react, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("physical_state", physical_state, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("chekhov", chekhov, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("themes", themes_mod, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("environment", environment_mod, session_id): modules_ok += 1
        else: modules_failed += 1

        # Phase 29: Endgame Watch — collapse triggers (now live via pop sync)
        await tick_header("Phase 29/31: Endgame Watch")
        if await tick("collapse", collapse_mod, session_id): modules_ok += 1
        else: modules_failed += 1

        # Phase 30: Ideology
        await tick_header("Phase 30/31: Ideology & Progress")
        if await tick("ideology", ideology, session_id): modules_ok += 1
        else: modules_failed += 1

        # Phase 31: Ship Operations
        await tick_header("Phase 31/31: Ship Operations")
        if await tick("ship_generation", ship_generation, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("ship_building", ship_building, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("fleet", fleet, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("refit", refit, session_id): modules_ok += 1
        else: modules_failed += 1
        if await tick("weapon_design", weapon_design, session_id): modules_ok += 1
        else: modules_failed += 1

        # Summary
        duration_ms = int((time.monotonic() - tick_start) * 1000)
        # ── After phase 31: housekeeping, not a phase ──
        # events retention: archive rows older than 180 days when the table
        # grows past 5K rows, so "recent events" queries stay fast.
        try:
            old = await Database.fetchval(
                "SELECT COUNT(*) FROM maya_rp.events WHERE happened_at < NOW() - INTERVAL '180 days'")
            total_ev = await Database.fetchval("SELECT COUNT(*) FROM maya_rp.events")
            if old and total_ev and total_ev > 5000:
                archived = await Database.execute(
                    "INSERT INTO maya_rp.events_archive SELECT * FROM maya_rp.events "
                    "WHERE happened_at < NOW() - INTERVAL '180 days'")
                await Database.execute(
                    "DELETE FROM maya_rp.events WHERE happened_at < NOW() - INTERVAL '180 days'")
                info("orchestrator", f"Housekeeping: archived {old} old events")
        except Exception as e:
            error("orchestrator", f"Housekeeping failed: {e}")
        try:
            # tick_summaries has no started_at/completed_at/modules_run/
            # modules_failed/duration_ms columns (live: id, session_id,
            # tick_number, categories jsonb, events_json jsonb,
            # formatted_bulletin, ai_prose, alerts_count, resource_snapshot,
            # summary_for_telegram, generated_at) — the old INSERT failed on
            # every tick and was swallowed, so this table stayed empty forever.
            tick_no = await Database.fetchval(
                "SELECT game_day FROM maya_rp.sessions WHERE id=$1", session_id) or 0
            await Database.execute(
                "INSERT INTO tick_summaries "
                "(session_id, tick_number, categories, alerts_count, generated_at) "
                "VALUES ($1, $2, $3::jsonb, $4, NOW())",
                session_id, tick_no,
                json.dumps({"modules_ok": modules_ok,
                            "modules_failed": modules_failed,
                            "duration_ms": duration_ms}),
                modules_failed)
        except Exception as e:
            error("orchestrator", f"tick_summaries insert failed: {e}")

        print(f"{'='*60}")
        print(f"  Tick complete: {modules_ok} OK, {modules_failed} failed ({duration_ms}ms)")
        # The second number that matters, and the one `modules_ok` cannot give: did the tick
        # write anything. A report of 80 OK with 3 tables moved is a tick that mostly looked.
        writes = await tick_writes.report(writes_before, await tick_writes.snapshot())
        if writes["readable"]:
            print(f"  Wrote to {writes['tables_moved']} table(s), {writes['rows']} row(s) — "
                  f"{len(writes['never_written'])} tables have never been written")
            for table, delta in sorted(writes["moved"].items(),
                                       key=lambda kv: -sum(kv[1].values()))[:12]:
                print(f"     {table:34} +{delta['ins']} ins, {delta['upd']} upd, {delta['del']} del")
        else:
            print(f"  ⚠ {writes['note']}")
        print(f"{'='*60}\n")

        # Auto-savegame after tick (game-engine style .sav + rotation)
        try:
            from core.savegame import export_sav
            sav_path = await export_sav(session_id)
            print(f"  💾 Auto-save: {sav_path}")
            # rotation: keep last 12 .sav files
            import glob, os
            savs = sorted(glob.glob(os.path.join(os.path.dirname(sav_path), f"save_{session_id}_day*.sav")))
            for old in savs[:-12]:
                try: os.remove(old)
                except Exception: pass
        except Exception as e:
            print(f"  ⚠ Auto-save failed: {e}")

        await Database.close()

MODULE_MAP = {
    "economy": economy, "market": market, "prison": prison, "social": social, "romance": romance,
    "pregnancy": pregnancy_mod,
    "council": council, "research": research, "diplomacy": diplomacy,
    "narrative": narrative, "pirates": pirates, "slave_system": slave_system,
    "victory": victory, "space_wonders": space_wonders,
    "megastructures_ports": megastructures_ports, "infrastructure": infrastructure,
    "space_horror": space_horror, "battle": battle, "celestial": celestial,
    "mystery": mystery, "tactics": tactics, "fleet_economy": fleet_economy,
    "events": encounters, "characters": characters,
    "espionage": espionage, "darkops": darkops, "stealth": stealth,
    "defense": defense, "siege": siege, "disasters": disasters,
    "tech_tree": tech_tree, "manufacturing": manufacturing, "auto_queue": auto_queue,
    "exoscience": exoscience, "academy": academy, "university": university,
    "alchemy": alchemy, "archaeology": archaeology, "artifacts": artifacts,
    "faction_ai": faction_ai, "event_catalog": event_catalog,
    "narrator": narrator, "news": news, "quest": quest,
    "epilogue": epilogue, "image_gen": image_gen,
    "adventures": adventures, "guardrails": guardrails,
    "ship_generation": ship_generation, "ship_building": ship_building,
    "fleet": fleet, "refit": refit, "weapon_design": weapon_design,
    "calendar": calendar_tkg, "consequences": consequences_mod,
    "narrative_seeds": narrative_seeds, "war": war, "memories": memories,
    "locations": locations,
    "pacing": PacingDirector, "objectives": objectives_mod, "environment": environment_mod,
    "npc_autonomy": npc_autonomy, "secrets": secrets_mod, "themes": themes_mod,
    "conversation_log": conversation_log,
    "physical_state": physical_state, "chekhov": chekhov, "world_react": world_react,
    "logistics": logistics, "geopolitics": geopolitics,
    "crew_career": crew_career, "ideology": ideology,
    "corporations": corporations, "collapse": collapse_mod,
    "wreck_assembly": wreck_assembly, "duel": duel, "crew_system": crew_system,
    "voyage": voyage_mod, "population_sentiment": population_sentiment_mod, "ministry_ai": ministry_ai_mod,
}

async def run_single(session_id: int, module_name: str):
    """Run a single module by name."""
    await Database.init()
    mod = MODULE_MAP.get(module_name)
    if not mod:
        print(f"Unknown module: {module_name}")
        print(f"Available: {', '.join(sorted(MODULE_MAP.keys()))}")
        return
    print(f"\nRunning single module: {module_name}")
    await run_module(module_name, mod, session_id)
    await Database.close()

if __name__ == "__main__":
    report_session_drift()
    if len(sys.argv) > 1 and sys.argv[1] != "all":
        asyncio.run(run_single(Config.SESSION_ID, sys.argv[1]))
    else:
        asyncio.run(run_full_tick())
