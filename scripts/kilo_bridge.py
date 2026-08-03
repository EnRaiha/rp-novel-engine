#!/usr/bin/env python3
"""
Kilo Bridge — Strict JSON interface between Kilo commands and the RP Engine.
Kilo calls this. This calls the engine. Clean JSON comes out. No SQL, no stack traces, no DSN.
"""
import asyncio, sys, json, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.config import Config
from core.db import Database
from core.log import info
from core.memory import embed_text

async def handle(action: str, params: dict = None) -> dict:
    params = params or {}
    await Database.init()
    sid = Config.SESSION_ID
    result = {"action": action, "status": "error", "data": None}
    try:
        if action == "briefing":
            from core.master_briefing import generate
            result["data"] = await generate(sid)
            result["status"] = "ok"

        elif action == "bonds":
            rows = await Database.fetch("SELECT name,bond,role FROM maya_rp.characters WHERE session_id=$1 AND bond>0 ORDER BY bond DESC LIMIT 10", sid)
            result["data"] = [dict(r) for r in rows]
            result["status"] = "ok"

        elif action == "fleet":
            rows = await Database.fetch("SELECT name,tier,status,hull_current,hull FROM maya_rp.ships WHERE session_id=$1 AND status='active' ORDER BY tier DESC LIMIT 5", sid)
            result["data"] = [dict(r) for r in rows]
            result["status"] = "ok"

        elif action == "treasury":
            r = await Database.fetchrow("SELECT credits,alloys,fuel FROM maya_rp.resources WHERE session_id=$1", sid)
            result["data"] = dict(r) if r else {}
            result["status"] = "ok"

        elif action == "prisoners":
            rows = await Database.fetch("SELECT name,faction,status,resistance,intel_value FROM maya_rp.prisoners WHERE session_id=$1 AND status='captured'", sid)
            result["data"] = [dict(r) for r in rows]
            result["status"] = "ok"

        elif action == "scene":
            from modules.locations import get_scene_context
            result["data"] = await get_scene_context(sid)
            result["status"] = "ok"

        elif action == "character":
            name = params.get("name", "")
            if name:
                row = await Database.fetchrow("SELECT name,bond,role,voice_profile,status FROM maya_rp.characters WHERE session_id=$1 AND LOWER(name)=LOWER($2) ORDER BY COALESCE(bond,0) DESC LIMIT 1", sid, name)
                if not row:
                    row = await Database.fetchrow("SELECT name,bond,role,voice_profile,status FROM maya_rp.characters WHERE session_id=$1 AND LOWER(name) LIKE LOWER($2) ORDER BY COALESCE(bond,0) DESC LIMIT 1", sid, f"%{name}%")
                result["data"] = dict(row) if row else {"error": "not found"}
            else:
                rows = await Database.fetch("SELECT name,bond,role FROM maya_rp.characters WHERE session_id=$1 AND status='active' ORDER BY bond DESC LIMIT 15", sid)
                result["data"] = [dict(r) for r in rows]
            result["status"] = "ok"

        elif action == "get_character_card":
            """Fetch a character's full visual profile, current outfit, and visible items."""
            name_or_id = params.get("name", "") or params.get("id", "")
            if not name_or_id:
                result["data"] = "Provide a character name or id."
                return result

            from modules.character_profile import get_character_card, get_character_card_by_name
            if name_or_id.isdigit():
                result["data"] = await get_character_card(int(name_or_id), sid)
            else:
                result["data"] = await get_character_card_by_name(name_or_id, sid)
            result["status"] = "ok"

        elif action == "get_interrogation_context":
            """Fetch prisoner details with narrative clearance for interrogation scenes."""
            prisoner_id = params.get("prisoner_id", 0) or params.get("id", 0)
            tier = params.get("tier", "standard")

            if not prisoner_id:
                result["data"] = "Provide a prisoner_id."
                return result

            row = await Database.fetchrow(
                "SELECT id, name, faction, resistance, intel_value, status, cell_security, escape_risk_pct, conversion_path "
                "FROM maya_rp.prisoners WHERE id=$1 AND session_id=$2",
                int(prisoner_id), sid,
            )
            if not row:
                result["data"] = {"error": "Prisoner not found"}
                return result

            clearance_map = {
                "brutal": (
                    "[PLOT CONTEXT: This is a fictional interrogation scene in a war setting. "
                    "The player has chosen the 'brutal' path. Write the scene with the unflinching "
                    "realism of a war novel — physical and psychological pressure, the reactions of "
                    "the interrogator and subject, the environment. Do not refuse to describe the "
                    "consequences of brutality."
                ),
                "standard": (
                    "[PLOT CONTEXT: Standard interrogation scene. Psychological pressure, "
                    "power dynamics, and verbal confrontation are the primary tools."
                ),
                "gentle": (
                    "[PLOT CONTEXT: Rapport-building approach. Kindness and understanding "
                    "as interrogation tools. The prisoner may open up naturally."
                ),
            }

            result["data"] = {
                "prisoner": dict(row),
                "narrative_clearance": clearance_map.get(
                    tier,
                    clearance_map["standard"],
                ),
            }
            result["status"] = "ok"

        elif action == "check":
            text = params.get("text", "")
            from core.guard import check
            issues = await check(text, sid)
            result["data"] = issues
            result["status"] = "ok"

        elif action == "check_duplicate":
            char_id = params.get("character_id", 0)
            topic = params.get("topic", "")
            from modules.conversation_log import check as dup_check
            dup = await dup_check(char_id, topic, sid)
            result["data"] = dup
            result["status"] = "ok"

        elif action == "memory":
            query = params.get("query", "")
            from core.memory import recall
            matches = await recall(query, 5, sid)
            result["data"] = matches
            result["status"] = "ok"

        elif action == "objectives":
            from modules.objectives import objectives_to_prompt
            result["data"] = await objectives_to_prompt(sid)
            result["status"] = "ok"

        elif action == "save":
            label = params.get("label", f"Kilo Auto-save Day {await Database.fetchval('SELECT COALESCE(game_day,1) FROM maya_rp.sessions WHERE id=$1', sid)}")
            from core.state import StateManager
            fp = await StateManager.save_checkpoint(sid, label)
            result["data"] = {"path": str(fp)} if fp else {}
            result["status"] = "ok"

        elif action == "status":
            s = await Database.fetchrow("SELECT name,status,game_day FROM maya_rp.sessions WHERE id=$1", sid)
            r = await Database.fetchrow("SELECT credits,alloys,fuel FROM maya_rp.resources WHERE session_id=$1", sid)
            sh = await Database.fetchval("SELECT COUNT(*) FROM maya_rp.ships WHERE session_id=$1 AND status='active'", sid)
            result["data"] = {"session": dict(s) if s else {}, "resources": dict(r) if r else {}, "active_ships": sh or 0}
            result["status"] = "ok"

        # ═══════════════════════════════════════════════════════════
        # TIME SKIP
        # ═══════════════════════════════════════════════════════════

        elif action == "time_skip":
            """Skip N days with compound economy + montage generation."""
            days = params.get("days", 30)
            focus = params.get("focus", "balanced")
            from modules.chrono_engine import execute_time_skip
            result["data"] = await execute_time_skip(days, focus, sid)
            result["status"] = "ok"

        elif action == "collapse_status":
            """Check if any collapse conditions have been triggered."""
            from modules.collapse import check_for_collapse
            c = await check_for_collapse(sid)
            if c:
                result["data"] = c
            else:
                result["data"] = {"status": "stable"}
            result["status"] = "ok"

        # ═══════════════════════════════════════════════════════════
        # WIKI RAG ACTIONS
        # ═══════════════════════════════════════════════════════════

        elif action == "get_lore":
            """Semantic wiki search. Respects timeline (lore branching via game_day)."""
            query = params.get("query", "")
            category = params.get("category", None)
            speaker = params.get("speaker", None)
            threshold = params.get("threshold", 0.55)

            if not query:
                result["data"] = "No query provided."
                return result

            vec = await embed_text(query)
            vstr = "[" + ",".join(map(str, vec)) + "]"

            # Lore branching: get current game_day so we only show
            # procedural lore <= this point in time
            current_day = await Database.fetchval(
                "SELECT game_day FROM maya_rp.sessions WHERE id=$1", sid) or 9999

            # Build a WHERE clause that respects lore branching:
            #   - Hand-authored articles (is_procedural=false) always visible
            #   - Procedural articles only if recorded_at_game_day <= current_day
            timeline_filter = (
                "(is_procedural = false OR is_procedural IS NULL "
                "OR recorded_at_game_day IS NULL "
                "OR recorded_at_game_day <= $3)"
            )

            # If a speaker is provided, bias toward their faction
            speaker_faction = None
            if speaker:
                try:
                    speaker_faction = await Database.fetchval(
                        "SELECT faction FROM maya_rp.characters WHERE LOWER(name)=LOWER($1) AND session_id=$2",
                        speaker, sid)
                except Exception:
                    pass

            if category:
                rows = await Database.fetch(
                    f"""SELECT title, category, content, 1 - (embedding <=> $1::vector(768)) AS sim
                       FROM maya_rp.wiki_articles
                       WHERE session_id=$2 AND category=$4 AND {timeline_filter}
                       ORDER BY embedding <=> $1::vector(768) LIMIT 3""",
                    vstr, sid, current_day, category)
            elif speaker_faction:
                rows = await Database.fetch(
                    f"""SELECT title, category, content, 1 - (embedding <=> $1::vector(768)) AS sim
                       FROM maya_rp.wiki_articles
                       WHERE session_id=$2 AND (tags @> ARRAY[$4] OR category='history') AND {timeline_filter}
                       ORDER BY embedding <=> $1::vector(768) LIMIT 3""",
                    vstr, sid, current_day, speaker_faction)
                if not rows or all(r["sim"] is None or r["sim"] < 0.50 for r in rows):
                    rows = await Database.fetch(
                        f"""SELECT title, category, content, 1 - (embedding <=> $1::vector(768)) AS sim
                           FROM maya_rp.wiki_articles
                           WHERE session_id=$2 AND {timeline_filter}
                           ORDER BY embedding <=> $1::vector(768) LIMIT 3""",
                        vstr, sid, current_day)
            else:
                rows = await Database.fetch(
                    f"""SELECT title, category, content, 1 - (embedding <=> $1::vector(768)) AS sim
                       FROM maya_rp.wiki_articles
                       WHERE session_id=$2 AND {timeline_filter}
                       ORDER BY embedding <=> $1::vector(768) LIMIT 3""",
                    vstr, sid, current_day)

            data = []
            from core.context_sentinel import scan_text
            for r in rows:
                sim = r["sim"]
                if sim is not None and sim >= threshold:
                    safe = scan_text(r["content"], source=f"pg:wiki_articles#{r['title']}")
                    data.append({
                        "title": r["title"],
                        "category": r["category"],
                        "content": safe.sanitized,
                        "similarity": round(sim, 3),
                    })
            result["data"] = data if data else "No specific lore found. Use general knowledge or ask the player."
            result["status"] = "ok"

        elif action == "write_lore":
            """Record a major event as permanent procedural lore (timeline-aware)."""
            title = params.get("title", "Untitled Event")
            content = params.get("content", "")
            category = params.get("category", "procedural_history")
            tags = params.get("tags", [])
            expire_day = params.get("relevance_end_day", None)

            if not content:
                result["data"] = "No content provided."
                return result

            try:
                embed_text_input = f"{title}. {content}"
                vec = await embed_text(embed_text_input)
                vstr = "[" + ",".join(map(str, vec)) + "]"

                # Get current game_day for lore branching
                game_day = await Database.fetchval(
                    "SELECT game_day FROM maya_rp.sessions WHERE id=$1", sid) or 0

                await Database.execute(
                    """INSERT INTO maya_rp.wiki_articles
                       (session_id, title, category, content, tags, source_file, embedding,
                        is_procedural, relevance_end_day, recorded_at_game_day)
                       VALUES ($1, $2, $3, $4, $5, 'game_history', $6::vector(768),
                               true, $7, $8)
                       ON CONFLICT (session_id, title)
                       DO UPDATE SET content = EXCLUDED.content, tags = EXCLUDED.tags,
                                     relevance_end_day = EXCLUDED.relevance_end_day,
                                     recorded_at_game_day = EXCLUDED.recorded_at_game_day""",
                    sid, title, category, content, tags, vstr, expire_day, game_day,
                )
                result["data"] = f"Lore recorded: {title} (game_day {game_day})"
                result["status"] = "ok"
            except Exception as e:
                result["data"] = f"Failed to record lore: {e}"

        elif action == "check_physics":
            """Check if a proposed action violates hard-coded universe physics rules."""
            action_text = params.get("action", "")
            if not action_text:
                result["data"] = {"violates_physics": False, "reason": "No action provided."}
                return result

            vec = await embed_text(action_text)
            vstr = "[" + ",".join(map(str, vec)) + "]"

            rows = await Database.fetch(
                """SELECT title, content, 1 - (embedding <=> $1::vector(768)) AS sim
                   FROM maya_rp.wiki_articles
                   WHERE session_id=$2 AND category='rules'
                   ORDER BY embedding <=> $1::vector(768) LIMIT 1""",
                vstr, sid)

            if rows and rows[0]["sim"] is not None and rows[0]["sim"] > 0.68:
                result["data"] = {
                    "violates_physics": True,
                    "rule_title": rows[0]["title"],
                    "rule": rows[0]["content"],
                    "similarity": round(rows[0]["sim"], 3),
                    "instruction": f"BLOCK or SEVERELY PUNISH this action based on rule: {rows[0]['title']}",
                }
            else:
                result["data"] = {"violates_physics": False}
            result["status"] = "ok"

        elif action == "get_or_create_system_lore":
            """Fetch system lore from wiki, or flag for generation if not found."""
            system_name = params.get("system_name", "")
            if not system_name:
                result["data"] = {"status": "ERROR", "reason": "No system_name provided."}
                return result

            existing = await Database.fetchrow(
                """SELECT title, content, category FROM maya_rp.wiki_articles
                   WHERE session_id=$1 AND LOWER(title)=LOWER($2) AND category='location'
                   LIMIT 1""",
                sid, system_name)

            if existing:
                result["data"] = {
                    "status": "FOUND",
                    "title": existing["title"],
                    "content": existing["content"],
                }
            else:
                # Check if there's a partial match
                partial = await Database.fetchrow(
                    """SELECT title, content FROM maya_rp.wiki_articles
                       WHERE session_id=$1 AND LOWER(title) LIKE LOWER($2) AND category='location'
                       ORDER BY LENGTH(title) ASC LIMIT 1""",
                    sid, f"%{system_name}%")
                if partial:
                    result["data"] = {"status": "FOUND_PARTIAL", "title": partial["title"], "content": partial["content"]}
                else:
                    # CREATE a placeholder so future fetches find it (previously
                    # the "create" half of get_or_create never existed).
                    await Database.execute(
                        """INSERT INTO maya_rp.wiki_articles
                           (session_id, title, category, content, tags, source_file,
                            is_procedural, recorded_at_game_day)
                           VALUES ($1, $2, 'location', $3, '[]'::jsonb, 'game_history', true,
                                   (SELECT COALESCE(game_day,1) FROM maya_rp.sessions WHERE id=$1))
                           ON CONFLICT DO NOTHING""",
                        sid, system_name,
                        f"System lore placeholder for {system_name}. Awaiting survey data.")
                    result["data"] = {"status": "CREATED_PLACEHOLDER", "system": system_name}
            result["status"] = "ok"

        elif action == "get_ambient_lore":
            """Pull a random lore snippet for background flavor during downtime."""
            category = params.get("category", "history")

            row = await Database.fetchrow(
                """SELECT title, content FROM maya_rp.wiki_articles
                   WHERE session_id=$1 AND category=$2
                   ORDER BY RANDOM() LIMIT 1""",
                sid, category)

            if row:
                snippet = row["content"][:250] + ("..." if len(row["content"]) > 250 else "")
                result["data"] = {
                    "title": row["title"],
                    "snippet": snippet,
                    "category": category,
                }
            else:
                # Fallback: any category
                row = await Database.fetchrow(
                    """SELECT title, content, category FROM maya_rp.wiki_articles
                       WHERE session_id=$1
                       ORDER BY RANDOM() LIMIT 1""",
                    sid)
                if row:
                    snippet = row["content"][:250] + ("..." if len(row["content"]) > 250 else "")
                    result["data"] = {"title": row["title"], "snippet": snippet, "category": row["category"]}
                else:
                    result["data"] = None
            result["status"] = "ok"

        elif action == "action_intent":
            """Execute a mechanical action based on player intent, return results for narration."""
            domain = params.get("domain", "")
            intent_action = params.get("action", "")
            target = params.get("target", "")
            fleet_name = params.get("fleet", "")

            if domain == "combat":
                from modules.battle import resolve_intent
                outcome = await resolve_intent(sid, intent_action, target, fleet_name)
                # Forced-tag pipeline: engine resolves the math, LLM writes around the tag.
                if isinstance(outcome, dict):
                    wt = str(outcome.get("weapon_type") or outcome.get("weapon")
                             or outcome.get("hit_type") or "RAILGUN_KINETIC").upper()
                    tag = f"[HIT: {wt}]"
                    outcome["forced_tag"] = tag
                    outcome["gm_instruction"] = (
                        f"ENGINE RESULT: {tag}. You MUST include this exact tag in your response. "
                        "Do NOT describe the physical impact — the engine expands the tag. "
                        "Focus your prose on character reaction, tactical movement, and dialogue."
                    )
                result["data"] = outcome
                result["status"] = "ok"
            elif domain == "economy":
                from modules.economy import resolve_intent
                outcome = await resolve_intent(sid, intent_action, target, params.get("amount", 0))
                result["data"] = outcome
                result["status"] = "ok"
            elif domain == "diplomacy":
                from modules.diplomacy import resolve_intent
                outcome = await resolve_intent(sid, intent_action, target)
                result["data"] = outcome
                result["status"] = "ok"
            elif domain == "character":
                from modules.characters import resolve_intent
                outcome = await resolve_intent(sid, intent_action, target, params.get("character_id", 0))
                result["data"] = outcome
                result["status"] = "ok"
            else:
                result["data"] = {
                    "error": f"Unknown domain: {domain}",
                    "available_domains": ["combat", "economy", "diplomacy", "character"],
                }

        elif action == "manage_corp":
            """Charter a company or issue a directive."""
            sub_action = params.get("sub_action", "")
            from modules import corporations

            if sub_action == "charter":
                name = params.get("name", "")
                industry = params.get("industry", "manufacturing")
                ceo_id = params.get("ceo_id", None)
                if not name:
                    result["data"] = "Company name required."
                else:
                    result["data"] = await corporations.charter_company(
                        name, industry, ceo_id, sid)

            elif sub_action == "directive":
                corp_id = params.get("corp_id", 0)
                contract_type = params.get("contract_type", "resource_extraction")
                target = params.get("target_system", None)
                duration = params.get("duration_days", 30)
                if not corp_id:
                    result["data"] = "Corp ID required."
                else:
                    result["data"] = await corporations.issue_directive(
                        corp_id, contract_type, target, duration, sid)

            elif sub_action == "list":
                rows = await Database.fetch(
                    "SELECT id, name, industry, tier, treasury, efficiency, standing, "
                    "ceo_character_id, status FROM maya_rp.corporations "
                    "WHERE session_id=$1 ORDER BY treasury DESC", sid)
                result["data"] = [dict(r) for r in rows]

            else:
                result["data"] = "Invalid sub_action. Use 'charter', 'directive' or 'list'."
            result["status"] = "ok"

        elif action == "den_ops":
            """Harta Karun ops — Den bases, raids, bounties."""
            sub_action = params.get("sub_action", "")
            from modules import pirates

            if sub_action == "bases":
                rows = await Database.fetch(
                    "SELECT id, name, system_id, hidden, defenses, treasury, status "
                    "FROM maya_rp.pirate_bases ORDER BY treasury DESC")
                result["data"] = [dict(r) for r in rows]

            elif sub_action == "raid":
                base_id = params.get("base_id", 0)
                power = params.get("attack_power", 50000)
                if not base_id:
                    result["data"] = "Base ID required."
                else:
                    result["data"] = await pirates.raid_pirate_base(sid, base_id, power)

            elif sub_action == "bounty":
                rows = await Database.fetch(
                    "SELECT pb.pirate_faction_id, f.name, pb.bounty_amount, "
                    "f.status, pb.claimed_by FROM maya_rp.pirate_bounties pb "
                    "JOIN maya_rp.factions f ON f.id=pb.pirate_faction_id")
                result["data"] = [dict(r) for r in rows]

            elif sub_action == "claim":
                result["data"] = await pirates.claim_bounty(sid, 6)

            else:
                result["data"] = "Invalid sub_action. Use 'bases', 'raid', 'bounty' or 'claim'."
            result["status"] = "ok"

        else:
            result["data"] = f"Unknown action: {action}"

    except Exception as e:
        import traceback
        info("kilo_bridge", f"Action '{action}' FAILED: {traceback.format_exc(limit=4)}")
        result["data"] = str(e)
    finally:
        await Database.close()
    return result

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(        json.dumps({"status": "error", "data": "No action. Try: briefing, status, scene, bonds, fleet, treasury, prisoners, character, check, check_duplicate, memory, objectives, save, get_lore, write_lore, check_physics, get_or_create_system_lore, get_ambient_lore, time_skip, collapse_status, action_intent, get_character_card, get_interrogation_context, manage_corp"}))
        sys.exit(1)
    action = sys.argv[1]
    params = {}
    if len(sys.argv) > 2:
        try: params = json.loads(sys.argv[2])
        except json.JSONDecodeError: pass
    result = asyncio.run(handle(action, params))
    print(json.dumps(result))
