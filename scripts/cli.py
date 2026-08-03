#!/usr/bin/env python3
"""Unified CLI — single entry point for everything RP."""
import asyncio, sys
sys.path.insert(0, str(__file__ + "/../../"))

from core.config import Config
from core.db import Database
from core.state import StateManager
from scripts.orchestrator import run_full_tick, MODULE_MAP

SID = Config.SESSION_ID

async def cmd_status():
    await Database.init()
    s = await Database.fetchrow("SELECT name, status FROM sessions WHERE id=$1", SID)
    r = await Database.fetchrow("SELECT credits, alloys, fuel FROM resources WHERE session_id=$1", SID)
    t = await Database.fetchval("SELECT COUNT(*) FROM territory WHERE session_id=$1 AND controlling_faction='Setia Empire'", SID)
    sh = await Database.fetchval("SELECT COUNT(*) FROM ships WHERE session_id=$1", SID)
    v = await Database.fetchrow("SELECT progress FROM victory_tracking WHERE faction_id=(SELECT id FROM factions WHERE name='Setia Empire') AND victory_type='score'")
    print(f"\n{'RP Engine Status':^50}")
    print(f"  Session:    {s['name'] if s else 'N/A'} (id={SID}) | Status: {s['status'] if s else 'N/A'}")
    if r: print(f"  Resources:  {r['credits']:,}C / {r['alloys']:,}A / {r['fuel']:,}F")
    print(f"  Territories: {t or 0:,} | Ships: {sh or 0:,}")
    print(f"  Victory:     {v['progress']:.0f}%" if v else "")
    print(f"  Modules:     {len(Config.active_modules())} active ({len([k for k,v in Config.MODULES.items() if v])} enabled)")
    await Database.close()

async def cmd_health():
    await Database.init()
    status = await Database.status()
    print(f"DB connected: {status['connected']}")
    print(f"Tables: {status['tables']}")
    print(f"Session: {status['session']}")
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
    await Database.close()

async def cmd_export():
    await Database.init()
    md = await StateManager.export_md(SID)
    print(md)
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
    r = await Database.fetchrow("SELECT credits, alloys, fuel FROM maya_rp.resources WHERE session_id=$1", SID)
    print(f"\n{'═'*60}")
    print(f"  ECONOMY FLOW — Session {SID}")
    print(f"{'═'*60}")
    print(f"\n  TREASURY:  {r['credits']:>12,}C  {r['alloys']:>10,}A  {r['fuel']:>10,}F")
    territories = await Database.fetch(
        "SELECT system_name, population, tax_rate, development_level, crisis_level "
        "FROM maya_rp.territory WHERE session_id=$1 AND controlling_faction='Setia Empire' "
        "ORDER BY population DESC LIMIT 10", SID)
    if territories:
        print(f"\n  {'TERRITORY':<25} {'POP':>10} {'TAX':>6} {'TOTAL/DAY':>10}")
        total_tax = 0
        for t in territories:
            pop = t["population"] or 0
            rate = float(t["tax_rate"] or 0.05)
            dev = t["development_level"] or 1
            daily = int(pop * rate * (1 + (dev-1)*0.1))
            total_tax += daily
            print(f"  {t['system_name']:<25} {pop:>10,} {rate*100:>5.0f}% {daily:>10,}C")
        print(f"  {'TOTAL TAX/DAY':<25} {'':>10} {'':>6} {total_tax:>10,}C")
    ships_active = await Database.fetchval("SELECT COUNT(*) FROM maya_rp.ships WHERE session_id=$1 AND status='active'", SID) or 0
    print(f"\n  FLEET: {ships_active} active ships")
    fuel_burn = await Database.fetchval("SELECT COALESCE(SUM(hull_current/speed),0) FROM maya_rp.ships WHERE session_id=$1 AND status='active'", SID) or 1000
    print(f"  FUEL BURN/DAY: ~{int(fuel_burn):,}")
    print(f"  DAYS OF FUEL:  {r['fuel'] // max(1, int(fuel_burn))}")
    net = total_tax + 200000 - int(fuel_burn) * 50
    print(f"\n  {'═'*40}")
    print(f"  EST. NET FLOW: {net:+,}C/day")
    print()
    await Database.close()

async def cmd_intel():
    await Database.init()
    print(f"\n{'═'*60}")
    print(f"  INTEL DASHBOARD — Session {SID}")
    print(f"{'═'*60}")
    missions = await Database.fetch(
        "SELECT id, mission_type, target_faction, status, success_chance, assigned_agent "
        "FROM maya_rp.espionage_missions WHERE session_id=$1 AND status='active' ORDER BY id", SID)
    print(f"\n  ACTIVE MISSIONS ({len(missions)})")
    icons = {"recon":"\U0001f441","sabotage":"\U0001f4a3","theft":"\U0001f4cb",
             "assassination":"\u2620","infiltration":"\U0001f977","extraction":"\U0001f681"}
    for m in missions:
        icon = icons.get(m["mission_type"], "\u2753")
        print(f"    {icon} [{m['id']}] {m['mission_type']} vs {m['target_faction']} ({m['success_chance']}%) — {m['assigned_agent'] or 'unassigned'}")
    stealth = await Database.fetch(
        "SELECT su.name, sut.name as type_name, su.assigned_lane, su.status "
        "FROM maya_rp.stealth_units su "
        "JOIN maya_rp.stealth_unit_types sut ON sut.id=su.unit_type_id "
        "WHERE su.session_id=$1 AND su.status='active'", SID)
    if stealth:
        print(f"\n  DEPLOYED STEALTH UNITS ({len(stealth)})")
        for s in stealth:
            print(f"    \U0001f6f0 {s['name']} ({s['type_name']})")
    pipeline = await Database.fetch(
        "SELECT p.name, p.faction, pip.intel_text, pip.converted_to_clue "
        "FROM maya_rp.prisoner_intel_pipeline pip JOIN maya_rp.prisoners p ON p.id=pip.prisoner_id "
        "WHERE pip.session_id=$1 ORDER BY pip.id DESC LIMIT 5", SID)
    if pipeline:
        print(f"\n  PRISONER INTEL ({len(pipeline)})")
        for p in pipeline:
            icon = "\u2713" if p["converted_to_clue"] else "\u23f3"
            print(f"    {icon} {p['name']} ({p['faction']}): {p['intel_text'][:60]}...")
    print()
    await Database.close()

async def cmd_dashboard():
    await Database.init()
    s = await Database.fetchrow("SELECT name, game_day, status FROM maya_rp.sessions WHERE id=$1", SID)
    from modules.calendar_tkg import get_game_date
    date = await get_game_date(SID)
    from core.pacing import PacingDirector
    pm = await PacingDirector.get_mode(SID)
    r = await Database.fetchrow("SELECT credits, alloys, fuel FROM maya_rp.resources WHERE session_id=$1", SID)
    morale = await Database.fetchval("SELECT COALESCE(AVG(morale),50) FROM maya_rp.crew_roster WHERE session_id=$1", SID) or 50
    bonds = await Database.fetch("SELECT c.name,c.bond FROM maya_rp.characters c JOIN maya_rp.romance_arcs ra ON ra.character_id=c.id WHERE c.session_id=$1 AND c.bond>0 ORDER BY c.bond DESC LIMIT 5", SID)
    from modules.objectives import get_active as get_obj
    obj = await get_obj(SID)
    from core.player_profile import get_profile
    prof = await get_profile(SID)
    from core.scene_stack import get_stack_summary
    stack = await get_stack_summary(SID)
    fleet = await Database.fetchval("SELECT COUNT(*) FROM maya_rp.ships WHERE session_id=$1 AND status='active'", SID)

    def bar(val, mx=1_000_000, w=20):
        filled = min(w, max(0, int(val / mx * w)))
        return "\u2588" * filled + "\u2591" * (w - filled)

    print(f"\n  \u2554{'='*50}\u2557")
    print(f"  \u2551  TKG RP  —  {date.get('formatted','?'):<30} \u2551")
    print(f"  \u2551  Mode: {pm['mode'].upper():<10} Tension: {bar(pm['tension'],10,10)} {pm['tension']}/10 \u2551")
    print(f"  \u255a{'='*50}\u255d")
    print(f"\n  CREDITS  {bar(r['credits']):20} {r['credits']:>10,}")
    print(f"  ALLOYS   {bar(r['alloys']):20} {r['alloys']:>10,}")
    print(f"  FUEL     {bar(r['fuel']):20} {r['fuel']:>10,}  {'\u26a0 LOW' if r['fuel'] < 300_000 else ''}")
    print(f"  MORALE   {bar(morale,100,20)} {morale:>5}%  {'\u26a0 LOW' if morale < 30 else ''}")
    print(f"\n  BONDS")
    for b in bonds:
        bv = min(10, max(0, b["bond"] // 10))
        print(f"  {b['name']:<12} {'\u2665'*bv + '\u2661'*(10-bv)}")
    print(f"\n  FLEET  {fleet} active ships")
    print(f"  STYLE  {prof['style'].upper()}")
    c = [o for o in obj.get("critical",[])]
    u = [o for o in obj.get("urgent",[])]
    if c: print(f"\n  \U0001f534 CRITICAL: {c[0]['detail'][:50]}")
    if u: print(f"\n  \U0001f7e1 URGENT: {u[0]['detail'][:50]}")
    a = len(obj.get("active",[]))
    b = len(obj.get("background",[]))
    print(f"  {a} active, {b} background objectives")
    if stack: print(f"\n  \u23f8 Suspended scenes: {len(stack)}")
    print()
    await Database.close()

async def cmd_query(sql: str):
    await Database.init()
    try:
        rows = await Database.fetch(sql)
        import json
        print(json.dumps([dict(r) for r in rows], indent=2, default=str))
    except Exception as e:
        print(f"Query error: {e}")
    await Database.close()

async def cmd_run_single(module_name: str):
    from scripts.orchestrator import run_single
    await run_single(SID, module_name)

async def cmd_romance():
    """romance arcs | romance roll <initiator> <target> <position> [location]"""
    await Database.init()
    from modules.romance import get_romance_arcs, execute_rolling_scene, _get_character_id

    if len(sys.argv) < 3:
        print("Usage: cli.py romance {arcs|roll <initiator> <target> <position> [location]}")
        return

    sub = sys.argv[2]
    if sub == "arcs":
        arcs = await get_romance_arcs(SID)
        if not arcs:
            print("No romance arcs.")
            return
        print(f"\n{'Character':<26} {'Bond':<5} {'Stage':<12} {'Intimacy':<9} {'Sat':<5} {'Pursuit'}")
        print("-" * 76)
        for a in arcs:
            print(f"{a['character_name']:<26} {a['bond'] or 0:<5} {a['arc_stage']:<12} "
                  f"{a['intimacy_level'] or 0:<9} {a['saturation_pct'] or 0:<5} {a['pursuit_stage']}")
    elif sub == "roll":
        if len(sys.argv) < 6:
            print("Usage: cli.py romance roll <initiator> <target> <position> [location]")
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
        print(f"\n🎲 {r['initiator']} → {r['target']} — {r['position']} @ {r['location']}")
        print(f"   Roll {r['roll']} + {r['modifier']} = {r['final_score']} vs {r['threshold']}  →  {'✅ PASS' if r['passed'] else '❌ FAIL'}")
        print(f"   Tier: {r['tier']} (bond {r['required_bond']}+)")
        print(f"   Hook: {r['narrative_hook']}")
        sp = r["sensory_packet"]
        print(f"   Env: {sp['environment']['lighting']}")
        print(f"   Senses: {sp['sensory']['sight']} · {sp['sensory']['sound']} · {sp['sensory']['touch']}")
        print(f"   Beat: {sp['emotional_beat']}")
    else:
        print("Unknown romance subcommand: arcs|roll")

async def cmd_roll():
    """Generic dice: 'roll 100 +50 vs 90' | 'roll 3d6' | 'roll d20'"""
    expr = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""
    if not expr:
        print("Usage: cli.py roll <expr> — e.g. '100 +50 vs 90' or '3d6'")
        return
    import re, random
    m = re.match(r"^(\d*)d(\d+)([+-]\d+)?$", expr.replace(" ", ""))
    if m:
        n = int(m.group(1) or 1); die = int(m.group(2)); mod = int(m.group(3) or 0)
        rolls = [random.randint(1, die) for _ in range(n)]
        total = sum(rolls) + mod
        print(f"🎲 {expr}: [{', '.join(map(str, rolls))}] + {mod} = {total}")
        return
    m = re.match(r"^(\d+)\s*([+-])\s*(\d+)\s+vs\s+(\d+)$", expr, re.I)
    if m:
        base, sign, mod, thr = int(m.group(1)), m.group(2), int(m.group(3)), int(m.group(4))
        total = base + (mod if sign == "+" else -mod)
        print(f"🎲 Roll {base} {sign} {mod} = {total} vs {thr} → {'✅ PASS' if total >= thr else '❌ FAIL'}")
        return
    print(f"Unparsed: {expr} — try '100 +50 vs 90' or '3d6'")

async def cmd_templates():
    """templates [category] | templates embed — list or embed stream templates."""
    await Database.init()
    if len(sys.argv) > 2 and sys.argv[2] == "embed":
        from core.memory import _embed
        rows = await Database.fetch(
            "SELECT id, trigger_tag, readable_hint FROM maya_rp.stream_templates WHERE trigger_tag_embed IS NULL")
        if not rows:
            print("All templates already embedded.")
            return
        for r in rows:
            readable = r["readable_hint"] or r["trigger_tag"].replace("[", "").replace("]", "").replace("_", " ").lower()
            vec = await _embed(readable)
            vstr = "[" + ",".join(map(str, vec)) + "]"
            await Database.execute(
                "UPDATE maya_rp.stream_templates SET trigger_tag_embed=$1::vector WHERE id=$2",
                vstr, r["id"])
            print(f"Embedded: {r['trigger_tag']}")
        print(f"Done — {len(rows)} templates embedded.")
        return
    if len(sys.argv) > 2:
        rows = await Database.fetch(
            "SELECT trigger_tag, category FROM maya_rp.stream_templates "
            "WHERE category=$1 ORDER BY trigger_tag", sys.argv[2])
    else:
        rows = await Database.fetch(
            "SELECT trigger_tag, category FROM maya_rp.stream_templates ORDER BY category, trigger_tag")
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
    print(f"Consolidation (day {r['game_day']}): {r['consolidated']} summaries from {r['archived']} archived memories "
          f"across {r['characters']} characters (age>{r['age_days']}d, min {r['min_count']}).")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/cli.py {status|tick|save|export|config|health|modules|run|query} [args]")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "config": cmd_config()
    elif cmd == "modules": cmd_modules()
    elif cmd == "health": asyncio.run(cmd_health())
    elif cmd == "status": asyncio.run(cmd_status())
    elif cmd == "tick": asyncio.run(cmd_tick())
    elif cmd == "save": asyncio.run(cmd_save(sys.argv[2] if len(sys.argv) > 2 else ""))
    elif cmd == "export": asyncio.run(cmd_export())
    elif cmd == "run":
        if len(sys.argv) < 3: print("Usage: cli.py run <module_name>"); sys.exit(1)
        asyncio.run(cmd_run_single(sys.argv[2]))
    elif cmd == "briefing": asyncio.run(cmd_briefing())
    elif cmd == "flow" or cmd == "economy": asyncio.run(cmd_economy_flow())
    elif cmd == "intel": asyncio.run(cmd_intel())
    elif cmd == "dash" or cmd == "dashboard": asyncio.run(cmd_dashboard())
    elif cmd == "query":
        if len(sys.argv) < 3: print("Usage: cli.py query <sql>"); sys.exit(1)
        asyncio.run(cmd_query(" ".join(sys.argv[2:])))
    elif cmd == "romance":
        asyncio.run(cmd_romance())
    elif cmd == "roll":
        asyncio.run(cmd_roll())
    elif cmd == "templates":
        asyncio.run(cmd_templates())
    elif cmd == "stream":
        asyncio.run(cmd_stream())
    elif cmd == "memories":
        asyncio.run(cmd_memories())
    else:
        print(f"Unknown: {cmd}\nTry: status, tick, save, export, config, health, modules, run, query, briefing, economy, intel, romance, roll, templates, stream, memories")
