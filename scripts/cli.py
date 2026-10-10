#!/usr/bin/env python3
"""Unified CLI — single entry point for everything RP."""

import asyncio, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import Config
from core.db import Database
from core.state import StateManager
from scripts.orchestrator import run_full_tick, MODULE_MAP

SID = Config.SESSION_ID  # process default; `_session_id()` resolves the arc per run

#: The `--session` value `__main__` pulled out of argv, or None when the caller passed none.
#: `_session_id()` resolves through it, so a direct call can hold one session for one call.
EXPLICIT_SESSION: str | None = None


def _session_id() -> int:
    """The session this call is for, resolved at call time through `core.session`.

    `Config.SESSION_ID` is fixed at import, so a long-lived process kept answering for the session it
    started on. `require_session` answers per call, and refuses rather than guessing.
    """
    from core.session import require_session

    if EXPLICIT_SESSION is None:
        return require_session(None)
    return require_session(EXPLICIT_SESSION)


def take_session_flag(argv: list[str]) -> tuple[str | None, list[str]]:
    """Pull `--session N` and `--session=N` out of argv. Both forms count."""
    explicit, rest, i = None, [], 0
    while i < len(argv):
        item = argv[i]
        if item == "--session" and i + 1 < len(argv):
            explicit, i = argv[i + 1], i + 2
            continue
        if item.startswith("--session="):
            explicit, i = item.split("=", 1)[1], i + 1
            continue
        rest.append(item)
        i += 1
    return explicit, rest


async def print_status(session: int) -> None:
    """Print the status headline of one session. The pool must be open; the caller closes it.

    `cmd_status` and `continue` share this print, so the loadout lines `main/reference/rp-loadout.md`
    names for `cli.py status` come from one place and cannot drift apart.
    """
    s = await Database.fetchrow("SELECT name, status FROM sessions WHERE id=$1", session)
    r = await Database.fetchrow(
        "SELECT credits, alloys, fuel FROM resources WHERE session_id=$1", session
    )
    t = await Database.fetchval(
        "SELECT COUNT(*) FROM territory WHERE session_id=$1 AND controlling_faction='Setia Empire'",
        session,
    )
    sh = await Database.fetchval("SELECT COUNT(*) FROM ships WHERE session_id=$1", session)
    v = await Database.fetchrow(
        "SELECT progress FROM victory_tracking WHERE faction_id=(SELECT id FROM factions WHERE name='Setia Empire') AND victory_type='score'"
    )
    print(f"\n{'RP Engine Status':^50}")
    print(
        f"  Session:    {s['name'] if s else 'N/A'} (id={session}) | Status: {s['status'] if s else 'N/A'}"
    )
    if r:
        print(f"  Resources:  {r['credits']:,}C / {r['alloys']:,}A / {r['fuel']:,}F")
    print(f"  Territories: {t or 0:,} | Ships: {sh or 0:,}")
    print(f"  Victory:     {v['progress']:.0f}%" if v else "")
    print(
        f"  Modules:     {len(Config.active_modules())} active ({len([k for k, v in Config.MODULES.items() if v])} enabled)"
    )


async def cmd_status():
    await Database.init()
    await print_status(_session_id())
    await Database.close()


async def cmd_health():
    await Database.init()
    status = await Database.status()
    connected = status.get("connected", False)
    print(f"DB connected: {connected}")
    print(f"Tables: {status.get('tables', 0)}")
    print(f"Session: {status.get('session')}")
    await Database.close()


def cmd_modules():
    print(f"{'Modules':^50}")
    print(f"{'Active':8} {'Module':25} {'Source'}")
    print("-" * 50)
    for name in sorted(Config.MODULES.keys()):
        active = "🟢" if Config.MODULES[name] else "🔴"
        in_orch = "orchestrator" if name in MODULE_MAP else "standalone"
        print(f"  {active:6} {name:25} {in_orch}")


async def cmd_tick():
    await run_full_tick(SID)


async def cmd_save(label=""):
    await Database.init()
    fp = await StateManager.save_checkpoint(SID, label)
    print(f"Checkpoint saved: {fp}")
    # also produce full .sav (game-engine style portable snapshot)
    from core.savegame import export_sav

    sav = await export_sav(SID)
    print(f"SAVEGAME saved: {sav}")
    await Database.close()


async def cmd_tail():
    """tail {batch <class> <tier> <type> <count> ["prefix"] | close | prompt | state <character-id> |
    pirate <pirate-json> | start | recall <event-id> "<title>" "<desc>" "<query>" | endings |
    refit "<ship>"}

    The last ten caller-less functions, one per module. Each is the only door its module was missing.
    """
    await Database.init()
    usage = ('Usage: cli.py tail batch <class> <tier> <type> <count> ["prefix"] | close | prompt\n'
             '       cli.py tail state <character-id> | pirate <pirate-json> | start | endings\n'
             '       cli.py tail recall <event-id> "<title>" "<desc>" "<query>" | refit "<ship>"')
    sid = SID
    action = sys.argv[2] if len(sys.argv) > 2 else "close"
    from core import campaign, dramatic_structure, memory, session_rituals
    from core.decision_models import pirate_event_features
    from modules import image_gen, physical_state, refit, ship_generation
    if action == "batch":
        if len(sys.argv) < 7:
            print(usage); await Database.close(); return
        prefix = sys.argv[7] if len(sys.argv) > 7 else None
        out = await ship_generation.generate_batch(sys.argv[3], int(sys.argv[4]), sys.argv[5],
                                                   int(sys.argv[6]), prefix, sid)
    elif action == "prompt":
        out = await image_gen.generate_prompt(sid)
    elif action == "state":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        out = await physical_state.get_state(int(sys.argv[3]), sid)
    elif action == "pirate":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        out = pirate_event_features(json.loads(sys.argv[3]))
    elif action == "start":
        out = await dramatic_structure.session_start(sid)
    elif action == "recall":
        if len(sys.argv) < 7:
            print(usage); await Database.close(); return
        out = await memory.store_and_recall(int(sys.argv[3]), sys.argv[4], sys.argv[5], sys.argv[6], sid)
    elif action == "endings":
        out = await campaign.triggered_endings(sid)
    elif action == "refit":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        out = await refit.upgrade_ship(sys.argv[3], sid)
    else:
        out = await session_rituals.generate_close(sid)
    if isinstance(out, dict):
        for key, value in out.items():
            print(f"  {key}: {value}")
    elif out is None:
        print("  no result")
    else:
        print(f"  result: {out}")
    await Database.close()


async def cmd_misc():
    """misc {herring <investigation-id> | influence <faction> | salvage "<ship-class>" | redacted |
    guard "<action>" | link <decision-id> <event-id> | news-read <article-id> "<headline>"}

    The last scattered entry points. Each of these is the only caller-less function left in its module:
    the red herring in mystery, the influence score in council, ship salvage in pirates, the action
    guardrail, the decision-to-event link, the news read marker, and the register delta in
    core/text_processor.
    """
    await Database.init()
    usage = ('Usage: cli.py misc herring <investigation-id> | influence "<faction>"\n'
             '       cli.py misc salvage "<ship-class>" | guard "<action>"\n'
             '       cli.py misc link <decision-id> <event-id> | news-read <article-id> "<headline>"\n'
             '       cli.py misc register "<text>"')
    sid = SID
    action = sys.argv[2] if len(sys.argv) > 2 else "guard"
    from core import decision
    from modules import council, mystery, news, pirates
    if action == "herring":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        out = await mystery.generate_red_herring(sid, int(sys.argv[3]))
    elif action == "influence":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        territories = await Database.fetch(
            "SELECT system_name, status, controlling_faction, governor_name, fleet_presence"
            " FROM maya_rp.territory WHERE session_id=$1 LIMIT 200", sid)
        ships = await Database.fetch(
            "SELECT id, name FROM maya_rp.ships WHERE session_id=$1 LIMIT 200", sid)
        # The faction argument is a record, not a name: the function reads fields off it, and a string
        # raised AttributeError on the first run.
        faction = await Database.fetchrow(
            "SELECT * FROM maya_rp.factions WHERE name ILIKE $1 LIMIT 1", f"%{sys.argv[3]}%")
        if faction is None:
            out = {"error": f"no faction matching '{sys.argv[3]}'"}
        else:
            out = council.calculate_influence(dict(faction), [dict(r) for r in territories],
                                              [dict(r) for r in ships])
    elif action == "salvage":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        out = await pirates.salvage_ship(sys.argv[3])
    elif action == "guard":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        from modules import guardrails
        out = await guardrails.check_action(sys.argv[3], {"session_id": sid})
    elif action == "link":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        out = await decision.link_event(sid, int(sys.argv[3]), int(sys.argv[4]))
    elif action == "news-read":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        out = await news.mark_read(sid, int(sys.argv[3]), sys.argv[4])
    elif action == "register":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        from core.text_processor import ds_register_delta, enforce_ds_register
        text = sys.argv[3]
        out = {"delta": ds_register_delta(text, enforce_ds_register(text)),
               "processed": enforce_ds_register(text)}
    else:
        out = {"usage": usage}
    if isinstance(out, dict):
        for key, value in out.items():
            print(f"  {key}: {value}")
    elif out is None:
        print("  no result")
    else:
        print(f"  result: {out}")
    await Database.close()


async def cmd_war():
    """war {position <zone> ["terrain"] ["formation"] | exchange <a-hull> <a-tier> <d-hull> <d-tier>
    ["weapon"] ["targeting"] | sieges | siege "<system>" | objectives | progress <kind> <amount> |
    mutiny "<ship>"}

    Eight entry points across four modules had no caller: the tactical position and the exchange
    resolver, the siege starter and its list, the quarterly progress writer and its view, the morale
    event rule and the mutiny scene generator.
    """
    await Database.init()
    usage = ('Usage: cli.py war position <zone> ["terrain"] ["formation"]\n'
             '       cli.py war exchange <a-hull> <a-tier> <d-hull> <d-tier> ["weapon"] ["targeting"]\n'
             '       cli.py war sieges | siege "<system>" | objectives | progress <kind> <amount>\n'
             '       cli.py war mutiny "<ship-name>"')
    sid = SID
    action = sys.argv[2] if len(sys.argv) > 2 else "sieges"
    from modules import objectives, siege, social, tactics
    if action == "position":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        terrain = sys.argv[4] if len(sys.argv) > 4 else None
        formation = sys.argv[5] if len(sys.argv) > 5 else None
        out = await tactics.get_tactical_position(sid, sys.argv[3], terrain, formation)
    elif action == "exchange":
        if len(sys.argv) < 7:
            print(usage); await Database.close(); return
        weapon = sys.argv[7] if len(sys.argv) > 7 else None
        targeting = sys.argv[8] if len(sys.argv) > 8 else None
        out = await tactics.resolve_exchange(int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]),
                                             int(sys.argv[6]), weapon, targeting)
    elif action == "siege":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        out = await siege.start_siege(sys.argv[3], sid)
    elif action == "objectives":
        out = await objectives.quarterly_tasks_view(sid)
    elif action == "progress":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        out = await objectives.update_quarterly_progress(sid, sys.argv[3], int(sys.argv[4]))
    elif action == "mutiny":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        mutiny = await social.calculate_mutiny_risk(sid)
        out = social.generate_mutiny_scene(sys.argv[3], mutiny.get("ringleaders", []))
    else:
        rows = await siege.list_sieges(sid)
        out = {"sieges": len(rows)}
        for row in rows[:8]:
            print(f"  {row}")
    if isinstance(out, dict):
        for key, value in out.items():
            print(f"  {key}: {value}")
    elif out is None:
        print("  no result")
    else:
        print(f"  result: {out}")
    await Database.close()


async def cmd_op():
    """op {darkops | run <operation> "<target>" | log | espionage <faction> <mission-type> <agent> |
    espionage-log}

    Five entry points across two modules had no caller: the dark operation runner and its log, and the
    espionage mission runner and its log. The engine could plan operations and stage none.
    """
    await Database.init()
    usage = ('Usage: cli.py op darkops | log\n'
             '       cli.py op run <operation> "<target>"\n'
             '       cli.py op espionage <faction> <mission-type> <agent> | espionage-log')
    sid = SID
    action = sys.argv[2] if len(sys.argv) > 2 else "darkops"
    from modules import darkops, espionage
    if action == "run":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        out = await darkops.run_op(sys.argv[3], sys.argv[4], sid)
    elif action == "espionage":
        if len(sys.argv) < 6:
            print(usage); await Database.close(); return
        out = await espionage.run_espionage(sys.argv[3], sys.argv[4], sys.argv[5], sid)
    elif action == "espionage-log":
        rows = await espionage.list_espionage_log(sid)
        out = {"entries": len(rows)}
        for row in rows[:8]:
            print(f"  {row}")
    elif action == "log":
        rows = await darkops.list_darkops(sid)
        out = {"operations": len(rows)}
        for row in rows[:8]:
            print(f"  {row}")
    else:
        rows = await darkops.list_darkops(sid)
        out = {"operations": len(rows)}
    if isinstance(out, dict):
        for key, value in out.items():
            print(f"  {key}: {value}")
    elif out is None:
        print("  no result")
    else:
        print(f"  result: {out}")
    await Database.close()


async def cmd_craft():
    """craft {recipes | transmute "<recipe>" [qty] | blueprints | sell <project-id> "<buyer>" [markdown] |
    enroll <crew-id> <program-id> <campus-id>}

    Five entry points across three modules had no caller: the recipe list and the transmutation in
    alchemy.py, the saleable blueprint list and its sale in corporations.py, and the academy enrolment.
    """
    await Database.init()
    usage = ('Usage: cli.py craft recipes | transmute "<recipe>" [qty]\n'
             '       cli.py craft blueprints | sell <project-id> "<buyer>" [markdown-pct]\n'
             '       cli.py craft enroll <crew-id> <program-id> <campus-id>')
    sid = SID
    action = sys.argv[2] if len(sys.argv) > 2 else "recipes"
    from modules import academy, alchemy, corporations
    if action == "transmute":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        qty = int(sys.argv[4]) if len(sys.argv) > 4 else 1
        out = await alchemy.transmute(sys.argv[3], qty, sid)
    elif action == "blueprints":
        rows = await corporations.list_saleable_blueprints(sid)
        out = {"blueprints": len(rows)}
        for row in rows[:8]:
            print(f"  {row}")
    elif action == "sell":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        # Omit the argument when the caller did not give one, so the module's own default stands. My
        # first version passed 0 and silently overrode it: `craft sell <id> <buyer>` sold at full
        # price while calling the function directly sold at the module's default markdown.
        if len(sys.argv) > 5:
            out = await corporations.sell_blueprint(sid, int(sys.argv[3]), sys.argv[4], int(sys.argv[5]))
        else:
            out = await corporations.sell_blueprint(sid, int(sys.argv[3]), sys.argv[4])
    elif action == "enroll":
        if len(sys.argv) < 6:
            print(usage); await Database.close(); return
        out = await academy.enroll_crew(int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), sid)
    else:
        rows = await alchemy.list_recipes()
        out = {"recipes": len(rows)}
        for row in rows[:8]:
            print(f"  {row}")
    if isinstance(out, dict):
        for key, value in out.items():
            print(f"  {key}: {value}")
    elif out is None:
        print("  no result")
    else:
        print(f"  result: {out}")
    await Database.close()


async def cmd_world():
    """world {where <character-id> "<location>" | goto "<location>" ["ship"] | seeds | plant <type>
    "<content>" | foreshadow <seed-id> | sites [count] | excavate <site-id> | secret | discover "<context>"}

    Nine entry points across four small modules had no caller: presence and travel in locations.py, the
    seed planter and its foreshadow bookkeeping in narrative_seeds.py, the site seeder and the dig in
    archaeology.py, and the discovery rolls in secrets.py.
    """
    await Database.init()
    usage = ('Usage: cli.py world where <character-id> "<location>" | goto "<location>" ["ship"]\n'
             '       cli.py world seeds | plant <type> "<content>" | foreshadow <seed-id>\n'
             '       cli.py world sites [count] | excavate <site-id>\n'
             '       cli.py world secret | discover "<context>"')
    sid = SID
    action = sys.argv[2] if len(sys.argv) > 2 else "seeds"
    from modules import archaeology, locations, narrative_seeds, secrets
    if action == "where":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        out = await locations.set_character_presence(int(sys.argv[3]), sys.argv[4], sid)
    elif action == "goto":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        ship = sys.argv[4] if len(sys.argv) > 4 else None
        out = await locations.cmd_goto(sys.argv[3], ship, sid)
    elif action == "plant":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        out = await narrative_seeds.plant_seed(sys.argv[3], sys.argv[4], None, None, None, sid)
    elif action == "foreshadow":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        out = await narrative_seeds.mark_foreshadowed(int(sys.argv[3]), sid)
    elif action == "sites":
        count = int(sys.argv[3]) if len(sys.argv) > 3 else 3
        out = await archaeology.seed_sites(sid, count)
    elif action == "excavate":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        out = await archaeology.excavate(int(sys.argv[3]), sid)
    elif action == "secret":
        out = await secrets.seed_initial(sid)
    elif action == "discover":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        out = await secrets.check_discovery(sys.argv[3], sid)
    else:
        rows = await narrative_seeds.get_foreshadow_ops(sid)
        out = {"foreshadow_ops": len(rows)}
        for row in rows[:8]:
            print(f"  {row}")
    if isinstance(out, dict):
        for key, value in out.items():
            print(f"  {key}: {value}")
    elif out is None:
        print("  no result")
    else:
        print(f"  result: {out}")
    await Database.close()


async def cmd_inner():
    """inner {world <character-id> | surface "<character-name>" "<context>" | react "<event-type>" |
    offscreen}

    Four entry points across two small modules: the inner world read and the memory surface in
    memories.py, and the event reaction and off-screen discovery in npc_autonomy.py.
    """
    await Database.init()
    usage = ('Usage: cli.py inner world <character-id> | surface "<name>" "<context>"\n'
       '       cli.py inner react "<event-type>" | offscreen')
    sid = SID
    action = sys.argv[2] if len(sys.argv) > 2 else "offscreen"
    from modules import memories, npc_autonomy
    if action == "world":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        out = await memories.get_inner_world(int(sys.argv[3]), sid)
    elif action == "surface":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        out = await memories.cmd_memory_surface(sys.argv[3], sys.argv[4], sid)
    elif action == "react":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        out = await npc_autonomy.react_to_event(sys.argv[3], sid)
    else:
        out = await npc_autonomy.discover_off_screen(sid)
    if isinstance(out, dict):
        for key, value in out.items():
            print(f"  {key}: {value}")
    elif out is None:
        print("  no result")
    else:
        print(f"  result: {out}")
    await Database.close()


async def cmd_burn():
    """burn {summary | caravan}

    Two entry points of `modules/fleet_economy.py` had no caller: the fuel burn summary and the caravan
    generator, so the fleet paid for fuel nothing accounted for.
    """
    await Database.init()
    sid = SID
    action = sys.argv[2] if len(sys.argv) > 2 else "summary"
    from modules import fleet_economy
    out = (await fleet_economy.generate_caravan(sid) if action == "caravan"
           else await fleet_economy.get_burn_summary(sid))
    if isinstance(out, dict):
        for key, value in out.items():
            print(f"  {key}: {value}")
    elif out is None:
        print("  no result")
    else:
        print(f"  result: {out}")
    await Database.close()


async def cmd_artifact():
    """artifact {list | medals | award <recipient> <tier> "<backstory>" | equip <artifact-id> <target-id>}

    Three entry points of `modules/artifacts.py` had no caller: the relic list, the medal award and the
    medal list. The module could discover and equip, and nothing could look at what it had found.
    """
    await Database.init()
    usage = ('Usage: cli.py artifact list | medals\n'
             '       cli.py artifact award "<recipient>" <tier> "<backstory>"\n'
             '       cli.py artifact equip <artifact-id> <target-id>')
    sid = SID
    action = sys.argv[2] if len(sys.argv) > 2 else "list"
    from modules import artifacts
    if action == "award":
        if len(sys.argv) < 6:
            print(usage); await Database.close(); return
        out = await artifacts.award_medal(sid, sys.argv[3], int(sys.argv[4]), sys.argv[5])
    elif action == "medals":
        rows = await artifacts.list_medals(sid)
        out = {"medals": len(rows)}
        for row in rows[:10]:
            print(f"  {row}")
    elif action == "equip":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        out = await artifacts.equip(int(sys.argv[3]), int(sys.argv[4]), sid)
    else:
        rows = await artifacts.list_artifacts(sid)
        out = {"artifacts": len(rows)}
        for row in rows[:10]:
            print(f"  {row}")
    if isinstance(out, dict):
        for key, value in out.items():
            print(f"  {key}: {value}")
    elif out is None:
        print("  no result")
    else:
        print(f"  result: {out}")
    await Database.close()


async def cmd_encounter():
    """encounter {templates | generate <category> [difficulty] | log <type> "<title>" "<description>"}

    Three entry points of `modules/encounters.py` had no caller: the template list, the generator and the
    event log. The tick ran against events nothing could create or record.
    """
    await Database.init()
    usage = ('Usage: cli.py encounter templates\n'
             '       cli.py encounter generate <category> [difficulty]\n'
             '       cli.py encounter log "<event-type>" "<title>" "<description>"')
    sid = SID
    action = sys.argv[2] if len(sys.argv) > 2 else "templates"
    from modules import encounters
    if action == "generate":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        difficulty = int(sys.argv[4]) if len(sys.argv) > 4 else 5
        out = await encounters.generate_event(sid, sys.argv[3], difficulty)
    elif action == "log":
        if len(sys.argv) < 6:
            print(usage); await Database.close(); return
        out = await encounters.log_event(sid, sys.argv[3], sys.argv[4], sys.argv[5])
    else:
        templates = encounters.get_encounter_templates()
        out = {"templates": len(templates)}
        for name in list(templates)[:8]:
            print(f"  {name}")
    if isinstance(out, dict):
        for key, value in out.items():
            print(f"  {key}: {value}")
    elif out is None:
        print("  no result")
    else:
        print(f"  result: {out}")
    await Database.close()


async def cmd_bond():
    """bond {ranking | shift <action> [quality] | heal <character-id> "<activity>" |
    release <character-id> | aftercare <target-id> <initiator-id>}

    Five entry points of `modules/romance.py` had no caller. All five touch engine tables only
    (`romance_arcs`, `characters`, `intimacy_events`, `sessions`), which is what the house rule requires:
    private scenes live in engine state and never in a file or the novel.
    """
    await Database.init()
    usage = ('Usage: cli.py bond ranking\n'
             '       cli.py bond shift <action> [quality-word]\n'
             '       cli.py bond heal <character-id> "<activity>"\n'
             '       cli.py bond release <character-id>\n'
             '       cli.py bond aftercare <target-id> <initiator-id>')
    sid = SID
    action = sys.argv[2] if len(sys.argv) > 2 else "ranking"
    from modules import romance
    if action == "shift":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        # The second argument is a quality word, not a number: the function lowercases it and looks it
        # up in BOND_SHIFT_MATRIX. Passing an int raised AttributeError on the first run.
        quality = sys.argv[4] if len(sys.argv) > 4 else "neutral"
        out = romance.calculate_bond_shift(sys.argv[3], quality)
    elif action == "heal":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        out = await romance.process_healing(int(sys.argv[3]), sys.argv[4], sid)
    elif action == "release":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        out = await romance.release_and_heal(int(sys.argv[3]), sid)
    elif action == "aftercare":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        out = await romance.process_aftercare(int(sys.argv[3]), int(sys.argv[4]), sid)
    else:
        rows = await romance.get_bond_ranking(sid)
        out = {"ranked": len(rows)}
        for row in rows[:10]:
            print(f"  {row}")
    if isinstance(out, dict):
        for key, value in out.items():
            print(f"  {key}: {value}")
    elif out is None:
        print("  no result")
    else:
        print(f"  result: {out}")
    await Database.close()


async def cmd_shipyard():
    """shipyard {shortage | build <class> <tier> <type> "<name>" "<location>" |
    capacity <required-crew> | assign <ship-id> <required-crew>}

    Four entry points of `modules/ship_building.py` had no caller: the builder, the capacity check, the
    crew assignment and the shortage report. A hull could not be laid down, so the fleet had nothing to
    assign crew to.
    """
    await Database.init()
    usage = ('Usage: cli.py shipyard shortage\n'
             '       cli.py shipyard build <class> <tier> <type> "<name>" "<location>"\n'
             '       cli.py shipyard capacity <required-crew>\n'
             '       cli.py shipyard assign <ship-id> <required-crew>')
    sid = SID
    action = sys.argv[2] if len(sys.argv) > 2 else "shortage"
    from modules import ship_building
    if action == "build":
        if len(sys.argv) < 8:
            print(usage); await Database.close(); return
        out = await ship_building.build_ship(sys.argv[3], int(sys.argv[4]), sys.argv[5], sys.argv[6],
                                             sys.argv[7], sid)
    elif action == "capacity":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        out = await ship_building.check_crew_capacity(sid, int(sys.argv[3]))
    elif action == "assign":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        out = await ship_building.assign_crew_to_ship(sid, int(sys.argv[3]), int(sys.argv[4]))
    else:
        out = await ship_building.crew_shortage_report(sid)
    # A function that answers with a bool, a number or a list had its answer swallowed here: `or {}`
    # turned False into an empty dict and the script printed "no result", which reads as "nothing
    # happened" when the answer was actually no.
    if isinstance(out, dict):
        for key, value in out.items():
            print(f"  {key}: {value}")
    elif out is None:
        print("  no result")
    else:
        print(f"  result: {out}")
    await Database.close()


async def cmd_fleet():
    """fleet {list | create "<name>" [formation] | assign "<ship>" "<fleet>" [position] |
    battle "<fleet>" ["tactic"] [threat]}

    Formations the schema allows: wall, crescent, spearhead, screen, arrow, scatter.

    Three entry points of `modules/fleet.py` had no caller: the fleet builder, the ship assignment and
    the battle. The tick and the listing ran against fleets nothing could form.
    """
    await Database.init()
    usage = ('Usage: cli.py fleet list\n'
             '       cli.py fleet create "<name>" ["formation"]\n'
             '       cli.py fleet assign "<ship>" "<fleet>" [position]\n'
             '       cli.py fleet battle "<fleet>" ["tactic"] [threat]')
    sid = SID
    action = sys.argv[2] if len(sys.argv) > 2 else "list"
    from modules import fleet
    if action == "create":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        formation = sys.argv[4] if len(sys.argv) > 4 else "spearhead"
        out = await fleet.create_fleet(sys.argv[3], formation, sid)
    elif action == "assign":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        position = int(sys.argv[5]) if len(sys.argv) > 5 else 0
        out = await fleet.assign_ship(sys.argv[3], sys.argv[4], position, sid)
    elif action == "battle":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        tactic = sys.argv[4] if len(sys.argv) > 4 else "balanced"
        threat = int(sys.argv[5]) if len(sys.argv) > 5 else 100
        out = await fleet.fleet_battle(sys.argv[3], tactic, threat, sid)
    else:
        rows = await fleet.list_fleets(sid)
        out = {"fleets": len(rows)}
        for row in rows[:10]:
            print(f"  {row}")
    # A function that answers with a bool, a number or a list had its answer swallowed here: `or {}`
    # turned False into an empty dict and the script printed "no result", which reads as "nothing
    # happened" when the answer was actually no.
    if isinstance(out, dict):
        for key, value in out.items():
            print(f"  {key}: {value}")
    elif out is None:
        print("  no result")
    else:
        print(f"  result: {out}")
    await Database.close()


async def cmd_career():
    """career {shortage | specialize <crew-id> "<specialization>" | promote <crew-id> |
    award <crew-id> <xp> ["source"]}

    Three entry points of `modules/crew_career.py` had no caller: the specialization, the promotion and
    the shortage report. A crew member could earn experience and never spend it.
    """
    await Database.init()
    usage = ('Usage: cli.py career shortage\n'
             '       cli.py career specialize <crew-id> "<specialization>"\n'
             '       cli.py career promote <crew-id>\n'
             '       cli.py career award <crew-id> <xp> ["source"]')
    sid = SID
    action = sys.argv[2] if len(sys.argv) > 2 else "shortage"
    from modules import crew_career
    if action == "specialize":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        out = await crew_career.assign_specialization(int(sys.argv[3]), sys.argv[4], sid)
    elif action == "promote":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        out = await crew_career.promote_crew(int(sys.argv[3]), sid)
    elif action == "award":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        source = sys.argv[5] if len(sys.argv) > 5 else "manual"
        out = await crew_career.award(int(sys.argv[3]), int(sys.argv[4]), source, sid)
    elif action == "produce":
        from modules import crew_system
        out = await crew_system.produce_crew(sid)
    else:
        out = await crew_career.talent_shortage(sid)
    # A function that answers with a bool, a number or a list had its answer swallowed here: `or {}`
    # turned False into an empty dict and the script printed "no result", which reads as "nothing
    # happened" when the answer was actually no.
    if isinstance(out, dict):
        for key, value in out.items():
            print(f"  {key}: {value}")
    elif out is None:
        print("  no result")
    else:
        print(f"  result: {out}")
    await Database.close()


async def cmd_spy():
    """spy {build "<type>" "<name>" | deploy "<name>" "<lane>" | hack "<name>" <operation> <target> |
    cloaks | anticloak "<system>" <level>}

    Five entry points of `modules/stealth.py` had no caller: the two cloak actions, the spy builder, the
    deployment and the hack. The tick ran against spies nothing could build.
    """
    await Database.init()
    usage = ('Usage: cli.py spy build "<unit-type>" "<name>"\n'
             '       cli.py spy deploy "<name>" "<lane>"\n'
             '       cli.py spy hack "<name>" <operation> <target>\n'
             '       cli.py spy cloaks | anticloak "<system>" <level>')
    sid = SID
    action = sys.argv[2] if len(sys.argv) > 2 else "cloaks"
    from modules import stealth
    if action == "build":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        out = await stealth.build_spy(sys.argv[3], sys.argv[4], sid)
    elif action == "deploy":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        out = await stealth.deploy_spy(sys.argv[3], sys.argv[4], sid)
    elif action == "hack":
        if len(sys.argv) < 6:
            print(usage); await Database.close(); return
        out = await stealth.hack(sys.argv[3], sys.argv[4], sys.argv[5], sid)
    elif action == "anticloak":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        out = await stealth.build_anticloak(sys.argv[3], int(sys.argv[4]), sid)
    else:
        rows = await stealth.list_anticloak(sid)
        out = {"cloaks": len(rows)}
        for row in rows[:10]:
            print(f"  {row}")
    # A function that answers with a bool, a number or a list had its answer swallowed here: `or {}`
    # turned False into an empty dict and the script printed "no result", which reads as "nothing
    # happened" when the answer was actually no.
    if isinstance(out, dict):
        for key, value in out.items():
            print(f"  {key}: {value}")
    elif out is None:
        print("  no result")
    else:
        print(f"  result: {out}")
    await Database.close()


async def cmd_tech():
    """tech {view | info "<tech>" | labs | build-lab <colony> "<name>" "<field>" |
    assign <character> <lab-id> "<specialty>"}

    Four entry points of `modules/tech_tree.py` had no caller, and they are the research surface: the
    tree, one technology, the labs and the scientist assignment.
    """
    await Database.init()
    usage = ('Usage: cli.py tech view | labs\n'
             '       cli.py tech info "<tech-name>"\n'
             '       cli.py tech build-lab <colony-id> "<name>" "<field>"\n'
             '       cli.py tech assign <character-id> <lab-id> "<specialty>"')
    sid = SID
    action = sys.argv[2] if len(sys.argv) > 2 else "view"
    from modules import tech_tree
    if action == "info":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        out = await tech_tree.tech_info(sys.argv[3], sid)
    elif action == "build-lab":
        if len(sys.argv) < 6:
            print(usage); await Database.close(); return
        out = await tech_tree.build_lab(int(sys.argv[3]), sys.argv[4], sys.argv[5], sid)
    elif action == "assign":
        if len(sys.argv) < 6:
            print(usage); await Database.close(); return
        out = await tech_tree.assign_scientist(int(sys.argv[3]), int(sys.argv[4]), sys.argv[5], sid)
    elif action == "labs":
        rows = await tech_tree.list_labs(sid)
        out = {"labs": len(rows)}
        for row in rows[:10]:
            print(f"  {row}")
    else:
        rows = await tech_tree.view_tech(sid)
        out = {"technologies": len(rows)}
        for row in (rows or [])[:8]:
            print(f"  {row}")
    # A function that answers with a bool, a number or a list had its answer swallowed here: `or {}`
    # turned False into an empty dict and the script printed "no result", which reads as "nothing
    # happened" when the answer was actually no.
    if isinstance(out, dict):
        for key, value in out.items():
            print(f"  {key}: {value}")
    elif out is None:
        print("  no result")
    else:
        print(f"  result: {out}")
    await Database.close()


async def cmd_forge():
    """forge {weapons | blueprints | design <name> <category> <damage> <range> <slot> <tier> |
    produce <blueprint> [qty] | upgrades <weapon-id> | fit <weapon-id> "<upgrade>"}

    Six entry points of `modules/weapon_design.py` had no caller: the two catalogues, the designer, the
    production line, the upgrade list and the fitting. `apply_upgrade` had been repaired in this review
    and still had no caller, which is the state this command exists to end.
    """
    await Database.init()
    usage = ('Usage: cli.py forge weapons | blueprints | upgrades <weapon-id>\n'
             '       cli.py forge design <name> <category> <damage> <range> <slot> <tier>\n'
             '       cli.py forge produce "<blueprint>" [qty]\n'
             '       cli.py forge fit <weapon-id> "<upgrade-name>"')
    sid = SID
    action = sys.argv[2] if len(sys.argv) > 2 else "weapons"
    from modules import weapon_design as wd
    if action == "blueprints":
        rows = await wd.list_blueprints()
        out = {"blueprints": len(rows)}
        for row in rows[:10]:
            print(f"  #{row.get('id')} {row.get('name')} · {row.get('category')}"
                  f" · dmg {row.get('base_damage')}")
    elif action == "design":
        if len(sys.argv) < 9:
            print(usage); await Database.close(); return
        out = await wd.design_blueprint(sys.argv[3], sys.argv[4], int(sys.argv[5]), int(sys.argv[6]),
                                        sys.argv[7], int(sys.argv[8]), sid)
    elif action == "produce":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        qty = int(sys.argv[4]) if len(sys.argv) > 4 else 1
        out = await wd.produce_weapons(sys.argv[3], qty, sid)
    elif action == "upgrades":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        rows = await wd.list_upgrades(int(sys.argv[3]))
        out = {"upgrades": len(rows)}
        for row in rows[:10]:
            print(f"  {row.get('upgrade_name')} · {row.get('effect_type')} {row.get('effect_value')}"
                  f" · {row.get('cost')} credits")
    elif action == "fit":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        out = await wd.apply_upgrade(int(sys.argv[3]), sys.argv[4], session_id=sid)
    else:
        rows = await wd.list_weapons()
        out = {"weapons": len(rows)}
    # A function that answers with a bool, a number or a list had its answer swallowed here: `or {}`
    # turned False into an empty dict and the script printed "no result", which reads as "nothing
    # happened" when the answer was actually no.
    if isinstance(out, dict):
        for key, value in out.items():
            print(f"  {key}: {value}")
    elif out is None:
        print("  no result")
    else:
        print(f"  result: {out}")
    await Database.close()


async def cmd_council():
    """council {seats | status | cohesion | route "<task>" | authority [hours] | plots [quality] |
    assign <crew-id> <role> | thwart <id> <method> | titles | revoke "<system>" "<reason>"}

    The council is a cabinet politics engine with twenty-five unreachable functions. This wires the six
    that touch the database; the nineteen pure ones (votes, plots, crises, influence) need their own
    driver and their own round.
    """
    await Database.init()
    usage = ('Usage: cli.py council seats | status | cohesion | titles\n'
             '       cli.py council route "<task>" | authority [hours]\n'
             '       cli.py council plots [network-quality]\n'
             '       cli.py council assign <crew-id> <watcher|networker|interrogator>\n'
             '       cli.py council thwart <conspiracy-id> [method]\n'
             '       cli.py council revoke "<system-name>" "<reason>"')
    sid = SID
    action = sys.argv[2] if len(sys.argv) > 2 else "seats"
    from modules import council
    if action == "cohesion":
        # get_cohesion reads a seat list, not a session: it was written as a pure function and the
        # caller has to fetch the seats first.
        out = council.get_cohesion(await council.get_cabinet_seats(sid))
    elif action == "plots":
        quality = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        rows = await council.scan_for_plots(sid, quality)
        out = {"detected": len(rows)}
        for row in rows[:10]:
            print(f"  #{row['conspiracy_id']} {row['description']} (phase {row['phase']})")
    elif action == "assign":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        out = await council.assign_agent(sid, int(sys.argv[3]), sys.argv[4])
    elif action == "thwart":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        method = sys.argv[4] if len(sys.argv) > 4 else "surveillance"
        out = await council.thwart_plot(int(sys.argv[3]), method)
    elif action == "titles":
        out = {"revocations": await council.check_title_revocation(sid)}
    elif action == "revoke":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        out = await council.revoke_title(sid, sys.argv[3], sys.argv[4])
    elif action == "vote":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        seats = await council.get_cabinet_seats(sid)
        votes = [{"position": "aye"}] * int(sys.argv[3]) + [{"position": "nay"}] * int(sys.argv[4])
        if len(sys.argv) > 5:
            votes += [{"position": "abstain"}] * int(sys.argv[5])
        out = council.calculate_vote(seats, votes)
    elif action == "promote":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        seats = await council.get_cabinet_seats(sid)
        seat = next((s for s in seats if str(s.get("title", "")).lower() == sys.argv[3].lower()), None)
        if seat is None:
            out = {"error": f"no seat titled '{sys.argv[3]}' in session {sid}"}
        else:
            # `promote_seat` computes the new seat and writes nothing, so the boundary has to persist it
            # or the promotion is a sentence that never happened.
            promoted = council.promote_seat(seat, sys.argv[4])
            await Database.execute(
                "UPDATE maya_rp.cabinet_hierarchy SET holder=$1 WHERE id=$2", sys.argv[4], seat["id"])
            out = {"seat": promoted.get("title"), "holder": promoted.get("holder"), "persisted": True}
    elif action == "plot":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        seats = await council.get_cabinet_seats(sid)
        out = council.generate_plot(sys.argv[3], {}, seats)
    elif action == "expose":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        out = council.check_exposure(json.loads(sys.argv[3]))
    elif action == "phase":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        out = council.execute_phase(json.loads(sys.argv[3]), int(sys.argv[4]))
    elif action == "hooks":
        rows = await Database.fetch(
            "SELECT system_name, status, controlling_faction, governor_name, fleet_presence"
            " FROM maya_rp.territory WHERE session_id=$1 LIMIT 200", sid)
        seats = await council.get_cabinet_seats(sid)
        # `generate_mystery_hooks` reads `cabinet_control`, a field the territory table does not have, so
        # fed raw rows it always saw the default 100 and never produced a hook. The control is computed
        # by the module's own rule rather than invented here.
        enriched = []
        for row in rows:
            item = dict(row)
            item["cabinet_control"] = council.calculate_territory_control(item, seats)
            enriched.append(item)
        hooks = council.generate_mystery_hooks(enriched)
        out = {"hooks": len(hooks)}
        for hook in hooks[:5]:
            print(f"  {hook.get('system')}: {hook.get('hook')}")
    elif action == "wife":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        seats = await council.get_cabinet_seats(sid)
        seat = next((s for s in seats if str(s.get("title", "")).lower() == sys.argv[3].lower()), None)
        if seat is None:
            out = {"error": f"no seat titled '{sys.argv[3]}' in session {sid}"}
        else:
            hours = int(sys.argv[4]) if len(sys.argv) > 4 else 0
            decrees = await Database.fetchval(
                "SELECT count(*) FROM maya_rp.cabinet_decrees WHERE session_id=$1 AND status='executing'",
                sid) or 0
            out = {"seat": seat.get("title"), "wife_status": council.get_wife_status(seat, decrees, hours)}
    elif action == "control":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        row = await Database.fetchrow(
            "SELECT system_name, status, controlling_faction, governor_name, fleet_presence"
            " FROM maya_rp.territory WHERE session_id=$1 AND system_name ILIKE $2 LIMIT 1",
            sid, f"%{sys.argv[3]}%")
        if row is None:
            out = {"error": f"no territory matching '{sys.argv[3]}' in session {sid}"}
        else:
            seats = await council.get_cabinet_seats(sid)
            out = {"system": row["system_name"],
                   "control": council.calculate_territory_control(dict(row), seats)}
    elif action == "contest":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        action_name = sys.argv[5] if len(sys.argv) > 5 else "policy"
        out = council.influence_contest(int(sys.argv[3]), int(sys.argv[4]), action_name)
    elif action == "exposure":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        out = council.shadow_exposure_risk(int(sys.argv[3]), int(sys.argv[4]))
    elif action == "override":
        seats = await council.get_cabinet_seats(sid)
        consul = next((s for s in seats if s.get("tier") == 0), None)
        out = council.consul_override(consul)
    elif action == "decree":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        details = json.loads(sys.argv[4]) if len(sys.argv) > 4 else {}
        out = await council.issue_decree(sid, sys.argv[3], details)
    elif action == "crisis":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        out = council.trigger_crisis(sys.argv[3])
    elif action == "escalate":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        advance = int(sys.argv[4]) if len(sys.argv) > 4 else 1
        out = council.escalate_crisis(council.trigger_crisis(sys.argv[3]), advance)
    elif action == "meeting":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        out = council.convene_meeting(sys.argv[3], {"session_id": sid})
    elif action == "brief":
        decrees = await Database.fetch(
            "SELECT * FROM maya_rp.cabinet_decrees WHERE session_id=$1 ORDER BY id DESC LIMIT 20",
            sid)
        out = council.situation_briefing([dict(r) for r in decrees], [], [])
    elif action == "status":
        seats = await council.get_cabinet_seats(sid)
        print(council.status_report(seats))
        out = {"cohesion": council.get_cohesion(seats)}
    elif action == "route":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        out = council.route_task(await council.get_cabinet_seats(sid), sys.argv[3])
    elif action == "authority":
        hours = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        seats = await council.get_cabinet_seats(sid)
        found = council.get_emergency_authority(seats, hours)
        if found:
            out = found
        elif hours < 24:
            out = {"authority": f"none: {hours}h of absence, and the chain needs 24"}
        else:
            # 24 hours passed and still nobody, so the reason is the cabinet, not the clock. Saying the
            # clock would send the reader to look in the wrong place.
            out = {"authority": f"none: {hours}h passed but no active seat in the emergency chain",
                   "chain": list(council.EMERGENCY_CHAIN)}
    else:
        seats = await council.get_cabinet_seats(sid)
        out = {"seats": len(seats), "valid": council.validate_cabinet(seats)}
        for seat in seats[:12]:
            print(f"  {seat.get('seat_name') or seat.get('seat')}: {seat.get('holder_name') or seat.get('holder')}")
    # A function that answers with a bool, a number or a list had its answer swallowed here: `or {}`
    # turned False into an empty dict and the script printed "no result", which reads as "nothing
    # happened" when the answer was actually no.
    if isinstance(out, dict):
        for key, value in out.items():
            print(f"  {key}: {value}")
    elif out is None:
        print("  no result")
    else:
        print(f"  result: {out}")
    await Database.close()


async def cmd_map():
    """map {stats | sectors | planets | colonies | visible | reachable <origin> [jumps] |
    factions | relations <a> <b> | presence | find "<query>" | system "<name>" | reveal "<name>" [level]}

    Twelve readers of `modules/celestial.py` had no caller. They are the map surface the five-plane
    geometry will need, and every one of them takes a session and uses it.
    """
    await Database.init()
    usage = ('Usage: cli.py map stats | sectors | planets | colonies | visible | factions | presence\n'
             '       cli.py map reachable "<origin>" [max-jumps]\n'
             '       cli.py map relations "<faction-a>" "<faction-b>"\n'
             '       cli.py map find "<query>" | system "<name>" | reveal "<name>" [level]')
    sid = SID
    action = sys.argv[2] if len(sys.argv) > 2 else "stats"
    from modules import celestial as c
    if action == "sectors":
        out = await c.get_sector_breakdown(sid)
    elif action == "planets":
        out = await c.get_planet_stats(sid)
    elif action == "colonies":
        out = await c.get_colonies(sid)
    elif action == "visible":
        out = {"visible": len(await c.get_visible_systems(sid, 0))}
    elif action == "reachable":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        jumps = int(sys.argv[4]) if len(sys.argv) > 4 else 3
        rows = await c.get_reachable_systems(sid, sys.argv[3], jumps)
        out = {"reachable": len(rows)}
    elif action == "factions":
        out = await c.get_faction_territories(sid)
    elif action == "relations":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        out = {"relations": await c.get_faction_relations(sid, sys.argv[3], sys.argv[4])}
    elif action == "presence":
        out = await c.get_faction_presence(sid)
    elif action == "find":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        rows = await c.search_all(sid, sys.argv[3])
        out = {"hits": len(rows)}
        for row in rows[:10]:
            print(f"  {row}")
    elif action == "system":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        out = await c.get_system_detail(sid, sys.argv[3]) or {"system": "not found"}
    elif action == "reveal":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        level = int(sys.argv[4]) if len(sys.argv) > 4 else 2
        out = await c.reveal_system(sid, sys.argv[3], level)
    else:
        out = await c.get_system_stats(sid)
    if not out:
        print("  no result")
    for key, value in (out or {}).items():
        print(f"  {key}: {len(value) if isinstance(value, list) else value}")
    await Database.close()


async def cmd_prison():
    """prison {capture <count> <faction> | cells | tiers | hold <id> | paths <id> | convert <id> <path> |
    intel <id> <investigation-id> "<text>" | intimacy <id> <path> | secure <id> [level] [guards] |
    counter <id> "<measure>" | death <id> "<cause>"}

    Eleven entry points of `modules/prison.py` had no caller, and they are the module's whole surface:
    `resolve_capture` is the door prisoners come through, and nothing could open it, so the live paths
    (interrogate, check_conversion, process_escapes) could only ever run against prisoners nothing could
    create.
    """
    await Database.init()
    usage = ("Usage: cli.py prison capture <count> <faction> | cells | tiers | hold <prisoner-id>\n"
             "       cli.py prison paths <id> | convert <id> <path> | intimacy <id> <path>\n"
             "       cli.py prison intel <id> <investigation-id> \"<text>\"\n"
             "       cli.py prison secure <id> [level] [guards] | counter <id> \"<measure>\"\n"
             "       cli.py prison death <id> \"<cause>\"")
    sid = SID
    action = sys.argv[2] if len(sys.argv) > 2 else "cells"
    from modules import prison
    if action == "capture":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        rows = await prison.resolve_capture(int(sys.argv[3]), sys.argv[4], session_id=sid)
        out = {"prisoners_taken": len(rows)}
        for row in rows[:5]:
            print(f"  {row.get('name')} · {row.get('rank')}")
    elif action == "tiers":
        for tier in sorted(prison.INTERROGATION_TIERS):
            cfg = prison.get_interrogation_tier_info(tier)
            print(f"  {tier}: {cfg}")
        await Database.close(); return
    elif action == "hold":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        out = await prison.assign_cell(int(sys.argv[3]), sid)
    elif action == "paths":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        out = {"paths": await prison.get_available_intimacy_paths(int(sys.argv[3]), session_id=sid)}
    elif action == "convert":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        out = await prison.execute_conversion(int(sys.argv[3]), sys.argv[4], sid)
    elif action == "intimacy":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        out = await prison.initiate_intimacy(int(sys.argv[3]), sys.argv[4], session_id=sid)
    elif action == "intel":
        if len(sys.argv) < 6:
            print(usage); await Database.close(); return
        out = await prison.feed_intel_to_investigation(int(sys.argv[3]), int(sys.argv[4]), sys.argv[5], sid)
    elif action == "secure":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        level = sys.argv[4] if len(sys.argv) > 4 else "standard"
        guards = int(sys.argv[5]) if len(sys.argv) > 5 else 0
        out = await prison.upgrade_security(int(sys.argv[3]), level, guards, sid)
    elif action == "counter":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        out = await prison.apply_countermeasure(int(sys.argv[3]), sys.argv[4], sid)
    elif action == "death":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        out = await prison.record_death(int(sys.argv[3]), sys.argv[4], sid)
    else:
        out = await prison.get_fleet_capacity(sid)
    # A function that answers with a bool, a number or a list had its answer swallowed here: `or {}`
    # turned False into an empty dict and the script printed "no result", which reads as "nothing
    # happened" when the answer was actually no.
    if isinstance(out, dict):
        for key, value in out.items():
            print(f"  {key}: {value}")
    elif out is None:
        print("  no result")
    else:
        print(f"  result: {out}")
    await Database.close()


async def cmd_social():
    """social {tick | mutiny | morale <delta> [reason] | events <type> | relation <a> <b> | bond <a> <b> <delta>}

    The social cluster had no door: update_morale was a second, unused morale writer, and the event,
    tension and relationship helpers were reachable from nothing while the tick reported only a number.
    """
    await Database.init()
    usage = ('Usage: cli.py social tick | mutiny\n'
             '       cli.py social morale <delta> ["reason"]\n'
             '       cli.py social events <event-type>\n'
             '       cli.py social relation <char-a> <char-b>\n'
             '       cli.py social bond <char-a> <char-b> <delta>')
    sid = SID
    action = sys.argv[2] if len(sys.argv) > 2 else "tick"
    from modules import social
    if action == "mutiny":
        out = await social.calculate_mutiny_risk(sid)
    elif action == "morale":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        reason = sys.argv[4] if len(sys.argv) > 4 else ""
        before = await social._get_fleet_morale(sid)
        after = await social.update_morale(sid, int(sys.argv[3]), reason)
        out = {"before": before, "after": after, "delta": int(sys.argv[3]), "reason": reason}
    elif action == "morale-event":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        multiplier = float(sys.argv[5]) if len(sys.argv) > 5 else 1.0
        current = await social._get_fleet_morale(sid)
        out = social.apply_morale_event(current, sys.argv[3], multiplier)
    elif action == "events":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        out = social.get_social_event_config(sys.argv[3])
        out = {"config_keys": len(out), "event_type": social.detect_event_type(sys.argv[3])}
    elif action == "relation":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        out = await social.get_relationship(sid, int(sys.argv[3]), int(sys.argv[4])) or {"relationship": "none"}
    elif action == "bond":
        if len(sys.argv) < 6:
            print(usage); await Database.close(); return
        out = await social.shift_bond(sid, int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]))
    else:
        out = await social.run_tick(sid)
    # A function that answers with a bool, a number or a list had its answer swallowed here: `or {}`
    # turned False into an empty dict and the script printed "no result", which reads as "nothing
    # happened" when the answer was actually no.
    if isinstance(out, dict):
        for key, value in out.items():
            print(f"  {key}: {value}")
    elif out is None:
        print("  no result")
    else:
        print(f"  result: {out}")
    await Database.close()


async def cmd_wonders():
    """wonders {overview | explore <discovery-id> [fleet-power] | hunt <encounter-id> [power] |
    tame <encounter-id> [skill]}

    Four entry points of `modules/space_wonders.py` had no caller: the overview and the three actions
    that resolve a discovery or an encounter. Nothing could hunt, tame or explore before this.
    """
    await Database.init()
    usage = ('Usage: cli.py wonders overview\n'
             '       cli.py wonders explore <discovery-id> [fleet-power]\n'
             '       cli.py wonders hunt <encounter-id> [fleet-power]\n'
             '       cli.py wonders tame <encounter-id> [trainer-skill]')
    sid = SID
    action = sys.argv[2] if len(sys.argv) > 2 else "overview"
    from modules import space_wonders as sw
    if action == "explore":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        power = int(sys.argv[4]) if len(sys.argv) > 4 else 100
        out = await sw.explore_anomaly(int(sys.argv[3]), power, sid)
    elif action == "hunt":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        power = int(sys.argv[4]) if len(sys.argv) > 4 else 100
        out = await sw.hunt_animal(int(sys.argv[3]), power, sid)
    elif action == "tame":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        skill = int(sys.argv[4]) if len(sys.argv) > 4 else 5
        out = await sw.tame_animal(int(sys.argv[3]), skill, sid)
    else:
        out = await sw.get_wonders_overview(sid)
    if not out:
        print("  no result")
    for key, value in (out or {}).items():
        print(f"  {key}: {len(value) if isinstance(value, list) else value}")
    await Database.close()


async def cmd_horror():
    """horror {measures | assets | threats | detail <id> | contain <id> <measure> | eradicate <id> [strategy]}

    Six entry points of `modules/space_horror.py` had no caller, and the module is the bug war: the
    subsystem the five-plane gradient puts one plane from the human core. Nothing could read a threat,
    apply a containment measure or launch an eradication, while the tick advanced infestations.
    """
    await Database.init()
    usage = ('Usage: cli.py horror measures | assets | threats\n'
             '       cli.py horror detail <infestation-id>\n'
             '       cli.py horror contain <infestation-id> "<measure name>"\n'
             '       cli.py horror eradicate <infestation-id> [strategy]')
    sid = SID
    action = sys.argv[2] if len(sys.argv) > 2 else "threats"
    from modules import space_horror as sh
    if action == "measures":
        for row in await sh.get_containment_measures():
            print(f"  {row['name']} · {row.get('effect') or row.get('description') or ''}")
        await Database.close(); return
    if action == "assets":
        for row in await sh.get_bug_war_assets():
            print(f"  {row.get('name')} · {row.get('type')}")
        await Database.close(); return
    if action == "detail":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        out = await sh.get_infestation_detail(int(sys.argv[3]), sid)
    elif action == "contain":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        out = await sh.apply_containment(sid, int(sys.argv[3]), sys.argv[4])
    elif action == "eradicate":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        strategy = sys.argv[4] if len(sys.argv) > 4 else "systematic"
        out = await sh.launch_eradication(sid, int(sys.argv[3]), strategy)
    else:
        rows = await sh.get_active_threats(sid)
        out = {"threats": len(rows)}
        for row in rows:
            print(f"  #{row.get('id')} {row.get('name')} · {row.get('status')}")
    # A function that answers with a bool, a number or a list had its answer swallowed here: `or {}`
    # turned False into an empty dict and the script printed "no result", which reads as "nothing
    # happened" when the answer was actually no.
    if isinstance(out, dict):
        for key, value in out.items():
            print(f"  {key}: {value}")
    elif out is None:
        print("  no result")
    else:
        print(f"  result: {out}")
    await Database.close()


async def cmd_mega():
    """mega {types | status | ports | advance <days> | start <type-id> [sector-id] [territory-id] |
    port-types | build-port <territory-id> <port-type-id> [name] | upgrade-port <port-id> <upgrade>}

    `types` answers what a build costs before it is attempted, names the research gate the catalogue
    holds, and prints the reason that gate refuses: `catalogue-miss` when the value names no
    `research_projects` row, `locked` when the row exists and is not unlocked. `status` and `ports`
    print the rows they counted. `advance` is the only verb that moves a site in a play session.
    Nothing here cancels a build: no refund, no delete.
    """
    await Database.init()
    usage = ("Usage: cli.py mega types | status | ports | advance <days>\n"
             "       cli.py mega start <type-id> [sector-id] [territory-id]\n"
             "       cli.py mega port-types\n"
             "       cli.py mega build-port <territory-id> <port-type-id> [name]\n"
             "       cli.py mega upgrade-port <port-id> <upgrade-name>")
    sid = SID
    action = sys.argv[2] if len(sys.argv) > 2 else "status"
    from modules import megastructures_ports as mp
    if action == "types":
        from core.research_gate import CATALOGUE_MISS, LOCKED, check_gate
        from modules._economy import _check_afford
        ledger_row = await Database.fetchrow(
            "SELECT 1 AS present FROM maya_rp.resources WHERE session_id = $1", sid)
        for row in await mp.get_megastructure_types():
            gate = row.get("research_required") or "none"
            if gate == "none":
                gate_state = "ungated"
            else:
                # The gate answers one text per reason, and the CLI must read which one arrived. A
                # catalogue value that names no project and a project that exists but is locked both
                # answer truthy, so both printed as `locked`, and a catalogue fault read as a lock.
                # A text matching neither is not called locked either: it names no reason here.
                refusal = await check_gate(gate)
                if refusal is None:
                    gate_state = "unlocked"
                elif refusal == CATALOGUE_MISS.format(gate):
                    gate_state = "catalogue-miss"
                elif refusal == LOCKED.format(gate):
                    gate_state = "locked"
                else:
                    gate_state = "gated"
            phases = mp._j(row.get("construction_phases"))
            days = sum(p.get("time_days", 0) for p in phases)
            cost = phases[0].get("cost", {}) if phases else {}
            if not ledger_row:
                ledger = "no ledger row"
            else:
                ok, why = await _check_afford(sid, cost)
                ledger = "can charge" if ok else f"short: {why}"
            print(f"  #{row['id']} {row['name']} · tier {row.get('fantasy_tier')}"
                  f" · research {gate} ({gate_state}) · phase 1 {cost}"
                  f" · total days {days} · ledger {ledger}")
        await Database.close(); return
    if action == "port-types":
        for row in await mp.get_port_types():
            print(f"  #{row['id']} {row['name']} · {row.get('category')}"
                  f" · {row.get('build_cost_credits')} credits")
        await Database.close(); return
    if action == "start":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        sector = int(sys.argv[4]) if len(sys.argv) > 4 else None
        territory = int(sys.argv[5]) if len(sys.argv) > 5 else None
        out = await mp.start_construction(sid, int(sys.argv[3]), sector, territory)
    elif action == "build-port":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        name = sys.argv[5] if len(sys.argv) > 5 else None
        out = await mp.build_port(sid, int(sys.argv[3]), int(sys.argv[4]), name)
    elif action == "upgrade-port":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        out = await mp.upgrade_port(sid, int(sys.argv[3]), sys.argv[4])
    elif action == "ports":
        rows = await mp.get_port_overview(sid)
        print(f"  ports: {len(rows)}")
        for row in rows:
            print(f"  #{row['id']} {row['name']} · {row.get('port_type')}"
                  f" · {'L' + str(row.get('level'))} · {row.get('status')}"
                  f" · {row.get('territory_name') or 'no territory'}")
        await Database.close(); return
    elif action == "advance":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        out = await mp.advance_megastructure(sid, float(sys.argv[3]))
    else:
        rows = await mp.get_megastructure_status(sid)
        print(f"  megastructures: {len(rows)}")
        for row in rows:
            print(f"  #{row['id']} {row['name']} · phase {row.get('current_phase')}"
                  f" · {row.get('progress_pct')}% · {row.get('status')}"
                  f" · {row.get('territory_name') or 'no territory'}")
        rows = await mp.get_port_overview(sid)
        print(f"  ports: {len(rows)}")
        for row in rows:
            print(f"  #{row['id']} {row['name']} · {row.get('port_type')}"
                  f" · {'L' + str(row.get('level'))} · {row.get('status')}"
                  f" · {row.get('territory_name') or 'no territory'}")
        await Database.close(); return
    for key, value in (out or {}).items():
        print(f"  {key}: {value}")
    await Database.close()


async def cmd_build():
    """build {types <category> | list | show <id> | new <type-id> [name] | upgrade <id>} — facilities.

    Five entry points of `modules/infrastructure.py` had no caller: the catalogue reader, the builder,
    the viewer, the lister and the upgrader. `run_tick` produced from facilities nothing could build.
    """
    await Database.init()
    usage = ('Usage: cli.py build types "<category>"\n'
             '       cli.py build list\n'
             '       cli.py build show <instance-id>\n'
             '       cli.py build new <type-id> ["name"]\n'
             '       cli.py build upgrade <instance-id>')
    sid = SID
    action = sys.argv[2] if len(sys.argv) > 2 else "list"
    from modules import infrastructure
    if action == "types":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        rows = await infrastructure.get_types_by_category(sys.argv[3])
        print(f"  {len(rows)} type(s) in {sys.argv[3]}")
        for row in rows:
            print(f"  #{row['id']} {row['name']} · tier {row.get('fantasy_tier')}"
                  f" · {row.get('build_cost_credits')} credits")
        await Database.close(); return
    if action == "new":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        name = sys.argv[4] if len(sys.argv) > 4 else None
        out = await infrastructure.build_infrastructure(sid, int(sys.argv[3]), name=name)
    elif action == "show":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        out = await infrastructure.get_infrastructure(int(sys.argv[3]), sid)
    elif action == "upgrade":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        out = await infrastructure.upgrade_infrastructure(sid, int(sys.argv[3]))
    else:
        rows = await infrastructure.list_infrastructure(sid)
        out = {"facilities": len(rows)}
        for row in rows:
            print(f"  #{row['id']} {row.get('name')} · {row.get('type_name')}"
                  f" · level {row.get('level')} · {row.get('territory_name') or row.get('sector_id')}")
    # A function that answers with a bool, a number or a list had its answer swallowed here: `or {}`
    # turned False into an empty dict and the script printed "no result", which reads as "nothing
    # happened" when the answer was actually no.
    if isinstance(out, dict):
        for key, value in out.items():
            print(f"  {key}: {value}")
    elif out is None:
        print("  no result")
    else:
        print(f"  result: {out}")
    await Database.close()


async def cmd_cargo():
    """cargo {create <item> <qty> <loc-type> <loc-id> | ship <cargo-id> <dest-type> <dest-id> <ship-id> | status}

    `create_cargo` and `transport` both had no caller, so `run_tick` delivered missions nothing could
    create and the cargo table held no rows. This is the only door.
    """
    await Database.init()
    usage = ('Usage: cli.py cargo create "<item>" <qty> <location-type> <location-id>\n'
             '       cli.py cargo ship <cargo-id> <dest-type> <dest-id> <ship-id>\n'
             '       cli.py cargo status')
    sid = SID
    action = sys.argv[2] if len(sys.argv) > 2 else "status"
    from modules import logistics
    if action == "create":
        if len(sys.argv) < 7:
            print(usage); await Database.close(); return
        out = await logistics.create_cargo(sys.argv[3], float(sys.argv[4]), sys.argv[5], int(sys.argv[6]), sid)
    elif action == "ship":
        if len(sys.argv) < 7:
            print(usage); await Database.close(); return
        out = await logistics.transport(int(sys.argv[3]), sys.argv[4], int(sys.argv[5]), int(sys.argv[6]), sid)
    else:
        rows = await Database.fetch(
            "SELECT id, item_type, quantity, location_type, location_id FROM maya_rp.cargo"
            " WHERE session_id=$1 ORDER BY id DESC LIMIT 20", sid)
        out = {"held": len(rows)}
        for row in rows:
            print(f"  #{row['id']} {row['quantity']} x {row['item_type']} at {row['location_type']}:{row['location_id']}")
    for key, value in (out or {}).items():
        print(f"  {key}: {value}")
    await Database.close()


async def cmd_science():
    """science {mission <type> | anomaly <location> | status} — the exoscience board.

    `start_mission` and `generate_anomaly` were the two unreachable entry points of the module:
    `run_tick` progressed missions and studied anomalies that nothing could create.
    """
    await Database.init()
    usage = ('Usage: cli.py science mission "<type>"\n'
             '       cli.py science anomaly "<location>"\n'
             '       cli.py science status')
    sid = SID
    action = sys.argv[2] if len(sys.argv) > 2 else "status"
    from modules import exoscience
    if action == "mission":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        out = await exoscience.start_mission(sys.argv[3], sid)
    elif action == "anomaly":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        out = await exoscience.generate_anomaly(sys.argv[3], sid)
    else:
        out = await exoscience.run_tick(sid)
    for key, value in (out or {}).items():
        print(f"  {key}: {value}")
    await Database.close()


async def cmd_mystery():
    """mystery {new <title> | clue <inv-id> <text> | deduce <inv-id> [note] | status} — the case file.

    The whole investigation subsystem had no production caller: `create_investigation`, `add_clue`,
    `deduce` and `generate_red_herring` were reachable from nothing, and `run_tick` ages cases that
    never exist. This is the boundary.
    """
    await Database.init()
    usage = ('Usage: cli.py mystery new "<title>" [template] [difficulty]\n'
             '       cli.py mystery clue <investigation-id> "<text>" [source]\n'
             '       cli.py mystery deduce <investigation-id> ["note"]\n'
             '       cli.py mystery status')
    sid = SID
    action = sys.argv[2] if len(sys.argv) > 2 else "status"
    from modules import mystery
    if action == "new":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        template = sys.argv[4] if len(sys.argv) > 4 else "generic"
        difficulty = int(sys.argv[5]) if len(sys.argv) > 5 else 5
        out = await mystery.create_investigation(sid, sys.argv[3], template, difficulty)
    elif action == "clue":
        if len(sys.argv) < 5:
            print(usage); await Database.close(); return
        source = sys.argv[5] if len(sys.argv) > 5 else "discovery"
        out = await mystery.add_clue(sid, int(sys.argv[3]), sys.argv[4], source=source)
    elif action == "deduce":
        if len(sys.argv) < 4:
            print(usage); await Database.close(); return
        note = sys.argv[4] if len(sys.argv) > 4 else ""
        out = await mystery.deduce(sid, int(sys.argv[3]), note)
    else:
        out = await mystery.run_tick(sid)
    for key, value in (out or {}).items():
        print(f"  {key}: {value}")
    await Database.close()


async def cmd_character():
    """character <name> {item|outfit|wear|profile} <json|id> — hand a character something new.

    One command for four mutations, because four commands is four places to forget one.
    """
    await Database.init()
    usage = """Usage: cli.py character "<name>" item '{"name": "..."}'
       cli.py character "<name>" outfit '{"id": "...", "name": "..."}'
       cli.py character "<name>" wear <outfit-id>
       cli.py character "<name>" profile '{"face": "..."}'"""
    if len(sys.argv) < 5:
        print(usage)
        await Database.close()
        return
    name, action, payload = sys.argv[2], sys.argv[3], sys.argv[4]
    from modules.character_profile import grant
    sid = SID
    row = await Database.fetchrow(
        # Wildcards go in the parameter, not in the SQL: building them in the statement needs
        # four levels of quoting and one of them always wins.
        "SELECT id FROM maya_rp.characters WHERE session_id=$1 AND name ILIKE $2"
        " ORDER BY importance DESC NULLS LAST, id LIMIT 1", sid, f"%{name}%")
    if not row:
        print(f"no character named {name} in session {sid}")
        await Database.close()
        return
    kwargs = {"session_id": sid}
    try:
        if action == "item":
            kwargs["item"] = json.loads(payload)
        elif action == "outfit":
            kwargs["outfit"] = json.loads(payload)
        elif action == "profile":
            kwargs["profile"] = json.loads(payload)
        elif action == "wear":
            kwargs["wear"] = payload
        else:
            print(usage)
            await Database.close()
            return
        applied = await grant(int(row["id"]), **kwargs)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"refused: {exc}")
        await Database.close()
        return
    for field, what in applied.items():
        print(f"  {field}: {what}")
    await Database.close()


async def cmd_load():
    """load <file.sav> [--keep-session] — restore PG from a .sav snapshot."""
    await Database.init()
    if len(sys.argv) < 3:
        print("Usage: cli.py load <file.sav> [--keep-session] [--allow-session-mismatch]"
              " [--allow-novel-mismatch] [--force]")
        await Database.close()
        return
    from core.savegame import DetachRefused, RestoreIncomplete, SessionMismatch, import_sav

    wipe = "--keep-session" not in sys.argv
    forced = "--allow-session-mismatch" in sys.argv
    # A novel mismatch is its own refusal: `NovelMismatch` names this switch in its message, so a
    # loader without it strands the operator on a refusal whose remedy the CLI does not offer. The
    # default stays a refusal.
    other_novel = "--allow-novel-mismatch" in sys.argv
    # --force restores a file whose checksum does not match; it is a separate switch from the session check.
    try:
        r = await import_sav(sys.argv[2], wipe=wipe, allow_session_mismatch=forced,
                             allow_novel_mismatch=other_novel, force="--force" in sys.argv)
    except (DetachRefused, RestoreIncomplete, SessionMismatch) as exc:
        # Each of these refuses before a write commits; say so instead of a traceback.
        print(f"LOAD REFUSED: {exc}")
        await Database.close()
        return
    if not r.get("ok"):
        print(f"LOAD FAILED: {r.get('error')}")
    else:
        print(
            f"LOADED: {r['restored_rows']} rows → session {r['session_id']} (day {r.get('game_day')})"
        )
    await Database.close()


async def cmd_export():
    await Database.init()
    md = await StateManager.export_md(SID)
    print(md)
    await Database.close()


# ── continue: take a novel title, land in its session ────────────────────────────────────────────
#
# `continue` replaces the ritual in `main/rp-continue-session.md`: read the novel's title, find the
# session that plays it, point the arc file at it, print the status headline. A title is resolved
# against `novels.title`; `novels.novel_id` then names the session through `sessions.novel_id`.

class NovelNotFound(RuntimeError):
    """No novel carries the title, or several do. `candidates` holds the matches, empty when none."""

    def __init__(self, asked: str, candidates: list[tuple[str, str]]):
        self.asked = asked
        self.candidates = candidates
        if not candidates:
            what = f"no novel is titled {asked!r}"
        else:
            names = ", ".join(f"{title!r} ({novel_id})" for novel_id, title in candidates)
            what = f"{asked!r} matches {len(candidates)} novels: {names}"
        RuntimeError.__init__(self, what)


async def _read_novels() -> list:
    """Every novel with the sessions that play it, in reading order.

    The join answers the list form of `continue` and the "no session" refusal in one read. A
    superseded novel keeps its row, so it stays visible here.
    """
    return await Database.fetch(
        "SELECT n.novel_id, n.title, n.status, n.supersedes, n.adventures_dir,"
        " s.id AS session_id, s.name AS session_name, s.status AS session_status,"
        " s.game_day AS game_day"
        " FROM maya_rp.novels n LEFT JOIN maya_rp.sessions s ON s.novel_id = n.novel_id"
        " ORDER BY n.story_order NULLS LAST, n.novel_id, s.id"
    )


async def _find_novel(title: str) -> tuple[str, str]:
    """Resolve a title to `(novel_id, title)`: an exact case-insensitive match first, then a prefix.

    @param title - the title the caller typed.
    @returns the one match.
    @raises NovelNotFound - no match, or several; `candidates` names them.
    """
    # LIKE has its own wildcards, so a title holding them must not widen the search.
    escaped = title.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    exact = await Database.fetch(
        "SELECT novel_id, title FROM maya_rp.novels WHERE lower(title) = lower($1) ORDER BY novel_id",
        title,
    )
    if len(exact) == 1:
        return exact[0]["novel_id"], exact[0]["title"]
    if len(exact) > 1:
        raise NovelNotFound(title, [(row["novel_id"], row["title"]) for row in exact])
    prefix = await Database.fetch(
        "SELECT novel_id, title FROM maya_rp.novels"
        " WHERE title ILIKE $1 ESCAPE '\\' ORDER BY title",
        escaped + "%",
    )
    found = [(row["novel_id"], row["title"]) for row in prefix]
    if len(found) == 1:
        return found[0]
    raise NovelNotFound(title, found)


async def _find_session(novel_id: str) -> list:
    """The sessions that play one novel, oldest first."""
    return await Database.fetch(
        "SELECT s.id, s.name, s.status, s.game_day, s.novel_id, s.story_path FROM maya_rp.sessions s"
        " WHERE s.novel_id = $1 ORDER BY s.id",
        novel_id,
    )


def _frozen_reason(session_id: int) -> str | None:
    """Why a write into `session_id` is refused, or None when the campaign is writable.

    An unreadable frozen list is not a licence to write: it refuses with its own reason.
    """
    from core.session import FrozenListUnreadable, is_frozen

    try:
        if is_frozen(session_id):
            return "it is frozen for reference; arm GM MAYA maintenance to write it"
    except FrozenListUnreadable as exc:
        return f"the frozen list is unreadable ({exc}), so no campaign is writable"
    return None


def print_novels(rows) -> None:
    """One block per novel: novel id, title, status, then the sessions that play it."""
    order: list = []
    sessions: dict[str, list] = {}
    for row in rows:
        novel_id = row["novel_id"]
        if novel_id not in sessions:
            order.append(row)
            sessions[novel_id] = []
        if row["session_id"] is not None:
            sessions[novel_id].append(row)
    print(f"novels — {len(order)}")
    for novel in order:
        novel_id = novel["novel_id"]
        print(f"  {novel_id:18s} {novel['title']}  [{novel['status']}]"
              + (f"  supersedes {novel['supersedes']}" if novel["supersedes"] else ""))
        if not sessions[novel_id]:
            print("      (no session plays this novel)")
        for played in sessions[novel_id]:
            print(f"      session {played['session_id']:<5} {played['session_name']}"
                  f"  [{played['session_status']}]  day {played['game_day']}")


async def cmd_continue():
    """continue ["<novel title>"] — play the novel: set the arc, print the loadout.

    With no title the novels and their sessions are listed, which is the answer when the operator
    has forgotten the exact title.
    """
    await Database.init()
    title = sys.argv[2] if len(sys.argv) > 2 else ""
    if not title:
        print_novels(await _read_novels())
        await Database.close()
        return

    try:
        novel_id, resolved_title = await _find_novel(title)
    except NovelNotFound as exc:
        if exc.candidates:
            names = ", ".join(f"{shown!r} ({novel_id})" for novel_id, shown in exc.candidates)
            print(f"no novel matches {title!r}; candidates: {names}", file=sys.stderr)
        else:
            print(f"no novel is titled {title!r}; run `cli.py continue` for the list", file=sys.stderr)
        await Database.close()
        sys.exit(1)

    novel = await Database.fetchrow(
        "SELECT novel_id, title, status, supersedes, adventures_dir FROM maya_rp.novels"
        " WHERE novel_id = $1",
        novel_id,
    )
    if novel_id == "scratch":
        print("refused: `scratch` is no novel; its sessions take --session=<id> instead",
              file=sys.stderr)
        await Database.close()
        sys.exit(1)
    if novel["status"] == "superseded":
        successor = await Database.fetchrow(
            "SELECT novel_id, title FROM maya_rp.novels WHERE supersedes = $1"
            " ORDER BY story_order NULLS LAST, novel_id LIMIT 1",
            novel_id,
        )
        if successor:
            print(f"refused: {resolved_title!r} is superseded by {successor['title']!r}"
                  f" ({successor['novel_id']}); continue that novel instead", file=sys.stderr)
        else:
            print(f"refused: {resolved_title!r} is superseded, and no novel names it as its"
                  " predecessor", file=sys.stderr)
        await Database.close()
        sys.exit(1)

    rows = await _find_session(novel_id)
    if not rows:
        print(f"refused: novel {novel_id!r} ({resolved_title!r}) has no session to continue",
              file=sys.stderr)
        await Database.close()
        sys.exit(1)
    if len(rows) > 1:
        listed = ", ".join(f"{row['id']} ({row['name']})" for row in rows)
        print(f"refused: novel {novel_id!r} is played by {len(rows)} sessions: {listed};"
              " pass one with --session=<id>", file=sys.stderr)
        await Database.close()
        sys.exit(1)

    session_id = int(rows[0]["id"])
    reason = _frozen_reason(session_id)
    if reason:
        print(f"refused: session {session_id} cannot be continued: {reason}", file=sys.stderr)
        await Database.close()
        sys.exit(1)

    # The novel and its session are read before anything moves: a refused title must not move the arc.
    from core.session import set_active_arc

    set_active_arc(session_id)
    print(f"\ncontinued: {resolved_title} ({novel_id}) → session {session_id}")
    await print_status(session_id)
    print(f"  Game day:    {rows[0]['game_day']}")
    print("  Command:     cd /home/maya/Bumi-Hijau/rp-engine-py && python3 scripts/cli.py status")
    print(f"  Brief:       {rows[0]['story_path'] or _brief_from_dir(novel['adventures_dir'])}")
    await Database.close()


def _brief_from_dir(adventures_dir: str | None) -> str:
    """The brief path a novel without `sessions.story_path` falls back to."""
    if not adventures_dir:
        return "none: this novel names no adventures directory"
    return adventures_dir.rstrip("/") + "/story.md"


# ── clear: delete play-state clutter, never world or cast ────────────────────────────────────────
#
# Nine tables hold what a run produced (events, logs, news). A clear removes only those rows, for one
# session. Dry run by default: the operator sees the counts before anything is deleted.

#: The nine play-state tables `clear` owns. Not one more.
PLAY_STATE_TABLES: tuple[str, ...] = (
    "events",
    "story_log",
    "news_articles",
    "tick_summaries",
    "adjutant_prompts",
    "morale_history",
    "crew_production_log",
    "pirate_alerts",
    "npc_offscreen_interactions",
)

_DELETE_FROM = re.compile(r"^\s*delete\s+from\s+(?:maya_rp\.)?\"?([\w]+)\"?", re.I)


def _deleted_rows(status: str) -> int:
    """The row count in a `DELETE n` status tag; 0 when the tag carries no count."""
    parts = str(status).split()
    return int(parts[-1]) if parts and parts[-1].isdigit() else 0


async def _play_state_counts(session: int) -> dict[str, int]:
    """Current row count of each play-state table for one session.

    @param session - campaign whose rows are counted.
    """
    counts = {}
    for table in PLAY_STATE_TABLES:
        sql = f'SELECT COUNT(*) FROM maya_rp."{table}" WHERE session_id = $1'
        counts[table] = await Database.fetchval(sql, session)
    return counts


async def cmd_clear():
    """clear [--session N] [--yes] — remove the play-state rows of one session.

    Dry run by default. `--yes` exports a `.sav` first and refuses to delete when that export
    fails, so the rows are always recoverable.

    `--session` is read through `take_session_flag`, the same reader `__main__` uses. A second
    reader here kept the first flag where that one keeps the last, so `clear --session=919
    --session=918` cleared a different campaign than the one the rest of the process resolved.
    """
    await Database.init()
    own, _ = take_session_flag(sys.argv[2:])
    try:
        # The flag on this call wins; otherwise resolve the arc the way every other verb does.
        from core.session import require_session

        session = _session_id() if own is None else require_session(own)
    except (RuntimeError, ValueError) as exc:
        print(f"session: {exc}", file=sys.stderr)
        await Database.close()
        sys.exit(2)

    reason = _frozen_reason(session)
    if reason:
        print(f"refused: clear on session {session}: {reason}", file=sys.stderr)
        await Database.close()
        sys.exit(1)

    counts = await _play_state_counts(session)
    total = sum(counts.values())
    for table in PLAY_STATE_TABLES:
        print(f"  {table:28s} {counts[table]:>8,}")
    print(f"  {'TOTAL':28s} {total:>8,}   session {session}")

    if "--yes" not in sys.argv[2:]:
        print("dry run: nothing deleted. Pass --yes to export a .sav and then delete these rows.")
        await Database.close()
        return

    from core.savegame import export_sav

    try:
        sav = await export_sav(session)
    except Exception as exc:  # noqa: BLE001 - every export failure must abort before the delete
        print(f"refused: .sav export failed ({type(exc).__name__}: {exc}); nothing deleted",
              file=sys.stderr)
        await Database.close()
        sys.exit(1)
    print(f"savegame: {sav}")

    deleted: dict[str, int] = {}
    async with Database.transaction() as conn:
        # `maya_rp.roll_history.context_event_id` references `events(id)` with NO ACTION, and
        # `events` is one of the nine tables above. A roll row that names an event of this session
        # refuses the delete of that event, which fails the transaction. The reference is released
        # first, in the same transaction: the roll rows stay, and the events they named go with the
        # rest of the play state.
        await conn.execute(
            "UPDATE maya_rp.roll_history SET context_event_id = NULL WHERE session_id = $1",
            session)
        for table in PLAY_STATE_TABLES:
            status = await conn.execute(
                f'DELETE FROM maya_rp."{table}" WHERE session_id = $1', session)
            deleted[table] = _deleted_rows(status)
    for table in PLAY_STATE_TABLES:
        print(f"  deleted {table:28s} {deleted[table]:>8,}")
    print(f"cleared session {session}: {sum(deleted.values()):,} rows from"
          f" {len(PLAY_STATE_TABLES)} play-state tables")
    await Database.close()


def cmd_config():
    print(Config.summary())


async def cmd_briefing():
    await Database.init()
    from core.master_briefing import generate

    print(await generate(SID))
    await Database.close()


async def cmd_economy_flow():
    await Database.init()
    r = await Database.fetchrow(
        "SELECT credits, alloys, fuel FROM maya_rp.resources WHERE session_id=$1", SID
    )
    print(f"\n{'═' * 60}")
    print(f"  ECONOMY FLOW — Session {SID}")
    print(f"{'═' * 60}")
    print(
        f"\n  TREASURY:  {r['credits']:>12,}C  {r['alloys']:>10,}A  {r['fuel']:>10,}F"
    )
    territories = await Database.fetch(
        "SELECT system_name, population, tax_rate, development_level, crisis_level "
        "FROM maya_rp.territory WHERE session_id=$1 AND controlling_faction='Setia Empire' "
        "ORDER BY population DESC LIMIT 10",
        SID,
    )
    if territories:
        print(f"\n  {'TERRITORY':<25} {'POP':>10} {'TAX':>6} {'TOTAL/DAY':>10}")
        total_tax = 0
        for t in territories:
            pop = t["population"] or 0
            rate = float(t["tax_rate"] or 0.05)
            dev = t["development_level"] or 1
            daily = int(pop * rate * (1 + (dev - 1) * 0.1))
            total_tax += daily
            print(
                f"  {t['system_name']:<25} {pop:>10,} {rate * 100:>5.0f}% {daily:>10,}C"
            )
        print(f"  {'TOTAL TAX/DAY':<25} {'':>10} {'':>6} {total_tax:>10,}C")
    ships_active = (
        await Database.fetchval(
            "SELECT COUNT(*) FROM maya_rp.ships WHERE session_id=$1 AND status='active'",
            SID,
        )
        or 0
    )
    print(f"\n  FLEET: {ships_active} active ships")
    fuel_burn = (
        await Database.fetchval(
            "SELECT COALESCE(SUM(hull_current/speed),0) FROM maya_rp.ships WHERE session_id=$1 AND status='active'",
            SID,
        )
        or 1000
    )
    print(f"  FUEL BURN/DAY: ~{int(fuel_burn):,}")
    print(f"  DAYS OF FUEL:  {r['fuel'] // max(1, int(fuel_burn))}")
    net = total_tax + 200000 - int(fuel_burn) * 50
    print(f"\n  {'═' * 40}")
    print(f"  EST. NET FLOW: {net:+,}C/day")
    print()
    await Database.close()


async def cmd_intel():
    await Database.init()
    print(f"\n{'═' * 60}")
    print(f"  INTEL DASHBOARD — Session {SID}")
    print(f"{'═' * 60}")
    missions = await Database.fetch(
        "SELECT em.id, em.mission_type, "
        "       COALESCE(f.name, em.faction_id::text) AS target_faction, "
        "       em.outcome AS status, em.success_chance, em.agent_name AS assigned_agent "
        "FROM maya_rp.espionage_missions em "
        "LEFT JOIN maya_rp.factions f ON f.id = em.faction_id "
        "WHERE em.session_id=$1 AND em.resolved_at IS NULL ORDER BY em.id",
        SID,
    )
    print(f"\n  ACTIVE MISSIONS ({len(missions)})")
    icons = {
        "recon": "\U0001f441",
        "sabotage": "\U0001f4a3",
        "theft": "\U0001f4cb",
        "assassination": "\u2620",
        "infiltration": "\U0001f977",
        "extraction": "\U0001f681",
    }
    for m in missions:
        icon = icons.get(m["mission_type"], "\u2753")
        print(
            f"    {icon} [{m['id']}] {m['mission_type']} vs {m['target_faction']} ({m['success_chance']}%) — {m['assigned_agent'] or 'unassigned'}"
        )
    stealth = await Database.fetch(
        "SELECT su.name, sut.name as type_name, su.assigned_lane, su.status "
        "FROM maya_rp.stealth_units su "
        "JOIN maya_rp.stealth_unit_types sut ON sut.id=su.unit_type_id "
        "WHERE su.session_id=$1 AND su.status='active'",
        SID,
    )
    if stealth:
        print(f"\n  DEPLOYED STEALTH UNITS ({len(stealth)})")
        for s in stealth:
            print(f"    \U0001f6f0 {s['name']} ({s['type_name']})")
    pipeline = await Database.fetch(
        "SELECT p.name, p.faction, pip.intel_text, pip.converted_to_clue "
        "FROM maya_rp.prisoner_intel_pipeline pip JOIN maya_rp.prisoners p ON p.id=pip.prisoner_id "
        "WHERE p.session_id=$1 ORDER BY pip.id DESC LIMIT 5",
        SID,
    )
    if pipeline:
        print(f"\n  PRISONER INTEL ({len(pipeline)})")
        for p in pipeline:
            icon = "\u2713" if p["converted_to_clue"] else "\u23f3"
            print(f"    {icon} {p['name']} ({p['faction']}): {p['intel_text'][:60]}...")
    print()
    await Database.close()


async def cmd_dashboard():
    await Database.init()
    s = await Database.fetchrow(
        "SELECT name, game_day, status FROM maya_rp.sessions WHERE id=$1", SID
    )
    from modules.calendar_tkg import get_game_date

    date = await get_game_date(SID)
    from core.pacing import PacingDirector

    pm = await PacingDirector.get_mode(SID)
    r = await Database.fetchrow(
        "SELECT credits, alloys, fuel FROM maya_rp.resources WHERE session_id=$1", SID
    )
    morale = (
        await Database.fetchval(
            "SELECT COALESCE(AVG(morale),50) FROM maya_rp.crew_roster WHERE session_id=$1",
            SID,
        )
        or 50
    )
    bonds = await Database.fetch(
        "SELECT c.name,c.bond FROM maya_rp.characters c JOIN maya_rp.romance_arcs ra ON ra.character_id=c.id WHERE c.session_id=$1 AND c.bond>0 ORDER BY c.bond DESC LIMIT 5",
        SID,
    )
    from modules.objectives import get_active as get_obj

    obj = await get_obj(SID)
    from core.player_profile import get_profile

    prof = await get_profile(SID)
    from core.scene_stack import get_stack_summary

    stack = await get_stack_summary(SID)
    fleet = await Database.fetchval(
        "SELECT COUNT(*) FROM maya_rp.ships WHERE session_id=$1 AND status='active'",
        SID,
    )

    def bar(val, mx=1_000_000, w=20):
        filled = min(w, max(0, int(val / mx * w)))
        return "\u2588" * filled + "\u2591" * (w - filled)

    print(f"\n  \u2554{'=' * 50}\u2557")
    print(f"  \u2551  TKG RP  —  {date.get('formatted', '?'):<30} \u2551")
    print(
        f"  \u2551  Mode: {pm['mode'].upper():<10} Tension: {bar(pm['tension'], 10, 10)} {pm['tension']}/10 \u2551"
    )
    print(f"  \u255a{'=' * 50}\u255d")
    print(f"\n  CREDITS  {bar(r['credits']):20} {r['credits']:>10,}")
    print(f"  ALLOYS   {bar(r['alloys']):20} {r['alloys']:>10,}")
    warn_fuel = "\u26a0 LOW" if r["fuel"] < 300_000 else ""
    print(f"  FUEL     {bar(r['fuel']):20} {r['fuel']:>10,}  {warn_fuel}")
    warn_morale = "\u26a0 LOW" if morale < 30 else ""
    print(f"  MORALE   {bar(morale, 100, 20)} {morale:>5}%  {warn_morale}")
    print(f"\n  BONDS")
    for b in bonds:
        bv = min(10, max(0, b["bond"] // 10))
        print(f"  {b['name']:<12} {'\u2665' * bv + '\u2661' * (10 - bv)}")
    print(f"\n  FLEET  {fleet} active ships")
    print(f"  STYLE  {prof['style'].upper()}")
    c = [o for o in obj.get("critical", [])]
    u = [o for o in obj.get("urgent", [])]
    if c:
        print(f"\n  \U0001f534 CRITICAL: {c[0]['detail'][:50]}")
    if u:
        print(f"\n  \U0001f7e1 URGENT: {u[0]['detail'][:50]}")
    a = len(obj.get("active", []))
    b = len(obj.get("background", []))
    print(f"  {a} active, {b} background objectives")
    if stack:
        print(f"\n  \u23f8 Suspended scenes: {len(stack)}")
    print()
    await Database.close()


async def cmd_query(sql: str):
    await Database.init()
    try:
        # read-only transaction — the server enforces it, not a regex
        rows = await Database.fetch_readonly(sql)
        import json

        print(json.dumps([dict(r) for r in rows], indent=2, default=str))
    except Exception as e:
        print(f"Query error: {e}", file=sys.stderr)
        await Database.close()
        sys.exit(1)
    await Database.close()


async def cmd_run_single(module_name: str):
    from scripts.orchestrator import run_single

    await run_single(SID, module_name)


async def cmd_romance():
    """romance arcs | romance roll <initiator> <target> <position> [location]"""
    await Database.init()
    from modules.romance import (
        get_romance_arcs,
        execute_rolling_scene,
        _get_character_id,
    )

    if len(sys.argv) < 3:
        print(
            "Usage: cli.py romance {arcs|roll <initiator> <target> <position> [location]}"
        )
        return

    sub = sys.argv[2]
    if sub == "arcs":
        arcs = await get_romance_arcs(SID)
        if not arcs:
            print("No romance arcs.")
            return
        print(
            f"\n{'Character':<26} {'Bond':<5} {'Stage':<12} {'Intimacy':<9} {'Sat':<5} {'Pursuit'}"
        )
        print("-" * 76)
        for a in arcs:
            print(
                f"{a['character_name']:<26} {a['bond'] or 0:<5} {a['arc_stage']:<12} "
                f"{a['intimacy_level'] or 0:<9} {a['saturation_pct'] or 0:<5} {a['pursuit_stage']}"
            )
    elif sub == "roll":
        if len(sys.argv) < 6:
            print(
                "Usage: cli.py romance roll <initiator> <target> <position> [location]"
            )
            return
        init_name, tgt_name, position = sys.argv[3], sys.argv[4], sys.argv[5]
        location = sys.argv[6] if len(sys.argv) > 6 else "heaven_pool"
        init_id = await _get_character_id(init_name, SID)
        tgt_id = await _get_character_id(tgt_name, SID)
        if not init_id or not tgt_id:
            print(f"Character not found: {init_name if not init_id else tgt_name}")
            return
        r = await execute_rolling_scene(init_id, tgt_id, position, location, SID)
        if not r.get("success"):
            print(r.get("error", "error"))
            return
        print(
            f"\n🎲 {r['initiator']} → {r['target']} — {r['position']} @ {r['location']}"
        )
        print(
            f"   Roll {r['roll']} + {r['modifier']} = {r['final_score']} vs {r['threshold']}  →  {'✅ PASS' if r['passed'] else '❌ FAIL'}"
        )
        print(f"   Tier: {r['tier']} (bond {r['required_bond']}+)")
        print(f"   Hook: {r['narrative_hook']}")
        sp = r["sensory_packet"]
        print(f"   Env: {sp['environment']['lighting']}")
        print(
            f"   Senses: {sp['sensory']['sight']} · {sp['sensory']['sound']} · {sp['sensory']['touch']}"
        )
        print(f"   Beat: {sp['emotional_beat']}")
    else:
        print("Unknown romance subcommand: arcs|roll")


async def cmd_assembly():
    """assembly list | assembly add <name> <tier> <hull> <power> <sub_class> | assembly assemble <name> <wreck_ids> [skill]"""
    await Database.init()
    from modules.wreck_assembly import cmd as wa_cmd

    sub = sys.argv[2] if len(sys.argv) > 2 else ""
    if sub == "list":
        r = await wa_cmd(SID, "list", {})
        print(f"\nWrecks available: {len(r.get('wrecks', []))}")
        for w in r.get("wrecks", []):
            print(
                f"  #{w['id']} {w['name']} — T{w['tier']} hull {w['hull']:,} power {w['power_rating']:,} ({w['sub_class']})"
            )
    elif sub == "add" and len(sys.argv) >= 7:
        r = await wa_cmd(
            SID,
            "add",
            {
                "name": sys.argv[3],
                "tier": int(sys.argv[4]),
                "hull": int(sys.argv[5]),
                "power": int(sys.argv[6]),
                "sub_class": sys.argv[7] if len(sys.argv) > 7 else "Wreck",
            },
        )
        print(f"ADDED: {r}")
    elif sub == "assemble" and len(sys.argv) >= 5:
        ids = [int(x) for x in sys.argv[4].split(",")]
        skill = int(sys.argv[5]) if len(sys.argv) > 5 else 5
        r = await wa_cmd(
            SID, "assemble", {"name": sys.argv[3], "wreck_ids": ids, "skill": skill}
        )
        print(f"ASSEMBLE: {r}")
    else:
        print(
            "Usage: cli.py assembly {list|add <name> <tier> <hull> <power> <sub_class>|assemble <name> <wreck_ids> [skill]}"
        )


async def cmd_duel():
    """duel challenge <ship_id> <opp_name> <tier> <hull> <power> [stakes_type] [stakes_value] | duel resolve <id> | duel list"""
    await Database.init()
    from modules.duel import cmd as duel_cmd

    sub = sys.argv[2] if len(sys.argv) > 2 else ""
    if sub == "challenge" and len(sys.argv) >= 7:
        r = await duel_cmd(
            SID,
            "challenge",
            {
                "player_ship_id": int(sys.argv[3]),
                "opponent": {
                    "name": sys.argv[4],
                    "tier": int(sys.argv[5]),
                    "hull": int(sys.argv[6]),
                    "power": int(sys.argv[7]),
                },
                "stakes": {
                    "type": sys.argv[8] if len(sys.argv) > 8 else "favor",
                    "value": int(sys.argv[9])
                    if len(sys.argv) > 9 and sys.argv[8] == "credits"
                    else 0,
                },
                "venue": "Open Space",
            },
        )
        print(f"CHALLENGE: {r}")
    elif sub == "resolve" and len(sys.argv) >= 4:
        r = await duel_cmd(SID, "resolve", {"duel_id": int(sys.argv[3])})
        print(f"RESOLVE: {r}")
    elif sub == "list":
        r = await duel_cmd(SID, "list", {})
        for d in r.get("duels", []):
            print(
                f"  #{d['id']} {d['opponent_name']} — {d['stakes_type']} — {d['status']} {d.get('result') or ''}"
            )
    else:
        print(
            "Usage: cli.py duel {challenge <ship_id> <opp_name> <tier> <hull> <power> [stakes_type] [value]|resolve <id>|list}"
        )


async def cmd_roll():
    """Generic dice: 'roll 100 +50 vs 90' | 'roll 3d6' | 'roll d20'

    Roll Theater (2026-08-14):
      roll <expr> --with <blessing>     # forge_luck|navigator_reroll|oracle_peek|brace|whisper
      roll blessings                    # list queen blessing tokens
      roll pool open <name>             # open a betting pool for the next vs-roll
      roll hall                         # legendary rolls gallery
      roll telegram <1-6> <domain>      # map a Telegram dice result to d100
    Rolls persist to roll_history; crits/fumbles memorialize; partial/fumble
    rolls plant consequence ripples.
    """
    expr = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
    if not expr:
        print("Usage: cli.py roll <expr> — e.g. '100 +50 vs 90' or '3d6'")
        return
    await Database.init()
    from modules import roll_theater as rt

    # theater subcommands
    if expr.startswith("blessings"):
        rows = await rt.list_blessings(SID)
        print("👑 Queen blessings (one per session, refresh 30 days):")
        for r in rows:
            ch = r["charges"] or 0
            print(
                f"  {r['blessing']:<18} {r['character_name']:<28} {r['effect']}"
                f" {'· ' + str(ch) + ' charge' + ('s' if ch != 1 else '') if ch else '· spent'}"
            )
        return
    if expr.startswith("pool open "):
        name = expr[len("pool open ") :].strip() or "The King's Roll"
        res = await rt.open_pool(SID, name, 70)
        print(f"🎰 Pool open: {res['name']} — {res['odds']}")
        print(f"   {res['bettors']} bettors · {res['credits_in_pool']}C in the pool")
        return
    if expr.startswith("hall"):
        rows = await Database.fetch(
            "SELECT roll_name, roll_value, domain, game_day, story FROM maya_rp.roll_hall "
            "WHERE session_id=$1 ORDER BY id DESC LIMIT 10",
            SID,
        )
        if not rows:
            print("🏛 The hall is empty. Roll a 100 or a 1 and earn a name.")
            return
        print("🏛 Hall of Legendary Rolls:")
        for r in rows:
            icon = "💥" if r["roll_value"] >= 96 else "💀"
            print(
                f"  {icon} {r['roll_name']} — {r['roll_value']} ({r['domain']}, day {r['game_day']})"
            )
            print(f"     {r['story'][:110]}")
        return
    if expr.startswith("telegram "):
        parts = expr.split()
        if len(parts) < 2:
            print("Usage: roll telegram <1-6> <domain>")
            return
        val = int(parts[1])
        domain = parts[2] if len(parts) > 2 else "social"
        total = rt.parse_telegram_dice(val)
        tier = rt.tier_of(total, 70)
        print(
            f"📲 Telegram dice {val} → d100: {total} [{rt.TIER_ICONS[tier]} {tier.upper()}]"
        )
        print(f"   {rt.flavor(domain, tier, total)}")
        await Database.execute(
            "INSERT INTO maya_rp.roll_history "
            "(session_id, roll_code, source_table, source_id, dice_used, raw_roll, "
            " final_score, dc, outcome, created_at) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())",
            SID,
            "telegram_dice",
            "telegram",
            val,
            f"tg:{val}",
            total,
            total,
            70,
            tier,
        )
        return

    import re, random

    outcome = None
    total = None
    raw_value = None
    dc = 0
    domain = "social"
    # parse --with blessing
    blessing = None
    m_with = re.search(r"\s+--with\s+(\S+)", expr)
    if m_with:
        blessing = m_with.group(1).lower()
        expr = expr[: m_with.start()].strip()
    m = re.match(r"^(\d*)d(\d+)([+-]\d+)?$", expr.replace(" ", ""))
    if m:
        n = int(m.group(1) or 1)
        die = int(m.group(2))
        mod = int(m.group(3) or 0)
        rolls = [random.randint(1, die) for _ in range(n)]
        total = sum(rolls) + mod
        raw_value = sum(rolls)
        outcome = "raw"
        print(f"🎲 {expr}: [{', '.join(map(str, rolls))}] + {mod} = {total}")
    else:
        m = re.match(r"^(\d+)\s*([+-])\s*(\d+)\s+vs\s+(\d+)$", expr, re.I)
        if not m:
            print(f"Unparsed: {expr} — try '100 +50 vs 90' or '3d6'")
            return
        base, sign, mod, thr = (
            int(m.group(1)),
            m.group(2),
            int(m.group(3)),
            int(m.group(4)),
        )
        total = base + (mod if sign == "+" else -mod)
        raw_value = base          # the die itself, before modifiers
        dc = thr
        # ── Roll Theater resolution ──
        tier = rt.tier_of(total, dc)
        # blessings that alter the roll
        if blessing == "forge_luck" and await rt.consume_blessing(SID, blessing):
            total += 10
            tier = rt.tier_of(total, dc)
            print(f"⚒️ Callista's Forge-luck: +10 → {total}")
        elif blessing == "navigator_reroll" and await rt.consume_blessing(
            SID, blessing
        ):
            alt = base + (mod if sign == "+" else -mod) + random.randint(-10, 10)
            if alt > total:
                total, tier = alt, rt.tier_of(alt, dc)
                print(f"🧭 Vera's Reroll: kept the better — {total}")
            else:
                print(f"🧭 Vera's Reroll: kept the original — {total}")
        elif blessing == "oracle_peek" and await rt.consume_blessing(SID, blessing):
            alt = base + (mod if sign == "+" else -mod) + random.randint(-20, 20)
            if alt > total:
                total, tier = alt, rt.tier_of(alt, dc)
            print(f"🔮 Aeliana's Peek: the Oracle saw both futures — you took {total}")
        elif (
            blessing == "brace"
            and await rt.consume_blessing(SID, blessing)
            and tier == "fumble"
        ):
            total = max(total, dc - 19)
            tier = rt.tier_of(total, dc)
            print(f"🛡️ Rika's Brace: the fumble was caught — {total}")
        elif blessing == "whisper" and await rt.consume_blessing(SID, blessing):
            print(
                f"🤫 Kira's Whisper: the roll is hidden. Only you know: {total} ({tier.upper()})"
            )
            outcome = tier
        else:
            if blessing:
                print(f"⚠ blessing '{blessing}' unavailable (spent?) — rolling bare")
            print(
                f"🎲 Roll {base} {sign} {mod} = {total} vs {dc} → {rt.TIER_ICONS[tier]} {tier.upper()}"
            )
        if not (blessing == "whisper" and outcome):
            outcome = tier
        print(f"   {rt.flavor(domain, tier, total)}")
        # consequences ripples on partial/fumble
        if tier in ("partial", "fumble"):
            await rt.plant_ripple(SID, domain, tier, dc)
        # pools resolve on any vs-roll
        king_won = tier in ("success", "crit")
        pres = await rt.resolve_pool(SID, king_won)
        if pres.get("resolved"):
            print(
                f"🎰 Pools closed: {pres['winner'].upper()} won — {pres['paid']}C paid, {pres['house_keeps']}C house"
            )
        # memorialize 100s and 1s
        if total >= 96 or total <= 5:
            name = await rt.memorialize(SID, domain, total, total, dc)
            print(f"🏛 {name} — memorialized.")
    try:
        await Database.execute(
            "INSERT INTO maya_rp.roll_history "
            "(session_id, roll_code, source_table, source_id, dice_used, raw_roll, "
            " modifier_total, final_score, dc, outcome, created_at) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW())",
            SID,
            "cli_roll",
            "cli_roll",
            0,
            expr,
            # raw_roll must be the DIE, not the modified total — roll_theater's
            # open_pool odds treat raw_roll>=96 as a crit, so logging the total
            # (e.g. 100+50=150) inflated every crit rate.
            raw_value if raw_value is not None else total,
            (total - raw_value) if raw_value is not None else 0,
            total,
            dc,
            outcome,
        )
    except Exception as e:
        print(f"⚠ roll not logged: {e}")


async def cmd_templates():
    """templates [category] | templates embed — list or embed stream templates."""
    await Database.init()
    if len(sys.argv) > 2 and sys.argv[2] == "embed":
        from core.memory import _embed

        rows = await Database.fetch(
            "SELECT id, trigger_tag, readable_hint FROM maya_rp.stream_templates WHERE trigger_tag_embed IS NULL"
        )
        if not rows:
            print("All templates already embedded.")
            return
        for r in rows:
            readable = (
                r["readable_hint"]
                or r["trigger_tag"]
                .replace("[", "")
                .replace("]", "")
                .replace("_", " ")
                .lower()
            )
            vec = await _embed(readable)
            vstr = "[" + ",".join(map(str, vec)) + "]"
            await Database.execute(
                "UPDATE maya_rp.stream_templates SET trigger_tag_embed=$1::vector WHERE id=$2",
                vstr,
                r["id"],
            )
            print(f"Embedded: {r['trigger_tag']}")
        print(f"Done — {len(rows)} templates embedded.")
        return
    if len(sys.argv) > 2:
        rows = await Database.fetch(
            "SELECT trigger_tag, category FROM maya_rp.stream_templates "
            "WHERE category=$1 ORDER BY trigger_tag",
            sys.argv[2],
        )
    else:
        rows = await Database.fetch(
            "SELECT trigger_tag, category FROM maya_rp.stream_templates ORDER BY category, trigger_tag"
        )
    if not rows:
        print("No templates.")
        return
    print(f"\n{'Tag':<28} {'Category'}")
    print("-" * 42)
    for r in rows:
        print(f"{r['trigger_tag']:<28} {r['category']}")


async def cmd_stream():
    """stream — demo: run a mock LLM stream through the StreamInterceptor."""
    await Database.init()
    import asyncio
    from core.stream_interceptor import StreamInterceptor

    async def mock_llm_stream():
        tokens = [
            "Maya walks onto the bridge. ",
            "[ENV: BRIDGE]\n",
            "She squeezes the trigger. ",
            "[HIT: RAILGUN_KINETIC] ",
            "The squad advanced. ",
            "[SENSE: MISSIONARY]\n",
            "And then the pool. [ENV: HEAVEN_POOL]\n",
        ]
        for t in tokens:
            await asyncio.sleep(0.05)
            yield t

    print("--- Intercepted CLI Output Stream ---")
    interceptor = StreamInterceptor()
    async for chunk in interceptor.process_stream(mock_llm_stream()):
        print(chunk, end="", flush=True)
    print("\n--- Stream Complete ---")
    st = interceptor.stats
    print(
        f"[interceptor stats] lines={st['lines_processed']} exact={st['exact_hits']} "
        f"semantic_attempts={st['semantic_attempts']} semantic_hits={st['semantic_hits']} "
        f"skipped={st['semantic_skipped']} breaker={st['breaker_engaged']} "
        f"semantic_ms={st['semantic_total_ms']:.0f}"
    )


async def cmd_memories():
    """memories consolidate [character_id] — sleep-cycle memory consolidation."""
    await Database.init()
    sub = sys.argv[2] if len(sys.argv) > 2 else ""
    if sub != "consolidate":
        print("Usage: cli.py memories consolidate [character_id]")
        return
    cid = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3].isdigit() else None
    from modules.memories import consolidate_memories

    r = await consolidate_memories(SID, character_id=cid)
    if "error" in r:
        print(f"Error: {r['error']}")
        return
    print(
        f"Consolidation (day {r['game_day']}): {r['consolidated']} summaries from {r['archived']} archived memories "
        f"across {r['characters']} characters (age>{r['age_days']}d, min {r['min_count']})."
    )


async def cmd_intimacy():
    """intimacy gen <position> [target_desc] | intimacy text <prompt> — local abliterated generation."""
    await Database.init()
    if len(sys.argv) < 4:
        print(
            "Usage: cli.py intimacy {gen <position> [target_desc...] | text <prompt...>}"
        )
        return
    from modules.local_gen import generate, generate_intimacy_template, upsert_template

    sub = sys.argv[2]
    if sub == "text":
        print(await generate(" ".join(sys.argv[3:])))
    elif sub == "gen":
        position = sys.argv[3].lower().replace(" ", "_")
        target_desc = " ".join(sys.argv[4:]) if len(sys.argv) > 4 else ""
        print(
            f"Generating [SENSE: {position.upper()}] locally... (8B on 1060, ~1 t/s — be patient)"
        )
        text = await generate_intimacy_template(position, target_desc=target_desc)
        print(f"\n--- GENERATED ---\n{text}\n------------------")
        hint = f"sensual intimacy {position} position"
        await upsert_template(
            f"[SENSE: {position.upper()}]",
            text,
            category="intimacy",
            readable_hint=hint,
        )
        print(
            f"✅ Template [SENSE: {position.upper()}] upserted — interceptor will serve it."
        )
    else:
        print("Unknown intimacy subcommand: gen|text")


async def cmd_intent():
    """intent "<json>" — Intent-Driven Architecture entry point.

    Parse LLM-produced strict JSON intent → CPU validate → CPU resolve → Result Event.
    LLM never touches state; CPU is the only source of truth.

    Usage:
      cli.py intent '{"action_type":"attack","target":"Iron Concord","item_used":"Legion Vanguard","dialogue":"For the throne!"}'
      cli.py intent '{"action_type":"use_item","item_used":"TKG Heaven","creative_intent":"attempt to open Gate 7"}'
      cli.py intent '{"action_type":"talk","dialogue":"Open the gates!"}'
    """
    await Database.init()
    if len(sys.argv) < 3:
        print(
            "Usage: cli.py intent '<json>'\n"
            "  Parse player intent -> CPU validate -> CPU resolve -> Result Event"
        )
        await Database.close()
        return

    from core.intent import parse_to_intent, resolve_intent_dispatch, PlayerIntent

    raw = " ".join(sys.argv[2:])
    try:
        intent = parse_to_intent(raw)
    except Exception as e:
        print(f"INTENT REJECTED (schema violation): {e}")
        print(
            "LLM must retry with valid PlayerIntent — CPU does not accept malformed input."
        )
        await Database.close()
        return

    print(f"INTENT  : {intent.model_dump_json(indent=2)}")
    result = await resolve_intent_dispatch(SID, intent)
    print(f"\nRESULT EVENT:")
    for k, v in result.items():
        print(f"  {k}: {v}")
    await Database.close()


async def cmd_roll100():
    """roll100 [days] [--dry-run] — roll N game days with transparent overrides."""
    await Database.init()
    import subprocess

    subprocess.run([sys.executable, "scripts/roll100.py"] + sys.argv[2:])


async def cmd_voyage():
    """voyage {status|register|arrive|wormhole|slingshot|whitehole} — voyage transit ledger.

    voyage status                                   → list all voyages
    voyage register <name> <origin> <dest> --ly N   → book a voyage (real math: 710 ly/day)
    voyage register ... --tag T --ships N
    voyage register ... hidden-thread opts (when crossing z-planes via a thread):
        --act sneak|run|guard|bribe   → how the run is conducted (default sneak)
        --guide NAME                  → guide present (no guide = +20% danger)
        --prep N --equip N --know N   → persediaan/peralatan/pengetahuan 0-3 (each -5% danger)
        --heat N                      → cargo_heat 0-3 (+5% danger, +8% margin)
        --cargo N                     → cargo_value credits (profit on clean run)
    voyage register ... exotic transit (2026-08-15 theory build):
        --wormhole NAME               → A↔B pair, ~90% travel cut; decaying hole may collapse
        --slingshot NAME              → black-hole Oberth boost ×0.6 + time dilation; horizon risk
        --void --fleet "NAME"         → VOID CROSSING (inter-nebular, no gate): needs a Void
                                        Drive in the fleet; fast (12h/u) but risk 20% (cut by
                                        Nebular Ward); z-planes must differ
    voyage shipmods                   → list void module catalog
    voyage shipmods install <ship_id> <module>  → fit a module (checks tier + slots)
    voyage wormholes                  → list wormholes (stability/status)
    voyage slingshots                 → list black holes (hazard/dilation)
    voyage whiteholes                 → list white-hole exits (mystery feed)
    voyage decay                      → run wormhole decay tick now
    voyage arrive                     → run arrival check now
    """
    await Database.init()
    from modules.voyage import (register, advance, status as voyage_status,
                                wormhole_jump, wormhole_status, wormhole_decay,
                                black_hole_slingshot, white_hole_events)
    from modules.ship_modules import (install_module, list_modules,
                                      list_void_modules, fleet_void_capable,
                                      void_crossing_cost)

    sub = sys.argv[2] if len(sys.argv) > 2 else "status"
    if sub == "status":
        rows = await voyage_status()
        if not rows:
            print("No voyages.")
            return
        print(f"\n{'Name':<40} {'Route':<28} {'Days':>6} {'Dep':>5} {'Arr':>5}  Status")
        print("-" * 118)
        for r in rows:
            route = f"{r['origin'] or '?'}→{r['destination'] or '?'}"
            extra = ""
            if r.get("transit_kind") in ("wormhole", "slingshot", "void"):
                extra = f" · {r['transit_kind']}:{r.get('transit_name')}"
                if r.get("dilation_days"):
                    extra += f" (+{r['dilation_days']}d dilate)"
                if r.get("collapse_roll"):
                    extra += f" (collapse {r['collapse_roll']})"
            elif r.get("via_hidden"):
                extra = f" · {r.get('act') or 'sneak'} danger {r.get('danger_pct')}%"
                if r.get("loss_ships"):
                    extra += f" · -{r['loss_ships']} ships"
                if r.get("reward_credits"):
                    extra += f" · +{r['reward_credits']:,}C"
            else:
                lane = r.get("lane_type") or "standard"
                extra = f" · {lane} lane"
                if r.get("toll_paid"):
                    extra += f" · toll {r['toll_paid']:,}C"
                if r.get("loss_ships"):
                    extra += f" · -{r['loss_ships']} ships (pirates)"
            print(
                f"{r['voyage_name']:<40} {route:<28} {float(r['travel_days']):>6.1f} "
                f"{r['depart_day'] or 0:>5} {r['arrive_day'] or 0:>5}  {r['status']}{extra}"
            )
    elif sub == "register":
        if len(sys.argv) < 6:
            print(
                "Usage: voyage register <name> <origin> <dest> [--ly N | --units N | --tag T | --ships N]"
                "\n       + hidden-thread: --act sneak|run|guard|bribe --guide N --prep N --equip N --know N --heat N --cargo N"
                "\n       + exotic: --wormhole NAME | --slingshot NAME"
            )
            return
        name, origin, dest = sys.argv[3], sys.argv[4], sys.argv[5]
        ly = units = None
        tag = ships = None
        act, guide = "sneak", None
        prep = equip = know = heat = cargo = 0
        wormhole = slingshot = fleet_name = None
        void = False
        i = 6
        while i < len(sys.argv):
            if sys.argv[i] == "--ly" and i + 1 < len(sys.argv):
                ly = float(sys.argv[i + 1])
                i += 2
            elif sys.argv[i] == "--units" and i + 1 < len(sys.argv):
                units = float(sys.argv[i + 1])
                i += 2
            elif sys.argv[i] == "--tag" and i + 1 < len(sys.argv):
                tag = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--ships" and i + 1 < len(sys.argv):
                ships = int(sys.argv[i + 1])
                i += 2
            elif sys.argv[i] == "--act" and i + 1 < len(sys.argv):
                act = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--guide" and i + 1 < len(sys.argv):
                guide = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--prep" and i + 1 < len(sys.argv):
                prep = int(sys.argv[i + 1])
                i += 2
            elif sys.argv[i] == "--equip" and i + 1 < len(sys.argv):
                equip = int(sys.argv[i + 1])
                i += 2
            elif sys.argv[i] == "--know" and i + 1 < len(sys.argv):
                know = int(sys.argv[i + 1])
                i += 2
            elif sys.argv[i] == "--heat" and i + 1 < len(sys.argv):
                heat = int(sys.argv[i + 1])
                i += 2
            elif sys.argv[i] == "--cargo" and i + 1 < len(sys.argv):
                cargo = int(sys.argv[i + 1])
                i += 2
            elif sys.argv[i] == "--wormhole" and i + 1 < len(sys.argv):
                wormhole = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--slingshot" and i + 1 < len(sys.argv):
                slingshot = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--fleet" and i + 1 < len(sys.argv):
                fleet_name = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--void":
                void = True
                i += 1
            else:
                i += 1
        try:
            v = await register(
                name,
                origin,
                destination=dest,
                distance_ly=ly,
                distance_units=units,
                fleet_tag=tag,
                ship_count=ships or 0,
                act=act,
                guide=guide,
                prep_level=prep,
                equip_level=equip,
                knowledge_level=know,
                cargo_heat=heat,
                cargo_value=cargo,
                wormhole=wormhole,
                slingshot=slingshot,
                fleet=fleet_name,
                void=void,
            )
            print("REGISTERED:", v)
        except ValueError as e:
            print(f"❌ {e}")
    elif sub == "shipmods":
        if len(sys.argv) > 3 and sys.argv[3] == "install":
            ship_id = int(sys.argv[4])
            mod_name = sys.argv[5]
            try:
                r = await install_module(ship_id, mod_name)
                print(f"✅ {r['module']} fitted on {r['ship']} (slot {r['slot']})")
                fitted = await list_modules(ship_id)
                for m in fitted:
                    print(f"   [{m['slot_index']}] {m['name']} ({m['category']}, "
                          f"{m['effect_type']}={m['effect_value']})")
            except ValueError as e:
                print(f"❌ {e}")
        else:
            rows = await list_void_modules()
            print("🌀 VOID modules (cross the void between nebulas):")
            for r in rows:
                print(f"   {r['name']:<22} {r['effect_type']}={r['effect_value']}  "
                      f"grade {r['grade']} · tier {r['tier_min']}-{r['tier_max']} · "
                      f"{r['cost_alloys']:,}A {r['cost_credits']:,}C")
    elif sub == "fleetcheck":
        fname = sys.argv[3] if len(sys.argv) > 3 else "SEF-3 Silent Maw"
        cap = await fleet_void_capable(fname)
        print(f"Fleet {fname!r}: {cap['ships']} ships · "
              f"{'VOID CAPABLE' if cap['capable'] else 'NO VOID DRIVE'} "
              f"({cap['drive_ships']} drive ships: {', '.join(cap['drive_names']) or '—'})")
    elif sub == "wormholes":
        rows = await wormhole_status()
        if not rows:
            print("No wormholes.")
            return
        print("🌀 Wormholes:")
        for r in rows:
            print(f"   {r['name']:<20} {r['entry_name']}↔{r['exit_name']}  "
                  f"status={r['status']}  stability={r['stability']:.2f}  "
                  f"travel={float(r['travel_multiplier'] or 0.1)*100:.0f}% of normal")
    elif sub == "slingshots":
        rows = await Database.fetch(
            "SELECT b.name, b.hazard_level, b.slingshot_multiplier, b.time_dilation_ratio, s.name AS sector "
            "FROM maya_rp.black_holes b JOIN maya_rp.sectors s ON s.id=b.sector_id "
            "WHERE b.session_id=$1 ORDER BY b.id", SID)
        if not rows:
            print("No black holes.")
            return
        print("⚫ Black holes:")
        for r in rows:
            print(f"   {r['name']:<16} @{r['sector']}  hazard={r['hazard_level']:.2f}  "
                  f"mult={r['slingshot_multiplier']:.2f}  dilation={r['time_dilation_ratio']:.1f}×")
    elif sub == "whiteholes":
        rows = await white_hole_events()
        print("⚪ White holes (exit-only):")
        for r in rows:
            print(f"   {r['name']:<16} sector={r['sector']}  status={r['status']}  "
                  f"mystery={r['mystery_pct']:.0f}%  linked_bh={r['linked_bh']}")
    elif sub == "decay":
        r = await wormhole_decay()
        print(f"Wormhole decay: {len(r['decayed'])} decaying, {len(r['collapsed'])} collapsed")
    elif sub == "arrive":
        r = await advance()
        print(f"Arrivals now: {r.get('arrivals', 0)}"
              + (f" · {r.get('interdictions', 0)} interdicted" if r.get('interdictions') else "")
              + (f" · {r.get('clean_runs', 0)} clean" if r.get('clean_runs') else "")
              + (f" · {r.get('collapses', 0)} wormhole collapses" if r.get('collapses') else "")
              + (f" · {r.get('slingshot_fails', 0)} slingshot fails" if r.get('slingshot_fails') else "")
              + (f" · +{r.get('profit_credits', 0):,}C" if r.get('profit_credits') else ""))
        for n in r.get("arrived", []):
            print(f"   ✅ {n}")
    else:
        print("Unknown voyage subcommand:", sub)
    await Database.close()


async def cmd_schema():
    """schema [schema_name] [outfile] — export PG schema to markdown (default wiki/rp-dev/schema.md)."""
    import subprocess

    subprocess.run([sys.executable, "scripts/export_schema.py"] + sys.argv[2:])


async def cmd_sync_pack():
    """sync-pack [--dry-run] — refresh wiki/rp-dev canon copies + regenerate one-file."""
    import subprocess

    subprocess.run([sys.executable, "scripts/sync_pack.py"] + sys.argv[2:])


async def cmd_check_object():
    """check <coordinate|name> — resolve what OBJECT is at a coordinate.

    Coordinate → territory (planet) + planets (detail) + infrastructure + factions.
    Answers the question: "apa kat koordinat 20-6?" — planet, station, gas giant, etc.
    """
    await Database.init()
    q = " ".join(sys.argv[2:]).strip()
    if not q:
        print(
            "Usage: cli.py check <coordinate|name>  (e.g. 'check 20-6', 'check TKG Mastika')"
        )
        await Database.close()
        return

    print(f"\n🔭 OBJECT CHECK — '{q}'\n")

    # Normalise: exact coordinate match preferred (X-Y), else name substring
    import re as _re

    exact = _re.fullmatch(r"\s*(\d+)\s*[-xX,]\s*(\d+)\s*", q)
    if exact:
        norm = f"{int(exact.group(1))}-{int(exact.group(2))}"
        terr = await Database.fetch(
            """SELECT id, system_name, development_level, population, status, governor_name
               FROM maya_rp.territory
               WHERE session_id=$1 AND system_name = $2
               ORDER BY system_name""",
            Config.SESSION_ID,
            norm,
        )
        # also planets whose system_name is this coordinate
        pl_at = await Database.fetch(
            """SELECT id, name, system_name, planet_type, diameter_km, gravity_g, atmosphere,
                      water_pct, habitability, status, territory_id
               FROM maya_rp.planets
               WHERE session_id=$1 AND system_name = $2
               ORDER BY id""",
            Config.SESSION_ID,
            norm,
        )
        label = norm
    else:
        terr = await Database.fetch(
            """SELECT id, system_name, development_level, population, status, governor_name
               FROM maya_rp.territory
               WHERE session_id=$1 AND system_name ILIKE $2
               ORDER BY system_name""",
            Config.SESSION_ID,
            f"%{q}%",
        )
        pl_at = await Database.fetch(
            """SELECT id, name, system_name, planet_type, diameter_km, gravity_g, atmosphere,
                      water_pct, habitability, status, territory_id
               FROM maya_rp.planets
               WHERE session_id=$1 AND (name ILIKE $2 OR system_name ILIKE $2)
               ORDER BY id""",
            Config.SESSION_ID,
            f"%{q}%",
        )
        label = q

    if not terr and not pl_at:
        print(f"  ❌ Tiada objek pada rujukan '{label}'.")
    for t in terr:
        pop = (t["population"] or 0) / 1e6
        print(f"  🪐 TERRITORY/PLANET: {t['system_name']} (id {t['id']})")
        print(
            f"     Dev: {t['development_level']} · Pop: {pop:,.1f}M · Status: {t['status']} · Gov: {t['governor_name'] or '—'}"
        )
    for p in pl_at:
        print(
            f"  🌍 PLANET DETAIL: {p['name']} (system {p['system_name']}, terr {p['territory_id'] or '?'})"
        )
        print(
            f"     Type: {p['planet_type'] or '?'} · Ø {p['diameter_km'] or 0:,}km · g {p['gravity_g'] or 0} · "
            f"Water {p['water_pct'] or 0}% · Hab {p['habitability'] or 0} · Status: {p['status']}"
        )

    # Territory ids for infra/factions: territories found + territories of planets found
    tids = [t["id"] for t in terr]
    tids += [
        p["territory_id"]
        for p in pl_at
        if p["territory_id"] and p["territory_id"] not in tids
    ]

    # Species composition for planets found (who actually lives there)
    pl_ids = [p["id"] for p in pl_at]
    if pl_ids:
        sp = await Database.fetch(
            """SELECT pp.planet_id, pp.species_name, pp.count, pp.pct, pp.dominant
               FROM maya_rp.planet_population pp
               WHERE pp.session_id=$1 AND pp.planet_id = ANY($2::int[])
               ORDER BY pp.planet_id, pp.count DESC""",
            Config.SESSION_ID,
            pl_ids,
        )
        if sp:
            print("  👥 SPECIES COMPOSITION:")
            cur_pl = None
            for x in sp:
                if x["planet_id"] != cur_pl:
                    cur_pl = x["planet_id"]
                    pname = next(
                        (p["name"] for p in pl_at if p["id"] == cur_pl), str(cur_pl)
                    )
                    print(f"    {pname}:")
                mark = " ★" if x["dominant"] else ""
                print(
                    f"      {x['species_name']:<14} {x['count']:>12,}  ({x['pct']}%){mark}"
                )
        else:
            print("  👥 Tiada species data (population 0 atau belum seed).")

    # 3. Infrastructure at those territories
    if tids:
        infra = await Database.fetch(
            """SELECT i.name, t.name AS type_name, i.territory_id, i.status, i.level
               FROM maya_rp.infrastructure_instances i
               LEFT JOIN maya_rp.infrastructure_types t ON t.id = i.infrastructure_type_id
               WHERE i.session_id=$1 AND i.territory_id = ANY($2::int[])
               ORDER BY i.territory_id""",
            Config.SESSION_ID,
            tids,
        )
        if infra:
            for it in infra:
                print(
                    f"  🏭 INFRA: {it['name']} ({it['type_name']}) · L{it['level']} · {it['status']} · terr {it['territory_id']}"
                )
        else:
            print("  🏗️ Tiada infrastruktur di territory ini.")

    # 4. Factions based at those coordinates
    if tids:
        fac = await Database.fetch(
            """SELECT name, status, pirate_fleet_power FROM maya_rp.factions
               WHERE session_id=$1 AND pirate_base_system_id = ANY($2::int[])""",
            Config.SESSION_ID,
            tids,
        )
        if fac:
            for f in fac:
                print(
                    f"  🏴‍☠️ FAKSYEN: {f['name']} · {f['status']} · fleet {f['pirate_fleet_power'] or 0}"
                )

    await Database.close()


async def cmd_sentiment():
    """sentiment [coord|name] — population sentiment/bias per system.

    sentiment                → top/bottom sentiment galaxy-wide
    sentiment <coord|name>   → sentiment rows for that system
    sentiment --faction X    → filter by faction (default Setia Empire)
    sentiment --shift <coord> <faction> <delta> <reason>  → manual narrative shift
    """
    await Database.init()
    from modules.population_sentiment import status as s_status, shift as s_shift

    argv = sys.argv[2:]
    if argv and argv[0] == "--shift":
        if len(argv) < 5:
            print("Usage: sentiment --shift <coord> <faction> <delta> <reason>")
            await Database.close()
            return
        coord, faction, delta, reason = (
            argv[1],
            argv[2],
            int(argv[3]),
            " ".join(argv[4:]),
        )
        terr = await Database.fetchrow(
            "SELECT id FROM maya_rp.territory WHERE session_id=$1 AND (system_name=$2 OR system_name ILIKE $3::text) LIMIT 1",
            Config.SESSION_ID,
            coord,
            f"%{coord}%",
        )
        if not terr:
            print(f"❌ Tiada sistem '{coord}'")
            await Database.close()
            return
        r = await s_shift(Config.SESSION_ID, terr["id"], faction, delta, reason)
        print("SHIFT:", r)
        await Database.close()
        return

    fac_filter = None
    if argv and argv[0] == "--faction":
        fac_filter = argv[1]
        argv = argv[2:]
    q = argv[0] if argv else None

    if q:
        terr = await Database.fetchrow(
            "SELECT id, system_name FROM maya_rp.territory WHERE session_id=$1 AND (system_name=$2::text OR system_name ILIKE $3::text) LIMIT 1",
            Config.SESSION_ID,
            q,
            f"%{q}%",
        )
        if not terr:
            print(f"❌ Tiada sistem '{q}' — cuba koordinat atau nama")
            await Database.close()
            return
        rows = await s_status(
            Config.SESSION_ID, territory_id=terr["id"], faction_name=fac_filter
        )
        print(f"\n📊 SENTIMENT — {terr['system_name']} ({len(rows)} faction rows)\n")
        for x in rows:
            print(
                f"  {x['faction_name']:<28} sent {x['sentiment']:>4}  app {x['approval']:>3}  fear {x['fear']:>3}  trust {x['trust']:>3}  bias {x['bias']:>3}"
            )
        if rows:
            print(f"\n  last: {rows[0]['last_shift_reason']}")
    else:
        rows = await s_status(Config.SESSION_ID, faction_name=fac_filter)
        top = sorted(rows, key=lambda x: -x["sentiment"])[:8]
        bot = sorted(rows, key=lambda x: x["sentiment"])[:8]
        print(f"\n🌍 SENTIMENT GALAXY-WIDE ({len(rows)} rows)\n")
        print("  ✅ PALING HAPPY:")
        for x in top:
            print(
                f"    {x['system_name']:<18} {x['faction_name']:<28} sent {x['sentiment']:>4}"
            )
        print("\n  ⚠️ PALING TIDAK HAPPY:")
        for x in bot:
            print(
                f"    {x['system_name']:<18} {x['faction_name']:<28} sent {x['sentiment']:>4}"
            )
    await Database.close()


async def cmd_king():
    """king present|away — set King presence (ministries prompt vs autonomous)."""
    await Database.init()
    from modules.ministry_ai import set_king, set_dark, king_status, dark_status

    sub = sys.argv[2] if len(sys.argv) > 2 else "status"
    if sub == "present":
        await set_king(Config.SESSION_ID, True)
        print("👑 King PRESENT — ministries prompt via adjutant")
    elif sub == "away":
        await set_king(Config.SESSION_ID, False)
        print("🌙 King AWAY — ministries decide autonomously")
    elif sub == "dark":
        await set_dark(Config.SESSION_ID, True)
        print(
            "🌑 DARK MODE ON — King unreachable; ministries run via co-ministers (deputies), prompt only critical/Mastika"
        )
    elif sub == "light":
        await set_dark(Config.SESSION_ID, False)
        print("☀️ DARK MODE OFF — King present")
    else:
        pres = await king_status()
        dark = await dark_status()
        state = (
            "🌑 DARK MODE (King unreachable)"
            if dark
            else ("👑 PRESENT" if pres else "🌙 AWAY")
        )
        print(f"King state: {state}")
    await Database.close()


async def cmd_adjutant():
    """adjutant pending | resolve <id> accept|reject — ministry prompt queue."""
    await Database.init()
    from modules.ministry_ai import pending as p_list, resolve as p_resolve

    sub = sys.argv[2] if len(sys.argv) > 2 else "pending"
    if sub == "pending":
        rows = await p_list()
        if not rows:
            print("No pending prompts.")
        else:
            print(
                f"\n📋 ADJUTANT PROMPTS — {len(rows)} pending (via Maya/Hanum/Sara/Maria)\n"
            )
            for r in rows:
                flag = {"critical": "🔴", "high": "🟠", "normal": "🟡"}.get(
                    r["urgency"], "🟡"
                )
                print(
                    f"  {flag} #{r['id']} [{r['urgency']}] {r['ministry']} ({r['holder']})"
                )
                print(f"      {r['action']} → {r['target']}")
                print(f"      {r['impact']}")
                print(f"      via {r['routed_via']} · {r['created_at']}")
    elif sub == "resolve":
        if len(sys.argv) < 5:
            print("Usage: adjutant resolve <id> accept|reject")
            await Database.close()
            return
        decision = (
            "accepted"
            if sys.argv[4] == "accept"
            else "rejected"
            if sys.argv[4] == "reject"
            else sys.argv[4]
        )
        r = await p_resolve(Config.SESSION_ID, int(sys.argv[3]), decision)
        print("RESOLVED:", r)
    else:
        print("Unknown adjutant subcommand:", sub)
    await Database.close()


async def cmd_decisions():
    """cli.py decisions list|add — unified decision stream + manual record."""
    from core.decision import decisions, add_cli
    sub = sys.argv[2] if len(sys.argv) > 2 else "list"
    await Database.init()
    if sub == "list":
        kwargs = {}
        for i in range(3, len(sys.argv) - 1, 2):
            key = sys.argv[i].lstrip("-")
            val = sys.argv[i + 1]
            if key in ("day", "limit"):
                kwargs[key] = int(val)
            else:
                kwargs[key] = val
        rows = await decisions(Config.SESSION_ID, **kwargs)
        for r in rows:
            print(
                f"[{r['kind']} #{r['decision_id']}] "
                f"D{r['game_day'] or '?'} · {r['actor']} · {r['decision_type']} · "
                f"{r['title'][:60]} · {r['status']}"
            )
        print(f"--- {len(rows)} decisions")
    elif sub == "add":
        r = await add_cli(sys.argv[3:])
        print("DECISION RECORDED:", r)
    else:
        print("Usage: cli.py decisions list [--day N] [--kind decree] [--limit N] | decisions add --title ...")
    await Database.close()


async def cmd_lineage():
    """cli.py lineage <decision_id|fact> [fact_value] — walk causal chain."""
    from core.decision import chain, by_fact
    if len(sys.argv) < 3:
        print("Usage: cli.py lineage <decision_id> | lineage <fact_key> [fact_value]")
        return
    await Database.init()
    target = sys.argv[2]
    try:
        did = int(target)
        hops = await chain(Config.SESSION_ID, did)
        print(f"LINEAGE #{did} — {len(hops)} hops")
        for h in reversed(hops):
            ev = f" · events {h['event_ids']}" if h.get("event_ids") else ""
            print(
                f"  [D{h['game_day'] or '?'}] {h['actor']} · {h['decision_type']} · "
                f"{h['title'][:70]} · {h['status']}{ev}"
            )
    except ValueError:
        fact = target
        val = sys.argv[3] if len(sys.argv) > 3 else None
        rows = await by_fact(Config.SESSION_ID, fact, val)
        print(f"FACT '{fact}' — {len(rows)} touching decisions")
        for r in rows:
            print(
                f"  [D{r['game_day'] or '?'}] #{r['id']} {r['actor']} · {r['decision_type']} · "
                f"{r['title'][:70]}"
            )
    await Database.close()


async def cmd_programme():
    """Science programmes and the long knife (Fasa 2.3 and 2.4).

    Reads and writes `maya_rp.research_queue`; the arithmetic lives in
    `modules/programme_cost.py`, so nothing here decides a number.

      cli.py programme list [--session N]
      cli.py programme quote --tier=5 [--lab=N]
      cli.py programme tick [--session N] [--days=N] [--apply]     # dry by default
      cli.py programme kill --target=ID --spend=1..3 [--screened] [--deniable]
                           [--importance=N] [--apply]              # dry by default

    Writes require --apply on purpose. A read-only command that silently advances the
    world is how a test ends up changing the campaign.
    """
    import modules.programme_cost as cost

    flags = {a[2:].split("=", 1)[0]: (a.split("=", 1)[1] if "=" in a else "")
             for a in sys.argv[2:] if a.startswith("--")}
    args = [a for a in sys.argv[2:] if not a.startswith("--")]
    sub = args[0] if args else "list"
    # `SID` is the run-resolved session: `__main__` strips --session before dispatch,
    # so Config.SESSION_ID is only the process default and would be the wrong fallback.
    session = int(flags.get("session") or SID)

    def show(row) -> str:
        if isinstance(row, dict):
            return row
        return {}

    if sub == "quote":
        tier = int(flags.get("tier") or 5)
        lab = int(flags.get("lab") or 0)
        days = cost.target_days(tier)
        credits = cost.target_credits(tier, lab if "lab" in flags else cost.LAB_LEVEL_CAP)
        print(f"tier {tier}: {days} programme-days ({cost.lost_years(days, 1):.1f} years at one rate) "
              f"· {credits:,} C")
        for doctrine in ("science_tech", "magic", "balance"):
            rate = cost.progress_per_day(True, lab, doctrine)
            print(f"  doctrine {doctrine:<13} rate {rate}/day → {days / rate:,.0f} days with a lead")
        return

    db = Database

    if sub == "kill":
        target = flags.get("target")
        if not target:
            print("Usage: cli.py programme kill --target=ID --spend=1..3 [--screened] [--deniable] [--apply]")
            sys.exit(1)
        try:
            spend = int(flags.get("spend") or 1)
        except ValueError:
            print("--spend must be 1, 2 or 3")
            sys.exit(1)
        importance = int(flags.get("importance") or 5)
        score = cost.kill_score(spend, bool(flags.get("deniable")), bool(flags.get("screened")), importance)
        outcome = cost.kill_outcome(score)
        row = await db.fetch(
            "SELECT id, programme_days, lead_character_id, tier_target FROM maya_rp.research_queue WHERE id=$1",
            int(target))
        if not row:
            print(f"no programme with id {target}")
            sys.exit(1)
        days = int(row[0]["programme_days"] or 0)
        setback = cost.setback_days(days, outcome)
        print(f"programme {target}: score {score} → {outcome} · setback {setback} programme-days "
              f"({cost.lost_years(setback, 1):.1f} years)")
        case = cost.investigation_score(False, False, outcome)
        print(f"  a case would open at strength {case} (opens at {cost.INVESTIGATION_OPEN_AT}, "
              f"names a payer at {cost.INVESTIGATION_PAYER_AT})")
        if not "--apply" in sys.argv:
            print("dry run: nothing written (pass --apply to write)")
            return
        await db.execute(
            "UPDATE maya_rp.research_queue SET programme_days = GREATEST(0, programme_days - $1) WHERE id=$2",
            setback, int(target))
        print(f"  applied: programme {target} lost {setback} days")
        return

    if sub == "tick":
        rows = await db.fetch(
            """SELECT id, programme_days, tier_target, lead_character_id, theory_only, faction_id
               FROM maya_rp.research_queue WHERE session_id=$1 ORDER BY id""", session)
        if not rows:
            print(f"session {session} has no programme row; the seed is blocked on funding")
            return
        days_to_run = int(flags.get("days") or 1)
        for row in rows:
            target_tier = row["tier_target"] or 5
            target = cost.target_days(int(target_tier))
            doctrine = "unaligned"
            if row["faction_id"]:
                doctrine_row = await db.fetch(
                    "SELECT doctrine FROM maya_rp.factions WHERE id=$1", int(row["faction_id"]))
                if doctrine_row:
                    doctrine = doctrine_row[0]["doctrine"] or "unaligned"
            rate = 0 if row["theory_only"] else cost.progress_per_day(
                row["lead_character_id"] is not None, 0, doctrine)
            current = int(row["programme_days"] or 0)
            new = min(target, current + rate * days_to_run)
            print(f"programme {row['id']}: {current} → {new} / {target} days "
                  f"(rate {rate}/day, {'theory only' if row['theory_only'] else 'building'})")
            if "--apply" in sys.argv and new != current:
                await db.execute("UPDATE maya_rp.research_queue SET programme_days=$1 WHERE id=$2",
                                 new, int(row["id"]))
                print(f"  applied: {row['id']} now {new}")
        if "--apply" not in sys.argv:
            print("dry run: nothing written (pass --apply to write)")
        return

    rows = await db.fetch(
        """SELECT r.id, r.session_id, r.status, r.tier_target, r.programme_days, r.theory_only,
                  r.lead_character_id, f.name AS faction, c.name AS lead
           FROM maya_rp.research_queue r
           LEFT JOIN maya_rp.factions f ON f.id = r.faction_id
           LEFT JOIN maya_rp.characters c ON c.id = r.lead_character_id
           WHERE r.session_id=$1 ORDER BY r.id""", session)
    if not rows:
        print(f"session {session}: no programme rows. Seed is blocked on funding; "
              f"see wiki/rp-dev/SCIENCE-ASSASSINATION-2026-10-02.md")
        return
    for row in rows:
        tier = row["tier_target"]
        target = cost.target_days(int(tier)) if tier else None
        progress = int(row["programme_days"] or 0)
        pct = f"{100 * progress / target:.0f}%" if target else "n/a"
        print(f"#{row['id']} {str(row['faction'] or '—')[:22]:<22} tier {tier or '—'} "
              f"{progress}/{target or '—'} {pct} {'theory' if row['theory_only'] else 'building'} "
              f"lead {str(row['lead'] or '—')[:18]}")


async def cmd_ooc():
    """OOC engine — System overseer.

    Usage:
      cli.py ooc status [--session N]
      cli.py ooc audit "<text>" [--layer=dialogue|somatic|tool] [--trait=aloof,mentor]
                                     [--magic=well:close_wound,sight:read] [--witnessed] [--instrument]
                                     [--preview]   # answer the price without writing anything
                                [--evidence] [--turn=REF]
      cli.py ooc persona [--slug=…]                    # voice/lore/intro/play-guide summary
      cli.py ooc portrait <name> [occasion]            # preset image lookup or queue
      cli.py ooc spend <kind> [target]                 # RPP sinks: skip_beat · calm_observer · reveal_intel
      cli.py ooc effects                               # active penalty as concrete modifiers
      cli.py ooc know [list|learn <fact>] [--observer=N]
      cli.py ooc rules  [--trait=…] [--stage=…]
      cli.py ooc beats  [--all] [--from-text="<prose>"]  # scripted beats; --from-text fires the prose path
      cli.py ooc milestone done <name> [--text=…] [--evidence]
      cli.py ooc exemption list|buy <rule_id> <action_key> [--cost=N] [--condition=scene:medical]
      cli.py ooc suspicion [--observer=N] [--bump] [--delta=5] [--reason=…]
      cli.py ooc readiness                            # arc-stage gates (§7)
      cli.py ooc advance [--auto]
      cli.py ooc stage <lockdown|selective|confrontation>
      cli.py ooc mirror                               # push state into the harness JSON
      cli.py ooc events [N]
      cli.py ooc prune [DAYS]
    """
    from core import campaign, ooc
    from core import session as session_policy

    flags = [a for a in sys.argv[2:] if a.startswith("--")]
    args = [a for a in sys.argv[2:] if not a.startswith("--")]

    def flag(name: str, default: str | None = None) -> str | None:
        for item in flags:
            if item.startswith(f"--{name}="):
                return item.split("=", 1)[1]
        return default

    sub = args[0] if args else "status"
    session = int(flag("session", str(SID)) or SID)
    traits = tuple((flag("trait", "general") or "general").split(","))
    context = {
        key: value
        for key, _, value in (part.partition(":") for part in (flag("context") or "").split(","))
        if key
    }

    if sub == "status":
        row = await ooc.state(session)
        stage = row["arc_stage"]
        bounds = ooc.STAGE_THRESHOLDS[stage]
        penalty = ooc.debuff_for(row["deviation"], stage)
        print(f"OOC — session {session} · stage {stage} (λ decay {bounds['decay']}/turn)")
        print(f"  deviation      {row['deviation']}/100   (warn {bounds['warning']} · crit {bounds['critical']} · exec {bounds['execution']})")
        print(f"  roleplay pts   {row['roleplay_points']}")
        print(f"  audits         {row['audits']}   findings {row['findings']}")
        print(f"  debuff         {row['debuff'] or '—'}")
        try:
            frozen_now = session_policy.is_frozen(session)
        except PermissionError as exc:  # the frozen list is unreadable: say so, writes are refused
            print(f"  frozen         UNKNOWN ({exc}); writes are refused until it is repaired")
            frozen_now = False
        if frozen_now:
            print("  frozen         reference only; GM MAYA maintenance to write")
        if penalty:
            print(f"  active effect  {penalty[1]}")
        # §6.2 — a required beat past its window is reported, never billed.
        for beat in await ooc.overdue_milestones(session, traits=traits):
            print(f"  ⚠ REQUIRED BEAT OVERDUE  {beat['name']} (expired {beat['expires_at']})")
        print(f"  updated        {row['updated_at']}")
    elif sub == "audit":
        if len(args) < 2:
            print('Usage: cli.py ooc audit "<text>" [--layer=…] [--trait=…] [--evidence]')
            sys.exit(1)
        try:
            magic = [a for a in flag("magic", "").split(",") if a.strip()]
            result = await ooc.audit(
                " ".join(args[1:]),
                session,
                layer=flag("layer", ooc.LAYER_DIALOGUE) or ooc.LAYER_DIALOGUE,
                traits=traits,
                action_evidence="--evidence" in flags,
                context=context,
                turn_ref=flag("turn"),
                magic_acts=magic,
                magic_witnessed="--witnessed" in flags,
                magic_instrument="--instrument" in flags,
                preview="--preview" in flags,
            )
        except ooc.FrozenSession as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return
        print(f"layer={result['layer']} rules={result['rules']} disposition={result['disposition']}"
              + (f" ({result['skip_reason']})" if result.get("skip_reason") else ""))
        for finding in result["findings"]:
            print(f"  ✖ [{finding['rule_id']}] {finding['kind']}/{finding['layer']} +{finding['delta']}  «{finding['match']}»")
        if result.get("magic_delta"):
            priced = ", ".join(f"{act} +{cost}" for act, (cost, _) in result["magic"]["priced"].items())
            print(f"  magic +{result['magic_delta']}  {priced}"
                  + ("  record raised" if result["magic"]["record"] else ""))
        for unknown in result.get("magic", {}).get("unknown", []):
            print(f"  ✖ unknown magic act {unknown!r}; add it to modules/magic_cost.ACT_TABLE")
        print(f"  delta {result['delta']} → deviation {result['deviation']} (decay {result['decay']})"
              f" · debuff {result['debuff'] or '—'} · loophole {result['loophole_score']} · rpp +{result['rpp_award']}")
        for exempt in result["exempted"]:
            print(f"  ⚪ [{exempt['rule_id']}] exempt ({exempt['action_key']})")
        if result["suspicion_delta"]:
            print(f"  observer suspicion {result['suspicion_delta']:+d}"
                  + (f" — {result['suspicion_reason']}" if result["suspicion_reason"] else ""))
        for beat in result.get("beats_completed", []):
            print(f"  ★ beat complete {beat['name']}  rpp +{beat['rpp_reward']}"
                  + (f"  latch={beat['latched_ruleset']}" if beat.get("latched_ruleset") else ""))
        if result.get("preview"):
            print("  preview: nothing written")
        else:
            print(f"  audit_event #{result['audit_event_id']}")
    elif sub == "rules":
        stage = flag("stage")
        rules = await ooc.effective_rules(session, traits, stage)
        print(f"effective ruleset — session {session} · traits {','.join(traits)} · {len(rules)} rules")
        for rule in rules:
            print(f"  {rule.id:24s} {rule.kind:17s} layer={rule.layer:8s} trait={rule.trait or '(campaign)':9s} +{rule.delta}  {rule.pattern[:48]}")
    elif sub == "endings":
        rows = await campaign.endings(session)
        print(f"endings — session {session} · {len(rows)} registered")
        for entry in rows:
            mark = "✔" if entry["met"] else "·"
            triggered = f"  triggered {entry['triggered_at']}" if entry.get("triggered_at") else ""
            print(f"  {mark} {entry['name']:28s} {entry['kind']:7s} {entry['condition']}{triggered}")

    elif sub == "lore":
        entries = await campaign.lore_entries(session)
        print(f"lorebook — session {session} · {len(entries)} entries")
        for entry in entries:
            print(f"  · {entry['title']:28s} keywords: {', '.join(entry['keywords'])}")

    elif sub == "note":
        note = " ".join(args[1:]) or flag("text") or ""
        try:
            row = await campaign.add_directive(session, note)
        except ooc.FrozenSession as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return
        print(f"director note #{row['id']} recorded (never audited as prose)")

    elif sub == "snapshot":
        action = args[1] if len(args) > 1 else "save"
        path = flag("path") or f"/home/maya/.dsh/ooc/snapshots/session-{session}.json"
        if action == "save":
            data = await campaign.snapshot(session)
            target = campaign.save_snapshot(data, path)
            print(f"snapshot saved → {target} (milestones {len(data['milestones'])}, "
                  f"exemptions {len(data['exemptions'])}, suspicion {len(data['suspicion'])})")
        elif action == "load":
            data = campaign.load_snapshot(path)
            try:
                restored = await campaign.restore_snapshot(data)
            except ooc.FrozenSession as exc:
                print(f"refused: {exc}", file=sys.stderr)
                return
            print(json.dumps(restored, default=str))
        else:
            print("Usage: cli.py ooc snapshot save|load [--path=…]")

    elif sub == "spend":
        kind = args[1] if len(args) > 1 else ""
        target = args[2] if len(args) > 2 else flag("target")
        try:
            row = await campaign.spend(session, kind, target)
            print(f"spent {row['price']} rpp on {row['sink']} — {row['detail']} (balance was {row['spent_from']})")
        except (ValueError, ooc.FrozenSession) as error:
            print(f"refused: {error}")

    elif sub == "effects":
        fx = await campaign.debuff_effects(session)
        print(f"debuff: {fx['debuff'] or 'none'} · battle {fx['battle_penalty']:+d} · "
              f"romance {'blocked' if fx['romance_blocked'] else 'open'} · morale {fx['crew_morale']:+d} — {fx['note']}")

    elif sub == "know":
        from core import campaign as _campaign

        action = args[1] if len(args) > 1 else "list"
        observer = int(flag("observer", "0") or 0) or await ooc.observer_id(session)
        if action == "learn":
            fact = " ".join(args[2:]) or flag("fact") or ""
            try:
                row = await _campaign.learn(session, observer, fact, flag("source") or "")
            except ooc.FrozenSession as exc:
                print(f"refused: {exc}", file=sys.stderr)
                return
            print(f"observer {row['character_id']} knows: {row['fact_key']}")
        else:
            rows = await _campaign.knowledge_of(session, observer)
            print(f"knowledge — observer {observer} · {len(rows)} facts")
            for row in rows[:20]:
                print(f"  · {row['fact_key']}")

    elif sub == "persona":
        from core import persona

        slug = flag("slug") or persona.DEFAULT_SLUG
        data = persona.load(slug)
        print(f"persona {data['slug']} · block {len(data['block'])} chars · "
              f"boundary cases {len(data['boundary_cases'])} · play guide {data['has_play_guide']}")
        for case in data["boundary_cases"]:
            print(f"  - {case}")

    elif sub == "portrait":
        from core import portraits

        name = args[1] if len(args) > 1 else ""
        occasion = args[2] if len(args) > 2 else "portrait"
        if not name:
            print("Usage: cli.py ooc portrait <name> [occasion]")
        else:
            hit = await portraits.lookup(session, name, occasion)
            if hit:
                print(f"{hit['character']['name']} [{occasion}] → {hit['asset']['image_path']}")
            else:
                try:
                    queued = await portraits.queue(session, name, occasion)
                except ooc.FrozenSession as exc:
                    print(f"refused: {exc}", file=sys.stderr)
                    return
                print(f"queued {queued['character']['name']} [{occasion}] — run: python3 scripts/portrait_render.py --session {session}")

    elif sub == "beats" and flag("from-text"):
        # §6.3 — the same prose path `audit()` uses, callable on demand.
        completed = await ooc.beats_from_prose(
            session, flag("from-text"), traits=traits, turn_ref=flag("turn"),
        )
        print(f"beats from prose — session {session} · {len(completed)} completed")
        for beat in completed:
            print(f"  ★ {beat['name']}  rpp +{beat['rpp_reward']}"
                  + (f"  latch={beat['latched_ruleset']}" if beat.get("latched_ruleset") else ""))
    elif sub in ("beats", "milestone"):
        action = args[1] if len(args) > 1 else "list"
        if action == "list":
            due = await ooc.milestones(session, traits=traits, due_only="--all" not in flags)
            print(f"scripted beats — session {session} · traits {','.join(traits)} · {len(due)} shown")
            for beat in due:
                mark = "✔" if beat["completed_at"] else ("⚠" if beat["overdue"] else "·")
                print(f"  {mark} {beat['name']:32s} trait={beat['trait'] or '(any)':9s}"
                      f" stage={beat['stage']:13s} rpp={beat['rpp_reward']}"
                      + ("  required" if beat["required"] else "")
                      + ("  OVERDUE" if beat["overdue"] else ""))
        elif action == "add":
            name = args[2] if len(args) > 2 else flag("name")
            if not name:
                print("Usage: cli.py ooc milestone add <name> [--trait=…] [--stage=…] [--rpp=N] [--latch=…] [--pattern=re:…]")
            else:
                stage = flag("stage", "lockdown")
                trait = flag("trait") or None
                latch = flag("latch") or None
                rpp = int(flag("rpp", "5"))
                pattern = flag("pattern")
                try:
                    await ooc.add_milestone(session, name, trait=trait, stage=stage,
                                            rpp_reward=rpp, latch_ruleset=latch, pattern=pattern)
                except ooc.FrozenSession as exc:
                    print(f"refused: {exc}", file=sys.stderr)
                    return
                print(f"beat {name} authored (stage {stage}, rpp {rpp}" + (f", rule {pattern}" if pattern else "") + ")")

        elif action == "done":
            if len(args) < 3:
                print("Usage: cli.py ooc milestone done <name> [--text=…] [--evidence]")
                sys.exit(1)
            result = await ooc.complete_milestone(
                session,
                args[2],
                text=flag("text") or (" ".join(args[3:]) or None),
                traits=traits,
                evidence="--evidence" in flags,
            )
            print(json.dumps(result, default=str, indent=2))
        else:
            print("Usage: cli.py ooc milestone {list|done <name>}")
            sys.exit(1)
    elif sub == "exemption":
        action = args[1] if len(args) > 1 else "list"
        if action == "list":
            rows = await ooc.exemptions(session)
            print(f"exemptions — session {session} · {len(rows)} rows")
            for row in rows:
                print(f"  {row['rule_id']:24s} {row['action_key']:18s} cost={row['cost_rpp']:<4}"
                      f" condition={row['condition'] or '—':24s} {'live' if row['live'] else 'expired'}")
        elif action == "buy":
            if len(args) < 4:
                print("Usage: cli.py ooc exemption buy <rule_id> <action_key>"
                      " [--cost=N] [--condition=scene:medical] [--temp --ttl=24]")
                sys.exit(1)
            result = await ooc.buy_exemption(
                session,
                args[2],
                args[3],
                int(flag("cost")) if flag("cost") else None,
                condition=flag("condition"),
                permanent="--temp" not in flags,
                ttl_hours=int(flag("ttl")) if flag("ttl") else None,
            )
            print(json.dumps(result, default=str, indent=2))
        else:
            print("Usage: cli.py ooc exemption {list|buy <rule_id> <action_key>}")
            sys.exit(1)
    elif sub == "suspicion":
        if "--bump" in flags:
            result = await ooc.bump_suspicion(
                session,
                observer=int(flag("observer")) if flag("observer") else None,
                delta=int(flag("delta", "5") or 5),
                reason=flag("reason"),
            )
            print(json.dumps(result, default=str, indent=2))
        else:
            rows = await ooc.suspicion(session)
            print(f"observer suspicion — session {session} · {len(rows)} observer(s)")
            for row in rows:
                print(f"  {row['observer_id']:<6} {(row['name'] or '?')[:22]:24s} {row['suspicion']:>3}/100"
                      f"  {row['last_reason'] or '—'}")
    elif sub in ("readiness", "advance"):
        if sub == "readiness":
            ready = await ooc.stage_readiness(session, traits)
            print(f"stage {ready['stage']} → {ready['next'] or '(last stage)'} · ready={ready['ready']}")
            for key, check in ready["gates"].items():
                print(f"  {key:12s} {check['have']}/{check['required']}"
                      f" {'✔' if check['met'] else '✖'}")
        else:
            result = await ooc.advance_stage(session, auto="--auto" in flags, traits=traits)
            print(json.dumps(result, default=str, indent=2))
    elif sub == "mirror":
        path = await ooc.mirror_state_file(session)
        print(f"state mirrored → {path}")
    elif sub == "stage":
        if len(args) < 2:
            print(f"Usage: cli.py ooc stage <{'|'.join(ooc.STAGES)}>")
            sys.exit(1)
        row = await ooc.set_stage(session, args[1])
        print(f"session {row['session_id']} → stage {row['arc_stage']} (deviation {row['deviation']})")
    elif sub == "events":
        limit = int(args[1]) if len(args) > 1 else 15
        rows = await Database.fetch(
            "SELECT id, rule_id, layer, disposition, skip_reason, match_sha256, match_len, delta,"
            " deviation_after, created_at FROM maya_rp.ooc_audit_events"
            " WHERE session_id=$1 ORDER BY id DESC LIMIT $2",
            session,
            limit,
        )
        print(f"last {len(rows)} audit events — session {session}")
        for row in rows:
            fingerprint = (row["match_sha256"] or "")[:12]
            print(f"  #{row['id']:<6} {row['created_at']:%m-%d %H:%M} {row['disposition']:8s}"
                  f" {row['layer']:8s} {row['rule_id'] or '—':22s} Δ{row['delta']:<3}"
                  f" dev={row['deviation_after']:<3} sha={fingerprint or '—'}")
    elif sub == "prune":
        days = int(args[1]) if len(args) > 1 else 30
        deleted = await Database.execute(
            "DELETE FROM maya_rp.ooc_audit_events WHERE created_at < now() - ($1 || ' days')::interval",
            days,
        )
        print(f"pruned audit events older than {days} days: {deleted}")
    else:
        print("Usage: cli.py ooc {status|audit|rules|beats|milestone|exemption|suspicion"
              "|readiness|advance|stage|mirror|events|prune}")
        sys.exit(1)
    await Database.close()


if __name__ == "__main__":
    explicit, sys.argv = take_session_flag(sys.argv)
    EXPLICIT_SESSION = explicit
    try:
        from core.session import resolve_session

        resolved = resolve_session(explicit)
    except RuntimeError as exc:
        print(f"session: {exc}", file=sys.stderr)
        sys.exit(2)
    if resolved is None:
        print("session: maintenance mode resolves no arc; pass --session=<id>", file=sys.stderr)
        sys.exit(2)
    SID = int(resolved)
    if len(sys.argv) < 2:
        print(
            "Usage: python3 scripts/cli.py {status|continue|clear|tick|save|export|config|health|modules|run|query} [args]"
        )
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "config":
        cmd_config()
    elif cmd == "modules":
        cmd_modules()
    elif cmd == "health":
        asyncio.run(cmd_health())
    elif cmd == "status":
        asyncio.run(cmd_status())
    elif cmd == "continue":
        asyncio.run(cmd_continue())
    elif cmd == "clear":
        asyncio.run(cmd_clear())
    elif cmd == "tick":
        asyncio.run(cmd_tick())
    elif cmd == "save":
        asyncio.run(cmd_save(sys.argv[2] if len(sys.argv) > 2 else ""))
    elif cmd == "load":
        asyncio.run(cmd_load())
    elif cmd == "export":
        asyncio.run(cmd_export())
    elif cmd == "run":
        if len(sys.argv) < 3:
            print("Usage: cli.py run <module_name>")
            sys.exit(1)
        asyncio.run(cmd_run_single(sys.argv[2]))
    elif cmd == "briefing":
        asyncio.run(cmd_briefing())
    elif cmd == "flow" or cmd == "economy":
        asyncio.run(cmd_economy_flow())
    elif cmd == "intel":
        asyncio.run(cmd_intel())
    elif cmd == "dash" or cmd == "dashboard":
        asyncio.run(cmd_dashboard())
    elif cmd == "query":
        if len(sys.argv) < 3:
            print("Usage: cli.py query <sql>")
            sys.exit(1)
        asyncio.run(cmd_query(" ".join(sys.argv[2:])))
    elif cmd == "romance":
        asyncio.run(cmd_romance())
    elif cmd == "ooc":
        asyncio.run(cmd_ooc())
    elif cmd == "programme" or cmd == "programmes":
        asyncio.run(cmd_programme())
    elif cmd == "assembly":
        asyncio.run(cmd_assembly())
    elif cmd == "duel":
        asyncio.run(cmd_duel())
    elif cmd == "roll":
        asyncio.run(cmd_roll())
    elif cmd == "voyage" or cmd == "voyages":
        asyncio.run(cmd_voyage())
    elif cmd == "check" or cmd == "object" or cmd == "coord":
        asyncio.run(cmd_check_object())
    elif cmd == "sentiment" or cmd == "opinion":
        asyncio.run(cmd_sentiment())
    elif cmd == "king":
        asyncio.run(cmd_king())
    elif cmd == "adjutant":
        asyncio.run(cmd_adjutant())
    elif cmd == "decisions":
        asyncio.run(cmd_decisions())
    elif cmd == "lineage":
        asyncio.run(cmd_lineage())
    elif cmd == "templates":
        asyncio.run(cmd_templates())
    elif cmd == "stream":
        asyncio.run(cmd_stream())
    elif cmd == "memories":
        asyncio.run(cmd_memories())
    elif cmd == "intimacy":
        asyncio.run(cmd_intimacy())
    elif cmd == "intent":
        asyncio.run(cmd_intent())
    elif cmd == "roll100":
        asyncio.run(cmd_roll100())
    elif cmd == "schema":
        asyncio.run(cmd_schema())
    elif cmd == "sync-pack":
        asyncio.run(cmd_sync_pack())
    elif cmd == "character":
        asyncio.run(cmd_character())
    elif cmd == "mystery" or cmd == "investigation":
        asyncio.run(cmd_mystery())
    elif cmd == "science" or cmd == "exoscience":
        asyncio.run(cmd_science())
    elif cmd == "cargo":
        asyncio.run(cmd_cargo())
    elif cmd == "build" or cmd == "infra":
        asyncio.run(cmd_build())
    elif cmd in ("mega", "megastructure", "port", "ports"):
        asyncio.run(cmd_mega())
    elif cmd in ("horror", "infestation", "swarm"):
        asyncio.run(cmd_horror())
    elif cmd in ("wonders", "wonder"):
        asyncio.run(cmd_wonders())
    elif cmd in ("social", "morale"):
        asyncio.run(cmd_social())
    elif cmd in ("prison", "prisoner", "capture"):
        asyncio.run(cmd_prison())
    elif cmd in ("map", "celestial", "systems"):
        asyncio.run(cmd_map())
    elif cmd in ("council", "cabinet"):
        asyncio.run(cmd_council())
    elif cmd in ("forge", "weapon", "weapons"):
        asyncio.run(cmd_forge())
    elif cmd in ("spy", "spies", "stealth", "espionage"):
        asyncio.run(cmd_spy())
    elif cmd in ("tech", "tech-tree", "labs"):
        asyncio.run(cmd_tech())
    elif cmd in ("fleet", "fleets"):
        asyncio.run(cmd_fleet())
    elif cmd in ("career", "crew-career"):
        asyncio.run(cmd_career())
    elif cmd in ("shipyard", "ship-building", "build-ship"):
        asyncio.run(cmd_shipyard())
    elif cmd in ("bond", "romance"):
        asyncio.run(cmd_bond())
    elif cmd in ("artifact", "artifacts", "relics"):
        asyncio.run(cmd_artifact())
    elif cmd in ("world", "seeds", "secrets"):
        asyncio.run(cmd_world())
    elif cmd in ("inner", "memories", "autonomy"):
        asyncio.run(cmd_inner())
    elif cmd in ("burn", "fleet-economy", "caravan"):
        asyncio.run(cmd_burn())
    elif cmd in ("op", "darkops", "espionage"):
        asyncio.run(cmd_op())
    elif cmd in ("craft", "alchemy", "corp", "corporation", "academy"):
        asyncio.run(cmd_craft())
    elif cmd in ("war", "siege", "tactics", "objectives"):
        asyncio.run(cmd_war())
    elif cmd in ("misc", "odds"):
        asyncio.run(cmd_misc())
    elif cmd in ("tail", "last"):
        asyncio.run(cmd_tail())
    elif cmd in ("encounter", "encounters", "events"):
        asyncio.run(cmd_encounter())
    else:
        print(
            f"Unknown: {cmd}\nTry: status, continue, clear, tick, save, export, config, health, modules, run, query, briefing, economy, intel, romance, roll, templates, stream, memories, intimacy, roll100, schema, sync-pack"
        )
