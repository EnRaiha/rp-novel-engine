#!/usr/bin/env python3
"""Unified CLI — single entry point for everything RP."""

import asyncio, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import Config
from core.db import Database
from core.state import StateManager
from scripts.orchestrator import run_full_tick, MODULE_MAP

SID = Config.SESSION_ID  # process default; the __main__ block re-resolves per run


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


async def cmd_status():
    await Database.init()
    s = await Database.fetchrow("SELECT name, status FROM sessions WHERE id=$1", SID)
    r = await Database.fetchrow(
        "SELECT credits, alloys, fuel FROM resources WHERE session_id=$1", SID
    )
    t = await Database.fetchval(
        "SELECT COUNT(*) FROM territory WHERE session_id=$1 AND controlling_faction='Setia Empire'",
        SID,
    )
    sh = await Database.fetchval("SELECT COUNT(*) FROM ships WHERE session_id=$1", SID)
    v = await Database.fetchrow(
        "SELECT progress FROM victory_tracking WHERE faction_id=(SELECT id FROM factions WHERE name='Setia Empire') AND victory_type='score'"
    )
    print(f"\n{'RP Engine Status':^50}")
    print(
        f"  Session:    {s['name'] if s else 'N/A'} (id={SID}) | Status: {s['status'] if s else 'N/A'}"
    )
    if r:
        print(f"  Resources:  {r['credits']:,}C / {r['alloys']:,}A / {r['fuel']:,}F")
    print(f"  Territories: {t or 0:,} | Ships: {sh or 0:,}")
    print(f"  Victory:     {v['progress']:.0f}%" if v else "")
    print(
        f"  Modules:     {len(Config.active_modules())} active ({len([k for k, v in Config.MODULES.items() if v])} enabled)"
    )
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


async def cmd_load():
    """load <file.sav> [--keep-session] — restore PG from a .sav snapshot."""
    await Database.init()
    if len(sys.argv) < 3:
        print("Usage: cli.py load <file.sav> [--keep-session]")
        await Database.close()
        return
    from core.savegame import import_sav

    wipe = "--keep-session" not in sys.argv
    r = await import_sav(sys.argv[2], wipe=wipe)
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
        if session_policy.is_frozen(session):
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
        row = await campaign.add_directive(session, note)
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
            print(json.dumps(await campaign.restore_snapshot(data), default=str))
        else:
            print("Usage: cli.py ooc snapshot save|load [--path=…]")

    elif sub == "spend":
        kind = args[1] if len(args) > 1 else ""
        target = args[2] if len(args) > 2 else flag("target")
        try:
            row = await campaign.spend(session, kind, target)
            print(f"spent {row['price']} rpp on {row['sink']} — {row['detail']} (balance was {row['spent_from']})")
        except ValueError as error:
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
            row = await _campaign.learn(session, observer, fact, flag("source") or "")
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
                queued = await portraits.queue(session, name, occasion)
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
                await Database.execute(
                    "INSERT INTO maya_rp.ooc_milestones (session_id, name, trait, stage, rpp_reward, latch_ruleset)"
                    " VALUES ($1,$2,$3,$4,$5,$6) ON CONFLICT (session_id, name) DO UPDATE SET"
                    " trait=EXCLUDED.trait, stage=EXCLUDED.stage, rpp_reward=EXCLUDED.rpp_reward,"
                    " latch_ruleset=EXCLUDED.latch_ruleset",
                    session, name, trait, stage, rpp, latch,
                )
                if pattern:
                    await Database.execute(
                        "INSERT INTO maya_rp.ooc_rules"
                        " (id, scope, session_id, trait, kind, layer, pattern, is_regex, delta)"
                        " VALUES ($1,'session',$2,$3,'scripted_beat','both',$4,true,1)"
                        " ON CONFLICT (id) DO UPDATE SET trait=EXCLUDED.trait, pattern=EXCLUDED.pattern",
                        f"beat:{name}", session, trait, pattern,
                    )
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
            "Usage: python3 scripts/cli.py {status|tick|save|export|config|health|modules|run|query} [args]"
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
    else:
        print(
            f"Unknown: {cmd}\nTry: status, tick, save, export, config, health, modules, run, query, briefing, economy, intel, romance, roll, templates, stream, memories, intimacy, roll100, schema, sync-pack"
        )
